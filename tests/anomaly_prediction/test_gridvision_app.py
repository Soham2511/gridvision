from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

import sys

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

from gridvision_app.inference import InferenceService  # noqa: E402
from gridvision_app.jobs import AnalysisStore, _event_geojson  # noqa: E402
from app.models.anomaly_prediction.service import estimate_workload_rows  # noqa: E402
from app import create_app  # noqa: E402
from app.config import TestingConfig  # noqa: E402
from gridvision_event_localization import (  # noqa: E402
    ANOMALY_COLUMNS,
    EVENT_SUMMARY_COLUMNS,
    EventLocalizationConfig,
)
from gridvision_pipeline import INPUT_COLUMNS, POINT_FEATURES  # noqa: E402


class SpikeDetector:
    def predict_proba(self, matrix: np.ndarray) -> np.ndarray:
        relative_deviation = matrix[:, POINT_FEATURES.index("relative_deviation")]
        anomaly_probability = np.where(relative_deviation > 1.0, 0.99, 0.01)
        return np.column_stack((1.0 - anomaly_probability, anomaly_probability))


def make_source(path: Path, customer_ids: tuple[int, ...] = (101,)) -> None:
    timestamps = pd.date_range("2019-01-01", periods=96, freq="h")
    parts = []
    for customer_id in customer_ids:
        energy = np.full(len(timestamps), 1.0)
        energy[48] = 8.0
        parts.append(
            pd.DataFrame(
                {
                    "OBJECTID": np.full(
                        len(timestamps), customer_id, dtype=np.int64
                    ),
                    "timestamp": timestamps,
                    "normalized_building_energy_kwh": energy,
                    "latitude": np.full(len(timestamps), 34.0),
                    "longitude": np.full(len(timestamps), -118.0),
                    "is_anomaly": np.ones(len(timestamps), dtype=bool),
                    "anomaly_event_id": np.full(
                        len(timestamps), "MUST_NOT_BE_USED"
                    ),
                    "anomaly_type": np.full(len(timestamps), "zero_block"),
                }
            )
        )
    data = pd.concat(parts, ignore_index=True)
    table = pa.Table.from_pandas(data, preserve_index=False)
    pq.write_table(table, path, row_group_size=len(data))


def make_bundle(path: Path) -> None:
    joblib.dump(
        {
            "detector": SpikeDetector(),
            "detector_threshold": 0.5,
            "rule_thresholds": {
                "spike_relative_deviation": 0.5,
                "drop_relative_deviation": -0.5,
                "zero_block_minimum_hours": 3.0,
                "flatline_minimum_hours": 6.0,
                "flatline_minimum_pre_event_cv": 0.05,
                "flatline_minimum_level_deviation": 0.001,
            },
            "point_features": POINT_FEATURES,
            "anomaly_types": ["spike", "drop", "zero_block", "flatline"],
            "evaluation_metrics": {},
        },
        path,
    )


