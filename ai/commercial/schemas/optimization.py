"""Validated schedules accepted by the Commercial cost optimizer."""

from __future__ import annotations

import math

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_JOBS = 40
MAX_HORIZON_HOURS = 24


class MaintenanceWindow(BaseModel):
    """A half-open period when a machine is unavailable."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    machine_id: str = Field(min_length=1, max_length=80)
    start_hour: int = Field(ge=0, le=23)
    end_hour: int = Field(ge=1, le=24)

    @model_validator(mode="after")
    def validate_window(self) -> MaintenanceWindow:
        if self.end_hour <= self.start_hour:
            raise ValueError("A maintenance window must have positive duration.")
        return self


class BatteryInput(BaseModel):
    """Explicit battery limits and optional baseline dispatch, in kW/kWh."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    capacity_kwh: float = Field(gt=0, le=1_000_000, allow_inf_nan=False)
    initial_soc_kwh: float = Field(ge=0, le=1_000_000, allow_inf_nan=False)
    min_soc_kwh: float = Field(default=0, ge=0, le=1_000_000, allow_inf_nan=False)
    terminal_soc_kwh: float | None = Field(
        default=None, ge=0, le=1_000_000, allow_inf_nan=False
    )
    max_charge_kw: float = Field(gt=0, le=1_000_000, allow_inf_nan=False)
    max_discharge_kw: float = Field(gt=0, le=1_000_000, allow_inf_nan=False)
    charge_efficiency: float = Field(gt=0, le=1, allow_inf_nan=False)
    discharge_efficiency: float = Field(gt=0, le=1, allow_inf_nan=False)
    baseline_charge_kw: tuple[float, ...] = ()
    baseline_discharge_kw: tuple[float, ...] = ()

    @model_validator(mode="after")
    def validate_battery_limits(self) -> BatteryInput:
        if self.min_soc_kwh > self.capacity_kwh:
            raise ValueError("Minimum state of charge exceeds battery capacity.")
        if self.min_soc_kwh > self.initial_soc_kwh:
            raise ValueError("Initial state of charge is below the minimum.")
        if self.initial_soc_kwh > self.capacity_kwh:
            raise ValueError("Initial state of charge exceeds battery capacity.")
        if self.terminal_soc_kwh is not None and not (
            self.min_soc_kwh
            <= self.terminal_soc_kwh
            <= self.capacity_kwh
        ):
            raise ValueError("Terminal state of charge is outside battery limits.")
        if len(self.baseline_charge_kw) != len(self.baseline_discharge_kw):
            raise ValueError(
                "Baseline battery charge and discharge schedules must have "
                "the same number of slots."
            )
        if any(
            not math.isfinite(power) or power < 0
            for power in (*self.baseline_charge_kw, *self.baseline_discharge_kw)
        ):
            raise ValueError("Baseline battery dispatch must be finite and non-negative.")
        if any(
            charge > self.max_charge_kw or discharge > self.max_discharge_kw
            for charge, discharge in zip(
                self.baseline_charge_kw,
                self.baseline_discharge_kw,
            )
        ):
            raise ValueError("Baseline battery dispatch exceeds its power limits.")
        if any(
            charge > 0 and discharge > 0
            for charge, discharge in zip(
                self.baseline_charge_kw,
                self.baseline_discharge_kw,
            )
        ):
            raise ValueError("The battery cannot charge and discharge simultaneously.")
        return self


