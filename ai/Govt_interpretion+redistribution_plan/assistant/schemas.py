from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Intent = Literal[
    "plan",
    "hourly_summary",
    "surplus_deficit",
    "transfers",
    "losses",
    "grid_plan",
    "compare_hours",
    "compare_grids",
    "unmet_demand",
    "demand_solution",
    "summary",
    "regenerate_image",
    "image_generation",
    "csv_generation",
    "follow_up",
    "historical_analysis",
    "predicted_analysis",
    "demand_comparison",
    "external_knowledge",
    "help",
    "clarification",
]
OutputFormat = Literal["text", "csv", "image"]


class QueryRequest(BaseModel):
    """Validated request shape returned by the query interpreter."""

    model_config = ConfigDict(extra="forbid", strict=True)

    intent: Intent
    forecast_date: str | None
    start_timestamp: str | None
    duration_hours: int | None = Field(ge=1, le=24)
    grid_ids: list[int] = Field(max_length=53)
    output_formats: list[OutputFormat] = Field(max_length=3)
    needs_clarification: bool
    clarification_question: str | None
    analysis_start_date: str | None = None
    analysis_end_date: str | None = None

    @field_validator("forecast_date")
    @classmethod
    def validate_forecast_date(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                date.fromisoformat(value)
            except ValueError as exc:
                raise ValueError("forecast_date must use YYYY-MM-DD") from exc
            if len(value) != 10:
                raise ValueError("forecast_date must use YYYY-MM-DD")
        return value

    @field_validator("analysis_start_date", "analysis_end_date")
    @classmethod
    def validate_analysis_date(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                date.fromisoformat(value)
            except ValueError as exc:
                raise ValueError("analysis dates must use YYYY-MM-DD") from exc
            if len(value) != 10:
                raise ValueError("analysis dates must use YYYY-MM-DD")
        return value

    @field_validator("start_timestamp")
    @classmethod
    def validate_timestamp(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("start_timestamp must be ISO 8601") from exc
            if timestamp.tzinfo is not None and timestamp.utcoffset() is not None:
                raise ValueError("start_timestamp must be timezone-naive")
            if timestamp.minute or timestamp.second or timestamp.microsecond:
                raise ValueError("start_timestamp must align to an exact hour")
        return value

    @field_validator("grid_ids")
    @classmethod
    def validate_unique_grids(cls, value: list[int]) -> list[int]:
        if len(set(value)) != len(value):
            raise ValueError("grid_ids must not contain duplicates")
        if any(grid_id < 0 for grid_id in value):
            raise ValueError("grid_ids must be non-negative")
        return value

    @field_validator("output_formats")
    @classmethod
    def validate_unique_formats(cls, value: list[OutputFormat]) -> list[OutputFormat]:
        if len(set(value)) != len(value):
            raise ValueError("output_formats must not contain duplicates")
        return value

    @model_validator(mode="after")
    def require_clarification_text(self) -> QueryRequest:
        if self.needs_clarification and not self.clarification_question:
            raise ValueError(
                "clarification_question is required when needs_clarification is true"
            )
        return self
