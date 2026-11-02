from __future__ import annotations

import logging
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_PATH = (
    ROOT
    / "backend"
    / "app"
    / "models"
    / "anomaly_prediction"
    / "runtime"
)
sys.path.insert(0, str(RUNTIME_PATH))

from gridvision_data import (  # noqa: E402
    build_gold_features,
    parse_bronze_to_silver,
    prepare_model_input,
)
from gridvision_logging import configure_logging  # noqa: E402
from gridvision_mlflow import (  # noqa: E402
    important_metrics,
    main as run_mlflow_cli,
    run_tracked_training,
)
from gridvision_pipeline import (  # noqa: E402
    INPUT_COLUMNS,
    POINT_FEATURES,
    GridVisionExperiment,
    PipelineConfig,
    add_causal_features,
)


class GridVisionWorkflowTests(unittest.TestCase):
    def write_source(self, path: Path, energy: list[float] | None = None) -> None:
        rows = 4
        frame = pd.DataFrame(
            {
                "OBJECTID": np.full(rows, 42, dtype=np.int64),
                "timestamp": pd.date_range("2019-01-01", periods=rows, freq="h"),
                "normalized_building_energy_kwh": energy or [0.1, 0.2, 0.3, 0.4],
                "latitude": np.full(rows, 34.0),
                "longitude": np.full(rows, -118.0),
                "is_anomaly": [False, True, False, False],
                "building.type": ["house"] * rows,
            }
        )
        pq.write_table(pa.Table.from_pandas(frame, preserve_index=False), path)

    def write_layer_source(self, path: Path) -> None:
        timestamps = pd.date_range("2019-01-01", periods=96, freq="h")
        rows = [
            {
                "OBJECTID": customer,
                "timestamp": timestamp,
                "normalized_building_energy_kwh": (
                    0.8
                    + customer * 0.01
                    + 0.2 * np.sin(hour * 2 * np.pi / 24)
                ),
                "latitude": 34.0 + customer * 0.001,
                "longitude": -118.0,
                "is_anomaly": False,
                "building.type": "single-family",
            }
            for customer in range(10)
            for hour, timestamp in enumerate(timestamps)
        ]
        pq.write_table(
            pa.Table.from_pandas(pd.DataFrame(rows), preserve_index=False),
            path,
            row_group_size=1_000,
        )

    def test_bronze_silver_gold_layers_and_gold_feature_reuse(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bronze = root / "bronze.parquet"
            silver_path = root / "silver" / "measurements.parquet"
            gold_path = root / "gold" / "features.parquet"
            self.write_layer_source(bronze)

            silver = parse_bronze_to_silver(bronze, silver_path, batch_size=128)
            original = pq.read_table(bronze).to_pandas()
            parsed = pq.read_table(silver_path).to_pandas()
            self.assertEqual(silver["rows"], len(original))
            self.assertEqual(parsed.columns.tolist(), original.columns.tolist())
            pd.testing.assert_frame_equal(parsed, original)

            config = PipelineConfig(
                parquet_path=str(silver_path),
                gold_features_path=str(gold_path),
                train_customer_sample=2,
                validation_customer_sample=1,
                test_customer_sample=1,
            )
            gold = build_gold_features(silver_path, gold_path, config)
            features = pq.read_table(gold_path).to_pandas()
            self.assertEqual(gold["rows"], 4 * 96)
            self.assertEqual(
                features.columns.tolist(),
                INPUT_COLUMNS + ["baseline"] + POINT_FEATURES,
            )
            self.assertNotIn("is_anomaly", features.columns)
            self.assertNotIn("building.type", features.columns)

            experiment = GridVisionExperiment(config)
            experiment.audit_and_load()
            cached = experiment._normal_features(experiment.train_history)
            expected = add_causal_features(experiment.train_history).loc[
                :, cached.columns
            ]
            pd.testing.assert_frame_equal(
                cached.reset_index(drop=True),
                expected.reset_index(drop=True),
                check_dtype=False,
                check_exact=False,
                rtol=1e-6,
                atol=1e-6,
            )

    def test_prepare_projects_and_preserves_only_model_input_columns(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.parquet"
            destination = root / "prepared" / "model_input.parquet"
            self.write_source(source)

            result = prepare_model_input(source, destination, batch_size=2)
            prepared = pq.read_table(destination).to_pandas()

            self.assertEqual(result["rows"], 4)
            self.assertEqual(prepared.columns.tolist(), INPUT_COLUMNS)
            self.assertEqual(prepared["OBJECTID"].tolist(), [42] * 4)
            self.assertNotIn("is_anomaly", prepared.columns)
            self.assertNotIn("building.type", prepared.columns)
            np.testing.assert_allclose(
                prepared["normalized_building_energy_kwh"].to_numpy(),
                [0.1, 0.2, 0.3, 0.4],
            )

    def test_prepare_rejects_non_finite_model_values_and_leaves_no_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.parquet"
            destination = root / "prepared.parquet"
            self.write_source(source, [0.1, float("nan"), 0.3, 0.4])

            with self.assertRaisesRegex(ValueError, "null values|non-finite"):
                prepare_model_input(source, destination, batch_size=2)

            self.assertFalse(destination.exists())
            self.assertEqual(list(root.glob(".*.tmp")), [])

    def test_prepare_requires_all_input_columns(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.parquet"
            pq.write_table(
                pa.table({"OBJECTID": [1], "timestamp": [pd.Timestamp("2019-01-01")]}),
                source,
            )

            with self.assertRaisesRegex(ValueError, "missing model columns"):
                prepare_model_input(source, root / "prepared.parquet")

    def test_tracking_metrics_are_selected_and_finite(self) -> None:
        metrics = {
            "validation_detection": {
                "f1": 0.8,
                "pr_auc": 0.9,
                "test_points": 100,
                "event_detection_delay_hours": None,
            },
            "test_detection": {"f1": 0.7, "false_alerts_per_customer": float("nan")},
            "test_classification": {"macro_f1": 0.6, "classification_report": {}},
            "spatial_event_localization": {"event_f1": 0.4, "false_events": 3},
        }

        selected = important_metrics(metrics)

        self.assertEqual(
            selected,
            {
                "validation_detection.f1": 0.8,
                "validation_detection.pr_auc": 0.9,
                "test_detection.f1": 0.7,
                "test_classification.macro_f1": 0.6,
                "spatial_event_localization.event_f1": 0.4,
            },
        )

    def test_training_logs_only_important_metrics_and_three_artifacts(self) -> None:
        import mlflow

        self.addCleanup(mlflow.set_tracking_uri, mlflow.get_tracking_uri())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            dataset = root / "input.parquet"
            dataset.touch()

            class FakeExperiment:
                def __init__(self, config: PipelineConfig):
                    self.config = config
                    self.profile = {"rows": 12}
                    self.split_integrity = {"customer_overlap": 0}
                    self.metrics = {
                        "validation_detection": {"f1": 0.8, "pr_auc": 0.9},
                        "test_detection": {"f1": 0.7, "positive_points": 4},
                    }
                    self.event_localization_metrics = {"event_f1": 0.6}

                def run(self) -> dict[str, object]:
                    model = Path(self.config.model_path)
                    report_directory = Path(self.config.report_dir)
                    model.parent.mkdir(parents=True, exist_ok=True)
                    report_directory.mkdir(parents=True, exist_ok=True)
                    metrics_path = report_directory / "evaluation_metrics.json"
                    event_path = report_directory / "event_localization_evaluation.json"
                    model.write_bytes(b"bundle")
                    metrics_path.write_text("{}", encoding="utf-8")
                    event_path.write_text("{}", encoding="utf-8")
                    artifacts = {
                        "model": str(model),
                        "metrics": str(metrics_path),
                        "event_localization_evaluation": str(event_path),
                    }
                    return {"metrics": self.metrics, "artifacts": artifacts}

            tracking_uri = f"sqlite:///{(root / 'mlflow.db').as_posix()}"
            previous_directory = Path.cwd()
            try:
                os.chdir(root)
                with patch("gridvision_pipeline.GridVisionExperiment", FakeExperiment):
                    result = run_tracked_training(
                        dataset,
                        root / "model.joblib",
                        root / "reports",
                        tracking_uri=tracking_uri,
                        experiment_name="workflow-test",
                    )
            finally:
                os.chdir(previous_directory)

            client = mlflow.tracking.MlflowClient(tracking_uri=tracking_uri)
            run = client.get_run(result["run_id"])
            self.assertEqual(
                run.data.metrics,
                {
                    "validation_detection.f1": 0.8,
                    "validation_detection.pr_auc": 0.9,
                    "test_detection.f1": 0.7,
                    "spatial_event_localization.event_f1": 0.6,
                },
            )
            self.assertEqual(
                {artifact.path for artifact in client.list_artifacts(result["run_id"])},
                {"evaluation", "model"},
            )
            self.assertEqual(
                {
                    Path(artifact.path).name
                    for artifact in client.list_artifacts(result["run_id"], "model")
                },
                {"model.joblib"},
            )
            self.assertEqual(
                {
                    Path(artifact.path).name
                    for artifact in client.list_artifacts(
                        result["run_id"], "evaluation"
                    )
                },
                {"evaluation_metrics.json", "event_localization_evaluation.json"},
            )

    def test_mlflow_module_entry_point_builds_layers_and_starts_training(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.parquet"
            silver_path = root / "silver.parquet"
            gold_path = root / "gold.parquet"
            model = root / "model.joblib"
            reports = root / "reports"
            silver = {"path": str(silver_path), "rows": 12}
            gold = {"path": str(gold_path), "rows": 12}
            result = {"run_id": "test-run", "metrics": {}, "artifacts": {}}
            with (
                patch.dict(
                    "os.environ",
                    {
                        "GRIDVISION_SOURCE_DATA": str(source),
                        "GRIDVISION_SILVER_DATA": str(silver_path),
                        "GRIDVISION_GOLD_DATA": str(gold_path),
                        "GRIDVISION_MODEL_PATH": str(model),
                        "GRIDVISION_REPORT_DIR": str(reports),
                    },
                    clear=False,
                ),
                patch("gridvision_logging.configure_logging"),
                patch(
                    "gridvision_data.parse_bronze_to_silver",
                    return_value=silver,
                ) as parse,
                patch(
                    "gridvision_data.build_gold_features",
                    return_value=gold,
                ) as engineer,
                patch(
                    "gridvision_mlflow.run_tracked_training",
                    return_value=result,
                ) as train,
            ):
                run_mlflow_cli()

            parse.assert_called_once_with(source, silver_path)
            engineer.assert_called_once_with(str(silver_path), gold_path)
            train.assert_called_once_with(
                prepared_data_path=str(silver_path),
                model_path=str(model),
                report_dir=str(reports),
                gold_features_path=str(gold_path),
            )

    def test_logging_setup_is_idempotent_and_writes_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "gridvision.log"
            root_logger = logging.getLogger()
            original_handlers = root_logger.handlers[:]
            try:
                for handler in root_logger.handlers[:]:
                    root_logger.removeHandler(handler)
                configure_logging(destination)
                handler_count = len(root_logger.handlers)
                configure_logging(destination)
                self.assertEqual(len(root_logger.handlers), handler_count)

                logging.getLogger("gridvision.test").info("anomaly pipeline test")
                for handler in root_logger.handlers:
                    handler.flush()

                self.assertIn("anomaly pipeline test", destination.read_text())
            finally:
                for handler in root_logger.handlers[:]:
                    root_logger.removeHandler(handler)
                    handler.close()
                for handler in original_handlers:
                    root_logger.addHandler(handler)


if __name__ == "__main__":
    unittest.main()
