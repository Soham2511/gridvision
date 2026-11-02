"""Tests for Government dashboard replay and short-horizon forecasts."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from app.providers.mlflow_adapter import MLflowModelAdapter
from app.providers.sample_data_provider import SampleDataProvider
from app.providers.trained_forecast_provider import TrainedForecastProvider
from app.services.dashboard_service import DashboardService


GOVERNMENT_FEATURES = [
    "building_count",
    "energy_at_origin",
    "energy_lag_1h",
    "energy_lag_24h",
    "energy_lag_168h",
    "energy_lag_336h",
    "energy_lag_720h",
    "energy_mean_24h",
    "energy_std_24h",
    "energy_count_24h",
    "energy_mean_7d",
    "energy_std_7d",
    "energy_count_7d",
    "energy_mean_30d",
    "energy_std_30d",
    "energy_count_30d",
    "forecast_horizon_hours",
    "target_hour",
    "target_year",
    "target_day_of_week",
    "target_month",
    "target_is_weekend",
    "target_day_of_month",
    "target_day_of_year",
    "target_hour_sin",
    "target_hour_cos",
    "target_day_of_year_sin",
    "target_day_of_year_cos",
]


class ConstantGovernmentModel:
    def __init__(self, value: float) -> None:
        self.value = value
        self.call_count = 0

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        self.call_count += 1
        assert frame["forecast_horizon_hours"].tolist() == list(
            map(float, range(1, 25))
        )
        assert frame["target_year"].eq(2019).all()
        return np.full(len(frame), self.value)


def _provider(tmp_path: Path) -> tuple[TrainedForecastProvider, ConstantGovernmentModel]:
    provider = TrainedForecastProvider(
        customer_provider=MLflowModelAdapter(tracking_uri=""),
        commercial_data=tmp_path / "unused-commercial.parquet",
        commercial_model=tmp_path / "unused-commercial-model.joblib",
        government_data=tmp_path / "unused-government.parquet",
        government_model=tmp_path / "unused-government-model.joblib",
    )
    timestamps = pd.date_range(end="2018-12-31 23:00:00", periods=72, freq="h")
    actual_rows = []
    for grid_id, demand in ((9, 1000.0), (10, 3000.0)):
        actual_rows.extend(
            {
                "grid_id": grid_id,
                "target_timestamp": timestamp,
                "target_energy": demand,
            }
            for timestamp in timestamps
        )
    provider._government_actuals = pd.DataFrame(actual_rows)
    provider._government_contexts = pd.DataFrame(
        [
            {
                "id.grid.coarse": grid_id,
                "target_timestamp": timestamps[-1],
                "forecast_horizon_hours": 1,
                "building_count": 25,
            }
            for grid_id in (9, 10)
        ]
    )
    original_model = ConstantGovernmentModel(2000.0)
    log_model = ConstantGovernmentModel(float(np.log1p(3000.0)))
    provider._load_government_bundle = lambda: {
        "features": GOVERNMENT_FEATURES,
        "routing": pd.DataFrame(
            [
                {"grid_id": 9, "selected_model": "original"},
                {"grid_id": 10, "selected_model": "log"},
            ]
        ),
        "original_model": original_model,
        "log_model": log_model,
    }
    return provider, original_model


def test_government_dashboard_uses_grid_history_and_24_hour_forecast(
    tmp_path: Path,
) -> None:
    provider, model = _provider(tmp_path)

    dashboard = provider.get_government_dashboard("overall", time_range="1D")
    actual_points = [
        point for point in dashboard["curve"] if point["actualDemand"] is not None
    ]
    forecast_points = [
        point for point in dashboard["curve"] if point["predictedDemand"] is not None
    ]

    assert dashboard["regionName"] == "System-Wide"
    assert dashboard["avgDemand"] == 4.0
    assert dashboard["peakDemand"] == 4.0
    assert dashboard["predictedPeak"] == 5.0
    assert dashboard["predictedTotal"] == 120.0
    assert dashboard["unit"] == "MW"
    assert dashboard["totalUnit"] == "MWh"
    assert dashboard["demarcationTime"] == "31 Dec 23:00"
    assert len(actual_points) == 24
    assert len(forecast_points) == 24
    assert model.call_count == 1
    assert "Historical replay through 31 Dec 2018 23:00" in dashboard["dataPeriod"]
    assert dashboard["predictedTotalHorizon"].startswith("Next 24 hours")

    quarterly = provider.get_government_dashboard("overall", time_range="3M")
    quarterly_actual = [
        point for point in quarterly["curve"] if point["actualDemand"] is not None
    ]
    quarterly_forecast = [
        point for point in quarterly["curve"] if point["predictedDemand"] is not None
    ]
    assert quarterly_actual[-1]["fullDate"] != quarterly_forecast[0]["fullDate"]

    annual = provider.get_government_dashboard("overall", time_range="1Y")
    assert annual["demarcationTime"] == "Dec 2018"


def test_government_region_dashboard_and_region_cards_are_data_backed(
    tmp_path: Path,
) -> None:
    provider, _ = _provider(tmp_path)
    service = DashboardService(SampleDataProvider(), model_provider=provider)

    region = service.get_government_dashboard("region", "9", "7D")
    regions = service.get_government_regions("7D")
    grid_nine = next(item for item in regions if item["id"] == "9")
    horizon = provider.predict_horizon("government", "9", horizon_count=6)

    assert region["regionName"] == "Grid 9"
    assert region["avgDemand"] == 1.0
    assert region["predictedPeak"] == 2.0
    assert region["predictedTotal"] == 48.0
    assert grid_nine["currentDemand"] == 1.0
    assert grid_nine["predictedDemand"] == 2.0
    assert grid_nine["sparkline"] == [1.0, 1.0, 1.0]
    assert {item["id"] for item in regions} == {"9", "10"}
    assert len(horizon) == 6
    assert [point["horizon_hours"] for point in horizon] == list(range(1, 7))
    assert all(point["prediction"] == 2000.0 for point in horizon)
    assert all(point["actual"] is None for point in horizon)


def test_government_historical_insights_aggregate_actual_grid_observations(
    tmp_path: Path,
) -> None:
    provider, _ = _provider(tmp_path)
    service = DashboardService(SampleDataProvider(), model_provider=provider)

    history = service.get_historical_insights("government", "30D", "9")

    assert history["persona"] == "government"
    assert history["entityId"] == "system-wide"
    assert history["timeRange"] == "30D"
    assert history["daysReturned"] == 3
    assert history["startDate"] == "29 Dec 2018"
    assert history["endDate"] == "31 Dec 2018"
    assert history["avgDailyConsumption"] == 4.0
    assert history["avgMonthlyConsumption"] == 4.0
    assert history["peakConsumption"] == 4.0
    assert history["unit"] == "MW"
    assert history["historyCurve"][-1]["totalConsumption"] == 96.0
