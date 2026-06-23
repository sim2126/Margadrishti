"""Shared test fixtures and synthetic data builders. Unit tests use synthetic data
(no network/OSM); integration tests for the repository/API are skipped if the gold
artifacts have not been built."""

from __future__ import annotations

import os

import pandas as pd
import pytest

os.environ.setdefault("MARGA_PII_SALT", "test-salt")
os.environ.setdefault("MARGA_DATA_ROOT", "./data")

# Hermetic copilot: a real ANTHROPIC_API_KEY may live in backend/.env, which Settings reads.
# Force the live path OFF for the suite so tests never spend the key or hit the network.
# The gated live test opts back in explicitly with MARGA_LIVE=1.
if os.environ.get("MARGA_LIVE") != "1":
    os.environ["ANTHROPIC_API_KEY"] = ""
    os.environ["MARGA_COPILOT_LLM_ENABLED"] = "false"

from margadrishti.core.config import get_settings  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield


def make_synthetic(n_days: int = 40, seed: int = 0):
    """Build matched / violations(safe) / segments frames for 4 segments over n_days."""
    import numpy as np

    rng = np.random.default_rng(seed)
    seg_ids = ["1_2_0", "3_4_0", "5_6_0", "7_8_0"]
    segments = pd.DataFrame(
        {
            "physical_id": seg_ids,
            "betweenness": [0.5, 0.2, 0.05, 0.3],
            "obstruction_weight": [0.9, 0.6, 0.4, 0.75],
            "length": [120.0, 80.0, 200.0, 60.0],
            "highway": ["primary", "tertiary", "residential", "secondary"],
            "h3_cells": [("8a1",), ("8a2",), ("8a3",), ("8a4",)],
        }
    )
    base = pd.Timestamp("2024-01-01", tz="UTC")
    rows = []
    rid = 0
    for d in range(n_days):
        for si, sid in enumerate(seg_ids):
            # busier, higher-index segments rarer; add daily noise
            k = int(rng.poisson(lam=[3, 1.5, 0.3, 2][si]))
            for _ in range(k):
                ts = base + pd.Timedelta(days=d, hours=int(rng.integers(0, 24)))
                rows.append(
                    {
                        "record_id": f"R{rid}", "physical_id": sid, "observed_at_utc": ts,
                        "validation_status": rng.choice(
                            ["approved", "rejected", "unvalidated"], p=[0.5, 0.2, 0.3]
                        ),
                        "officer_ref": f"O{rng.integers(0, 5)}",
                        "device_ref": f"D{rng.integers(0, 3)}",
                        "police_station": ["Madiwala", "Adugodi"][si % 2],
                        "junction_name": ["MG Jn", "No Junction"][si % 2],
                        "violation_types": ("WRONG PARKING",),
                    }
                )
                rid += 1
    viol = pd.DataFrame(rows)
    matched = viol[["record_id", "physical_id"]].copy()
    matched["match_confidence"] = 0.9
    matched["dist_m"] = 5.0
    matched["nearest_directed_edge"] = matched["physical_id"]
    return matched, viol, segments


@pytest.fixture
def synthetic():
    return make_synthetic()


def gold_exists() -> bool:
    s = get_settings()
    return (s.gold / "cii.parquet").exists() and (s.gold / "segments_dim.parquet").exists()


requires_gold = pytest.mark.skipif(
    not gold_exists(), reason="gold artifacts not built (run `make worker`)"
)
