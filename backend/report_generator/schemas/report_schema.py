"""Flexible validated report contracts independent of business domains."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ReportContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ReportMetric(ReportContract):
    name: str = Field(min_length=1, max_length=200)
    value: str | int | float | bool | None
    units: str | None = Field(default=None, max_length=100)
    source_fields: list[str] = Field(min_length=1, max_length=100)
    methodology: str = Field(min_length=1, max_length=1000)

    @field_validator("value")
    @classmethod
    def metric_float_must_be_finite(cls, value: Any) -> Any:
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("metric values must be finite")
        return value


class ReportTable(ReportContract):
    title: str = Field(min_length=1, max_length=200)
    columns: list[str] = Field(min_length=1, max_length=50)
    rows: list[list[str | int | float | bool | None]] = Field(max_length=5000)

    @field_validator("rows")
    @classmethod
    def table_rows_match_columns(
        cls, rows: list[list[Any]], info: Any
    ) -> list[list[Any]]:
        columns = info.data.get("columns")
        if columns is not None and any(len(row) != len(columns) for row in rows):
            raise ValueError("each table row must match the number of columns")
        for row in rows:
            if any(isinstance(value, float) and not math.isfinite(value) for value in row):
                raise ValueError("table values must be finite")
        return rows


class ReportSection(ReportContract):
    title: str = Field(min_length=1, max_length=200)
    order: int = Field(ge=0, le=1000)
    content: list[str] = Field(default_factory=list, max_length=100)
    metrics: list[ReportMetric] = Field(default_factory=list, max_length=100)
    tables: list[ReportTable] = Field(default_factory=list, max_length=50)
    observations: list[str] = Field(default_factory=list, max_length=100)


class ReportDocument(ReportContract):
    report_id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=240)
    subtitle: str | None = Field(default=None, max_length=500)
    generated_at: datetime
    executive_summary: str = Field(min_length=1, max_length=10_000)
    sections: list[ReportSection] = Field(max_length=100)
    metrics: list[ReportMetric] = Field(default_factory=list, max_length=500)
    observations: list[str] = Field(default_factory=list, max_length=200)
    conclusion: str | None = Field(default=None, max_length=10_000)
    limitations: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("sections")
    @classmethod
    def section_orders_are_unique(cls, sections: list[ReportSection]) -> list[ReportSection]:
        order_values = [section.order for section in sections]
        if len(order_values) != len(set(order_values)):
            raise ValueError("section order values must be unique")
        return sections
