#!/usr/bin/env python3
"""Log the fitted LightGBM model from hybrid_grid_2018.joblib to MLflow."""

from __future__ import annotations

import argparse
import math
import os
from pathlib import Path
from typing import Any

import joblib
import lightgbm
import mlflow
import mlflow.lightgbm
import numpy as np
import pandas as pd
from mlflow.models import infer_signature
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score


PROJECT_DIR = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Log hybrid_grid_2018.joblib's fitted LightGBM model to MLflow."
    )
    parser.add_argument(
        "--model-path",
        type=Path,
        default=PROJECT_DIR / "hybrid_grid_2018.joblib",
        help="Path to the trusted joblib model bundle.",
    )
    parser.add_argument(
        "--test-path",
        type=Path,
        default=PROJECT_DIR / "test_2018.parquet",
        help="Parquet file containing evaluation features and the target.",
    )
    parser.add_argument(
        "--target-column",
        default="target_energy",
        help="Name of the actual-value column in the evaluation parquet file.",
    )
    parser.add_argument(
        "--experiment",
        default="hybrid-grid-2018",
        help="MLflow experiment name.",
    )
    parser.add_argument(
        "--run-name",
        default="log-hybrid-grid-2018",
        help="Name for this MLflow run.",
    )
    parser.add_argument(
        "--registered-model-name",
        help="Optionally register the logged model under this name.",
    )
    return parser.parse_args()


def load_estimator(model_path: Path) -> lightgbm.LGBMRegressor:
    if not model_path.is_file():
        raise FileNotFoundError(f"Model file does not exist: {model_path}")

    bundle: Any = joblib.load(model_path)
    estimator = bundle.get("original_model") if isinstance(bundle, dict) else bundle
    if not isinstance(estimator, lightgbm.LGBMRegressor):
        found_type = type(estimator).__name__ if estimator is not None else "None"
        raise TypeError(
            "Expected a fitted lightgbm.LGBMRegressor in the joblib file "
            f"(bundle key 'original_model'); found {found_type}."
        )
    if not hasattr(estimator, "booster_"):
        raise ValueError("The LightGBM regressor is not fitted.")
    return estimator


def main() -> None:
    args = parse_args()
    model_path = args.model_path.expanduser().resolve()
    estimator = load_estimator(model_path)

    feature_names = estimator.booster_.feature_name()
    if not feature_names:
        raise ValueError("The fitted model does not contain feature names.")

    test_path = args.test_path.expanduser().resolve()
    if not test_path.is_file():
        raise FileNotFoundError(f"Test dataset does not exist: {test_path}")
    evaluation = pd.read_parquet(test_path, columns=[*feature_names, args.target_column])
    if evaluation.empty:
        raise ValueError(f"Test dataset contains no rows: {test_path}")

    y_true = evaluation[args.target_column]
    if y_true.isna().any() or not np.isfinite(y_true.to_numpy()).all():
        raise ValueError(
            f"Target column {args.target_column!r} contains missing or non-finite values."
        )
    X_eval = evaluation[feature_names]
    predictions = estimator.predict(X_eval)
    metrics = {
        "mae": mean_absolute_error(y_true, predictions),
        "rmse": math.sqrt(mean_squared_error(y_true, predictions)),
        "r2": r2_score(y_true, predictions),
    }

    # This example describes the model's input columns; it is not evaluation data.
    input_example = pd.DataFrame([[0.0] * len(feature_names)], columns=feature_names)
    signature = infer_signature(input_example, estimator.predict(input_example))

    tracking_uri = os.environ.get(
        "MLFLOW_TRACKING_URI",
        f"sqlite:///{(PROJECT_DIR / 'mlflow.db').resolve()}",
    )
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(args.experiment)

    model_log_options = {
        "artifact_path": "model",
        "input_example": input_example,
        "signature": signature,
        "registered_model_name": args.registered_model_name,
    }
    if args.registered_model_name is None:
        model_log_options.pop("registered_model_name")

    with mlflow.start_run(run_name=args.run_name) as run:
        mlflow.log_params(
            {
                "model_class": type(estimator).__name__,
                "model_file": model_path.name,
                "feature_count": len(feature_names),
                "evaluation_file": test_path.name,
                "evaluation_rows": len(evaluation),
                "target_column": args.target_column,
            }
        )
        mlflow.log_metrics(metrics)
        mlflow.set_tags(
            {
                "model_framework": "lightgbm",
                "model_source": str(model_path),
            }
        )
        model_info = mlflow.lightgbm.log_model(estimator, **model_log_options)

        print(f"Tracking URI: {tracking_uri}")
        print(f"Run ID: {run.info.run_id}")
        print(f"Logged model URI: {model_info.model_uri}")
        print(f"Evaluation metrics: {metrics}")


if __name__ == "__main__":
    main()
