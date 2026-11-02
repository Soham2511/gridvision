"""Persistable numeric preprocessing shared by fit and future assignments."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import RobustScaler
from sklearn.feature_selection import VarianceThreshold


class BehaviourFeatureEngineer(BaseEstimator, TransformerMixin):
    """Collapse correlated raw statistics into scale-aware behaviour features."""

    output_features = (
        "log_mean_energy_kwh",
        "coefficient_of_variation",
        "night_energy_share",
        "morning_energy_share",
        "afternoon_energy_share",
        "weekend_to_weekday_ratio",
        "p95_to_average_ratio",
        "daily_energy_cv",
        "monthly_energy_cv",
        "monthly_peak_to_average",
        "peak_hour_sin",
        "peak_hour_cos",
    )

    def fit(self, x: pd.DataFrame, y=None):
        del y
        if not isinstance(x, pd.DataFrame):
            raise TypeError("BehaviourFeatureEngineer expects a pandas DataFrame")
        return self

    def transform(self, x: pd.DataFrame) -> pd.DataFrame:
        if not isinstance(x, pd.DataFrame):
            raise TypeError("BehaviourFeatureEngineer expects a pandas DataFrame")
        mean = pd.to_numeric(x["mean_energy_kwh"], errors="coerce")
        positive_mean = mean.where(mean > 0)
        output = pd.DataFrame(index=x.index)
        output["log_mean_energy_kwh"] = np.log1p(mean.where(mean >= 0))
        for field in (
            "coefficient_of_variation",
            "night_energy_share",
            "morning_energy_share",
            "afternoon_energy_share",
            "weekend_to_weekday_ratio",
            "monthly_energy_cv",
            "monthly_peak_to_average",
            "peak_hour_sin",
            "peak_hour_cos",
        ):
            output[field] = pd.to_numeric(x[field], errors="coerce")
        output["p95_to_average_ratio"] = (
            pd.to_numeric(x["p95_energy_kwh"], errors="coerce") / positive_mean
        )
        output["daily_energy_cv"] = (
            pd.to_numeric(x["daily_energy_stddev_kwh"], errors="coerce")
            / pd.to_numeric(x["mean_daily_energy_kwh"], errors="coerce").where(
                pd.to_numeric(x["mean_daily_energy_kwh"], errors="coerce") > 0
            )
        )
        return output.loc[:, self.output_features]

    def get_feature_names_out(self, input_features=None):
        del input_features
        return np.asarray(self.output_features, dtype=object)


class CorrelationFilter(BaseEstimator, TransformerMixin):
    """Drop later features in the documented order when |correlation| is high."""

    def __init__(self, threshold: float = 0.98):
        self.threshold = threshold

    def fit(self, x: pd.DataFrame, y=None):
        del y
        if not isinstance(x, pd.DataFrame):
            raise TypeError("CorrelationFilter expects a pandas DataFrame")
        if not 0 < self.threshold <= 1:
            raise ValueError("correlation threshold must be in (0, 1]")
        self.feature_names_in_ = np.asarray(x.columns, dtype=object)
        correlations = x.corr().abs()
        keep = [True] * len(self.feature_names_in_)
        for left in range(len(self.feature_names_in_)):
            if not keep[left]:
                continue
            for right in range(left + 1, len(self.feature_names_in_)):
                value = correlations.iloc[left, right]
                if keep[right] and pd.notna(value) and value >= self.threshold:
                    keep[right] = False
        self.support_ = np.asarray(keep, dtype=bool)
        self.feature_names_out_ = self.feature_names_in_[self.support_]
        return self

    def transform(self, x: pd.DataFrame) -> pd.DataFrame:
        if not isinstance(x, pd.DataFrame):
            raise TypeError("CorrelationFilter expects a pandas DataFrame")
        return x.loc[:, self.feature_names_out_]

    def get_feature_names_out(self, input_features=None):
        del input_features
        return self.feature_names_out_


def build_preprocessor(correlation_threshold: float = 0.95) -> Pipeline:
    """Return the fixed preprocessing graph fitted once with each clustering model."""
    return Pipeline(
        steps=[
            ("behaviour_features", BehaviourFeatureEngineer()),
            ("remove_correlated", CorrelationFilter(threshold=correlation_threshold)),
            ("imputer", SimpleImputer(strategy="median", keep_empty_features=True)),
            ("remove_constant", VarianceThreshold(threshold=0.0)),
            ("scaler", RobustScaler()),
        ]
    )

