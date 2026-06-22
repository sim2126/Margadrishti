"""What-if flow simulator + Traffic Context compiler."""

from __future__ import annotations

import pandas as pd

from margadrishti.simulate.flow import k_hop_neighborhood, simulate_parking_blockage


def _segments():
    # Chain 1-2-3-4 (so 1_2_0 adjoins 2_3_0 adjoins 3_4_0), plus an isolated edge 9_10_0.
    return pd.DataFrame(
        {
            "physical_id": ["1_2_0", "2_3_0", "3_4_0", "9_10_0"],
            "name": ["A Rd", "B Rd", "C Rd", "Far Rd"],
            "junction": [None, None, None, None],
            "highway": ["primary", "secondary", "residential", "residential"],
            "betweenness": [0.9, 0.5, 0.2, 0.1],
        }
    )


def test_neighborhood_follows_shared_nodes():
    segs = _segments()
    nbrs = dict(k_hop_neighborhood("1_2_0", segs, hops=2))
    assert nbrs.get("2_3_0") == 1          # shares node 2
    assert nbrs.get("3_4_0") == 2          # two hops away
    assert "9_10_0" not in nbrs            # disconnected
    assert "1_2_0" not in nbrs             # seed excluded


def test_blockage_reduces_capacity_and_spills_over():
    segs = _segments()
    res = simulate_parking_blockage("1_2_0", segs, lanes_blocked=1, minutes=45, hops=2)
    assert res is not None
    assert res.kind == "simulated"
    assert res.capacity_after_vph < res.capacity_before_vph
    assert 0 < res.capacity_loss_fraction <= 1
    assert res.spillover_index >= 0
    assert any(a.physical_id == "2_3_0" for a in res.affected)  # neighbour affected
    assert "not measured flow" in res.caveats.lower()
    assert res.evidence_id.startswith("sim-")


def test_blocking_more_lanes_increases_impact():
    segs = _segments()
    one = simulate_parking_blockage("1_2_0", segs, lanes_blocked=1)
    two = simulate_parking_blockage("1_2_0", segs, lanes_blocked=2)  # primary = 2 lanes
    assert two.capacity_loss_fraction >= one.capacity_loss_fraction
    assert two.local_impact >= one.local_impact


def test_unknown_segment_returns_none():
    assert simulate_parking_blockage("no_such_0", _segments()) is None


# --- Traffic Context compiler (uses a tiny fake repo, no DB/gold needed) ---
class _FakeRepo:
    def segment_detail(self, pid):
        if pid != "1_2_0":
            return None
        return {
            "name": "A Rd", "zone": "Madiwala", "cii": 0.8, "observed_count": 50,
            "approved_count": 20.0, "approval_rate": 0.4, "n_officers": 5, "active_hours": 9,
            "predicted_risk": 0.6, "mean_match_confidence": 0.9,
            "cii_risk_is_interim_biased": False,
        }

    def all_segments(self, zone=None):
        return _segments()

    def manifest(self):
        return {
            "etl": {"dataset_version": "ds1", "feature_version": "panel-v1",
                    "road_network_version": "osm-x", "cii_version": "cii-v2"},
            "model": {"model_version": "recency_weighted-2026", "as_of": "2024-04-08T00:00:00Z",
                      "lightgbm_ships": False},
        }


def test_context_is_evidence_kinded_with_gaps():
    from margadrishti.context.compiler import build_segment_context

    ctx = build_segment_context(_FakeRepo(), "1_2_0", run_simulation=True)
    assert ctx is not None
    assert ctx.observed.kind == "observed" and ctx.observed.cii == 0.8
    assert ctx.predicted.kind == "predicted" and ctx.predicted.risk == 0.6
    assert ctx.simulation is not None and ctx.simulation.kind == "simulated"
    assert ctx.neighborhood.segments  # has graph neighbours
    # honesty: structural data gaps always present; learned model didn't ship → baseline
    assert any("flow/speed" in g for g in ctx.data_gaps)
    assert ctx.uncertainty.learned_model_shipped is False
    assert ctx.provenance.model_version.startswith("recency_weighted")


def test_context_missing_segment_returns_none():
    from margadrishti.context.compiler import build_segment_context

    assert build_segment_context(_FakeRepo(), "nope_0") is None
