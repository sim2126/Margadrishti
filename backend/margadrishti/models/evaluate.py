"""Evaluation harness — the gate every model passes through.

Protocol (CLAUDE.md):
  - rolling-origin splits (train earlier days → test later days; no leakage)
  - held-out-zone test (generalise to unseen jurisdictions)
  - metrics on top-K SEGMENTS per day: Precision@K, Recall@K, PR-AUC (accuracy is banned)
A learned model ships only if it beats every operational baseline on these.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

ModelFactory = Callable[[], object]  # zero-arg → fresh unfitted Forecaster


@dataclass(frozen=True)
class EvalReport:
    model_name: str
    precision_at_k: dict[int, float]
    recall_at_k: dict[int, float]
    pr_auc: float
    n_test_rows: int = 0
    extra: dict = field(default_factory=dict)


def _ranking_metrics(test: pd.DataFrame, scores: np.ndarray, ks: tuple[int, ...]) -> dict:
    t = test[["date", "y"]].copy()
    t["score"] = scores
    pak: dict[int, list[float]] = {k: [] for k in ks}
    rak: dict[int, list[float]] = {k: [] for k in ks}
    for _, day in t.groupby("date"):
        pos = day["y"].sum()
        ranked = day.sort_values("score", ascending=False)
        for k in ks:
            topk = ranked.head(k)
            pak[k].append(topk["y"].sum() / min(k, len(ranked)))
            if pos > 0:
                rak[k].append(topk["y"].sum() / pos)
    pr_auc = average_precision_score(t["y"], t["score"]) if t["y"].nunique() > 1 else float("nan")
    return {
        "precision_at_k": {k: float(np.mean(v)) if v else float("nan") for k, v in pak.items()},
        "recall_at_k": {k: float(np.mean(v)) if v else float("nan") for k, v in rak.items()},
        "pr_auc": float(pr_auc),
    }


def rolling_origin_evaluate(
    factory: ModelFactory,
    panel: pd.DataFrame,
    *,
    ks: tuple[int, ...] = (10, 25, 50),
    n_folds: int = 4,
    initial_frac: float = 0.5,
) -> EvalReport:
    """Expanding-window walk-forward evaluation."""
    dates = np.sort(panel["date"].unique())
    start = int(len(dates) * initial_frac)
    cutpoints = np.linspace(start, len(dates) - 1, n_folds + 1).astype(int)
    pak, rak, aucs, n = {k: [] for k in ks}, {k: [] for k in ks}, [], 0
    for i in range(n_folds):
        train_end, test_end = dates[cutpoints[i]], dates[cutpoints[i + 1]]
        train = panel[panel["date"] < train_end]
        test = panel[(panel["date"] >= train_end) & (panel["date"] <= test_end)]
        if train.empty or test.empty:
            continue
        model = factory().fit(train)
        m = _ranking_metrics(test, model.predict_risk(test), ks)
        for k in ks:
            pak[k].append(m["precision_at_k"][k])
            rak[k].append(m["recall_at_k"][k])
        if not np.isnan(m["pr_auc"]):
            aucs.append(m["pr_auc"])
        n += len(test)
    name = getattr(factory(), "name", "model")
    return EvalReport(
        model_name=name,
        precision_at_k={k: float(np.nanmean(v)) if v else float("nan") for k, v in pak.items()},
        recall_at_k={k: float(np.nanmean(v)) if v else float("nan") for k, v in rak.items()},
        pr_auc=float(np.mean(aucs)) if aucs else float("nan"),
        n_test_rows=n,
    )


def held_out_zone_evaluate(
    factory: ModelFactory, panel: pd.DataFrame, *, ks: tuple[int, ...] = (10, 25, 50), max_zones: int = 5
) -> EvalReport:
    """Train excluding a zone, test on it — spatial transfer to unseen jurisdictions."""
    zones = panel["zone"].value_counts().head(max_zones).index
    pak, rak, aucs, n = {k: [] for k in ks}, {k: [] for k in ks}, [], 0
    for z in zones:
        train, test = panel[panel["zone"] != z], panel[panel["zone"] == z]
        if train.empty or test.empty:
            continue
        model = factory().fit(train)
        m = _ranking_metrics(test, model.predict_risk(test), ks)
        for k in ks:
            pak[k].append(m["precision_at_k"][k])
            rak[k].append(m["recall_at_k"][k])
        if not np.isnan(m["pr_auc"]):
            aucs.append(m["pr_auc"])
        n += len(test)
    return EvalReport(
        model_name=getattr(factory(), "name", "model") + "@held_out_zone",
        precision_at_k={k: float(np.nanmean(v)) if v else float("nan") for k, v in pak.items()},
        recall_at_k={k: float(np.nanmean(v)) if v else float("nan") for k, v in rak.items()},
        pr_auc=float(np.mean(aucs)) if aucs else float("nan"),
        n_test_rows=n,
    )


def beats_baselines(candidate: EvalReport, baselines: list[EvalReport], k: int = 25) -> bool:
    """Candidate ships only if its PR-AUC and P@k exceed every baseline's."""
    return all(
        (candidate.pr_auc >= b.pr_auc) and (candidate.precision_at_k[k] >= b.precision_at_k[k])
        for b in baselines
    )