class ScheduleJob(BaseModel):
    """A production job with a bounded contiguous run window."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")
    machine_id: str = Field(min_length=1, max_length=80)
    power_kw: float = Field(gt=0, le=100_000, allow_inf_nan=False)
    duration_hours: int = Field(ge=1, le=24)
    release_hour: int = Field(default=0, ge=0, le=23)
    deadline_hour: int = Field(ge=1, le=24)
    predecessor_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_window(self) -> ScheduleJob:
        if self.deadline_hour <= self.release_hour:
            raise ValueError("A job deadline must be after its release hour.")
        if self.duration_hours > self.deadline_hour - self.release_hour:
            raise ValueError("A job does not fit inside its allowed time window.")
        if self.job_id in self.predecessor_ids:
            raise ValueError("A job cannot depend on itself.")
        return self


class ScheduleInput(BaseModel):
    """Explicit, user-supplied data for a one-day hourly schedule."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    horizon_hours: int = Field(ge=1, le=MAX_HORIZON_HOURS)
    prices_inr_per_kwh: tuple[float, ...]
    jobs: tuple[ScheduleJob, ...] = Field(min_length=1, max_length=MAX_JOBS)
    demand_limit_kw: float | None = Field(default=None, gt=0, le=1_000_000)
    baseline_start_hours: dict[str, int] = Field(default_factory=dict)
    renewable_generation_kw: tuple[float, ...] = ()
    maintenance_windows: tuple[MaintenanceWindow, ...] = ()
    battery: BatteryInput | None = None

    @model_validator(mode="after")
    def validate_schedule_inputs(self) -> ScheduleInput:
        if len(self.prices_inr_per_kwh) != self.horizon_hours:
            raise ValueError("Provide one tariff rate per scheduling hour.")
        if any(
            not math.isfinite(price) or price < 0 or price > 100_000
            for price in self.prices_inr_per_kwh
        ):
            raise ValueError("Tariff rates must be finite and non-negative.")
        if self.renewable_generation_kw and (
            len(self.renewable_generation_kw) != self.horizon_hours
        ):
            raise ValueError("Provide one renewable generation value per hour.")
        if any(
            not math.isfinite(power) or power < 0 or power > 1_000_000
            for power in self.renewable_generation_kw
        ):
            raise ValueError("Renewable generation values are outside valid bounds.")
        job_ids = [job.job_id for job in self.jobs]
        if len(set(job_ids)) != len(job_ids):
            raise ValueError("Job IDs must be unique.")
        known_ids = set(job_ids)
        if any(
            predecessor not in known_ids
            for job in self.jobs
            for predecessor in job.predecessor_ids
        ):
            raise ValueError("Every job dependency must refer to a supplied job.")
        if any(job.deadline_hour > self.horizon_hours for job in self.jobs):
            raise ValueError("A job deadline exceeds the scheduling horizon.")
        if any(
            window.end_hour > self.horizon_hours
            for window in self.maintenance_windows
        ):
            raise ValueError("A maintenance window exceeds the scheduling horizon.")
        for job in self.jobs:
            available_starts = range(
                job.release_hour,
                job.deadline_hour - job.duration_hours + 1,
            )
            if not any(
                not any(
                    window.machine_id == job.machine_id
                    and start < window.end_hour
                    and start + job.duration_hours > window.start_hour
                    for window in self.maintenance_windows
                )
                for start in available_starts
            ):
                raise ValueError(
                    f"Job {job.job_id!r} has no start time outside maintenance."
                )
        if self.battery is not None:
            battery = self.battery
            if battery.baseline_charge_kw and (
                len(battery.baseline_charge_kw) != self.horizon_hours
            ):
                raise ValueError(
                    "Provide one baseline battery dispatch value per hour."
                )
            if battery.initial_soc_kwh > battery.capacity_kwh:
                raise ValueError("Initial state of charge exceeds battery capacity.")
            if battery.baseline_charge_kw:
                soc = battery.initial_soc_kwh
                for charge, discharge in zip(
                    battery.baseline_charge_kw,
                    battery.baseline_discharge_kw,
                ):
                    soc += (
                        charge * battery.charge_efficiency
                        - discharge / battery.discharge_efficiency
                    )
                    if not battery.min_soc_kwh - 1e-9 <= soc <= battery.capacity_kwh + 1e-9:
                        raise ValueError(
                            "Baseline battery dispatch violates state-of-charge limits."
                        )
                if battery.terminal_soc_kwh is not None:
                    if abs(soc - battery.terminal_soc_kwh) > 1e-9:
                        raise ValueError(
                            "Baseline battery dispatch does not meet the "
                            "terminal state of charge."
                        )
                elif soc + 1e-9 < battery.initial_soc_kwh:
                    raise ValueError(
                        "Baseline battery dispatch ends below its initial "
                        "state of charge."
                    )
        if set(self.baseline_start_hours) - known_ids:
            raise ValueError("Baseline schedule includes an unknown job.")
        if self.baseline_start_hours and set(self.baseline_start_hours) != known_ids:
            raise ValueError("A baseline must provide a start time for every job.")
        for job in self.jobs:
            if self.baseline_start_hours:
                start = self.baseline_start_hours[job.job_id]
                if not job.release_hour <= start <= job.deadline_hour - job.duration_hours:
                    raise ValueError(
                        f"Baseline start for {job.job_id!r} is outside its allowed window."
                    )
                if any(
                    window.machine_id == job.machine_id
                    and start < window.end_hour
                    and start + job.duration_hours > window.start_hour
                    for window in self.maintenance_windows
                ):
                    raise ValueError(
                        f"Baseline overlaps maintenance for {job.machine_id!r}."
                    )
        if self.baseline_start_hours:
            jobs_by_id = {job.job_id: job for job in self.jobs}
            for job in self.jobs:
                for predecessor_id in job.predecessor_ids:
                    predecessor = jobs_by_id[predecessor_id]
                    if (
                        self.baseline_start_hours[job.job_id]
                        < self.baseline_start_hours[predecessor_id]
                        + predecessor.duration_hours
                    ):
                        raise ValueError(
                            f"Baseline violates dependency for {job.job_id!r}."
                        )
            for hour in range(self.horizon_hours):
                running = [
                    job
                    for job in self.jobs
                    if self.baseline_start_hours[job.job_id]
                    <= hour
                    < self.baseline_start_hours[job.job_id]
                    + job.duration_hours
                ]
                machine_ids = [job.machine_id for job in running]
                if len(machine_ids) != len(set(machine_ids)):
                    raise ValueError("Baseline overlaps jobs on the same machine.")
                if self.demand_limit_kw is not None:
                    battery_charge = (
                        self.battery.baseline_charge_kw[hour]
                        if self.battery is not None
                        and self.battery.baseline_charge_kw
                        else 0.0
                    )
                    battery_discharge = (
                        self.battery.baseline_discharge_kw[hour]
                        if self.battery is not None
                        and self.battery.baseline_discharge_kw
                        else 0.0
                    )
                    net_power = max(
                        0.0,
                        sum(job.power_kw for job in running)
                        + battery_charge
                        - (
                            self.renewable_generation_kw[hour]
                            if self.renewable_generation_kw
                            else 0.0
                        )
                        - battery_discharge,
                    )
                    if net_power > self.demand_limit_kw + 1e-9:
                        raise ValueError("Baseline exceeds the demand limit.")
        return self
