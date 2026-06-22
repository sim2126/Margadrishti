"""Congestion-Impact Index — a transparent prioritisation proxy, NOT a causal measure.

CII = weighted sum of robustly-scaled, individually-inspectable components that are
ACTUALLY IMPLEMENTED:
  risk         · bias-adjusted predicted enforcement-relevant risk (not raw density)
  centrality   · segment betweenness — choking a corridor hurts more
  obstruction  · road-class × violation-type severity

PLANNED (not yet implemented — never pitch as live): poi_proximity (metro/market/
junction nearness), incident_overlap (co-located ASTraM incidents). They are listed in
`PLANNED_COMPONENTS` and reported in provenance, but contribute ZERO weight today.

Every active component is returned alongside the score so the UI/copilot can show the
"why". No "delay prevented"/"congestion reduced" language is permitted from this number.
"""

from __future__ import annotations

import warnings

import pandas as pd

# Only implemented components carry weight (sum need not be 1; comparable within a run).
DEFAULT_WEIGHTS = {
    "risk": 0.50,
    "centrality": 0.25,
    "obstruction": 0.25,
}
# Designed but NOT implemented — surfaced honestly, never silently counted.
PLANNED_COMPONENTS = ("poi_proximity", "incident_overlap")


def _robust_scale(s: pd.Series) -> pd.Series:
    """Scale to [0,1] using 5th–95th pct (robust to the heavy tail of enforcement counts)."""
    lo, hi = s.quantile(0.05), s.quantile(0.95)
    if hi <= lo:
        return pd.Series(0.0, index=s.index)
    return ((s - lo) / (hi - lo)).clip(0, 1)


def score_cii(
    seg_features: pd.DataFrame,
    segments: pd.DataFrame,
    risk: pd.Series | None = None,
    weights: dict[str, float] | None = None,
) -> pd.DataFrame:
    """Return per-physical-segment CII with its components.

    `risk` is the model's bias-adjusted predicted risk per physical_id (the correct
    input). If omitted, we fall back to raw observed-enforcement density as an explicit
    INTERIM proxy and flag it — this reinforces patrol bias and must not ship as final.
    `seg_features` from features.aggregate_to_segments; `segments` from build_segments.
    """
    w = weights or DEFAULT_WEIGHTS
    df = seg_features.merge(
        segments[["physical_id", "name", "highway", "betweenness", "obstruction_weight", "h3_cells"]],
        on="physical_id",
        how="left",
    )

    interim_bias = risk is None
    if interim_bias:
        warnings.warn(
            "CII risk term is using RAW observed-enforcement density (interim, biased). "
            "Replace with bias-adjusted forecast risk before shipping.",
            stacklevel=2,
        )
        risk_raw = df["observed_count"]
    else:
        risk_raw = df["physical_id"].map(risk).fillna(0)

    comp = pd.DataFrame(index=df.index)
    comp["risk"] = _robust_scale(risk_raw)
    comp["centrality"] = _robust_scale(df["betweenness"].fillna(0))
    comp["obstruction"] = _robust_scale(df["obstruction_weight"].fillna(0.4) * df["mean_severity"])

    # CII is the weighted sum of IMPLEMENTED components only. Planned components do not
    # silently leak in as zeros within a weighted blend — they carry no weight at all.
    df["cii"] = sum(comp[k] * w[k] for k in w)
    df["cii_risk_is_interim_biased"] = interim_bias
    for k in w:
        df[f"cii_component__{k}"] = comp[k]

    cols = ["physical_id", "name", "highway", "cii", "cii_risk_is_interim_biased",
            "observed_count", "approved_count", "approval_rate", "h3_cells"] + [
        f"cii_component__{k}" for k in w
    ]
    return df[cols].sort_values("cii", ascending=False).reset_index(drop=True)
