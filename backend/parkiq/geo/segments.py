"""Directed OSM road segments (the modelling entity) + H3 attachment + map-matching.

Graph acquisition is decoupled from segment/match logic: `load_or_build_graph` fetches
once (cached to GraphML so repeat runs and the CI/offline tier need no network), and the
extent is derived from the data's bounding box. Opposite carriageways / parallel roads
stay distinct directed segments even when sharing an H3 cell; H3 is render-only.
"""

from __future__ import annotations

from pathlib import Path

import h3
import networkx as nx
import osmnx as ox
import pandas as pd

from parkiq.core.config import get_settings

# Obstruction weight by highway class — a main road choked by parking hurts flow more
# than a residential lane. Consumed by CII; defined next to the segments.
HIGHWAY_OBSTRUCTION_WEIGHT = {
    "motorway": 1.0, "trunk": 0.95, "primary": 0.9, "secondary": 0.75,
    "tertiary": 0.6, "residential": 0.4, "unclassified": 0.4, "service": 0.25,
}

# (west, south, east, north)
BBox = tuple[float, float, float, float]


def bbox_from_points(points: pd.DataFrame, pad_deg: float = 0.01) -> BBox:
    return (
        points["lon"].min() - pad_deg, points["lat"].min() - pad_deg,
        points["lon"].max() + pad_deg, points["lat"].max() + pad_deg,
    )


def load_or_build_graph(bbox: BBox, cache_path: Path) -> nx.MultiDiGraph:
    """Drivable directed graph for the bbox, cached to GraphML."""
    if cache_path.exists():
        return ox.load_graphml(cache_path)
    G = ox.graph_from_bbox(bbox=bbox, network_type="drive")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    ox.save_graphml(G, cache_path)
    return G


def _segment_h3_cells(geom, res: int) -> tuple[str, ...]:
    if geom is None or not hasattr(geom, "coords"):
        return ()
    return tuple({h3.latlng_to_cell(lat, lon, res) for lon, lat in geom.coords})


def _physical_id(u: int, v: int, key: int) -> str:
    """Canonical undirected key: opposite carriageways of one road collapse here."""
    a, b = (u, v) if u <= v else (v, u)
    return f"{a}_{b}_{key}"


def build_segments(G: nx.MultiDiGraph, *, betweenness_k: int = 500, h3_res: int = 10) -> pd.DataFrame:
    """One row per *physical* segment (directions collapsed), carrying the candidate
    directed edges. Geometry, length, highway class, obstruction weight, sampled
    betweenness (full-graph betweenness is O(VE); sampling is the standard scalable
    approximation), and covering H3 cells."""
    node_bc = nx.betweenness_centrality(G, k=min(betweenness_k, len(G)), seed=get_settings().seed)

    edges = ox.graph_to_gdfs(G, nodes=False).reset_index()  # u, v, key columns
    edges["directed_id"] = (
        edges["u"].astype(str) + "_" + edges["v"].astype(str) + "_" + edges["key"].astype(str)
    )
    edges["physical_id"] = [_physical_id(u, v, k) for u, v, k in zip(edges.u, edges.v, edges.key)]
    edges["highway"] = edges["highway"].apply(lambda h: h[0] if isinstance(h, list) else h)
    edges["name"] = edges["name"].apply(
        lambda n: ", ".join(n) if isinstance(n, list) else n
    ).astype("string")
    edges["obstruction_weight"] = edges["highway"].map(HIGHWAY_OBSTRUCTION_WEIGHT).fillna(0.4)
    edges["betweenness"] = (
        edges["u"].map(node_bc).fillna(0) + edges["v"].map(node_bc).fillna(0)
    ) / 2
    edges["h3_cells"] = edges["geometry"].apply(lambda g: _segment_h3_cells(g, h3_res))

    g = edges.groupby("physical_id", sort=False)
    out = pd.DataFrame(
        {
            "directed_edges": g["directed_id"].apply(tuple),
            "name": g["name"].first(),
            "highway": g["highway"].first(),
            "length": g["length"].max(),
            "obstruction_weight": g["obstruction_weight"].max(),
            "betweenness": g["betweenness"].max(),
            "h3_cells": g["h3_cells"].apply(lambda s: tuple({c for cells in s for c in cells})),
            "geometry": g["geometry"].first(),
        }
    ).reset_index()
    return out


def match_points_to_segments(points: pd.DataFrame, G: nx.MultiDiGraph) -> pd.DataFrame:
    """Map-match each (lat, lon) to its nearest candidate edge, then to the *physical*
    segment. We never claim the travel direction (no heading in the source) — we keep
    the nearest directed edge as a candidate and a distance-based match confidence.

    `points` needs record_id, lat, lon. Returns
    (record_id, physical_id, nearest_directed_edge, dist_m, match_confidence).
    """
    import geopandas as gpd
    import numpy as np

    Gp = ox.project_graph(G)
    pts = gpd.GeoDataFrame(
        points.copy(), geometry=gpd.points_from_xy(points["lon"], points["lat"]), crs="EPSG:4326"
    ).to_crs(Gp.graph["crs"])
    uvk, dist = ox.distance.nearest_edges(
        Gp, X=pts.geometry.x.to_numpy(), Y=pts.geometry.y.to_numpy(), return_dist=True
    )
    dist = np.asarray(dist, dtype=float)
    # Distance-based confidence (15 m scale). TODO: incorporate nearest/runner-up margin.
    confidence = np.exp(-dist / 15.0)
    return pd.DataFrame(
        {
            "record_id": points["record_id"].to_numpy(),
            "physical_id": [_physical_id(u, v, k) for u, v, k in uvk],
            "nearest_directed_edge": [f"{u}_{v}_{k}" for u, v, k in uvk],
            "dist_m": dist,
            "match_confidence": confidence,
        }
    )
