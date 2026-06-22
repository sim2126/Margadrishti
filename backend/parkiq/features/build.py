"""Segment-level feature aggregation (gold layer).

Joins map-matched violations to their directed segment and aggregates into:
  - observed enforcement counts by validation status (NEVER called "prevalence")
  - enforcement-exposure features (distinct officers/devices/active hours) so models
    can separate genuine risk from patrol bias (CLAUDE.md)
  - violation-type severity (footpath/main-road/crossing obstruct flow more)
All temporal features are derived in IST via core.timeutils.
"""

from __future__ import annotations

import pandas as pd

from parkiq.core.schemas import ValidationStatus
from parkiq.core.timeutils import IST

# How obstructive the violation itself is, independent of road class.
VIOLATION_SEVERITY = {
    "PARKING ON FOOTPATH": 1.0,
    "PARKING NEAR ROAD CROSSING": 0.95,
    "PARKING NEAR TRAFFIC LIGHT OR ZEBRA CROSS": 0.95,
    "DOUBLE PARKING": 0.9,
    "PARKING IN A MAIN ROAD": 0.85,
    "PARKING OPPOSITE TO ANOTHER PARKED VEHICLE": 0.7,
    "WRONG PARKING": 0.6,
    "NO PARKING": 0.5,
}
_DEFAULT_SEVERITY = 0.5


def _severity(types: tuple[str, ...]) -> float:
    return max((VIOLATION_SEVERITY.get(t, _DEFAULT_SEVERITY) for t in types), default=_DEFAULT_SEVERITY)


def aggregate_to_segments(matched: pd.DataFrame, violations: pd.DataFrame) -> pd.DataFrame:
    """Per-physical-segment observed-enforcement aggregate. `matched` carries
    (record_id, physical_id, match_confidence, ...); `violations`=safe ingestion output.
    Returns one row per physical segment. Counts are confidence-weighted so low-quality
    map-matches contribute less. These are OBSERVED ENFORCEMENT, never 'prevalence'."""
    df = matched.merge(violations, on="record_id", how="inner")
    df["severity"] = df["violation_types"].apply(_severity)
    df["ist_hour"] = df["observed_at_utc"].dt.tz_convert(IST).dt.hour
    w = df["match_confidence"].clip(0, 1)
    df["w_approved"] = w * (df["validation_status"] == ValidationStatus.APPROVED.value)
    df["w_rejected"] = w * (df["validation_status"] == ValidationStatus.REJECTED.value)

    g = df.groupby("physical_id")
    out = pd.DataFrame(
        {
            "observed_count": g.size(),                       # raw event count
            "weighted_count": g.apply(lambda d: d["match_confidence"].clip(0, 1).sum()),
            "approved_count": g["w_approved"].sum(),
            "rejected_count": g["w_rejected"].sum(),          # weak signal, not hard-neg
            "mean_severity": g["severity"].mean(),
            # exposure: many distinct officers/devices/hours ⇒ broad patrol, not a fluke
            "n_officers": g["officer_ref"].nunique(),
            "n_devices": g["device_ref"].nunique(),
            "active_hours": g["ist_hour"].nunique(),
            "mean_match_confidence": g["match_confidence"].mean(),
            "first_seen_utc": g["observed_at_utc"].min(),
            "last_seen_utc": g["observed_at_utc"].max(),
        }
    ).reset_index()
    out["approval_rate"] = out["approved_count"] / out["weighted_count"].clip(lower=1e-6)
    return out


def segment_hour_of_week(matched: pd.DataFrame, violations: pd.DataFrame) -> pd.DataFrame:
    """Physical-segment × IST hour-of-week counts — base for temporal baselines/forecasting."""
    df = matched.merge(violations[["record_id", "observed_at_utc"]], on="record_id", how="inner")
    ist = df["observed_at_utc"].dt.tz_convert(IST)
    df["hour_of_week"] = ist.dt.weekday * 24 + ist.dt.hour
    return (
        df.groupby(["physical_id", "hour_of_week"]).size().rename("count").reset_index()
    )


# Feature columns the learned model consumes (order-independent; categoricals declared).
PANEL_FEATURES = [
    "dow", "is_weekend", "day_index",
    "betweenness", "obstruction_weight", "length", "highway",
    "lag_1", "lag_7", "roll_mean_7", "roll_mean_28",
    "expo_cum_count", "expo_cum_officers",
]
PANEL_CATEGORICALS = ["highway"]


def build_daily_panel(
    matched: pd.DataFrame, violations: pd.DataFrame, segments: pd.DataFrame
) -> pd.DataFrame:
    """Leakage-safe (physical_id × IST-date) panel for forecasting.

    Target `y_count` = observed violations that day (observed enforcement, not
    prevalence); `y` = y_count > 0. Lags/rolling/exposure are all shifted to use only
    information available strictly before the prediction day. Exposure features
    (cumulative counts/officers) let the model separate patrol bias from intrinsic risk.
    Restricted to segments that were ever observed (the universe enforcement cares about).
    """
    df = matched.merge(
        violations[["record_id", "observed_at_utc", "officer_ref", "police_station"]],
        on="record_id",
        how="inner",
    )
    df["date"] = df["observed_at_utc"].dt.tz_convert(IST).dt.normalize().dt.tz_localize(None)
    # Modal police station per segment → the zone label for held-out-zone evaluation.
    seg_zone = (
        df.groupby("physical_id")["police_station"]
        .agg(lambda s: s.mode().iloc[0] if not s.mode().empty else "Unknown")
        .rename("zone")
    )

    daily = (
        df.groupby(["physical_id", "date"])
        .agg(y_count=("record_id", "size"), n_officers=("officer_ref", "nunique"))
        .reset_index()
    )

    # Dense (segment × every date in range) grid so "no violation" days are real zeros.
    dates = pd.date_range(daily["date"].min(), daily["date"].max(), freq="D")
    seg_ids = daily["physical_id"].unique()
    grid = pd.MultiIndex.from_product([seg_ids, dates], names=["physical_id", "date"]).to_frame(
        index=False
    )
    panel = grid.merge(daily, on=["physical_id", "date"], how="left").fillna(
        {"y_count": 0, "n_officers": 0}
    )
    panel = panel.sort_values(["physical_id", "date"]).reset_index(drop=True)

    g = panel.groupby("physical_id", sort=False)["y_count"]
    panel["lag_1"] = g.shift(1).fillna(0)
    panel["lag_7"] = g.shift(7).fillna(0)
    panel["roll_mean_7"] = g.shift(1).rolling(7, min_periods=1).mean().reset_index(0, drop=True).fillna(0)
    panel["roll_mean_28"] = g.shift(1).rolling(28, min_periods=1).mean().reset_index(0, drop=True).fillna(0)
    # Exposure: cumulative history strictly before today (anti-bias signal).
    panel["expo_cum_count"] = g.cumsum().sub(panel["y_count"])
    panel["expo_cum_officers"] = (
        panel.groupby("physical_id")["n_officers"].cumsum().sub(panel["n_officers"])
    )

    panel["dow"] = panel["date"].dt.weekday
    panel["is_weekend"] = (panel["dow"] >= 5).astype(int)
    panel["day_index"] = (panel["date"] - panel["date"].min()).dt.days
    panel["y"] = (panel["y_count"] > 0).astype(int)

    seg_static = segments[["physical_id", "betweenness", "obstruction_weight", "length", "highway"]]
    panel = panel.merge(seg_static, on="physical_id", how="left")
    panel = panel.merge(seg_zone, on="physical_id", how="left")
    panel["highway"] = panel["highway"].astype("category")
    return panel
