"""Tests for Gold-backed commercial history and annual forecasts."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from app.providers.mlflow_adapter import MLflowModelAdapter
from app.providers.trained_forecast_provider import TrainedForecastProvider
from app.providers.sample_data_provider import SampleDataProvider
from app.services.dashboard_service import DashboardService
from training.commercial_forecast.features import FEATURE_COLUMNS


class ConstantCommercialModel:
    def __init__(self) -> None:
        self.call_count = 0

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        self.call_count += 1
        assert frame["forecast_horizon_hours"].tolist() == list(
            map(float, range(1, 25))
        )
        return np.full(len(frame), 1.5)


def _write_gold_fixture(path: Path, include_second_building: bool = False) -> None:
    timestamps = pd.date_range("2019-01-02", periods=48, freq="h")
    static_values = {
        "GeneralUseType": "Commercial",
        "SpecificUseType": "Office",
        "usetype": "Office",
        "building.type": "Office",
        "idf.kw": "100",
        "building.area.m2": 100.0,
        "FootprintArea.m2": 100.0,
        "EffectiveYearBuilt": 2000.0,
        "latitude": 40.0,
        "longitude": -70.0,
    }
    rows = []
    for timestamp in timestamps:
        origin = timestamp - pd.Timedelta(hours=1)
        row = {column: 0.0 for column in FEATURE_COLUMNS}
        row.update(static_values)
        row.update(
            {
                "forecast_horizon_hours": 1,
                "energy_at_origin": 10.0,
                "energy_rolling_mean_24h": 10.0,
                "energy_rolling_mean_7d": 10.0,
                "energy_rolling_mean_30d": 10.0,
                "energy_observation_count_24h": 24,
                "energy_observation_count_7d": 48,
                "energy_observation_count_30d": 48,
                "target_hour": timestamp.hour,
                "target_day_of_week": (timestamp.weekday() + 1) % 7,
                "target_month": timestamp.month,
                "target_is_weekend": int(timestamp.weekday() >= 5),
                "target_day_of_month": timestamp.day,
                "target_day_of_year": timestamp.dayofyear,
            }
        )
        row.update(
            {
                "OBJECTID": 765794,
                "id.grid.coarse": 7,
                "forecast_origin_timestamp": origin,
                "target_timestamp": timestamp,
                "target_energy": 10.0,
            }
        )
        rows.append(row)
        if include_second_building:
            second_building = row.copy()
            second_building.update(
                {
                    "OBJECTID": 765795,
                    "energy_at_origin": 20.0,
                    "energy_rolling_mean_24h": 20.0,
                    "energy_rolling_mean_7d": 20.0,
                    "energy_rolling_mean_30d": 20.0,
                    "target_energy": 20.0,
                }
            )
            rows.append(second_building)
    pd.DataFrame(rows).to_parquet(path, index=False)


def test_commercial_building_catalog_includes_identity_metadata(
    tmp_path: Path,
) -> None:
    gold_path = tmp_path / "commercial_gold.parquet"
    _write_gold_fixture(gold_path)
    provider = TrainedForecastProvider(
        customer_provider=MLflowModelAdapter(tracking_uri=""),
        commercial_data=gold_path,
        commercial_model=tmp_path / "unused-commercial-model.joblib",
        government_data=tmp_path / "unused-government.parquet",
        government_model=tmp_path / "unused-government-model.joblib",
    )

    building = provider.get_commercial_buildings()[0]

    assert building["buildingId"] == "765794"
    assert building["sqm"] == 100.0
    assert building["footprintAreaM2"] == 100.0
    assert building["latitude"] == 40.0
    assert building["longitude"] == -70.0
    assert building["specificSpaceUsage"] == "Office"


def test_commercial_dashboard_uses_range_specific_forecast_horizons(
    tmp_path: Path, monkeypatch
) -> None:
    gold_path = tmp_path / "commercial_gold.parquet"
    _write_gold_fixture(gold_path)
    model = ConstantCommercialModel()
    provider = TrainedForecastProvider(
        customer_provider=MLflowModelAdapter(tracking_uri=""),
        commercial_data=gold_path,
        commercial_model=tmp_path / "unused-commercial-model.joblib",
        government_data=tmp_path / "unused-government.parquet",
        government_model=tmp_path / "unused-government-model.joblib",
    )
    monkeypatch.setattr(
        provider, "_load_mlflow_model", lambda sector: (model, "test-version")
    )

    latest_actual = pd.Timestamp("2019-01-03 23:00:00")
    expected_forecast_days = {"1D": 1, "7D": 3, "1M": 31, "3M": 90, "1Y": 365}
    expected_curve_points = {"1D": 24, "7D": 3, "1M": 31, "3M": 13, "1Y": 12}
    expected_model_calls_by_range = {
        "1D": 1,
        "7D": 3,
        "1M": 31,
        "3M": 13,
        "1Y": 12,
    }
    expected_horizon_labels = {
        "1D": "next 24 hours",
        "7D": "next 3 days",
        "1M": "next month",
        "3M": "next 3 months",
        "1Y": "next year",
    }
    expected_model_calls = 0

    for time_range, days in expected_forecast_days.items():
        expected_model_calls += expected_model_calls_by_range[time_range]
        dashboard = provider.get_commercial_dashboard("765794", time_range)
        predicted_points = [
            point
            for point in dashboard["curve"]
            if point["predictedDemand"] is not None
        ]
        assert dashboard["dataPeriod"].startswith("Gold history:")
        assert len(predicted_points) == expected_curve_points[time_range]
        assert all(point["predictedDemand"] == 1.5 for point in predicted_points)
        assert dashboard["predictedTotal"] == days * 24 * 1.5
        assert model.call_count == expected_model_calls
        assert expected_horizon_labels[time_range] in dashboard["predictedTotalHorizon"]
        predicted_peak_timestamp = pd.to_datetime(
            dashboard["predictedPeakTimestamp"], format="%d %b %Y, %I:%M %p"
        )
        assert predicted_peak_timestamp > latest_actual

    hourly_dashboard = provider.get_commercial_dashboard("765794", "1D")
    callout = hourly_dashboard["predictedCallout"]
    assert hourly_dashboard["avgDemand"] == 10.0
    assert hourly_dashboard["peakDemand"] == 10.0
    assert hourly_dashboard["predictedPeak"] == 1.5
    assert hourly_dashboard["predictedTotal"] == 24 * 1.5
    assert callout["label"] == "Predicted Peak · Next 24 Hours"
    assert any(
        point["time"] == callout["time"]
        and point["predictedDemand"] == callout["value"]
        for point in hourly_dashboard["curve"]
    )


class ConstantRegionalCommercialModel:
    def __init__(self) -> None:
        self.call_count = 0

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        self.call_count += 1
        assert len(frame) == 48
        return np.full(len(frame), 1.5)


def test_regional_commercial_dashboard_aggregates_gold_history_and_forecasts(
    tmp_path: Path, monkeypatch
) -> None:
    gold_path = tmp_path / "commercial_gold.parquet"
    _write_gold_fixture(gold_path, include_second_building=True)
    model = ConstantRegionalCommercialModel()
    provider = TrainedForecastProvider(
        customer_provider=MLflowModelAdapter(tracking_uri=""),
        commercial_data=gold_path,
        commercial_model=tmp_path / "unused-commercial-model.joblib",
        government_data=tmp_path / "unused-government.parquet",
        government_model=tmp_path / "unused-government-model.joblib",
    )
    monkeypatch.setattr(
        provider, "_load_mlflow_model", lambda sector: (model, "test-version")
    )

    dashboard = provider.get_commercial_dashboard("regional", "1M")

    predicted_points = [
        point for point in dashboard["curve"] if point["predictedDemand"] is not None
    ]
    actual_points = [
        point for point in dashboard["curve"] if point["actualDemand"] is not None
    ]
    assert dashboard["tab"] == "regional"
    assert dashboard["buildingId"] == "regional"
    assert dashboard["avgDemand"] == 30.0
    assert len(actual_points) == 2
    assert all(point["actualDemand"] == 30.0 for point in actual_points)
    assert len(predicted_points) == 31
    assert all(point["predictedDemand"] == 3.0 for point in predicted_points)
    assert dashboard["predictedTotal"] == 31 * 24 * 3.0
    assert model.call_count == 31
    assert dashboard["dataPeriod"].startswith("Gold history:")


def test_commercial_historical_insights_use_gold_daily_rollups(
    tmp_path: Path,
) -> None:
    gold_path = tmp_path / "commercial_gold.parquet"
    _write_gold_fixture(gold_path)
    provider = TrainedForecastProvider(
        customer_provider=MLflowModelAdapter(tracking_uri=""),
        commercial_data=gold_path,
        commercial_model=tmp_path / "unused-commercial-model.joblib",
        government_data=tmp_path / "unused-government.parquet",
        government_model=tmp_path / "unused-government-model.joblib",
    )
    service = DashboardService(SampleDataProvider(), provider)

    history = service.get_historical_insights(
        persona="commercial",
        time_range="30D",
        entity_id="765794",
    )

    assert history["persona"] == "commercial"
    assert history["entityId"] == "765794"
    assert history["timeRange"] == "30D"
    assert history["daysReturned"] == 2
    assert history["startDate"] == "02 Jan 2019"
    assert history["endDate"] == "03 Jan 2019"
    assert history["avgDailyConsumption"] == 240.0
    assert history["avgMonthlyConsumption"] == 7200.0
    assert history["peakConsumption"] == 10.0
    assert history["unit"] == "kWh"
    assert history["historyCurve"] == [
        {
            "date": "02 Jan",
            "fullDate": "02 Jan 2019",
            "peakDemand": 10.0,
            "avgDemand": 10.0,
            "totalConsumption": 240.0,
            "peakTime": "12:00 AM",
        },
        {
            "date": "03 Jan",
            "fullDate": "03 Jan 2019",
            "peakDemand": 10.0,
            "avgDemand": 10.0,
            "totalConsumption": 240.0,
            "peakTime": "12:00 AM",
        },
    ]
