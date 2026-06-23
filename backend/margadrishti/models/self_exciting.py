"""Spatial self-exciting forecaster (Hawkes / near-repeat inspired).

Research basis: self-exciting point processes for event hotspots (Mohler et al., 2011 —
self-exciting point-process models of crime) and the "near-repeat" phenomenon, where an
event raises the short-term risk at the same place AND its spatial neighbours. We adapt
that to parking enforcement on the road graph:

    risk(segment) = recency-weighted own history
                  + α · mean(recency-weighted history of its road neighbours)

Neighbours come from the canonical physical_id node encoding (same adjacency the simulator
uses) — so a segment is "hot" if it, or the segments it connects to, recently saw illegal
parking. This adds the spatial-contagion term that the plain recency baseline lacks.

Honesty (CLAUDE.md): this is still an enforcement-OBSERVATION model, not prevalence, and it
must clear the same rolling-origin + held-out-zone gates as any rung before it ships.
"""

from __future__ import annotations

from collections import defaultdict

import numpy as np
import pandas as pd


def _neighbours(physical_ids: list[str]) -> dict[str, set[str]]:
    """1-hop road adjacency parsed from physical_id ("nodeA_nodeB_key"): segments sharing
    an endpoint node are neighbours. No graph object needed."""
    node_to_segs: dict[str, set[str]] = defaultdict(set)
    seg_nodes: dict[str, tuple[str, str]] = {}
    for pid in physical_ids:
        parts = pid.split("_")
        a, b = (parts[0], parts[1]) if len(parts) >= 2 else (pid, pid)
        seg_nodes[pid] = (a, b)
        node_to_segs[a].add(pid)
        node_to_segs[b].add(pid)
    nbrs: dict[str, set[str]] = {}
    for pid, (a, b) in seg_nodes.items():
        s = (node_to_segs[a] | node_to_segs[b]) - {pid}
        nbrs[pid] = s
    return nbrs


class SelfExcitingForecaster:
    name = "self_exciting"

    def __init__(self, half_life_days: float = 14.0, alpha: float = 0.5) -> None:
        self.half_life_days = half_life_days
        self.alpha = alpha  # weight on neighbour contagion term

    def fit(self, panel: pd.DataFrame) -> "SelfExcitingForecaster":
        decay = np.log(2) / self.half_life_days
        last = panel["day_index"].max()
        w = np.exp(-decay * (last - panel["day_index"]))
        own = (
            panel.assign(_wy=w * panel["y_count"])
            .groupby("physical_id")["_wy"].sum()
        )
        self._global = float(panel["y_count"].mean())

        nbrs = _neighbours(list(own.index))
        own_d = own.to_dict()
        score = {}
        for seg, val in own_d.items():
            ns = nbrs.get(seg, set())
            neigh = np.mean([own_d[n] for n in ns]) if ns else 0.0
            score[seg] = val + self.alpha * neigh
        self._score = pd.Series(score)
        return self

    def predict_risk(self, panel: pd.DataFrame) -> np.ndarray:
        return panel["physical_id"].map(self._score).fillna(self._global).to_numpy()
