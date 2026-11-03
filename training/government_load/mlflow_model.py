"""MLflow pyfunc wrapper for the grid routed government model."""

from __future__ import annotations

from typing import Any

import joblib
import mlflow.pyfunc
import numpy as np
import pandas as pd


class GovernmentHybridModel(mlflow.pyfunc.PythonModel):
    """Apply the per-grid original/log route from the registered model bundle."""

    def load_context(self, context: Any) -> None:
        self.bundle = joblib.load(context.artifacts["bundle"])

    def predict(self, context: Any, model_input: pd.DataFrame, params: Any = None) -> np.ndarray:
        del context, params
        if "grid_id" not in model_input:
            raise ValueError("Government inference requires a grid_id column.")
        features = self.bundle["features"]
        missing = sorted(set(features).difference(model_input.columns))
        if missing:
            raise ValueError(f"Government inference is missing features: {missing}")
        matrix = model_input.loc[:, features].astype(np.float32)
        matrix = matrix.replace([np.inf, -np.inf], np.nan)
        grid_ids = model_input["grid_id"].astype(int).to_numpy()
        routes = self.bundle["routing"].set_index("grid_id")["selected_model"]
        selected = np.array([routes.get(grid_id, "original") for grid_id in grid_ids])
        output = np.zeros(len(matrix), dtype=float)
        for model_name, estimator in (
            ("original", self.bundle["original_model"]),
            ("log", self.bundle["log_model"]),
        ):
            positions = np.flatnonzero(selected == model_name)
            if len(positions):
                values = estimator.predict(matrix.iloc[positions])
                if model_name == "log":
                    values = np.expm1(np.maximum(values, 0))
                output[positions] = values
        return np.maximum(output, 0)
