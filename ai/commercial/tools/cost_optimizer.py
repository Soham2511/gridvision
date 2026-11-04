"""Constraint-checked hourly production scheduling with OR-Tools CP-SAT."""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from ai.commercial.schemas.communication import EvidenceRef, ToolObservation
from ai.commercial.schemas.optimization import ScheduleInput

COST_SCALE = 10_000
POWER_SCALE = 100
PRICE_SCALE = 100
EFFICIENCY_SCALE = 10_000


def _cost_for_starts(
    payload: ScheduleInput,
    start_hours: dict[str, int],
    charge_kw: tuple[float, ...] = (),
    discharge_kw: tuple[float, ...] = (),
) -> float:
    job_by_id = {job.job_id: job for job in payload.jobs}
    total = 0.0
    for hour, price in enumerate(payload.prices_inr_per_kwh):
        load_kw = sum(
            job_by_id[job_id].power_kw
            for job_id, start in start_hours.items()
            if start <= hour < start + job_by_id[job_id].duration_hours
        )
        renewable_kw = (
            payload.renewable_generation_kw[hour]
            if payload.renewable_generation_kw
            else 0.0
        )
        charge = charge_kw[hour] if charge_kw else 0.0
        discharge = discharge_kw[hour] if discharge_kw else 0.0
        total += max(0.0, load_kw + charge - renewable_kw - discharge) * price
    return total


def _battery_schedule(
    solver: Any,
    charge_variables: list[Any],
    discharge_variables: list[Any],
    soc_variables: list[Any],
) -> dict[str, Any]:
    charge = [solver.value(variable) / POWER_SCALE for variable in charge_variables]
    discharge = [
        solver.value(variable) / POWER_SCALE for variable in discharge_variables
    ]
    return {
        "charge_kw": [round(value, 2) for value in charge],
        "discharge_kw": [round(value, 2) for value in discharge],
        "state_of_charge_kwh": [
            round(solver.value(variable) / POWER_SCALE, 2)
            for variable in soc_variables
        ],
    }


