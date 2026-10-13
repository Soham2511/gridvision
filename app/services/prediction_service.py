"""Validate feature rows and run the verified model artifacts."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from app.models.registry import ModelBundle


class PredictionInputError(ValueError):
    """A request does not match the model's verified feature contract."""


def predict_one(bundle: ModelBundle, features: dict[str, Any]) -> float:
    """Run one inference after validating feature names, types, and categories."""
    expected = set(bundle.features)
    actual = set(features)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        raise PredictionInputError(
            f"Feature mismatch; missing={missing}, unexpected={extra}."
        )

    row: dict[str, Any] = {name: features[name] for name in bundle.features}
    if bundle.name == "commercial":
        _apply_lightgbm_categories(bundle, row)
    for name, value in row.items():
        if name in bundle.metadata.get("categorical_features", []):
            continue
        if isinstance(value, bool):
            row[name] = int(value)
            continue
        if value is None:
            row[name] = np.nan
            continue
        if isinstance(value, str):
            raise PredictionInputError(f"Numeric feature {name!r} cannot be text.")
        try:
            numeric = float(value)
        except (TypeError, ValueError) as error:
            raise PredictionInputError(
                f"Feature {name!r} must be numeric or null."
            ) from error
        if not np.isfinite(numeric):
            raise PredictionInputError(f"Feature {name!r} must be finite or null.")
        row[name] = numeric

    frame = pd.DataFrame([row], columns=bundle.features)
    if bundle.name == "commercial":
        for feature, palette in zip(
            bundle.metadata["categorical_features"],
            bundle.estimator.booster_.pandas_categorical,
            strict=True,
        ):
            frame[feature] = pd.Categorical(frame[feature], categories=palette)
    estimator = bundle.estimator
    prediction = estimator.predict(frame)
    values = np.asarray(prediction).reshape(-1)
    if values.size != 1 or not np.isfinite(values[0]):
        raise RuntimeError(
            f"Model {bundle.name} returned an invalid prediction: {prediction!r}"
        )
    return float(values[0])


def _apply_lightgbm_categories(bundle: ModelBundle, row: dict[str, Any]) -> None:
    categorical_features = bundle.metadata.get("categorical_features", [])
    palettes = bundle.estimator.booster_.pandas_categorical
    if len(categorical_features) != len(palettes):
        raise RuntimeError(
            "LightGBM categorical palettes do not match the model metadata."
        )
    for feature, palette in zip(categorical_features, palettes, strict=True):
        value = row[feature]
        if value is None or str(value) not in palette:
            raise PredictionInputError(
                f"Unsupported category {value!r} for {feature!r}; the supplied "
                "artifact only supports its stored category palette."
            )
        row[feature] = str(value)