class GridVisionApplicationTests(unittest.TestCase):
    def test_analysis_batches_customers_and_localizes_after_combining(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data_path = root / "input.parquet"
            model_path = root / "model.joblib"
            make_source(data_path, (101, 102, 103))
            make_bundle(model_path)
            service = InferenceService(data_path, model_path)

            import gridvision_app.inference as inference_module

            original_limit = inference_module.MAX_ANALYSIS_ROWS
            inference_module.MAX_ANALYSIS_ROWS = 100
            try:
                result = service.analyze(
                    customer_ids=[101, 102, 103],
                    start_date=pd.Timestamp("2019-01-03").date(),
                    end_date=pd.Timestamp("2019-01-03").date(),
                    localization=EventLocalizationConfig(),
                )
            finally:
                inference_module.MAX_ANALYSIS_ROWS = original_limit

            self.assertEqual(result["metadata"]["customer_batch_count"], 3)
            self.assertEqual(result["metadata"]["customer_batch_size"], 1)
            self.assertEqual(result["metrics"]["input_rows_scored"], 252)
            self.assertEqual(result["metrics"]["selected_customer_count"], 3)

    def test_multi_day_analysis_is_batched_when_workload_exceeds_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data_path = root / "input.parquet"
            model_path = root / "model.joblib"
            make_source(data_path, (101, 102, 103))
            make_bundle(model_path)
            inference = InferenceService(data_path, model_path)

            import gridvision_app.inference as inference_module

            original_limit = inference_module.MAX_ANALYSIS_ROWS
            inference_module.MAX_ANALYSIS_ROWS = 100
            try:
                result = inference.analyze(
                    customer_ids=[101, 102, 103],
                    start_date=pd.Timestamp("2019-01-03").date(),
                    end_date=pd.Timestamp("2019-01-04").date(),
                    localization=EventLocalizationConfig(),
                )
            finally:
                inference_module.MAX_ANALYSIS_ROWS = original_limit

            self.assertEqual(result["metadata"]["customer_batch_count"], 3)
            self.assertGreater(result["metadata"]["input_rows_scored"], 100)

    def test_geojson_contains_a_closed_event_extent_boundary(self) -> None:
        feature = _event_geojson(
            [
                {
                    "event_id": "event-1",
                    "event_scope": "LOCAL_AREA",
                    "latitude_center": 34.0,
                    "longitude_center": -118.0,
                    "spatial_extent_km": 2.0,
                }
            ]
        )["features"][0]
        self.assertEqual(feature["geometry"]["type"], "Polygon")
        ring = feature["geometry"]["coordinates"][0]
        self.assertEqual(ring[0], ring[-1])
        self.assertGreater(len(ring), 4)

    def test_saved_bundle_detects_localizes_and_persists_real_inference_results(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data_path = root / "input.parquet"
            model_path = root / "model.joblib"
            runs_path = root / "runs"
            make_source(data_path)
            make_bundle(model_path)
            service = InferenceService(data_path, model_path)
            self.assertEqual(len(service.customer_ids), 1)
            result = service.analyze(
                customer_ids=[101],
                start_date=pd.Timestamp("2019-01-03").date(),
                end_date=pd.Timestamp("2019-01-03").date(),
                localization=EventLocalizationConfig(),
            )
            self.assertGreater(result["metrics"]["anomaly_window_count"], 0)
            self.assertEqual(result["metrics"]["localized_event_count"], 1)
            event = result["events"][0]
            self.assertEqual(event["event_scope"], "SINGLE_CUSTOMER")
            self.assertEqual(event["customer_ids"], [101])
            self.assertEqual(result["anomaly_windows"][0]["anomaly_type"], "spike")
            self.assertEqual(result["affected_customer_ids"], [101])
            self.assertEqual(
                result["metrics"]["event_size_distribution"],
                {
                    "1 customer": 1,
                    "2-5 customers": 0,
                    "6-20 customers": 0,
                    "21+ customers": 0,
                },
            )

            store = AnalysisStore(runs_path)
            request = {
                "customer_ids": [101],
                "start_date": "2019-01-03",
                "end_date": "2019-01-03",
                "h3_resolution": 8,
                "spatial_radius_km": 5.0,
                "maximum_start_time_difference_minutes": 30,
                "minimum_temporal_overlap": 0.25,
                "maximum_interval_gap_minutes": 60,
            }
            manifest = store.create(request)
            store.run(service, manifest["analysis_id"], request)
            completed = store.get(manifest["analysis_id"])
            self.assertEqual(completed["status"], "completed")
            self.assertEqual(store.events(manifest["analysis_id"])["total"], 1)
            self.assertEqual(
                store.affected_customers(manifest["analysis_id"]), [101]
            )
            detail = store.event_detail(manifest["analysis_id"], event["event_id"])
            self.assertEqual(detail["event"]["customer_ids"], [101])
            self.assertTrue(detail["anomaly_windows"])
            self.assertTrue(store.result_file(manifest["analysis_id"], "events.csv").is_file())
            anomaly_records_path = store.result_file(
                manifest["analysis_id"], "anomaly_records.csv"
            )
            geographic_clusters_path = store.result_file(
                manifest["analysis_id"], "geographic_clusters.csv"
            )
            self.assertIn("event_id", pd.read_csv(anomaly_records_path).columns)
            self.assertEqual(
                list(pd.read_csv(geographic_clusters_path).columns),
                [
                    "event_id",
                    "spatial_cluster_id",
                    "customer_count",
                    "latitude_center",
                    "longitude_center",
                    "event_start",
                    "event_end",
                ],
            )
            manifest_path = runs_path / manifest["analysis_id"] / "analysis.json"
            persisted_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            persisted_manifest["status"] = "running"
            manifest_path.write_text(json.dumps(persisted_manifest), encoding="utf-8")
            recovered_store = AnalysisStore(runs_path)
            self.assertEqual(
                recovered_store.get(manifest["analysis_id"])["status"], "completed"
            )
            self.assertNotIn("is_anomaly", INPUT_COLUMNS)
            self.assertNotIn("anomaly_event_id", INPUT_COLUMNS)

    def test_workload_estimate_includes_causal_and_post_event_context(self) -> None:
        rows = estimate_workload_rows(
            customer_count=10,
            start_date=pd.Timestamp("2019-01-08").date(),
            end_date=pd.Timestamp("2019-01-08").date(),
            source_start=pd.Timestamp("2019-01-01").date(),
            source_end=pd.Timestamp("2019-12-31").date(),
        )
        self.assertEqual(rows, 10 * (24 + 168 + 12))

    def test_interrupted_run_without_persisted_results_is_failed_on_restart(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = AnalysisStore(temporary)
            manifest = store.create({"start_date": "2019-01-01"})
            recovered = AnalysisStore(temporary).get(manifest["analysis_id"])
            self.assertEqual(recovered["status"], "failed")
            self.assertIn("restarted", recovered["error"])

    def test_empty_analysis_exports_keep_their_column_headers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data_path = root / "input.parquet"
            model_path = root / "model.joblib"
            make_source(data_path)
            make_bundle(model_path)
            service = InferenceService(data_path, model_path)
            store = AnalysisStore(root / "runs")
            request = {
                "customer_ids": [101],
                "start_date": "2019-01-01",
                "end_date": "2019-01-01",
                "h3_resolution": 8,
                "spatial_radius_km": 5.0,
                "maximum_start_time_difference_minutes": 30,
                "minimum_temporal_overlap": 0.25,
                "maximum_interval_gap_minutes": 60,
            }
            manifest = store.create(request)
            store.run(service, manifest["analysis_id"], request)

            completed = store.get(manifest["analysis_id"])
            self.assertEqual(completed["status"], "completed")
            events_path = store.result_file(manifest["analysis_id"], "events.csv")
            windows_path = store.result_file(
                manifest["analysis_id"], "anomaly_windows.csv"
            )
            self.assertEqual(list(pd.read_csv(events_path).columns), EVENT_SUMMARY_COLUMNS)
            self.assertEqual(list(pd.read_csv(windows_path).columns), ANOMALY_COLUMNS)

    def test_workload_estimate_clips_to_source_edges(self) -> None:
        rows = estimate_workload_rows(
            customer_count=10,
            start_date=pd.Timestamp("2019-01-01").date(),
            end_date=pd.Timestamp("2019-01-01").date(),
            source_start=pd.Timestamp("2019-01-01").date(),
            source_end=pd.Timestamp("2019-01-01").date(),
        )
        self.assertEqual(rows, 10 * 24)

    def test_flask_api_runs_analysis_and_serves_allowlisted_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data_path = root / "input.parquet"
            model_path = root / "model.joblib"
            make_source(data_path)
            make_bundle(model_path)

            class AnomalyTestConfig(TestingConfig):
                ANOMALY_DATASET_PATH = data_path
                ANOMALY_MODEL_PATH = model_path
                ANOMALY_RUNS_PATH = root / "runs"

            client = create_app(AnomalyTestConfig).test_client()
            model = client.get("/api/v1/models/anomaly-prediction")
            self.assertEqual(model.status_code, 200)
            self.assertEqual(
                model.get_json()["data"]["modelId"], "anomaly-prediction"
            )
            locations = client.get(
                "/api/v1/models/anomaly-prediction/entities?offset=0&limit=10000"
            )
            self.assertEqual(locations.status_code, 200)
            self.assertEqual(locations.get_json()["data"]["items"][0]["OBJECTID"], 101)
            invalid_limit = client.get(
                "/api/v1/models/anomaly-prediction/entities?limit=10001"
            )
            self.assertEqual(invalid_limit.status_code, 422)
            response = client.post(
                "/api/v1/models/anomaly-prediction/predict",
                json={
                    "customer_ids": [101],
                    "start_date": "2019-01-03",
                    "end_date": "2019-01-03",
                },
            )
            self.assertEqual(response.status_code, 200)
            result = response.get_json()["data"]
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["events"][0]["event_scope"], "SINGLE_CUSTOMER")

            run_id = result["run_id"]
            runs = client.get("/api/v1/models/anomaly-prediction/runs")
            self.assertEqual(runs.status_code, 200)
            self.assertEqual(runs.get_json()["data"]["items"][0]["analysis_id"], run_id)
            for filename, content_type in (
                ("events.csv", "text/csv"),
                ("anomaly_records.csv", "text/csv"),
                ("spatial_temporal_events.csv", "text/csv"),
                ("geographic_clusters.csv", "text/csv"),
                ("analysis_result.json", "application/json"),
                ("events.geojson", "application/geo+json"),
                ("evaluation_metrics.json", "application/json"),
                ("event_localization_evaluation.json", "application/json"),
            ):
                artifact = client.get(
                    f"/api/v1/models/anomaly-prediction/runs/{run_id}/download/{filename}"
                )
                self.assertEqual(artifact.status_code, 200)
                self.assertTrue(artifact.content_type.startswith(content_type))
                if filename == "events.geojson":
                    feature_collection = artifact.get_json()
                    self.assertEqual(
                        feature_collection["features"][0]["geometry"]["type"],
                        "Point",
                    )
                    self.assertEqual(
                        feature_collection["features"][0]["geometry"]["coordinates"],
                        [-118.0, 34.0],
                    )

            invalid = client.post(
                "/api/v1/models/anomaly-prediction/predict",
                json={"start_date": "bad-date", "end_date": "2019-01-03"},
            )
            self.assertEqual(invalid.status_code, 422)


if __name__ == "__main__":
    unittest.main()
