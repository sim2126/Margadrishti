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


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from margadrishti.api.app import app

    return TestClient(app)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["dataset_version"] != "unknown"


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
