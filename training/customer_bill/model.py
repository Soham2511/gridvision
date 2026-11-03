"""Estimator implementations shared by training and MLflow inference."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.utils.validation import check_is_fitted


class NaiveProjectionRegressor(RegressorMixin, BaseEstimator):
    """Baseline that scales observed energy to the full calendar month."""

    feature_name = "naive_projected_month_kwh"

    def fit(self, X: pd.DataFrame, y: pd.Series | np.ndarray) -> NaiveProjectionRegressor:
        if self.feature_name not in X.columns:
            raise ValueError(f"Required baseline feature is missing: {self.feature_name}")
        if len(X) != len(y):
            raise ValueError("X and y must contain the same number of rows.")
        self.feature_names_in_ = np.asarray(X.columns, dtype=object)
        self.n_features_in_ = len(self.feature_names_in_)
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        check_is_fitted(self, "feature_names_in_")
        if self.feature_name not in X.columns:
            raise ValueError(f"Required baseline feature is missing: {self.feature_name}")
        return np.maximum(
            pd.to_numeric(X[self.feature_name], errors="raise").to_numpy(dtype=float),
            0.0,
        )
