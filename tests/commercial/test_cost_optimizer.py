"""Tests for the explicit-input CP-SAT cost optimizer."""

from __future__ import annotations

import pytest

from ai.commercial.schemas.optimization import ScheduleInput
from ai.commercial.tools.cost_optimizer import optimize_schedule


pytest.importorskip("ortools.sat.python.cp_model")


def _inputs() -> dict:
    return {
        "horizon_hours": 3,
        "prices_inr_per_kwh": [10, 2, 8],
        "jobs": [
            {
                "job_id": "batch-1",
                "machine_id": "press-1",
                "power_kw": 10,
                "duration_hours": 1,
                "release_hour": 0,
                "deadline_hour": 3,
            }
        ],
    }


def test_optimizer_uses_lowest_tariff_and_does_not_invent_savings() -> None:
    result = optimize_schedule(_inputs())

    assert result.status == "available"
    assert result.data["schedule"][0]["start_hour"] == 1
    assert result.data["calculated_cost_inr"] == 20
    assert "calculated_savings_inr" not in result.data
    assert any("no baseline schedule" in finding for finding in result.findings)
    assert result.evidence_refs[0].source_type == "user_input"


def test_optimizer_reports_savings_only_against_explicit_baseline() -> None:
    inputs = _inputs()
    inputs["baseline_start_hours"] = {"batch-1": 0}

    result = optimize_schedule(inputs)

    assert result.status == "available"
    assert result.data["baseline_cost_inr"] == 100
    assert result.data["calculated_savings_inr"] == 80


def test_optimizer_respects_dependencies_machine_capacity_and_demand_limit() -> None:
    inputs = {
        "horizon_hours": 4,
        "prices_inr_per_kwh": [1, 1, 1, 1],
        "demand_limit_kw": 5,
        "jobs": [
            {
                "job_id": "first",
                "machine_id": "line",
                "power_kw": 4,
                "duration_hours": 1,
                "release_hour": 0,
                "deadline_hour": 4,
            },
            {
                "job_id": "second",
                "machine_id": "line",
                "power_kw": 4,
                "duration_hours": 1,
                "release_hour": 0,
                "deadline_hour": 4,
                "predecessor_ids": ["first"],
            },
        ],
    }

    result = optimize_schedule(inputs)

    starts = {
        item["job_id"]: item["start_hour"]
        for item in result.data["schedule"]
    }
    assert result.status == "available"
    assert starts["second"] >= starts["first"] + 1


def test_optimizer_returns_explicit_infeasible_result() -> None:
    inputs = {
        "horizon_hours": 2,
        "prices_inr_per_kwh": [1, 1],
        "demand_limit_kw": 2,
        "jobs": [
            {
                "job_id": "large",
                "machine_id": "line",
                "power_kw": 3,
                "duration_hours": 2,
                "release_hour": 0,
                "deadline_hour": 2,
            }
        ],
    }

    result = optimize_schedule(inputs)

    assert result.status == "unavailable"
    assert result.error is not None
    assert result.error.code == "OPTIMIZATION_INFEASIBLE"


def test_optimizer_rejects_missing_tariff_slots() -> None:
    inputs = _inputs()
    inputs["prices_inr_per_kwh"] = [5]

    result = optimize_schedule(inputs)

    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "OPTIMIZATION_INPUT_INVALID"


def test_optimizer_avoids_machine_maintenance_windows() -> None:
    inputs = {
        "horizon_hours": 4,
        "prices_inr_per_kwh": [1, 10, 2, 10],
        "maintenance_windows": [
            {"machine_id": "press-1", "start_hour": 0, "end_hour": 2}
        ],
        "jobs": [
            {
                "job_id": "press-job",
                "machine_id": "press-1",
                "power_kw": 5,
                "duration_hours": 1,
                "release_hour": 0,
                "deadline_hour": 4,
            }
        ],
    }

    result = optimize_schedule(inputs)

    assert result.status == "available"
    assert result.data["schedule"][0]["start_hour"] == 2


def test_optimizer_models_battery_soc_and_dispatch() -> None:
    inputs = {
        "horizon_hours": 3,
        "prices_inr_per_kwh": [1, 1, 20],
        "baseline_start_hours": {"fixed-job": 2},
        "jobs": [
            {
                "job_id": "fixed-job",
                "machine_id": "press-1",
                "power_kw": 4,
                "duration_hours": 1,
                "release_hour": 2,
                "deadline_hour": 3,
            }
        ],
        "battery": {
            "capacity_kwh": 4,
            "initial_soc_kwh": 2,
            "min_soc_kwh": 0,
            "terminal_soc_kwh": 2,
            "max_charge_kw": 2,
            "max_discharge_kw": 2,
            "charge_efficiency": 0.9,
            "discharge_efficiency": 0.9,
            "baseline_charge_kw": [0, 0, 0],
            "baseline_discharge_kw": [0, 0, 0],
        },
    }

    result = optimize_schedule(inputs)

    assert result.status == "available"
    dispatch = result.data["battery_dispatch"]
    assert len(dispatch["state_of_charge_kwh"]) == 4
    assert dispatch["state_of_charge_kwh"][0] == 2
    assert dispatch["state_of_charge_kwh"][-1] == 2
    assert all(0 <= soc <= 4 for soc in dispatch["state_of_charge_kwh"])
    assert any(power > 0 for power in dispatch["charge_kw"])
    assert any(power > 0 for power in dispatch["discharge_kw"])
    assert result.data["calculated_savings_inr"] > 0


def test_terminal_soc_can_be_an_optimizer_target_without_baseline_dispatch() -> None:
    inputs = _inputs()
    inputs["battery"] = {
        "capacity_kwh": 40,
        "initial_soc_kwh": 20,
        "min_soc_kwh": 5,
        "terminal_soc_kwh": 10,
        "max_charge_kw": 10,
        "max_discharge_kw": 10,
        "charge_efficiency": 0.95,
        "discharge_efficiency": 0.95,
    }

    validated = ScheduleInput.model_validate(inputs)

    assert validated.battery is not None
    assert validated.battery.terminal_soc_kwh == 10
    assert validated.battery.initial_soc_kwh == 20


def test_optimizer_rejects_baseline_battery_soc_violation() -> None:
    inputs = {
        "horizon_hours": 2,
        "prices_inr_per_kwh": [1, 1],
        "jobs": [
            {
                "job_id": "job",
                "machine_id": "press-1",
                "power_kw": 1,
                "duration_hours": 1,
                "deadline_hour": 2,
            }
        ],
        "battery": {
            "capacity_kwh": 2,
            "initial_soc_kwh": 1,
            "min_soc_kwh": 0.5,
            "max_charge_kw": 1,
            "max_discharge_kw": 1,
            "charge_efficiency": 0.9,
            "discharge_efficiency": 0.9,
            "baseline_charge_kw": [0, 0],
            "baseline_discharge_kw": [1, 0],
        },
    }

    result = optimize_schedule(inputs)

    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "OPTIMIZATION_INPUT_INVALID"
