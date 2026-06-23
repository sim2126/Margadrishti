"""Leakage-safe panel + model ladder + evaluation gate."""

from __future__ import annotations

import numpy as np

from margadrishti.features.build import PANEL_FEATURES, build_daily_panel
from margadrishti.models.baselines import (
    DayOfWeekFrequency,
    HistoricalFrequency,
    RecencyWeightedFrequency,
)
from margadrishti.models.base import to_segment_risk
from margadrishti.models.evaluate import beats_baselines, rolling_origin_evaluate
from margadrishti.models.lightgbm_model import LightGBMForecaster
from margadrishti.models.self_exciting import SelfExcitingForecaster, _neighbours


def test_panel_is_dense_and_leakage_safe(synthetic):
    matched, viol, segs = synthetic
    panel = build_daily_panel(matched, viol, segs)

    # Dense grid: every segment × every date present (zero-violation days are real rows).
    assert len(panel) == panel["physical_id"].nunique() * panel["date"].nunique()
    assert (panel["y_count"] == 0).any()

    # Feature contract present; zone attached.
    assert set(PANEL_FEATURES).issubset(panel.columns)
    assert panel["zone"].notna().any()

    # No leakage: the first day per segment has lag_1 == 0 (nothing before it).
    first = panel.sort_values("date").groupby("physical_id").head(1)
    assert (first["lag_1"] == 0).all()

    # Exposure is strictly-prior cumulative: never counts today's events.
    assert (panel["expo_cum_count"] <= panel.groupby("physical_id")["y_count"].cumsum()).all()

    # Binary label consistent with count.
    assert ((panel["y"] == 1) == (panel["y_count"] > 0)).all()


def test_baselines_and_lightgbm_predict(synthetic):
    matched, viol, segs = synthetic
    panel = build_daily_panel(matched, viol, segs)
    panel["highway"] = panel["highway"].astype("category")
    for factory in (HistoricalFrequency, DayOfWeekFrequency, RecencyWeightedFrequency, LightGBMForecaster):
        model = factory().fit(panel)
        risk = model.predict_risk(panel)
        assert len(risk) == len(panel)
        assert np.all(np.isfinite(risk))


def test_to_segment_risk_one_row_per_segment(synthetic):
    matched, viol, segs = synthetic
    panel = build_daily_panel(matched, viol, segs)
    model = HistoricalFrequency().fit(panel)
    sr = to_segment_risk(panel, model.predict_risk(panel), panel["date"].max())
    assert sr["physical_id"].is_unique
    assert set(sr["physical_id"]) <= set(panel["physical_id"])


def test_rolling_origin_returns_finite_metrics(synthetic):
    matched, viol, segs = synthetic
    panel = build_daily_panel(matched, viol, segs)
    panel["highway"] = panel["highway"].astype("category")
    rep = rolling_origin_evaluate(RecencyWeightedFrequency, panel, ks=(2, 3), n_folds=2)
    assert rep.precision_at_k[2] >= 0
    assert 0 <= rep.pr_auc <= 1


def test_beats_baselines_logic():
    from margadrishti.models.evaluate import EvalReport

    base = [EvalReport("b", {25: 0.2}, {25: 0.1}, 0.10)]
    better = EvalReport("m", {25: 0.3}, {25: 0.2}, 0.15)
    worse = EvalReport("m", {25: 0.1}, {25: 0.05}, 0.05)
    assert beats_baselines(better, base, k=25) is True
    assert beats_baselines(worse, base, k=25) is False


def test_self_exciting_neighbours_from_physical_ids():
    # chain 1-2-3: 1_2_0 and 2_3_0 share node 2; 9_10_0 is disconnected
    nbrs = _neighbours(["1_2_0", "2_3_0", "3_4_0", "9_10_0"])
    assert "2_3_0" in nbrs["1_2_0"]
    assert "1_2_0" not in nbrs["1_2_0"]      # not its own neighbour
    assert nbrs["9_10_0"] == set()           # isolated


def test_self_exciting_fits_and_predicts(synthetic):
    matched, viol, segs = synthetic
    panel = build_daily_panel(matched, viol, segs)
    model = SelfExcitingForecaster().fit(panel)
    risk = model.predict_risk(panel)
    assert len(risk) == len(panel)
    assert np.all(np.isfinite(risk))


def test_self_exciting_neighbour_term_raises_score():
    # Two adjacent segments, only the neighbour has history → seed gets a spillover lift.
    import pandas as pd

    panel = pd.DataFrame(
        {
            "physical_id": ["1_2_0", "1_2_0", "2_3_0", "2_3_0"],
            "day_index": [0, 1, 0, 1],
            "y_count": [0, 0, 5, 5],  # history only on neighbour 2_3_0
        }
    )
    with_alpha = SelfExcitingForecaster(alpha=0.8).fit(panel)
    no_alpha = SelfExcitingForecaster(alpha=0.0).fit(panel)
    # seed 1_2_0 has zero own history; contagion from 2_3_0 lifts it only when alpha>0
    assert with_alpha._score["1_2_0"] > no_alpha._score["1_2_0"]
