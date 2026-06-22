"""Operational baselines. A learned model must beat ALL of these (CLAUDE.md) or it does
not ship. They are deliberately simple, transparent, and what a station already does
implicitly: "this spot is usually busy", "Tuesdays are bad here", "lately it's worse".
"""

from __future__ import annotations

import numpy as np
import pandas as pd


class HistoricalFrequency:
    """Per-segment mean daily count over the training window."""

    name = "historical_frequency"

    def fit(self, panel: pd.DataFrame) -> "HistoricalFrequency":
        self._mean = panel.groupby("physical_id")["y_count"].mean()
        self._global = float(panel["y_count"].mean())
        return self

    def predict_risk(self, panel: pd.DataFrame) -> np.ndarray:
        return panel["physical_id"].map(self._mean).fillna(self._global).to_numpy()


class DayOfWeekFrequency:
    """Per-(segment, day-of-week) mean — captures weekly seasonality per spot."""

    name = "day_of_week_frequency"

    def fit(self, panel: pd.DataFrame) -> "DayOfWeekFrequency":
        self._mean = panel.groupby(["physical_id", "dow"])["y_count"].mean()
        self._global = float(panel["y_count"].mean())
        return self

    def predict_risk(self, panel: pd.DataFrame) -> np.ndarray:
        idx = list(zip(panel["physical_id"], panel["dow"]))
        return pd.Series(self._mean.reindex(idx).to_numpy()).fillna(self._global).to_numpy()


class RecencyWeightedFrequency:
    """Exponentially recency-weighted per-segment mean (half-life in days)."""

    def __init__(self, half_life_days: float = 14.0) -> None:
        self.half_life_days = half_life_days
        self.name = "recency_weighted"

    def fit(self, panel: pd.DataFrame) -> "RecencyWeightedFrequency":
        decay = np.log(2) / self.half_life_days
        last = panel["day_index"].max()
        w = np.exp(-decay * (last - panel["day_index"]))
        wdf = panel.assign(_w=w, _wy=w * panel["y_count"])
        agg = wdf.groupby("physical_id").agg(num=("_wy", "sum"), den=("_w", "sum"))
        self._score = (agg["num"] / agg["den"]).fillna(0.0)
        self._global = float(panel["y_count"].mean())
        return self

    def predict_risk(self, panel: pd.DataFrame) -> np.ndarray:
        return panel["physical_id"].map(self._score).fillna(self._global).to_numpy()
