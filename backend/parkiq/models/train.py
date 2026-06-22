"""Training job (worker process). Reads gold panel, runs the baseline→LightGBM ladder
through the evaluation gate, selects the winner, emits per-segment bias-adjusted risk,
and recomputes CII from that risk (replacing the interim biased CII).

    python -m parkiq.models.train

Outputs: gold/predictions.parquet, gold/cii.parquet, gold/eval_report.json
"""

from __future__ import annotations

import datetime as dt
import json

import pandas as pd

from parkiq.cii.score import score_cii
from parkiq.core.config import get_settings
from parkiq.core.storage import Storage
from parkiq.core.versioning import as_of_rfc3339, now_rfc3339
from parkiq.models.base import to_segment_risk
from parkiq.models.baselines import (
    DayOfWeekFrequency,
    HistoricalFrequency,
    RecencyWeightedFrequency,
)
from parkiq.models.evaluate import (
    EvalReport,
    beats_baselines,
    held_out_zone_evaluate,
    rolling_origin_evaluate,
)
from parkiq.models.lightgbm_model import LightGBMForecaster

BASELINE_FACTORIES = [HistoricalFrequency, DayOfWeekFrequency, RecencyWeightedFrequency]


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
    # BOTH gates, for the WHOLE ladder — LightGBM only ships if it beats every baseline
    # on rolling-origin AND held-out-zone.
    base_roll = [rolling_origin_evaluate(f, panel) for f in BASELINE_FACTORIES]
    base_zone = [held_out_zone_evaluate(f, panel) for f in BASELINE_FACTORIES]
    lgbm_roll = rolling_origin_evaluate(LightGBMForecaster, panel)
    lgbm_zone = held_out_zone_evaluate(LightGBMForecaster, panel)
    wins_roll = beats_baselines(lgbm_roll, base_roll)
    wins_zone = beats_baselines(lgbm_zone, base_zone)
    ships = wins_roll and wins_zone

    for r in [*base_roll, lgbm_roll]:
        print(f"   [rolling] {r.model_name:24} PR-AUC={r.pr_auc:.3f}  P@25={r.precision_at_k.get(25, float('nan')):.3f}")
    for r in [*base_zone, lgbm_zone]:
        print(f"   [zone]    {r.model_name:24} PR-AUC={r.pr_auc:.3f}  P@25={r.precision_at_k.get(25, float('nan')):.3f}")
    print(f">> LightGBM ships? rolling={wins_roll} zone={wins_zone} -> {ships}")

    # Winner provides bias-adjusted risk; if LightGBM fails either gate, fall back to the
    # best baseline (working-over-fancy) and flag it.
    winner = LightGBMForecaster if ships else RecencyWeightedFrequency
    model = winner().fit(panel)
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
        "lightgbm_ships": ships,
        "lightgbm_beats_baselines_rolling": wins_roll,
        "lightgbm_beats_baselines_held_out_zone": wins_zone,
        "rolling_origin": [_report_dict(r) for r in [*base_roll, lgbm_roll]],
        "held_out_zone": [_report_dict(r) for r in [*base_zone, lgbm_zone]],
        "feature_importance": model.feature_importance() if hasattr(model, "feature_importance") else {},
    }
    (s.gold / "eval_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    _update_manifest(s, model_version, as_of, model.name, ships, wins_roll, wins_zone)
    print(f"OK predictions + CII written. winner={model.name} version={model_version}")
    return report


def _update_manifest(s, model_version, horizon, winner, ships, wins_roll, wins_zone) -> None:
    path = s.gold / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    manifest["model"] = {
        "model_version": model_version,
        "winner": winner,
        "as_of": horizon,
        "trained_at": now_rfc3339(),
        "lightgbm_ships": ships,
        "beats_baselines_rolling": wins_roll,
        "beats_baselines_held_out_zone": wins_zone,
    }
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


if __name__ == "__main__":
    train()
