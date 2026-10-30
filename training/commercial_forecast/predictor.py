"""Portable prediction wrapper packaged with the registered MLflow model."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, RegressorMixin

from training.commercial_forecast.features import prepare_features


class CommercialPredictionPipeline(BaseEstimator, RegressorMixin):
    """Apply the agreed feature contract and return non-negative predictions."""

    def __init__(self, estimator: Any) -> None:
        self.estimator = estimator

    def fit(
        self, features: pd.DataFrame, target: np.ndarray
    ) -> "CommercialPredictionPipeline":
        self.estimator.fit(prepare_features(features), target)
        return self

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        values = np.asarray(
            self.estimator.predict(prepare_features(features)), dtype=np.float64
        )
        return np.maximum(values.reshape(-1), 0.0)
