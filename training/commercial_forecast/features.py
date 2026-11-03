"""Stable LightGBM input contract for commercial building forecasting."""

import numpy as np
import pandas as pd

FEATURE_COLUMNS = [
    "GeneralUseType",
    "SpecificUseType",
    "usetype",
    "building.type",
    "idf.kw",
    "building.area.m2",
    "FootprintArea.m2",
    "EffectiveYearBuilt",
    "latitude",
    "longitude",
    "forecast_horizon_hours",
    "energy_at_origin",
    "energy_lag_1",
    "energy_lag_24",
    "energy_lag_168",
    "energy_lag_336",
    "energy_lag_720",
    "energy_rolling_mean_24h",
    "energy_rolling_std_24h",
    "energy_observation_count_24h",
    "energy_rolling_mean_7d",
    "energy_rolling_std_7d",
    "energy_observation_count_7d",
    "energy_rolling_mean_30d",
    "energy_rolling_std_30d",
    "energy_observation_count_30d",
    "target_hour",
    "target_day_of_week",
    "target_month",
    "target_is_weekend",
    "target_day_of_month",
    "target_day_of_year",
    "target_hour_sin",
    "target_hour_cos",
    "target_day_of_year_sin",
    "target_day_of_year_cos",
]
CATEGORICAL_FEATURES = [
    "GeneralUseType",
    "SpecificUseType",
    "usetype",
    "building.type",
    "idf.kw",
]
TARGET_COLUMN = "target_energy"
IDENTIFIER_COLUMNS = [
    "OBJECTID",
    "id.grid.coarse",
    "forecast_origin_timestamp",
    "target_timestamp",
]


def prepare_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Validate, order, and normalize a raw commercial model input frame."""
    missing = sorted(set(FEATURE_COLUMNS) - set(frame.columns))
    if missing:
        raise ValueError(f"Commercial model input is missing features: {missing}")
    result = frame.loc[:, FEATURE_COLUMNS].copy()
    for column in CATEGORICAL_FEATURES:
        result[column] = (
            result[column].astype("string").fillna("__MISSING__").astype(str)
        )
    for column in FEATURE_COLUMNS:
        if column not in CATEGORICAL_FEATURES:
            result[column] = pd.to_numeric(result[column], errors="coerce").astype(
                "float64"
            )
    return result.replace([np.inf, -np.inf], np.nan)
