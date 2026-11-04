from datetime import date

import pandas as pd

from app.services.customer_silver_history_service import CustomerSilverHistoryService


def test_silver_cohort_history_filters_window_and_aggregates_by_day(tmp_path):
    path = tmp_path / "customer_silver.parquet"
    pd.DataFrame(
        [
            {"OBJECTID": 1, "timestamp": "2026-10-01T01:00:00", "normalized_building_energy_kwh": 1.25},
            {"OBJECTID": 2, "timestamp": "2026-10-01T02:00:00", "normalized_building_energy_kwh": 2.75},
            {"OBJECTID": 1, "timestamp": "2026-10-02T01:00:00", "normalized_building_energy_kwh": 4.0},
            {"OBJECTID": 1, "timestamp": "2026-11-01T01:00:00", "normalized_building_energy_kwh": 100.0},
        ]
    ).to_parquet(path, index=False)

    result = CustomerSilverHistoryService(path).get_cohort_history(date(2026, 10, 1), date(2026, 10, 31))

    assert result["totalConsumptionKwh"] == 8.0
    assert result["householdCount"] == 2
    assert result["daysReturned"] == 2
    assert result["sourceCoverage"] == {"start": "2026-10-01", "end": "2026-11-01"}
    assert result["dailyConsumption"] == [
        {"date": "2026-10-01", "totalConsumptionKwh": 4.0, "householdCount": 2},
        {"date": "2026-10-02", "totalConsumptionKwh": 4.0, "householdCount": 1},
    ]


def test_silver_service_selects_month_of_latest_source_date(tmp_path):
    path = tmp_path / "customer_silver.parquet"
    pd.DataFrame(
        [
            {"OBJECTID": 1, "timestamp": "2018-11-30T23:00:00", "normalized_building_energy_kwh": 2.0},
            {"OBJECTID": 1, "timestamp": "2018-12-01T01:00:00", "normalized_building_energy_kwh": 3.0},
            {"OBJECTID": 1, "timestamp": "2018-12-31T23:00:00", "normalized_building_energy_kwh": 4.0},
        ]
    ).to_parquet(path, index=False)

    result = CustomerSilverHistoryService(path).get_latest_available_month()

    assert result["period"] == {"start": "2018-12-01", "end": "2018-12-31"}
    assert result["daysReturned"] == 2
    assert result["totalConsumptionKwh"] == 7.0
    assert result["sourceCoverage"]["end"] == "2018-12-31"


def test_silver_service_selects_month_of_latest_source_date(tmp_path):
    path = tmp_path / "customer_silver.parquet"
    pd.DataFrame(
        [
            {"OBJECTID": 1, "timestamp": "2018-11-30T23:00:00", "normalized_building_energy_kwh": 2.0},
            {"OBJECTID": 1, "timestamp": "2018-12-01T01:00:00", "normalized_building_energy_kwh": 3.0},
            {"OBJECTID": 1, "timestamp": "2018-12-31T23:00:00", "normalized_building_energy_kwh": 4.0},
        ]
    ).to_parquet(path, index=False)

    result = CustomerSilverHistoryService(path).get_latest_available_month()

    assert result["period"] == {"start": "2018-12-01", "end": "2018-12-31"}
    assert result["daysReturned"] == 2
    assert result["totalConsumptionKwh"] == 7.0
    assert result["sourceCoverage"]["end"] == "2018-12-31"
