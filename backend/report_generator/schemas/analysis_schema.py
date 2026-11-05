"""Generic structural analysis and deterministic metric contracts."""

from __future__ import annotations

import math
from typing import Any

from pydantic import Field, field_validator

from .report_schema import ReportContract


class FieldProfile(ReportContract):
    path: str = Field(min_length=1, max_length=1000)
    type_counts: dict[str, int]
    null_count: int = Field(ge=0)
    missing_count: int = Field(ge=0)
    examples: list[str] = Field(default_factory=list, max_length=5)


class JSONAnalysis(ReportContract):
    root_type: str
    object_count: int = Field(ge=0)
    array_count: int = Field(ge=0)
    array_lengths: list[dict[str, Any]] = Field(default_factory=list)
    fields: list[FieldProfile] = Field(default_factory=list)
    grouping_candidates: list[str] = Field(default_factory=list)
    date_candidates: list[str] = Field(default_factory=list)
    potential_relationships: list[dict[str, str]] = Field(default_factory=list)


class DerivedMetric(ReportContract):
    metric_id: str
    name: str
    value: float | int
    units: str | None = None
    source_fields: list[str]
    method: str
    sample_count: int = Field(ge=0)
    exclusions: list[str] = Field(default_factory=list)

    @field_validator("value")
    @classmethod
    def finite_metric_value(cls, value: float | int) -> float | int:
        try:
            if not math.isfinite(float(value)):
                raise ValueError("derived metric values must be finite")
        except OverflowError as exc:
            raise ValueError("derived metric values must be finite") from exc
        return value


class DeterministicAnalytics(ReportContract):
    metrics: list[DerivedMetric] = Field(default_factory=list)
    comparison_tables: list[dict[str, Any]] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

