"""Lightweight what-if flow-impact model for parking-induced congestion.

Theme 1 asks us to *quantify impact on traffic flow*. CII is a prioritisation proxy; this
module is the honest step toward an impact estimate: given that illegal parking blocks a
curb lane on a segment (reducing its capacity), it estimates the local impact and the
spillover onto downstream/adjacent segments via a capacity-and-queue heuristic.

HONESTY (CLAUDE.md): this is a *simulated estimate*, NOT measured flow. We have no live
flow/speed feed, so demand is proxied by network betweenness and outputs are relative /
illustrative until validated against a speed API. Travel direction is approximate (no
heading in the source), so the road neighbourhood is treated as undirected. Every result
carries its assumptions, caveats, and an evidence id.

Adjacency is derived directly from the canonical physical_id ("min_max_key"), whose two
node ids define connectivity — so no graph object or extra artifact is needed at runtime.
"""

from __future__ import annotations

import uuid
from collections import defaultdict, deque

import pandas as pd
from pydantic import BaseModel

# Saturation flow ~1800 veh/hour/lane (HCM rule of thumb). Lanes-per-direction by class.
LANE_CAPACITY_VPH = 1800
HIGHWAY_LANES = {
    "motorway": 3, "trunk": 3, "primary": 2, "secondary": 2,
    "tertiary": 1, "residential": 1, "unclassified": 1, "service": 1,
}
DEFAULT_LANES = 1
HOP_DECAY = 0.55  # spillover attenuation per hop along the network


def _nodes(physical_id: str) -> tuple[str, str]:
    parts = physical_id.split("_")
    return (parts[0], parts[1]) if len(parts) >= 2 else (physical_id, physical_id)


def _node_index(segments: pd.DataFrame) -> dict[str, set[str]]:
    """node id -> set of physical_ids touching it (undirected adjacency backbone)."""
    idx: dict[str, set[str]] = defaultdict(set)
    for pid in segments["physical_id"]:
        a, b = _nodes(pid)
        idx[a].add(pid)
        idx[b].add(pid)
    return idx


def k_hop_neighborhood(
    segment_id: str, segments: pd.DataFrame, hops: int = 2
) -> list[tuple[str, int]]:
    """BFS over node-shared adjacency. Returns [(physical_id, hop)], excluding the seed."""
    node_idx = _node_index(segments)
    seg_nodes = {pid: _nodes(pid) for pid in segments["physical_id"]}
    seen = {segment_id}
    out: list[tuple[str, int]] = []
    q: deque[tuple[str, int]] = deque([(segment_id, 0)])
    while q:
        pid, h = q.popleft()
        if h >= hops:
            continue
        a, b = seg_nodes.get(pid, _nodes(pid))
        for nb in node_idx[a] | node_idx[b]:
            if nb not in seen:
                seen.add(nb)
                out.append((nb, h + 1))
                q.append((nb, h + 1))
    return out


def _capacity(highway: str | None) -> tuple[int, float]:
    lanes = HIGHWAY_LANES.get((highway or "").lower(), DEFAULT_LANES)
    return lanes, lanes * LANE_CAPACITY_VPH


class AffectedSegment(BaseModel):
    physical_id: str
    name: str | None = None
    junction: str | None = None
    hop: int
    impact: float  # relative spillover impact (0..1-ish), higher = more affected


class SimulationResult(BaseModel):
    evidence_id: str
    kind: str = "simulated"  # NOT observed/measured
    target_segment: str
    target_name: str | None = None
    lanes: int
    lanes_blocked: int
    minutes: int
    capacity_before_vph: int
    capacity_after_vph: int
    capacity_loss_fraction: float
    local_impact: float
    spillover_index: float
    est_vehicle_minutes_affected: float
    affected: list[AffectedSegment]
    assumptions: dict
    caveats: str


def simulate_parking_blockage(
    segment_id: str,
    segments: pd.DataFrame,
    *,
    lanes_blocked: int = 1,
    minutes: int = 45,
    hops: int = 2,
    impact_threshold: float = 0.02,
    max_affected: int = 40,
) -> SimulationResult | None:
    """Estimate the flow impact of illegal parking blocking `lanes_blocked` lane(s) on a
    segment for `minutes`, plus spillover to its k-hop network neighbourhood.

    `segments` must contain physical_id, highway, betweenness (+ optional name, junction).
    Demand is proxied by betweenness (normalised), since we have no live flow.
    """
    rows = segments.set_index("physical_id")
    if segment_id not in rows.index:
        return None
    seg = rows.loc[segment_id]

    lanes, cap_before = _capacity(seg.get("highway"))
    eff_blocked = min(lanes_blocked, lanes)
    cap_after = max(0, lanes - eff_blocked) * LANE_CAPACITY_VPH
    loss_frac = (cap_before - cap_after) / cap_before if cap_before else 0.0

    # Normalised betweenness as a through-traffic load proxy in [0,1].
    bmax = float(segments["betweenness"].fillna(0).max()) or 1.0
    load = float(seg.get("betweenness") or 0.0) / bmax
    local_impact = round(load * loss_frac, 4)

    affected: list[AffectedSegment] = []
    spillover = 0.0
    for pid, hop in k_hop_neighborhood(segment_id, segments, hops):
        nb = rows.loc[pid]
        nb_load = float(nb.get("betweenness") or 0.0) / bmax
        impact = local_impact * (HOP_DECAY**hop) * (0.5 + 0.5 * nb_load)
        if impact >= impact_threshold:
            affected.append(
                AffectedSegment(
                    physical_id=pid, name=nb.get("name"), junction=nb.get("junction"),
                    hop=hop, impact=round(impact, 4),
                )
            )
            spillover += impact
    affected.sort(key=lambda a: a.impact, reverse=True)

    # Coarse, illustrative exposure: blocked throughput × duration.
    est_vehicle_minutes = round((cap_before - cap_after) / 60.0 * minutes, 1)

    return SimulationResult(
        evidence_id=f"sim-{uuid.uuid4().hex[:8]}",
        target_segment=segment_id,
        target_name=seg.get("name"),
        lanes=lanes,
        lanes_blocked=eff_blocked,
        minutes=minutes,
        capacity_before_vph=int(cap_before),
        capacity_after_vph=int(cap_after),
        capacity_loss_fraction=round(loss_frac, 3),
        local_impact=local_impact,
        spillover_index=round(spillover, 4),
        est_vehicle_minutes_affected=est_vehicle_minutes,
        affected=affected[:max_affected],
        assumptions={
            "lane_capacity_vph": LANE_CAPACITY_VPH,
            "lanes_by_highway_class": True,
            "demand_proxy": "normalised betweenness (no live flow)",
            "hop_decay": HOP_DECAY,
            "adjacency": "undirected (no heading in source)",
        },
        caveats=(
            "Simulated estimate, NOT measured flow. Demand is proxied by network "
            "centrality; absolute numbers are illustrative until validated against a "
            "speed API. Direction is approximate. Use for relative comparison and "
            "screening, under human judgement."
        ),
    )
