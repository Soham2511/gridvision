from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest

from ai.redistribution import (
    DEFAULT_ADDITIONAL_LOSS_PCT_PER_KM,
    DEFAULT_BASE_LOSS_PCT,
    DEFAULT_MAXIMUM_LOSS_PCT,
    GRID_COUNT,
    build_grid_network,
    calculate_grid_balance,
    calculate_transmission_loss,
    create_hourly_results,
    generate_forecast,
    generate_synthetic_supply,
    haversine_distance_km,
    load_hybrid_model,
    optimize_redistribution,
    run_simulation,
)

FEATURES = [
    "forecast_horizon_hours",
    "total_building_area_m2",
    "total_footprint_area_m2",
    "centroid_latitude",
    "centroid_longitude",
    "building_count",
    "Commercial_count",
    "Industrial_count",
    "Institutional_count",
    "Recreational_count",
    "Residential_count",
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
    "target_month",
    "target_day_of_month",
    "target_day_of_week",
    "target_hour",
    "target_day_of_year",
    "target_is_weekend",
    "target_hour_sin",
    "target_hour_cos",
    "target_day_of_year_sin",
    "target_day_of_year_cos",
]


class ConstantModel:
    def __init__(self, value: float, feature_names: list[str]) -> None:
        self.value = value
        self.feature_name_ = feature_names

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        return np.full(len(frame), self.value)


def _grid_metadata() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "id.grid.coarse": range(GRID_COUNT),
            "centroid_latitude": [40 + index * 0.01 for index in range(GRID_COUNT)],
            "centroid_longitude": [-75 + (index % 7) * 0.01 for index in range(GRID_COUNT)],
        }
    )


def _write_fixture_files(tmp_path: Path) -> tuple[Path, Path]:
    origin = datetime(2018, 9, 24, 23)
    rows = []
    for horizon in range(1, 25):
        target = origin + timedelta(hours=horizon)
        for grid in range(GRID_COUNT):
            row = {
                "id.grid.coarse": grid,
                "forecast_origin_timestamp": origin,
                "target_timestamp": target,
                "forecast_horizon_hours": horizon,
            }
            row.update({feature: 1.0 for feature in FEATURES})
            row["forecast_horizon_hours"] = horizon
            row["centroid_latitude"] = 40 + grid * 0.01
            row["centroid_longitude"] = -75 + (grid % 7) * 0.01
            rows.append(row)
    data_path = tmp_path / "gold.parquet"
    pd.DataFrame(rows).to_parquet(data_path, index=False)
    model_path = tmp_path / "hybrid.joblib"
    joblib.dump(
        {
            "original_model": ConstantModel(12.0, FEATURES),
            "log_model": ConstantModel(float(np.log1p(5.0)), FEATURES),
            "features": FEATURES,
            "routing": pd.DataFrame(
                {
                    "grid_id": range(GRID_COUNT),
                    "selected_model": [
                        "log" if grid % 2 == 0 else "original"
                        for grid in range(GRID_COUNT)
                    ],
                }
            ),
            "config": {"model_name": "Test hybrid"},
        },
        model_path,
    )
    return model_path, data_path


def test_load_and_generate_forecast_preserve_route_and_transform(
    tmp_path: Path,
) -> None:
    model_path, data_path = _write_fixture_files(tmp_path)
    model = load_hybrid_model(model_path)

    forecast = generate_forecast(model, data_path, "2018-09-24")

    assert len(forecast) == GRID_COUNT * 24
    assert forecast["target_timestamp"].min() == datetime(2018, 9, 25)
    assert forecast["target_timestamp"].max() == datetime(2018, 9, 25, 23)
    assert set(forecast["predicted_demand_kwh"]) == {5.0, 12.0}
    assert set(forecast["selected_model"]) == {"original", "log"}


def test_feature_missing_and_incomplete_origins_fail_explicitly(
    tmp_path: Path,
) -> None:
    model_path, data_path = _write_fixture_files(tmp_path)
    model = load_hybrid_model(model_path)
    complete = pd.read_parquet(data_path)
    complete.drop(columns=[FEATURES[0]]).to_parquet(data_path, index=False)
    with pytest.raises(ValueError, match="missing required columns"):
        generate_forecast(model, data_path, "2018-09-24")

    complete.to_parquet(data_path, index=False)
    with pytest.raises(ValueError, match="exactly 1272 forecast rows"):
        incomplete = pd.read_parquet(data_path).iloc[:-1]
        incomplete.to_parquet(data_path, index=False)
        generate_forecast(model, data_path, "2018-09-24")


def test_loss_model_clamps_and_conserves_energy() -> None:
    result = calculate_transmission_loss(20, 1000)

    assert result["loss_pct"] == pytest.approx(0.02)
    assert result["energy_lost_kwh"] == pytest.approx(20)
    assert result["energy_received_kwh"] == pytest.approx(980)
    assert result["energy_sent_kwh"] == pytest.approx(
        result["energy_received_kwh"] + result["energy_lost_kwh"]
    )
    assert calculate_transmission_loss(1000, 50)["loss_pct"] == pytest.approx(0.08)
    assert haversine_distance_km(0, 0, 0, 1) == pytest.approx(111.195, rel=1e-4)


