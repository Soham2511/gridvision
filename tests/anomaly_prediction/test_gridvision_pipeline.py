import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

RUNTIME_PATH = (
    Path(__file__).resolve().parents[2]
    / "backend"
    / "app"
    / "models"
    / "anomaly_prediction"
    / "runtime"
)
sys.path.insert(0, str(RUNTIME_PATH))

from gridvision_pipeline import (  # noqa: E402
    ANOMALY_TYPES,
    CUSTOMER,
    ENERGY,
    LATITUDE,
    LONGITUDE,
    TIMESTAMP,
    add_causal_features,
    _event_features,
    classify_anomaly_type,
    learn_rule_thresholds,
    generate_synthetic_events,
    GridVisionExperiment,
    PipelineConfig,
)


def make_hourly_data(customers: int = 8, hours: int = 600) -> pd.DataFrame:
    rows = []
    for customer in range(customers):
        for hour in range(hours):
            timestamp = pd.Timestamp("2019-01-01") + pd.Timedelta(hours=hour)
            energy = 1.0 + 0.2 * np.sin(hour * 2 * np.pi / 24) + customer * 0.01
            rows.append(
                {
                    CUSTOMER: customer,
                    TIMESTAMP: timestamp,
                    ENERGY: energy,
                    LATITUDE: 34.0 + customer * 0.01,
                    LONGITUDE: -118.0,
                }
            )
    return pd.DataFrame(rows)


class AlwaysAnomalousDetector:
    def predict_proba(self, features: np.ndarray) -> np.ndarray:
        return np.tile([0.01, 0.99], (len(features), 1))


class GridVisionPipelineTests(unittest.TestCase):
    def test_features_do_not_use_future_readings(self) -> None:
        original = make_hourly_data()
        changed = original.copy()
        changed.loc[
            (changed[CUSTOMER] == 3)
            & (changed[TIMESTAMP] == pd.Timestamp("2019-01-16 00:00:00")),
            ENERGY,
        ] = 1000.0

        original_features = add_causal_features(original)
        changed_features = add_causal_features(changed)
        before_change = original_features[TIMESTAMP] < pd.Timestamp(
            "2019-01-16 00:00:00"
        )
        columns = [
            "log_residual",
            "relative_deviation",
            "lag1_delta",
            "lag24_delta",
            "fft_spectral_energy",
            "wavelet_energy_s1",
        ]
        np.testing.assert_allclose(
            original_features.loc[before_change, columns].to_numpy(),
            changed_features.loc[before_change, columns].to_numpy(),
        )

    def test_synthetic_events_are_balanced_and_do_not_mutate_source(self) -> None:
        source = make_hourly_data()
        original = source.copy(deep=True)
        injected, events, counts = generate_synthetic_events(
            source,
            pd.Timestamp("2019-01-10"),
            pd.Timestamp("2019-01-25"),
            events_per_class=5,
            seed=42,
        )

        pd.testing.assert_frame_equal(source, original)
        self.assertEqual(len(events), 5 * len(ANOMALY_TYPES))
        self.assertEqual(set(counts), set(ANOMALY_TYPES))
        self.assertEqual(int(injected["injected_anomaly"].sum()), 5 * 21)
        self.assertEqual(set(events["anomaly_type"]), set(ANOMALY_TYPES))

    def test_wavelet_fft_features_and_rule_based_event_types(self) -> None:
        varying_pre_event = np.tile([0.5, 1.5], 12)
        thresholds = {
            "spike_relative_deviation": 2.0,
            "drop_relative_deviation": -0.8,
            "zero_block_minimum_hours": 3.0,
            "flatline_minimum_hours": 6.0,
            "flatline_minimum_pre_event_cv": 0.05,
            "flatline_minimum_level_deviation": 0.01,
        }
        cases = {
            "spike": np.r_[np.ones(12), 10.0, np.ones(12)],
            "drop": np.r_[np.ones(10), np.full(6, 0.01), np.ones(9)],
            "zero_block": np.r_[np.ones(10), np.zeros(5), np.ones(10)],
            "flatline": np.r_[np.ones(10), np.full(8, 0.8), np.ones(7)],
        }
        for expected_type, window in cases.items():
            with self.subTest(anomaly_type=expected_type):
                feature_row = _event_features(
                    window,
                    varying_pre_event,
                    pd.Timestamp("2019-01-01 12:00:00"),
                )
                self.assertEqual(
                    classify_anomaly_type(feature_row, thresholds), expected_type
                )
                self.assertIn("spectral_entropy", feature_row)
                self.assertIn("wavelet_energy_ratio_4", feature_row)
                self.assertTrue(np.isfinite(list(feature_row.values())).all())

    def test_rule_cutoffs_come_from_training_normal_features(self) -> None:
        data = make_hourly_data(customers=3, hours=96)
        features = add_causal_features(data)
        thresholds = learn_rule_thresholds(features, PipelineConfig())
        self.assertAlmostEqual(
            thresholds["spike_relative_deviation"],
            features["relative_deviation"].quantile(0.999),
        )
        self.assertAlmostEqual(
            thresholds["drop_relative_deviation"],
            features["relative_deviation"].quantile(0.001),
        )

    def test_experiment_localizes_existing_event_windows(self) -> None:
        raw = make_hourly_data(customers=2, hours=72)
        raw.loc[raw[CUSTOMER] == 1, LATITUDE] = 34.005
        raw.loc[raw[CUSTOMER] == 1, LONGITUDE] = -118.004
        thresholds = {
            "spike_relative_deviation": 2.0,
            "drop_relative_deviation": -0.8,
            "zero_block_minimum_hours": 3.0,
            "flatline_minimum_hours": 6.0,
            "flatline_minimum_pre_event_cv": 0.05,
            "flatline_minimum_level_deviation": 0.01,
        }
        with tempfile.TemporaryDirectory() as output_directory:
            experiment = GridVisionExperiment(
                PipelineConfig(report_dir=output_directory)
            )
            experiment.detector = AlwaysAnomalousDetector()
            experiment.threshold = 0.5
            experiment.rule_thresholds = thresholds
            experiment.test_history = raw.copy()
            experiment.test_injected_data = raw.copy()
            experiment.scored_test_points = pd.DataFrame()
            experiment.customer_splits = {"test": [0, 1]}
            experiment.test_ground_truth_events = pd.DataFrame(
                {
                    "event_id": ["ground-truth-1"],
                    CUSTOMER: [0],
                    TIMESTAMP: [raw[TIMESTAMP].min()],
                    "end_time": [raw[TIMESTAMP].min() + pd.Timedelta(hours=72)],
                }
            )

            events = experiment.localize()

        self.assertEqual(len(experiment.predicted_anomaly_windows), 2)
        self.assertEqual(len(experiment.localized_records), 2)
        self.assertEqual(len(events), 1)
        self.assertEqual(events.iloc[0]["event_scope"], "LOCAL_AREA")
        self.assertIn("anomaly_type", experiment.localized_records.columns)
        self.assertIn("event_id", experiment.predicted_anomaly_windows.columns)
        self.assertNotIn("anomaly_event_id", experiment.localized_records.columns)


if __name__ == "__main__":
    unittest.main()