def optimize_schedule(inputs: dict[str, Any]) -> ToolObservation:
    """Find a feasible lowest-tariff schedule; never infer missing site data."""
    try:
        payload = ScheduleInput.model_validate(inputs)
    except ValidationError as exc:
        return ToolObservation(
            status="failed",
            error={
                "code": "OPTIMIZATION_INPUT_INVALID",
                "message": str(exc)[:1000],
            },
        )

    try:
        from ortools.sat.python import cp_model
    except ImportError:
        return ToolObservation(
            status="unavailable",
            error={
                "code": "OPTIMIZATION_SOLVER_UNAVAILABLE",
                "message": (
                    "Install the optional commercial-optimizer dependency "
                    "group to run the CP-SAT schedule solver."
                ),
            },
        )

    model = cp_model.CpModel()
    starts: dict[str, list[tuple[int, Any]]] = {}
    start_expr: dict[str, Any] = {}
    for job in payload.jobs:
        candidates = []
        latest_start = job.deadline_hour - job.duration_hours
        for hour in range(job.release_hour, latest_start + 1):
            if any(
                window.machine_id == job.machine_id
                and hour < window.end_hour
                and hour + job.duration_hours > window.start_hour
                for window in payload.maintenance_windows
            ):
                continue
            candidates.append(
                (hour, model.new_bool_var(f"start_{job.job_id}_{hour}"))
            )
        starts[job.job_id] = candidates
        model.add_exactly_one(variable for _, variable in candidates)
        start_expr[job.job_id] = sum(
            hour * variable for hour, variable in candidates
        )

    for job in payload.jobs:
        for predecessor_id in job.predecessor_ids:
            predecessor = next(
                item for item in payload.jobs if item.job_id == predecessor_id
            )
            model.add(
                start_expr[job.job_id]
                >= start_expr[predecessor_id] + predecessor.duration_hours
            )

    charge_variables: list[Any] = []
    discharge_variables: list[Any] = []
    soc_variables: list[Any] = []
    battery = payload.battery
    if battery is not None:
        max_soc = round(battery.capacity_kwh * POWER_SCALE)
        soc_variables = [
            model.new_int_var(0, max_soc, f"battery_soc_{hour}")
            for hour in range(payload.horizon_hours + 1)
        ]
        model.add(
            soc_variables[0]
            == round(battery.initial_soc_kwh * POWER_SCALE)
        )
        min_soc = round(battery.min_soc_kwh * POWER_SCALE)
        max_charge = round(battery.max_charge_kw * POWER_SCALE)
        max_discharge = round(battery.max_discharge_kw * POWER_SCALE)
        charge_efficiency = round(
            battery.charge_efficiency * EFFICIENCY_SCALE
        )
        discharge_efficiency = round(
            battery.discharge_efficiency * EFFICIENCY_SCALE
        )
        for hour in range(payload.horizon_hours):
            charge = model.new_int_var(0, max_charge, f"battery_charge_{hour}")
            discharge = model.new_int_var(
                0, max_discharge, f"battery_discharge_{hour}"
            )
            charging = model.new_bool_var(f"battery_is_charging_{hour}")
            model.add(charge <= max_charge * charging)
            model.add(discharge <= max_discharge * (1 - charging))
            model.add(
                soc_variables[hour + 1] >= min_soc
            )
            model.add(
                (soc_variables[hour + 1] - soc_variables[hour])
                * EFFICIENCY_SCALE
                * discharge_efficiency
                == charge * charge_efficiency * discharge_efficiency
                - discharge * EFFICIENCY_SCALE * EFFICIENCY_SCALE
            )
            charge_variables.append(charge)
            discharge_variables.append(discharge)
        if battery.terminal_soc_kwh is not None:
            model.add(
                soc_variables[-1]
                == round(battery.terminal_soc_kwh * POWER_SCALE)
            )
        else:
            model.add(soc_variables[-1] >= soc_variables[0])

    objective_terms = []
    for hour in range(payload.horizon_hours):
        power_terms: list[Any] = []
        for job in payload.jobs:
            for start_hour, variable in starts[job.job_id]:
                if start_hour <= hour < start_hour + job.duration_hours:
                    power_terms.append(
                        round(job.power_kw * POWER_SCALE) * variable
                    )
        for machine_id in {job.machine_id for job in payload.jobs}:
            machine_active = [
                variable
                for job in payload.jobs
                if job.machine_id == machine_id
                for start_hour, variable in starts[job.job_id]
                if start_hour <= hour < start_hour + job.duration_hours
            ]
            if machine_active:
                model.add_at_most_one(machine_active)
        renewable_kw = (
            payload.renewable_generation_kw[hour]
            if payload.renewable_generation_kw
            else 0.0
        )
        grid_import = model.new_int_var(
            0,
            round(
                (
                    sum(job.power_kw for job in payload.jobs)
                    + (battery.max_charge_kw if battery is not None else 0)
                )
                * POWER_SCALE
            ),
            f"grid_import_{hour}",
        )
        net_load = sum(power_terms)
        if battery is not None:
            net_load += charge_variables[hour] - discharge_variables[hour]
        if power_terms:
            net_load -= round(renewable_kw * POWER_SCALE)
        elif battery is not None:
            net_load -= round(renewable_kw * POWER_SCALE)
        if power_terms or battery is not None:
            model.add(grid_import >= net_load)
        if payload.demand_limit_kw is not None:
            model.add(
                grid_import <= round(payload.demand_limit_kw * POWER_SCALE)
            )
        objective_terms.append(
            round(payload.prices_inr_per_kwh[hour] * PRICE_SCALE)
            * grid_import
        )
    model.minimize(sum(objective_terms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 10.0
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 0
    status = solver.solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return ToolObservation(
            status="unavailable",
            error={
                "code": "OPTIMIZATION_INFEASIBLE",
                "message": (
                    "No feasible schedule satisfies the supplied job windows, "
                    "dependencies, machine capacity, and demand limit."
                ),
            },
            assumptions=("No schedule was returned because the constraints are infeasible.",),
        )

    schedule: dict[str, int] = {}
    for job in payload.jobs:
        schedule[job.job_id] = next(
            hour
            for hour, variable in starts[job.job_id]
            if solver.boolean_value(variable)
        )
    battery_result = (
        _battery_schedule(
            solver,
            charge_variables,
            discharge_variables,
            soc_variables,
        )
        if battery is not None
        else None
    )
    optimized_charge = (
        tuple(battery_result["charge_kw"]) if battery_result else ()
    )
    optimized_discharge = (
        tuple(battery_result["discharge_kw"]) if battery_result else ()
    )
    optimized_cost = _cost_for_starts(
        payload,
        schedule,
        optimized_charge,
        optimized_discharge,
    )
    findings = [
        "A feasible schedule was found for the supplied hourly tariff and job constraints.",
        f"Calculated energy cost for scheduled jobs: ₹{optimized_cost:,.2f}.",
    ]
    data: dict[str, Any] = {
        "status": "optimal" if status == cp_model.OPTIMAL else "feasible",
        "schedule": [
            {
                "job_id": job.job_id,
                "machine_id": job.machine_id,
                "start_hour": schedule[job.job_id],
                "end_hour": schedule[job.job_id] + job.duration_hours,
            }
            for job in payload.jobs
        ],
        "calculated_cost_inr": round(optimized_cost, 2),
        "solver": "OR-Tools CP-SAT",
        "objective_bound_inr": round(
            solver.best_objective_bound / COST_SCALE,
            2,
        ),
    }
    if battery_result is not None:
        data["battery_dispatch"] = battery_result
    if payload.baseline_start_hours:
        baseline_charge = (
            battery.baseline_charge_kw if battery is not None else ()
        )
        baseline_discharge = (
            battery.baseline_discharge_kw if battery is not None else ()
        )
        baseline_cost = _cost_for_starts(
            payload,
            payload.baseline_start_hours,
            baseline_charge,
            baseline_discharge,
        )
        savings = baseline_cost - optimized_cost
        data["baseline_cost_inr"] = round(baseline_cost, 2)
        data["calculated_savings_inr"] = round(savings, 2)
        findings.append(
            f"Calculated savings versus the supplied baseline: ₹{savings:,.2f}."
        )
    else:
        findings.append(
            "Savings were not calculated because no baseline schedule was supplied."
        )
    source_excerpt = json.dumps(
        payload.model_dump(mode="json"),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )[:4000]
    return ToolObservation(
        status="available",
        findings=tuple(findings),
        data=data,
        evidence_refs=(
            EvidenceRef(
                source_id="user-provided-optimization-input",
                source_type="user_input",
                excerpt=source_excerpt,
            ),
        ),
        assumptions=(
            "Tariffs and job power are treated as hourly constant values.",
            "Only supplied jobs are included; idle/facility base load is excluded.",
            "Renewable generation offsets modeled job load and cannot be exported.",
            "Each slot is one hour; battery dispatch does not include degradation or reserve constraints beyond supplied state-of-charge limits.",
        ),
    )