def test_network_is_unique_persisted_and_stable(tmp_path: Path) -> None:
    path = tmp_path / "network.json"
    metadata = _grid_metadata()
    network = build_grid_network(metadata, network_path=path)
    reused = build_grid_network(metadata, network_path=path)
    edge_keys = {
        tuple(sorted((edge["grid_a_id"], edge["grid_b_id"])))
        for edge in network["connections"]
    }

    assert path.is_file()
    assert network == reused
    assert len(edge_keys) == len(network["connections"])
    assert all(edge["capacity_kwh_per_hour"] == 10_000 for edge in network["connections"])
    assert all(0.01 <= edge["loss_pct"] <= 0.08 for edge in network["connections"])
    assert json.loads(path.read_text())["grid_count"] == GRID_COUNT
    for grid in range(GRID_COUNT):
        distances = sorted(
            (
                haversine_distance_km(
                    metadata.loc[grid, "centroid_latitude"],
                    metadata.loc[grid, "centroid_longitude"],
                    other["centroid_latitude"],
                    other["centroid_longitude"],
                ),
                int(other["id.grid.coarse"]),
            )
            for _, other in metadata.iterrows()
            if other["id.grid.coarse"] != grid
        )
        assert all(
            tuple(sorted((grid, neighbor_id))) in edge_keys
            for _, neighbor_id in distances[:3]
        )


def test_supply_is_reproducible_bounded_and_keeps_demand_separate() -> None:
    forecast = pd.DataFrame(
        {
            "id.grid.coarse": [1, 2, 1],
            "target_timestamp": pd.to_datetime(
                ["2018-09-25 01:00", "2018-09-25 01:00", "2018-09-25 02:00"]
            ),
            "predicted_demand_kwh": [100.0, 200.0, 300.0],
        }
    )

    first = generate_synthetic_supply(forecast, random_seed=7)
    second = generate_synthetic_supply(forecast, random_seed=7)

    assert first["synthetic_supply_kwh"].tolist() == second["synthetic_supply_kwh"].tolist()
    assert first["predicted_demand_kwh"].tolist() == [100.0, 200.0, 300.0]
    assert first["supply_variation"].abs().max() <= 0.10
    assert np.allclose(
        first["synthetic_supply_kwh"],
        first["predicted_demand_kwh"] * (1 + first["supply_variation"]),
    )


def test_optimizer_respects_capacity_surplus_and_transfer_conservation() -> None:
    hour = pd.Timestamp("2018-09-25T01:00:00")
    balance = pd.DataFrame(
        {
            "id.grid.coarse": [1, 2, 3],
            "target_timestamp": [hour] * 3,
            "initial_surplus_kwh": [100.0, 0.0, 0.0],
            "initial_deficit_kwh": [0.0, 60.0, 30.0],
            "predicted_demand_kwh": [100.0] * 3,
            "synthetic_supply_kwh": [100.0] * 3,
            "supply_variation": [0.0] * 3,
        }
    )
    network = {
        "configuration": {
            "loss_parameters": {
                "base_loss_pct": DEFAULT_BASE_LOSS_PCT,
                "additional_loss_pct_per_km": DEFAULT_ADDITIONAL_LOSS_PCT_PER_KM,
                "maximum_loss_pct": DEFAULT_MAXIMUM_LOSS_PCT,
            }
        },
        "connections": [
            {
                "grid_a_id": 1,
                "grid_b_id": 2,
                "distance_km": 10.0,
                "capacity_kwh_per_hour": 70.0,
                "loss_pct": 0.015,
            },
            {
                "grid_a_id": 1,
                "grid_b_id": 3,
                "distance_km": 20.0,
                "capacity_kwh_per_hour": 50.0,
                "loss_pct": 0.02,
            },
        ],
    }

    transfers = optimize_redistribution(balance, network)
    sent = sum(transfer["energy_sent_kwh"] for transfer in transfers)

    assert sent <= 100.0 + 1e-6
    assert all(transfer["source_grid_id"] == 1 for transfer in transfers)
    assert all(transfer["energy_sent_kwh"] <= 70.0 + 1e-6 for transfer in transfers)
    assert all(
        transfer["energy_sent_kwh"]
        == pytest.approx(
            transfer["energy_received_kwh"] + transfer["energy_lost_kwh"]
        )
        for transfer in transfers
    )
    assert sum(transfer["energy_received_kwh"] for transfer in transfers) == pytest.approx(
        90.0
    )


def test_optimizer_handles_no_available_connections() -> None:
    balance = pd.DataFrame(
        {
            "id.grid.coarse": [1, 2],
            "target_timestamp": [pd.Timestamp("2018-09-25T01:00:00")] * 2,
            "initial_surplus_kwh": [50.0, 0.0],
            "initial_deficit_kwh": [0.0, 50.0],
        }
    )
    network = {"connections": []}

    assert optimize_redistribution(balance, network) == []


def test_simulation_writes_24_hours_and_persists_network(tmp_path: Path) -> None:
    model_path, data_path = _write_fixture_files(tmp_path)
    output_path = run_simulation(
        "2018-09-24",
        model_path=model_path,
        forecast_data_path=data_path,
        network_path=tmp_path / "network.json",
        output_dir=tmp_path / "output",
        random_seed=19,
    )
    result = json.loads(output_path.read_text())

    assert output_path.name == "redistribution_plan_2018-09-25.json"
    assert result["simulation_metadata"]["forecast_interval_count"] == 24
    assert len(result["hourly_results"]) == 24
    assert all(len(record["grids"]) == GRID_COUNT for record in result["hourly_results"])
    assert result["simulation_metadata"]["assumptions"]["network_and_losses_are_synthetic"]
    assert (tmp_path / "network.json").is_file()
