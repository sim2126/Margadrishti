"""Repository parameterisation + API contracts (integration; needs gold artifacts)."""

from __future__ import annotations

import re

import pytest

from margadrishti.api.repository import GoldRepository
from tests.conftest import requires_gold

pytestmark = requires_gold


def test_zones_nonempty():
    assert len(GoldRepository().zones()) > 0


def test_deployable_zones_exclude_sentinels():
    repo = GoldRepository()
    dep = repo.deployable_zones()
    assert set(dep) <= set(repo.zones())          # subset of analytics zones
    assert "No Police Station" not in dep
    assert "Unknown" not in dep


def test_cii_zone_filter_and_injection_safe():
    repo = GoldRepository()
    z = repo.zones()[0]
    filtered = repo.cii_segments(limit=50, zone=z)
    assert (filtered["zone"] == z).all()
    # A SQL-injection-shaped zone is treated as a literal parameter → empty, no error.
    evil = repo.cii_segments(limit=50, zone="'; DROP TABLE x; --")
    assert len(evil) == 0


def test_hourly_observed_window_within_allweek():
    """An hour-of-day window must never exceed a segment's all-week observed total."""
    repo = GoldRepository()
    allw = repo.hourly_observed(limit=20000).set_index("physical_id")["window_count"]
    h18 = repo.hourly_observed(hour=18, limit=20000).set_index("physical_id")["window_count"]
    common = h18.index.intersection(allw.index)
    assert len(common) > 0
    assert (h18.loc[common] <= allw.loc[common]).all()


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from margadrishti.api.app import app

    return TestClient(app)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["dataset_version"] != "unknown"
    assert r.json()["store"] in {"gold", "postgis"}


