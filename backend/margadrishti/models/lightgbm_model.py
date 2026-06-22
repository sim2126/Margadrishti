"""LightGBM forecaster — the ship-it learned rung. Predicts probability a segment sees
a violation on a given day, from temporal + spatial + exposure features. Including the
exposure features lets the model separate intrinsic risk from patrol bias; SHAP-style
gain attribution gives every prediction a human-readable "why".
"""

from __future__ import annotations

import lightgbm as lgb
import numpy as np
import pandas as pd

from margadrishti.core.config import get_settings
from margadrishti.features.build import PANEL_CATEGORICALS, PANEL_FEATURES


class LightGBMForecaster:
    name = "lightgbm"

    def __init__(self, **params: object) -> None:
        self.params = {
            "objective": "binary",
            "n_estimators": 300,
            "learning_rate": 0.05,
            "num_leaves": 31,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "random_state": get_settings().seed,
            "n_jobs": -1,
            "verbose": -1,
            **params,
        }
        self.model: lgb.LGBMClassifier | None = None

    def fit(self, panel: pd.DataFrame) -> "LightGBMForecaster":
        X = panel[PANEL_FEATURES]
        y = panel["y"]
        self.model = lgb.LGBMClassifier(**self.params)
        self.model.fit(X, y, categorical_feature=PANEL_CATEGORICALS)
        return self

    def predict_risk(self, panel: pd.DataFrame) -> np.ndarray:
        assert self.model is not None, "fit before predict"
        return self.model.predict_proba(panel[PANEL_FEATURES])[:, 1]

    def feature_importance(self) -> dict[str, float]:
        assert self.model is not None
        imp = self.model.booster_.feature_importance(importance_type="gain")
        total = float(imp.sum()) or 1.0
        return {f: round(float(v) / total, 4) for f, v in zip(PANEL_FEATURES, imp)}
