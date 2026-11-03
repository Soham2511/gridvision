import sys
import tempfile
import unittest
from pathlib import Path

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

from gridvision_event_localization import (  # noqa: E402
    EventLocalizationConfig,
    assign_spatial_cells,
    classify_event_scope,
    evaluate_events,
    form_events,
    generate_event_summary,
    prepare_anomaly_records,
    spatial_clustering,
    temporal_correlation,
    visualize_events,
)


def anomaly_frame() -> pd.DataFrame:
    start = pd.Timestamp("2020-01-01 10:00")
    rows = [
        # A nearby local group.
        ("A", "zero_block", start, start + pd.Timedelta(hours=2), 34.000, -118.000, 0.9),
        ("B", "drop", start + pd.Timedelta(minutes=10), start + pd.Timedelta(hours=2), 34.005, -118.004, 0.8),
        # A separate, simultaneous geographic cluster.
        ("C", "spike", start + pd.Timedelta(minutes=15), start + pd.Timedelta(hours=2), 34.200, -118.200, 0.95),
        ("D", "flatline", start + pd.Timedelta(minutes=20), start + pd.Timedelta(hours=2), 34.204, -118.197, 0.7),
        # A separate singleton in a later temporal episode.
        ("E", "spike", start + pd.Timedelta(hours=5), start + pd.Timedelta(hours=6), 34.400, -118.400, 0.6),
    ]
    return pd.DataFrame(
        rows,
        columns=[
            "customer_id",
            "anomaly_type",
            "anomaly_start",
            "anomaly_end",
            "latitude",
            "longitude",
            "anomaly_score",
        ],
    )


class EventLocalizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = EventLocalizationConfig(
            h3_resolution=8,
            spatial_radius_km=2,
            dbscan_min_customers=2,
            maximum_start_time_difference=pd.Timedelta(minutes=30),
            minimum_temporal_overlap=0.25,
            maximum_interval_gap=pd.Timedelta(minutes=30),
        )

    def test_prepare_and_assign_h3_without_ground_truth_columns(self) -> None:
        raw = anomaly_frame().rename(
            columns={
                "customer_id": "OBJECTID",
                "anomaly_start": "start_time",
                "anomaly_end": "end_time",
            }
        )
        raw["anomaly_event_id"] = "LEAKAGE_ONLY"
        records = prepare_anomaly_records(raw)
        self.assertEqual(len(records), 5)
        self.assertEqual(records.loc[0, "customer_id"], "A")
        self.assertEqual(records.loc[0, "severity"], records.loc[0, "anomaly_score"])
        with_cells = assign_spatial_cells(records, h3_resolution=8)
        self.assertTrue(with_cells["h3_cell"].str.len().gt(0).all())
        self.assertNotIn("anomaly_event_id", with_cells.columns)

    def test_temporal_rules_cover_start_overlap_gap_and_separation(self) -> None:
        base = pd.Timestamp("2020-01-01 10:00")
        first = {
            "anomaly_start": base,
            "anomaly_end": base + pd.Timedelta(hours=1),
        }
        close_start = {
            "anomaly_start": base + pd.Timedelta(minutes=20),
            "anomaly_end": base + pd.Timedelta(hours=2),
        }
        overlap = {
            "anomaly_start": base + pd.Timedelta(minutes=40),
            "anomaly_end": base + pd.Timedelta(hours=2),
        }
        close_gap = {
            "anomaly_start": base + pd.Timedelta(hours=1, minutes=20),
            "anomaly_end": base + pd.Timedelta(hours=2),
        }
        distant = {
            "anomaly_start": base + pd.Timedelta(hours=4),
            "anomaly_end": base + pd.Timedelta(hours=5),
        }
        self.assertTrue(temporal_correlation(first, close_start, self.config))
        self.assertTrue(temporal_correlation(first, overlap, self.config))
        self.assertTrue(temporal_correlation(first, close_gap, self.config))
        self.assertFalse(temporal_correlation(first, distant, self.config))

    def test_event_formation_uses_both_geography_and_time_for_scope(self) -> None:
        records, _ = form_events(anomaly_frame(), self.config)
        summary = generate_event_summary(
            records, population_customer_count=10, config=self.config
        )
        scope_by_customers = {
            tuple(row.customer_ids): row.event_scope
            for row in summary.itertuples(index=False)
        }
        self.assertEqual(scope_by_customers[("A", "B", "C", "D")], "MULTI_AREA")
        self.assertEqual(scope_by_customers[("E",)], "SINGLE_CUSTOMER")
        multi_area = summary.loc[
            summary["event_scope"] == "MULTI_AREA"
        ].iloc[0]
        clusters = multi_area["spatial_clusters"]
        self.assertEqual(len(clusters), 2)
        self.assertEqual(
            {tuple(cluster["customer_ids"]) for cluster in clusters},
            {("A", "B"), ("C", "D")},
        )
        self.assertTrue(all(cluster["spatial_extent_km"] > 0 for cluster in clusters))
        nearby_records, _ = form_events(anomaly_frame().iloc[[0, 1]], self.config)
        nearby_summary = generate_event_summary(
            nearby_records, config=self.config
        )
        self.assertEqual(nearby_summary.iloc[0]["event_scope"], "LOCAL_AREA")
        self.assertEqual(len(nearby_summary.iloc[0]["spatial_clusters"]), 1)
        self.assertEqual(classify_event_scope(10, 1), "LOCAL_AREA")
        self.assertEqual(classify_event_scope(100, 5), "MULTI_AREA")
        self.assertEqual(len(records["h3_cell"].unique()) > 1, True)

    def test_dbscan_noise_records_get_distinct_spatial_clusters(self) -> None:
        isolated = anomaly_frame().iloc[[0, 4]].copy()
        isolated.loc[isolated.index[1], "anomaly_start"] = isolated.iloc[0][
            "anomaly_start"
        ]
        isolated.loc[isolated.index[1], "anomaly_end"] = isolated.iloc[0][
            "anomaly_end"
        ]
        clustered = spatial_clustering(
            prepare_anomaly_records(isolated), self.config
        )
        self.assertEqual(clustered["spatial_cluster_id"].nunique(), 2)
        event_records, event_rows = form_events(isolated, self.config)
        self.assertEqual(len(event_rows), 2)
        summary = generate_event_summary(event_records, config=self.config)
        self.assertEqual(set(summary["event_scope"]), {"SINGLE_CUSTOMER"})

    def test_repeat_alerts_from_one_customer_do_not_meet_dbscan_density(self) -> None:
        repeated = pd.concat(
            [anomaly_frame().iloc[[0]], anomaly_frame().iloc[[0]]],
            ignore_index=True,
        )
        clustered = spatial_clustering(
            prepare_anomaly_records(repeated), self.config
        )
        self.assertEqual(clustered["spatial_cluster_id"].nunique(), 1)
        self.assertTrue(
            clustered["spatial_cluster_id"].iloc[0].startswith("SPATIAL_NOISE_")
        )

    def test_event_evaluation_and_visualizations(self) -> None:
        records, _ = form_events(anomaly_frame().iloc[[0, 1]], self.config)
        summary = generate_event_summary(records, config=self.config)
        truth = pd.DataFrame(
            {
                "event_id": ["truth-1", "truth-2"],
                "customer_id": ["A", "B"],
                "timestamp": [
                    pd.Timestamp("2020-01-01 10:00"),
                    pd.Timestamp("2020-01-01 10:10"),
                ],
                "end_time": [
                    pd.Timestamp("2020-01-01 12:00"),
                    pd.Timestamp("2020-01-01 12:00"),
                ],
            }
        )
        metrics = evaluate_events(summary, truth, self.config)
        self.assertEqual(metrics["matched_events"], 1)
        self.assertEqual(metrics["missed_events"], 1)
        with tempfile.TemporaryDirectory() as directory:
            outputs = visualize_events(records, summary, directory)
            self.assertEqual(len(outputs), 5)
            self.assertTrue(all(Path(path).is_file() for path in outputs.values()))


if __name__ == "__main__":
    unittest.main()