def test_ready_checks_serving_data(client):
    r = client.get("/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ready"
    assert body["checks"]["manifest"] is True
    assert body["checks"]["zones"] > 0
    assert body["checks"]["sample_cii_rows"] == 1


def test_request_id_header_is_returned(client):
    r = client.get("/health", headers={"x-request-id": "req-test-123"})
    assert r.status_code == 200
    assert r.headers["x-request-id"] == "req-test-123"


def test_cors_allows_configured_local_frontend(client):
    r = client.options(
        "/health",
        headers={
            "origin": "http://localhost:5173",
            "access-control-request-method": "GET",
        },
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_cii_contract_has_label_and_full_provenance(client):
    r = client.get("/segments/cii?limit=3")
    assert r.status_code == 200
    body = r.json()
    seg = body["segments"][0]
    assert seg["label"] and "·" in seg["label"]          # operationally distinguishable
    prov = body["provenance"]
    for field in ("generated_at", "dataset_version", "feature_version",
                  "road_network_version", "model_version"):
        assert prov[field] and prov[field] != "unknown"
    # as_of is RFC 3339 UTC, e.g. 2024-04-08T00:00:00Z (not "2024-04-08 00:00:00").
    assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", prov["as_of"]), prov["as_of"]


def test_hourly_cii_is_time_sliced_and_observed_labelled(client):
    r = client.get("/segments/cii/hourly?hour=18&limit=50")
    assert r.status_code == 200
    body = r.json()
    assert body["hour"] == 18
    assert body["day_of_week"] is None
    # Honesty contract: this is observed enforcement, never relabelled as prevalence/CII.
    assert body["is_observed_not_prevalence"] is True
    assert body["temporal_basis"] == "observed_enforcement_hour_of_week"
    segs = body["segments"]
    assert len(segs) > 0
    counts = [s["window_observed_count"] for s in segs]
    assert counts == sorted(counts, reverse=True)          # ranked by window intensity
    for s in segs:
        assert 0.0 <= s["hour_intensity"] <= 1.0
        assert s["window_observed_count"] >= 0
    if counts[0] > 0:
        assert segs[0]["hour_intensity"] == 1.0             # busiest segment sets the scale
    # full provenance travels with the time-sliced response too
    assert body["provenance"]["model_version"] != "unknown"


def test_hourly_cii_day_of_week_slice(client):
    r = client.get("/segments/cii/hourly?hour=9&day_of_week=0&limit=20")
    assert r.status_code == 200
    body = r.json()
    assert body["hour"] == 9 and body["day_of_week"] == 0
    assert isinstance(body["segments"], list)


def test_hourly_cii_rejects_out_of_range_hour(client):
    assert client.get("/segments/cii/hourly?hour=24").status_code == 422
    assert client.get("/segments/cii/hourly?day_of_week=7").status_code == 422


def test_area_summary_polygon_over_bbox_returns_subset(client):
    # A rectangle around Koramangala should contain a non-empty subset. On bounded
    # demo gold it may contain everything; on full-city gold it must not be assumed
    # to cover the whole serving surface.
    all_ct = len(client.get("/segments/cii?limit=20000").json()["segments"])
    body = client.post(
        "/area/summary",
        json={
            "polygon": [
                {"lon": 77.59, "lat": 12.90},
                {"lon": 77.66, "lat": 12.90},
                {"lon": 77.66, "lat": 12.96},
                {"lon": 77.59, "lat": 12.96},
            ],
            "limit": 5,
        },
    )
    assert body.status_code == 200
    b = body.json()
    assert b["method"] == "centroid_in_polygon"
    assert 0 < b["n_segments"] <= all_ct
    assert b["area_id"].startswith("area-")
    assert 0.0 <= b["mean_cii"] <= b["max_cii"]
    assert len(b["zones"]) >= 1
    assert len(b["top_segments"]) == 5                       # capped by `limit`
    ciis = [s["cii"] for s in b["top_segments"]]
    assert ciis == sorted(ciis, reverse=True)               # ranked by CII
    top = b["top_segments"][0]
    assert top["priority_utility"] >= 0 and "·" in top["label"]


def test_area_summary_far_polygon_is_empty(client):
    body = client.post(
        "/area/summary",
        json={"polygon": [
            {"lon": 0.0, "lat": 0.0},
            {"lon": 0.0, "lat": 0.01},
            {"lon": 0.01, "lat": 0.01},
        ]},
    )
    assert body.status_code == 200
    b = body.json()
    assert b["n_segments"] == 0
    assert b["top_segments"] == []
    assert b["mean_cii"] == 0.0 and b["observed_count"] == 0


def test_area_summary_requires_three_distinct_points(client):
    # two distinct points (first repeated) → 422 from the model validator
    r = client.post(
        "/area/summary",
        json={"polygon": [
            {"lon": 77.60, "lat": 12.92},
            {"lon": 77.60, "lat": 12.92},
            {"lon": 77.61, "lat": 12.93},
        ]},
    )
    assert r.status_code == 422


def test_area_deployment_plan_keeps_area_separate_from_zone(client):
    r = client.post(
        "/area/deployment/plan",
        json={
            "polygon": [
                {"lon": 77.59, "lat": 12.90},
                {"lon": 77.66, "lat": 12.90},
                {"lon": 77.66, "lat": 12.96},
                {"lon": 77.59, "lat": 12.96},
            ],
            "limit": 50,
            "n_units": 2,
            "shift_minutes": 180,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["area_id"].startswith("area-")
    assert "zone" not in body                         # drawn area must not masquerade as a jurisdiction
    assert body["method"] == "centroid_in_polygon"
    assert body["requires_human_approval"] is True
    assert body["n_segments"] >= body["n_candidate_segments"] > 0
    assert len(body["zones"]) >= 1                    # actual jurisdictions touched by the polygon
    assert "priority" in body["method_caveats"].lower()
    assert "jurisdiction" in body["area_caveats"].lower()
    for route in body["routes"]:
        assert route["minutes"] <= 180 + 1
        for stop in route["stops"]:
            assert "label" in stop


def test_deployment_unknown_zone_is_422(client):
    r = client.post("/deployment/plan", json={"zone": "Nowhere-XYZ", "n_units": 2})
    assert r.status_code == 422
    assert "valid_zones" in r.json()["detail"]


def test_deployment_valid_zone_plan(client):
    zone = client.get("/zones").json()["zones"][0]
    r = client.post("/deployment/plan", json={"zone": zone, "n_units": 2, "shift_minutes": 180})
    assert r.status_code == 200
    body = r.json()
    assert body["requires_human_approval"] is True
    assert "priority" in body["method_caveats"].lower()
    for route in body["routes"]:
        assert route["minutes"] <= 180 + 1
        for stop in route["stops"]:
            assert "label" in stop


def test_segment_detail_404(client):
    assert client.get("/segments/does_not_exist").status_code == 404


def test_neighborhood_and_simulation_and_context(client):
    # pick a real segment id from the CII list
    pid = client.get("/segments/cii?limit=1").json()["segments"][0]["physical_id"]

    nb = client.get(f"/segments/{pid}/neighborhood?hops=2").json()
    assert nb["found"] is True and "neighbors" in nb

    sim = client.post("/simulate/blockage", json={"segment_id": pid, "lanes_blocked": 1, "minutes": 45})
    assert sim.status_code == 200
    body = sim.json()
    assert body["kind"] == "simulated"
    assert body["capacity_after_vph"] <= body["capacity_before_vph"]
    assert "not measured flow" in body["caveats"].lower()

    ctx = client.get(f"/context/segment/{pid}?simulate=true").json()
    assert ctx["observed"]["kind"] == "observed"
    assert ctx["simulation"]["kind"] == "simulated"
    assert any("flow/speed" in g for g in ctx["data_gaps"])


def test_simulate_unknown_segment_404(client):
    assert client.post("/simulate/blockage", json={"segment_id": "nope_0"}).status_code == 404
