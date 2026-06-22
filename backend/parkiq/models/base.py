"""Forecaster contract. Every rung of the ladder implements the same Protocol so they
are interchangeable behind evaluation and serving.

Ladder (CLAUDE.md): operational baselines → LightGBM → ST-GNN. A higher rung ships only
if it beats the lower ones under rolling-origin AND held-out-zone evaluation, on
Precision@K / Recall@K / PR-AUC over top-N **segments** (not hexes, not accuracy).

Models operate on the leakage-safe daily panel (features.build_daily_panel) and return a
row-aligned risk score. `to_segment_risk` reduces per-row risk to one value per physical
segment (the CII input); `explain` provides the human-readable "why".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class SegmentPrediction:
    physical_id: str
    horizon_date: str
    risk: float                        # bias-adjusted predicted risk (CII input)
    why: dict[str, float]              # human-readable feature attribution
    confidence: float


@runtime_checkable
class Forecaster(Protocol):
    name: str

    def fit(self, panel: pd.DataFrame) -> "Forecaster":
        """Train on a panel slice (rows up to the train cutoff)."""
        ...

    def predict_risk(self, panel: pd.DataFrame) -> np.ndarray:
        """Row-aligned risk in [0, ∞) or [0, 1]; higher = more enforcement-relevant risk."""
        ...


# Operational baselines a learned model must beat before it earns its keep.
BASELINE_NAMES = ("historical_frequency", "day_of_week_frequency", "recency_weighted")


def to_segment_risk(panel: pd.DataFrame, risk: np.ndarray, horizon_date) -> pd.DataFrame:
    """Reduce row-level risk to one risk per physical segment, using the chosen horizon
    day's prediction (falls back to the latest available day per segment)."""
    df = panel[["physical_id", "date"]].copy()
    df["risk"] = risk
    day = df[df["date"] == horizon_date]
    if day.empty:
        day = df.sort_values("date").groupby("physical_id", as_index=False).last()
    return day.groupby("physical_id", as_index=False)["risk"].mean()
