"""CII invariants + optimiser constraints."""

from __future__ import annotations

import warnings

import pandas as pd
import pytest

from margadrishti.cii.score import DEFAULT_WEIGHTS, PLANNED_COMPONENTS, score_cii
from margadrishti.optimize.deployment import Stop, _solve_greedy, optimise_routes


def _seg_features():
    return pd.DataFrame(
        {
            "physical_id": ["1_2_0", "3_4_0", "5_6_0"],
            "observed_count": [50, 10, 1],
            "approved_count": [20.0, 4.0, 0.0],
            "approval_rate": [0.4, 0.4, 0.0],
            "mean_severity": [0.9, 0.6, 0.4],
        }
    )


def _segments():
    return pd.DataFrame(
        {
            "physical_id": ["1_2_0", "3_4_0", "5_6_0"],
            "name": ["A Rd", "B Rd", "C Rd"],
            "highway": ["primary", "tertiary", "residential"],
            "betweenness": [0.5, 0.2, 0.01],
            "obstruction_weight": [0.9, 0.6, 0.4],
            "h3_cells": [("8a1",), ("8a2",), ("8a3",)],
        }
    )


def test_cii_with_model_risk_is_not_interim():
    risk = pd.Series({"1_2_0": 0.8, "3_4_0": 0.3, "5_6_0": 0.05})
    out = score_cii(_seg_features(), _segments(), risk=risk)
    assert (out["cii_risk_is_interim_biased"] == False).all()  # noqa: E712
    assert out["cii"].between(0, 1).all()
    assert out["cii"].is_monotonic_decreasing  # sorted desc


def test_cii_without_risk_warns_and_flags_interim():
    with pytest.warns(UserWarning):
        out = score_cii(_seg_features(), _segments())
    assert (out["cii_risk_is_interim_biased"] == True).all()  # noqa: E712


def test_cii_excludes_planned_components():
    out = score_cii(_seg_features(), _segments(), risk=pd.Series({"1_2_0": 1.0}))
    for planned in PLANNED_COMPONENTS:
        assert f"cii_component__{planned}" not in out.columns
    # Only implemented components carry weight.
    assert set(DEFAULT_WEIGHTS) == {"risk", "centrality", "obstruction"}


def _stops(n=12):
    return [Stop(f"s{i}", 12.93 + i * 0.001, 77.62 + i * 0.001, impact_i) for i, impact_i
            in zip(range(n), [1.0] * n)]


def test_optimiser_respects_shift_and_requires_approval():
    res = optimise_routes(_stops(), n_units=2, shift_minutes=120, dwell_minutes=10, speed_kmph=18)
    assert res.requires_human_approval is True
    assert "priority utility" in res.method_caveats.lower()
    for r in res.routes:
        assert r.minutes <= 120 + 1e-6           # never exceeds the shift
    assert 0 <= res.coverage_fraction <= 1
    assert res.total_priority_utility >= 0


def test_optimiser_empty_input():
    res = optimise_routes([], n_units=3)
    assert res.routes == [] and res.solver == "empty"


def test_greedy_fallback_is_feasible():
    res = _solve_greedy(_stops(8), n_units=2, shift_minutes=90, dwell_minutes=10, speed_kmph=18)
    assert res.solver == "greedy"
    for r in res.routes:
        assert r.minutes <= 90 + 1e-6
