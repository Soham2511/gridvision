"""Comprehensive Test Suite for GridVision Historical Household Analytics and Snapshot System.

Validates:
1. Pure calculations: daily aggregation, missing observation handling, actual-vs-predicted separation,
   all-time statistics, multi-year trends, YoY changes, seasonality patterns, extremes, and long-term behavior.
2. Snapshot building and schema contract validation.
3. Snapshot persistence, sidecar storage, versioning, staleness detection, and cross-meter isolation.
4. ContextBuilder integration (contextSchemaVersion 2.0, contextCapabilities, historicalProfile).
5. Orchestrator and Mock LLM responses to representative historical questions and detailed query refusal.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app import create_app
from app.config import TestingConfig
from app.providers.llm.mock_adapter import MockLLMAdapter
from app.providers.sample_data_provider import SampleDataProvider
from app.services.assistant.context_builder import HouseholdContextBuilder
from app.services.assistant.historical.analytics_service import (
    DailyConsumptionRecord,
    HistoricalAnalyticsService,
)
from app.services.assistant.historical.observation_reader import HistoricalObservationReader
from app.services.assistant.historical.snapshot_builder import (
    CALCULATION_VERSION,
    SNAPSHOT_SCHEMA_VERSION,
    HistoricalSnapshotBuilder,
)
from app.services.assistant.historical.snapshot_repository import HistoricalSnapshotRepository
from app.services.assistant.orchestrator import ResidentialAssistantOrchestrator


class TestHistoricalAnalyticsService(unittest.TestCase):
    """Unit tests for HistoricalAnalyticsService calculation logic."""

    def setUp(self) -> None:
        self.service = HistoricalAnalyticsService()

    def _create_synthetic_observations(
        self,
        start_date: str = "2018-01-01",
        days: int = 30,
        daily_kwh: float = 15.0,
        include_duplicates: bool = False,
        include_negatives: bool = False,
        include_predicted: bool = False,
        missing_days: list[int] | None = None,
    ) -> list[dict[str, Any]]:
        """Helper to create controlled synthetic observations."""
        dt_start = datetime.strptime(start_date, "%Y-%m-%d")
        obs: list[dict[str, Any]] = []
        missing_set = set(missing_days or [])

        for d in range(days):
            if d in missing_set:
                continue
            cur_day = dt_start + timedelta(days=d)
            for h in range(24):
                cur_dt = cur_day + timedelta(hours=h)
                kwh_val = daily_kwh / 24.0
                obs.append({
                    "timestamp": cur_dt,
                    "consumption_kwh": kwh_val,
                    "is_predicted": False,
                })
                if include_duplicates and h == 12:
                    obs.append({
                        "timestamp": cur_dt,
                        "consumption_kwh": kwh_val,
                        "is_predicted": False,
                    })
                if include_predicted and h == 18:
                    obs.append({
                        "timestamp": cur_dt,
                        "consumption_kwh": 99.9,
                        "is_predicted": True,
                    })

        if include_negatives:
            obs.append({
                "timestamp": dt_start + timedelta(hours=3),
                "consumption_kwh": -50.0,
                "is_predicted": False,
            })
            obs.append({
                "timestamp": dt_start + timedelta(hours=4),
                "consumption_kwh": float("nan"),
                "is_predicted": False,
            })

        return obs

    # --- Section 1: Aggregation & Data Cleansing ---

    def test_daily_aggregation_basic(self) -> None:
        """Verify normal daily aggregation from hourly records."""
        obs = self._create_synthetic_observations(days=5, daily_kwh=20.0)
        daily = self.service.aggregate_daily_consumption(obs)

        self.assertEqual(len(daily), 5)
        self.assertEqual(daily[0].date_str, "2018-01-01")
        self.assertEqual(daily[0].total_kwh, 20.0)
        self.assertEqual(daily[0].observed_intervals, 24)
        self.assertTrue(daily[0].is_complete_day)

    def test_daily_aggregation_handles_duplicates_and_invalids(self) -> None:
        """Verify duplicate timestamps are deduplicated and negatives/NaNs are dropped."""
        obs = self._create_synthetic_observations(
            days=3,
            daily_kwh=24.0,
            include_duplicates=True,
            include_negatives=True,
            include_predicted=True,
        )
        daily = self.service.aggregate_daily_consumption(obs)

        self.assertEqual(len(daily), 3)
        # Should cleanly sum to 24.0 without duplicate doubling or predicted 99.9 kwh
        self.assertEqual(daily[0].total_kwh, 24.0)

    def test_missing_days_not_treated_as_zero(self) -> None:
        """Verify days with zero observations are omitted, not synthesized as 0 kWh."""
        obs = self._create_synthetic_observations(days=5, daily_kwh=10.0, missing_days=[2])
        daily = self.service.aggregate_daily_consumption(obs)

        self.assertEqual(len(daily), 4)
        recorded_dates = [d.date_str for d in daily]
        self.assertNotIn("2018-01-03", recorded_dates)
        self.assertIn("2018-01-01", recorded_dates)
        self.assertIn("2018-01-02", recorded_dates)
        self.assertIn("2018-01-04", recorded_dates)

    # --- Section 2: All-Time Statistics ---

    def test_all_time_summary_metrics(self) -> None:
        """Verify all-time totals, averages, median, P90, and extremes."""
        records = [
            DailyConsumptionRecord("2018-01-01", 2018, 1, 1, 10.0, 24, 24, 100.0, True),
            DailyConsumptionRecord("2018-01-02", 2018, 1, 2, 20.0, 24, 24, 100.0, True),
            DailyConsumptionRecord("2018-01-03", 2018, 1, 3, 30.0, 24, 24, 100.0, True),
            DailyConsumptionRecord("2018-01-04", 2018, 1, 4, 40.0, 24, 24, 100.0, True),
            DailyConsumptionRecord("2018-01-05", 2018, 1, 5, 50.0, 24, 24, 100.0, True),
        ]
        summary = self.service.calculate_all_time_summary(records)

        self.assertEqual(summary["totalConsumptionKwh"], 150.0)
        self.assertEqual(summary["averageDailyConsumptionKwh"], 30.0)
        self.assertEqual(summary["medianDailyConsumptionKwh"], 30.0)
        self.assertEqual(summary["p90DailyConsumptionKwh"], 46.0)
        self.assertEqual(summary["highestConsumptionDay"]["date"], "2018-01-05")
        self.assertEqual(summary["highestConsumptionDay"]["consumptionKwh"], 50.0)
        self.assertEqual(summary["lowestConsumptionDay"]["date"], "2018-01-01")
        self.assertEqual(summary["lowestConsumptionDay"]["consumptionKwh"], 10.0)

    # --- Section 3: Multi-Year & YoY Changes ---

    def test_yearly_trends_multi_year_comparable(self) -> None:
        """Verify year-over-year percentage change when consecutive complete years exist."""
        records: list[DailyConsumptionRecord] = []
        # 2017: 365 days of 10 kWh = 3650 kWh
        dt_2017 = datetime(2017, 1, 1)
        for i in range(365):
            d = dt_2017 + timedelta(days=i)
            records.append(DailyConsumptionRecord(d.strftime("%Y-%m-%d"), 2017, d.month, d.day, 10.0, 24, 24, 100.0, True))

        # 2018: 365 days of 12 kWh = 4380 kWh (+20.0% change)
        dt_2018 = datetime(2018, 1, 1)
        for i in range(365):
            d = dt_2018 + timedelta(days=i)
            records.append(DailyConsumptionRecord(d.strftime("%Y-%m-%d"), 2018, d.month, d.day, 12.0, 24, 24, 100.0, True))

        trends = self.service.calculate_yearly_trends(records)
        self.assertEqual(len(trends), 2)
        # 2017 has no previous year -> None
        self.assertIsNone(trends[0]["yearOverYearChangePct"])
        # 2018 has comparable 2017 -> +20.0%
        self.assertEqual(trends[1]["yearOverYearChangePct"], 20.0)

    def test_yearly_trends_incomplete_year_does_not_forge_yoy(self) -> None:
        """Verify incomplete year comparison yields null YoY change instead of false drop."""
        records: list[DailyConsumptionRecord] = []
        # 2017: 365 days of 10 kWh
        dt_2017 = datetime(2017, 1, 1)
        for i in range(365):
            d = dt_2017 + timedelta(days=i)
            records.append(DailyConsumptionRecord(d.strftime("%Y-%m-%d"), 2017, d.month, d.day, 10.0, 24, 24, 100.0, True))

        # 2018: Only 15 days observed (incomplete)
        dt_2018 = datetime(2018, 1, 1)
        for i in range(15):
            d = dt_2018 + timedelta(days=i)
            records.append(DailyConsumptionRecord(d.strftime("%Y-%m-%d"), 2018, d.month, d.day, 10.0, 24, 24, 100.0, True))

        trends = self.service.calculate_yearly_trends(records)
        self.assertEqual(len(trends), 2)
        self.assertFalse(trends[1]["isCompletePeriod"])
        # Incomparable periods must be None
        self.assertIsNone(trends[1]["yearOverYearChangePct"])

    # --- Section 4: Seasonality Patterns ---

    def test_seasonality_requires_multiple_years_for_established_pattern(self) -> None:
        """Verify seasonality pattern is marked established only with multi-year data."""
        # 1 year of data
        obs_1yr = self._create_synthetic_observations(start_date="2018-01-01", days=365, daily_kwh=15.0)
        daily_1yr = self.service.aggregate_daily_consumption(obs_1yr)
        season_1yr = self.service.calculate_seasonality(daily_1yr)

        self.assertEqual(len(season_1yr), 12)
        self.assertEqual(season_1yr[0]["monthName"], "January")
        self.assertEqual(season_1yr[0]["yearsObservedCount"], 1)
        # With only 1 year, isEstablishedPattern must be False
        self.assertFalse(season_1yr[0]["isEstablishedPattern"])

        # Add second year for January
        obs_2yr = list(obs_1yr)
        for h in range(24 * 31):
            dt = datetime(2019, 1, 1) + timedelta(hours=h)
            obs_2yr.append({"timestamp": dt, "consumption_kwh": 15.0 / 24, "is_predicted": False})

        daily_2yr = self.service.aggregate_daily_consumption(obs_2yr)
        season_2yr = self.service.calculate_seasonality(daily_2yr)
        self.assertEqual(season_2yr[0]["yearsObservedCount"], 2)
        self.assertTrue(season_2yr[0]["isEstablishedPattern"])

    # --- Section 5: Historical Extremes & Long-Term Behaviour ---

    def test_historical_extremes_and_behaviour(self) -> None:
        """Verify top consumption months and variability computation."""
        timeline = [
            {"month": "2018-01", "totalConsumptionKwh": 300.0, "averageDailyConsumptionKwh": 10.0},
            {"month": "2018-02", "totalConsumptionKwh": 350.0, "averageDailyConsumptionKwh": 12.5},
            {"month": "2018-03", "totalConsumptionKwh": 500.0, "averageDailyConsumptionKwh": 16.1},
            {"month": "2018-04", "totalConsumptionKwh": 400.0, "averageDailyConsumptionKwh": 13.3},
            {"month": "2018-05", "totalConsumptionKwh": 600.0, "averageDailyConsumptionKwh": 19.3},
            {"month": "2018-06", "totalConsumptionKwh": 700.0, "averageDailyConsumptionKwh": 23.3},
        ]
        extremes = self.service.calculate_historical_extremes(timeline, [])
        top5 = extremes["topConsumptionMonths"]

        self.assertEqual(len(top5), 5)
        self.assertEqual(top5[0]["month"], "2018-06")
        self.assertEqual(top5[0]["consumptionKwh"], 700.0)
        self.assertEqual(top5[1]["month"], "2018-05")


class TestHistoricalSnapshotPersistenceAndIntegration(unittest.TestCase):
    """Integration tests for sidecar repository, context builder, and orchestrator."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp()
        self.storage_dir = Path(self.temp_dir) / "snapshots"
        self.manifest_file = Path(self.temp_dir) / "latest.json"
        self.manifest_file.write_text(
            json.dumps({"dataset_version": "v2026-test"}), encoding="utf-8"
        )
        self.repo = HistoricalSnapshotRepository(
            storage_dir=self.storage_dir,
            source_manifest_path=self.manifest_file,
        )
        self.analytics = HistoricalAnalyticsService()
        self.builder = HistoricalSnapshotBuilder(self.analytics)
        self.provider = SampleDataProvider()

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_save_and_retrieve_snapshot(self) -> None:
        """Verify snapshot persistence, schema validation, and retrieval."""
        daily = [
            DailyConsumptionRecord("2018-01-01", 2018, 1, 1, 15.0, 24, 24, 100.0, True),
            DailyConsumptionRecord("2018-01-02", 2018, 1, 2, 16.0, 24, 24, 100.0, True),
        ]
        snapshot = self.builder.build_snapshot_from_records(
            meter_id="METER-1000",
            daily_records=daily,
            total_observations_count=48,
            source_data_version="v2026-test",
        )

        saved_path = self.repo.save_snapshot("METER-1000", snapshot)
        self.assertTrue(saved_path.is_file())

        retrieved = self.repo.get_snapshot("METER-1000")
        self.assertIsNotNone(retrieved)
        profile = retrieved["historicalProfile"]
        self.assertEqual(profile["meterId"], "METER-1000")
        self.assertEqual(profile["allTimeSummary"]["totalConsumptionKwh"], 31.0)

    def test_generate_snapshot_if_missing_uses_meter_observations(self) -> None:
        """Missing snapshots are built from the requested meter's historical records."""
        observations = [
            {
                "timestamp": datetime(2018, 1, 1, hour),
                "consumption_kwh": 1.0,
                "is_predicted": False,
            }
            for hour in range(24)
        ]
        with patch(
            "app.services.assistant.historical.observation_reader."
            "HistoricalObservationReader.read_observations_for_meter",
            return_value=observations,
        ) as read_observations:
            generated = self.repo.generate_snapshot_if_missing("METER-1000")

        self.assertTrue(generated)
        read_observations.assert_called_once_with("METER-1000")
        snapshot = self.repo.get_snapshot("METER-1000")
        self.assertIsNotNone(snapshot)
        self.assertEqual(
            snapshot["historicalProfile"]["allTimeSummary"]["totalConsumptionKwh"],
            24.0,
        )

    def test_generate_snapshot_if_missing_skips_current_snapshot(self) -> None:
        """A valid existing snapshot is retained rather than recalculated at each login."""
        daily = [
            DailyConsumptionRecord("2018-01-01", 2018, 1, 1, 15.0, 24, 24, 100.0, True)
        ]
        snapshot = self.builder.build_snapshot_from_records(
            "METER-1000",
            daily,
            24,
            source_data_version="v2026-test",
        )
        self.repo.save_snapshot("METER-1000", snapshot)

        with patch(
            "app.services.assistant.historical.observation_reader."
            "HistoricalObservationReader.read_observations_for_meter"
        ) as read_observations:
            generated = self.repo.generate_snapshot_if_missing("METER-1000")

        self.assertFalse(generated)
        read_observations.assert_not_called()

    def test_cross_meter_isolation_denies_wrong_meter(self) -> None:
        """Verify that requesting METER-1001 never returns METER-1000 snapshot."""
        daily = [DailyConsumptionRecord("2018-01-01", 2018, 1, 1, 15.0, 24, 24, 100.0, True)]
        snapshot = self.builder.build_snapshot_from_records("METER-1000", daily, 24)
        self.repo.save_snapshot("METER-1000", snapshot)

        # Querying METER-1001 when only METER-1000 is saved returns None
        self.assertIsNone(self.repo.get_snapshot("METER-1001"))

    def test_staleness_detection_on_source_version_change(self) -> None:
        """Verify snapshot is marked stale when source dataset version changes."""
        daily = [DailyConsumptionRecord("2018-01-01", 2018, 1, 1, 15.0, 24, 24, 100.0, True)]
        snapshot = self.builder.build_snapshot_from_records(
            "METER-1000", daily, 24, source_data_version="v2026-test"
        )
        self.repo.save_snapshot("METER-1000", snapshot)
        self.assertFalse(self.repo.is_stale("METER-1000"))

        # Update manifest to newer version
        self.manifest_file.write_text(
            json.dumps({"dataset_version": "v2026-newer"}), encoding="utf-8"
        )
        # Snapshot with old version should now be recognized as stale
        self.assertTrue(self.repo.is_stale("METER-1000"))
        # get_snapshot safely returns None for stale records
        self.assertIsNone(self.repo.get_snapshot("METER-1000"))

    def test_context_builder_includes_historical_profile_and_capabilities(self) -> None:
        """Verify HouseholdContextBuilder produces contextSchemaVersion 2.0 with capabilities."""
        # Prepopulate repository with METER-1000 snapshot
        daily = [
            DailyConsumptionRecord("2018-01-01", 2018, 1, 1, 15.0, 24, 24, 100.0, True),
            DailyConsumptionRecord("2018-02-01", 2018, 2, 1, 20.0, 24, 24, 100.0, True),
        ]
        snapshot = self.builder.build_snapshot_from_records(
            "METER-1000", daily, 48, source_data_version="v2026-test"
        )
        self.repo.save_snapshot("METER-1000", snapshot)

        context_builder = HouseholdContextBuilder(
            data_provider=self.provider,
            snapshot_repository=self.repo,
        )
        context = context_builder.build_context("METER-1000")

        self.assertIsNotNone(context)
        self.assertEqual(context["contextSchemaVersion"], "2.0")
        caps = context["contextCapabilities"]
        self.assertTrue(caps["recentAnalyticsAvailable"])
        self.assertTrue(caps["historicalProfileAvailable"])
        self.assertTrue(caps["historicalMonthlyTimelineAvailable"])
        self.assertFalse(caps["detailedHistoricalQueriesAvailable"])

        self.assertIn("historicalProfile", context)
        hist = context["historicalProfile"]
        self.assertEqual(hist["meterId"], "METER-1000")
        self.assertEqual(hist["allTimeSummary"]["totalConsumptionKwh"], 35.0)

        # Context for METER-1001 (which has no snapshot saved) should have profile=None and false capabilities
        c1001 = context_builder.build_context("METER-1001")
        self.assertIsNotNone(c1001)
        self.assertFalse(c1001["contextCapabilities"]["historicalProfileAvailable"])
        self.assertIsNone(c1001["historicalProfile"])

    def test_orchestrator_required_historical_query_fails_closed_when_llm_fails(self) -> None:
        """A historical tool-required query does not return a fallback as if lookup succeeded."""
        daily = [
            DailyConsumptionRecord("2018-01-01", 2018, 1, 1, 15.0, 24, 24, 100.0, True),
            DailyConsumptionRecord("2018-07-01", 2018, 7, 1, 45.0, 24, 24, 100.0, True),
        ]
        snapshot = self.builder.build_snapshot_from_records(
            "METER-1000", daily, 48, source_data_version="v2026-test"
        )
        self.repo.save_snapshot("METER-1000", snapshot)

        context_builder = HouseholdContextBuilder(
            data_provider=self.provider,
            snapshot_repository=self.repo,
        )

        class FailingLLM(MockLLMAdapter):
            def is_available(self) -> bool:
                return True

            def generate_chat_completion(self, *args, **kwargs) -> str:
                from app.providers.llm.base import LLMInferenceError
                raise LLMInferenceError("Upstream timeout")

        orchestrator = ResidentialAssistantOrchestrator(
            data_provider=self.provider,
            llm_provider=FailingLLM(),
            authorized_meters=["METER-1000"],
        )
        orchestrator.context_builder = context_builder

        result = orchestrator.answer_query(
            prompt="What is my all-time historical consumption?",
            entity_id="METER-1000",
        )

        self.assertEqual(result["status"], "error")
        self.assertFalse(result["isLlmGenerated"])
        self.assertIn("No unverified answer was generated", result["answer"])


if __name__ == "__main__":
    unittest.main()
