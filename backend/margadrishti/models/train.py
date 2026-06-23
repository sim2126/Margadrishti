"""Training job (worker process). Reads gold panel, runs the baseline→LightGBM ladder
through the evaluation gate, selects the winner, emits per-segment bias-adjusted risk,
and recomputes CII from that risk (replacing the interim biased CII).

    python -m margadrishti.models.train

Outputs: gold/predictions.parquet, gold/cii.parquet, gold/eval_report.json
"""

from __future__ import annotations

import datetime as dt
import json

import pandas as pd

from margadrishti.cii.score import score_cii
from margadrishti.core.config import get_settings
from margadrishti.core.storage import Storage
from margadrishti.core.versioning import as_of_rfc3339, now_rfc3339
from margadrishti.models.base import to_segment_risk
from margadrishti.models.baselines import (
    DayOfWeekFrequency,
    HistoricalFrequency,
    RecencyWeightedFrequency,
)
from margadrishti.models.evaluate import (
    EvalReport,
    beats_baselines,
    held_out_zone_evaluate,
    rolling_origin_evaluate,
)
from margadrishti.models.lightgbm_model import LightGBMForecaster
from margadrishti.models.self_exciting import SelfExcitingForecaster

BASELINE_FACTORIES = [HistoricalFrequency, DayOfWeekFrequency, RecencyWeightedFrequency]
# Candidates that must EARN their place by beating every baseline on both gates.
CANDIDATE_FACTORIES = [SelfExcitingForecaster, LightGBMForecaster]


def _report_dict(r: EvalReport) -> dict:
    return {
        "model": r.model_name,
        "precision_at_k": r.precision_at_k,
        "recall_at_k": r.recall_at_k,
        "pr_auc": r.pr_auc,
        "n_test_rows": r.n_test_rows,
    }


def train(storage: Storage | None = None) -> dict:
    s = get_settings()
    storage = storage or Storage(s)
    panel = storage.read_parquet(s.gold, "panel")
    panel["highway"] = panel["highway"].astype("category")
    segments = storage.read_parquet(s.silver, "segments")
    seg_feats = storage.read_parquet(s.gold, "segment_features")

    print(f">> evaluating ladder on {len(panel)} panel rows "
          f"({panel['physical_id'].nunique()} segments, {panel['date'].nunique()} days)")
    # BOTH gates for the WHOLE ladder. A candidate (self-exciting, LightGBM) ships only if
    # it beats EVERY operational baseline on rolling-origin AND held-out-zone.
    base_roll = [rolling_origin_evaluate(f, panel) for f in BASELINE_FACTORIES]
    base_zone = [held_out_zone_evaluate(f, panel) for f in BASELINE_FACTORIES]

    candidates = []  # (factory, roll_report, zone_report, ships)
    for f in CANDIDATE_FACTORIES:
        roll = rolling_origin_evaluate(f, panel)
        zone = held_out_zone_evaluate(f, panel)
        ships = beats_baselines(roll, base_roll) and beats_baselines(zone, base_zone)
        candidates.append((f, roll, zone, ships))

    for r in [*base_roll, *(c[1] for c in candidates)]:
        print(f"   [rolling] {r.model_name:24} PR-AUC={r.pr_auc:.3f}  P@25={r.precision_at_k.get(25, float('nan')):.3f}")
    for r in [*base_zone, *(c[2] for c in candidates)]:
        print(f"   [zone]    {r.model_name:24} PR-AUC={r.pr_auc:.3f}  P@25={r.precision_at_k.get(25, float('nan')):.3f}")

    # Winner = the shipping candidate with the best rolling-origin PR-AUC; else the best
    # baseline by rolling-origin PR-AUC (working-over-fancy, honest fallback).
    shipped = [c for c in candidates if c[3]]
    if shipped:
        winner_factory = max(shipped, key=lambda c: c[1].pr_auc)[0]
        a_candidate_shipped = True
    else:
        best_base = max(zip(BASELINE_FACTORIES, base_roll), key=lambda t: t[1].pr_auc)[0]
        winner_factory = best_base
        a_candidate_shipped = False
    print(f">> a learned/frontier candidate shipped: {a_candidate_shipped}")

    model = winner_factory().fit(panel)
    risk_rows = model.predict_risk(panel)
    horizon = panel["date"].max()
    seg_risk = to_segment_risk(panel, risk_rows, horizon)

    model_version = f"{model.name}-{dt.date.today().isoformat()}"
    as_of = as_of_rfc3339(horizon)
    preds = seg_risk.assign(model_version=model_version, as_of=as_of)
    storage.write_parquet(preds, s.gold, "predictions")

    # Recompute CII from bias-adjusted risk (no longer interim/biased).
    cii = score_cii(seg_feats, segments, risk=seg_risk.set_index("physical_id")["risk"])
    cii["h3_cells"] = cii["h3_cells"].apply(list)
    storage.write_parquet(cii, s.gold, "cii")
    # Artifacts only. PostGIS publication is the separate publish job (db.serving).

    report = {
        "model_version": model_version,
        "winner": model.name,
        "a_candidate_shipped": a_candidate_shipped,
        "candidates": {
            c[1].model_name: {"ships": c[3], "rolling": _report_dict(c[1]), "held_out_zone": _report_dict(c[2])}
            for c in candidates
        },
        "rolling_origin": [_report_dict(r) for r in [*base_roll, *(c[1] for c in candidates)]],
        "held_out_zone": [_report_dict(r) for r in [*base_zone, *(c[2] for c in candidates)]],
        "feature_importance": model.feature_importance() if hasattr(model, "feature_importance") else {},
    }
    (s.gold / "eval_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    _update_manifest(s, model_version, as_of, model.name, a_candidate_shipped)
    print(f"OK predictions + CII written. winner={model.name} version={model_version}")
    return report


def _update_manifest(s, model_version, horizon, winner, a_candidate_shipped) -> None:
    path = s.gold / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    manifest["model"] = {
        "model_version": model_version,
        "winner": winner,
        "as_of": horizon,
        "trained_at": now_rfc3339(),
        # True if a learned/frontier candidate beat all baselines on both gates and shipped;
        # False means the honest baseline fallback is in use.
        "lightgbm_ships": a_candidate_shipped,
    }
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


if __name__ == "__main__":
    train()
