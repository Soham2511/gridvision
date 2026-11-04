"""Historical Snapshot Builder for GridVision Residential Assistant.

Formats and validates pure analytics results into the compact, standardized JSON schema
contract for persistence and prompt integration.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services.assistant.historical.analytics_service import (
    DailyConsumptionRecord,
    HistoricalAnalyticsService,
)

SNAPSHOT_SCHEMA_VERSION = "1.0"
CALCULATION_VERSION = "1.0"


class HistoricalSnapshotBuilder:
    """Builds and validates the standardized historicalProfile JSON payload."""

    def __init__(self, analytics_service: HistoricalAnalyticsService | None = None) -> None:
        self.analytics = analytics_service or HistoricalAnalyticsService()

    def build_snapshot_from_records(
        self,
        meter_id: str,
        daily_records: list[DailyConsumptionRecord],
        total_observations_count: int,
        data_source: str = "customer_silver_hourly",
        source_data_version: str | None = None,
    ) -> dict[str, Any]:
        """Convert daily consumption records into the standardized historicalProfile structure."""
        coverage = self.analytics.calculate_coverage_metadata(
            daily_records=daily_records,
            total_observations_count=total_observations_count,
            data_source=data_source,
        )
        all_time = self.analytics.calculate_all_time_summary(daily_records)
        yearly = self.analytics.calculate_yearly_trends(daily_records)
        monthly = self.analytics.calculate_monthly_timeline(daily_records)
        seasonality = self.analytics.calculate_seasonality(daily_records)
        extremes = self.analytics.calculate_historical_extremes(monthly, yearly)
        behaviour = self.analytics.calculate_long_term_behaviour(
            daily_records=daily_records,
            monthly_timeline=monthly,
            yearly_trends=yearly,
        )

        generated_at = datetime.now(timezone.utc).isoformat()

        snapshot = {
            "historicalProfile": {
                "meterId": meter_id,
                "coverage": coverage,
                "allTimeSummary": {
                    "totalConsumptionKwh": all_time.get("totalConsumptionKwh"),
                    "averageDailyConsumptionKwh": all_time.get("averageDailyConsumptionKwh"),
                    "medianDailyConsumptionKwh": all_time.get("medianDailyConsumptionKwh"),
                    "p90DailyConsumptionKwh": all_time.get("p90DailyConsumptionKwh"),
                    "highestConsumptionDay": all_time.get("highestConsumptionDay"),
                    "lowestConsumptionDay": all_time.get("lowestConsumptionDay"),
                },
                "yearlyTrends": yearly,
                "monthlyTimeline": monthly,
                "seasonality": seasonality,
                "historicalExtremes": extremes,
                "longTermBehaviour": behaviour,
                "snapshotMetadata": {
                    "generatedAt": generated_at,
                    "schemaVersion": SNAPSHOT_SCHEMA_VERSION,
                    "calculationVersion": CALCULATION_VERSION,
                    "sourceDataVersion": source_data_version or "latest",
                },
            }
        }

        self.validate_snapshot(snapshot)
        return snapshot

    @staticmethod
    def validate_snapshot(snapshot: dict[str, Any]) -> bool:
        """Validate that a snapshot conforms to the required schema contract."""
        if not isinstance(snapshot, dict) or "historicalProfile" not in snapshot:
            raise ValueError("Snapshot must contain 'historicalProfile' top-level key.")

        profile = snapshot["historicalProfile"]
        required_sections = [
            "coverage",
            "allTimeSummary",
            "yearlyTrends",
            "monthlyTimeline",
            "seasonality",
            "historicalExtremes",
            "longTermBehaviour",
            "snapshotMetadata",
        ]

        for sec in required_sections:
            if sec not in profile:
                raise ValueError(f"Snapshot profile missing required section: '{sec}'")

        meta = profile["snapshotMetadata"]
        if meta.get("schemaVersion") != SNAPSHOT_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported schemaVersion '{meta.get('schemaVersion')}'; expected '{SNAPSHOT_SCHEMA_VERSION}'"
            )

        return True
