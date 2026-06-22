"""ETL spine: raw CSV >> gold artifacts. Offline-safe (Parquet/DuckDB; PostGIS publish
is a no-op unless serving). One bbox-bounded, reproducible pass:

    ingest >> graph >> segments >> map-match >> features >> CII >> gold/*.parquet

By default the extent is derived from the violation data; pass --bbox or --max-rows to
bound a fast dev/CI run. The same code scales to the full city by widening the bbox.
"""

from __future__ import annotations

import argparse
import hashlib
import json

import pandas as pd

from parkiq.cii.score import score_cii
from parkiq.core.config import get_settings
from parkiq.core.storage import Storage
from parkiq.core.versioning import (
    CII_VERSION,
    FEATURE_VERSION,
    file_fingerprint,
    now_rfc3339,
    road_network_version,
)
from parkiq.features.build import (
    aggregate_to_segments,
    build_daily_panel,
    segment_hour_of_week,
)
from parkiq.geo.segments import (
    bbox_from_points,
    build_segments,
    load_or_build_graph,
    match_points_to_segments,
)
from parkiq.ingestion.violations import load_violations


def _segment_junctions(matched: pd.DataFrame, safe: pd.DataFrame) -> pd.DataFrame:
    """Modal real junction per segment (excluding 'No Junction'/blank) so recommendations
    are operationally distinguishable when several segments share a road name."""
    j = matched[["record_id", "physical_id"]].merge(
        safe[["record_id", "junction_name"]], on="record_id", how="inner"
    )
    j = j[j["junction_name"].notna() & ~j["junction_name"].isin(["No Junction", ""])]
    if j.empty:
        return pd.DataFrame({"physical_id": [], "junction": []})
    mode = (
        j.groupby("physical_id")["junction_name"]
        .agg(lambda s: s.mode().iloc[0] if not s.mode().empty else None)
        .rename("junction")
        .reset_index()
    )
    return mode


def _serialisable(segments: pd.DataFrame) -> pd.DataFrame:
    df = segments.copy()
    df["centroid_lat"] = df["geometry"].apply(lambda g: g.centroid.y)
    df["centroid_lon"] = df["geometry"].apply(lambda g: g.centroid.x)
    df["geometry_wkt"] = df["geometry"].astype(str)
    df["h3_cells"] = df["h3_cells"].apply(list)
    df["directed_edges"] = df["directed_edges"].apply(list)
    return df.drop(columns=["geometry"])


def run(bbox: tuple | None = None, max_rows: int | None = None) -> dict:
    s = get_settings()
    csv_path = s.require_raw_violations()  # fail fast on missing/empty input
    storage = Storage(s)
    started = now_rfc3339()

    print(">> ingest")
    ing = load_violations(str(csv_path))
    n_input = ing.n_rows + ing.n_dropped
    safe = ing.safe
    if bbox:
        w, so, e, n = bbox
        safe = safe[safe.lat.between(so, n) & safe.lon.between(w, e)].reset_index(drop=True)
    if max_rows:
        safe = safe.head(max_rows)
    print(f"  {len(safe)}/{n_input} safe rows in scope (dropped {ing.n_dropped} invalid)")
    storage.write_parquet(safe, storage.s.bronze, "violations")
    storage.write_parquet(ing.restricted, storage.s.restricted_root, "violations_pii")

    extent = bbox or bbox_from_points(safe)
    print(f">> graph for bbox {tuple(round(x, 4) for x in extent)}")
    # Cache keyed by the exact extent so a wider (e.g. full-city) run never silently
    # reuses a narrower cached graph while claiming a new road-network version.
    bbox_key = hashlib.sha1(",".join(f"{c:.5f}" for c in extent).encode()).hexdigest()[:12]
    cache = storage.s.data_root / "cache" / f"graph_{bbox_key}.graphml"
    G = load_or_build_graph(extent, cache)

    print(">> segments")
    segs = build_segments(G, h3_res=s.h3_resolution)
    segs_ser = _serialisable(segs)
    storage.write_parquet(segs_ser, storage.s.silver, "segments")

    print(">> map-match")
    matched = match_points_to_segments(safe[["record_id", "lat", "lon"]], G)
    storage.write_parquet(matched, storage.s.silver, "violations_matched")

    print(">> features")
    seg_feats = aggregate_to_segments(matched, safe)
    how = segment_hour_of_week(matched, safe)
    panel = build_daily_panel(matched, safe, segs)
    storage.write_parquet(seg_feats, storage.s.gold, "segment_features")
    storage.write_parquet(how, storage.s.gold, "segment_hour_of_week")
    storage.write_parquet(panel, storage.s.gold, "panel")

    # Segment dimension (geometry, centroid, zone, junction) — serving/optimiser lookup.
    zone_map = panel[["physical_id", "zone"]].drop_duplicates("physical_id")
    junc_map = _segment_junctions(matched, safe)
    seg_dim = (
        segs_ser.drop(columns=["directed_edges"])
        .merge(zone_map, on="physical_id", how="left")
        .merge(junc_map, on="physical_id", how="left")
    )
    storage.write_parquet(seg_dim, storage.s.gold, "segments_dim")

    # Interim CII (raw density, flagged biased) so a heatmap always exists. The `train`
    # job recomputes CII from bias-adjusted model risk and overwrites this.
    print(">> interim CII (pre-model)")
    cii = score_cii(seg_feats, segs)
    cii["h3_cells"] = cii["h3_cells"].apply(list)
    storage.write_parquet(cii, storage.s.gold, "cii")
    # Artifacts only. PostGIS publication is a separate job (db.serving.publish_all).

    summary = {
        "etl_started_at": started,
        "etl_finished_at": now_rfc3339(),
        "bbox": list(extent),
        "max_rows": max_rows,
        "n_input_rows": int(n_input),
        "n_in_scope_rows": int(len(safe)),
        "n_dropped_invalid": int(ing.n_dropped),
        "n_segments": int(len(segs)),
        "n_panel_rows": int(len(panel)),
        "dataset_version": file_fingerprint(csv_path),
        "feature_version": FEATURE_VERSION,
        "cii_version": CII_VERSION,
        "road_network_version": road_network_version(cache, tuple(extent)),
    }
    _write_manifest(storage, summary)
    print(f"OK gold written. {summary['n_segments']} segments, {summary['n_panel_rows']} "
          f"panel rows from {summary['n_in_scope_rows']}/{summary['n_input_rows']} records.")
    return summary


def _write_manifest(storage: Storage, etl: dict) -> None:
    """gold/manifest.json — the single provenance source the API/copilot read."""
    path = storage.s.gold / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    manifest["etl"] = etl
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _parse_bbox(v: str | None):
    if not v:
        return None
    return tuple(float(x) for x in v.split(","))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--bbox", help="west,south,east,north", default=None)
    ap.add_argument("--max-rows", type=int, default=None)
    args = ap.parse_args()
    run(bbox=_parse_bbox(args.bbox), max_rows=args.max_rows)
