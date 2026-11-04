"""Pydantic inputs for registered data tools."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ConsumerProfileInput(StrictToolInput):
    consumer_id: int = Field(gt=0)


class HistoryInput(StrictToolInput):
    persona: Literal["residential", "commercial", "government"]
    entity_id: str | None = Field(default=None, min_length=1, max_length=120)
    time_range: Literal["30D", "90D", "3M", "6M", "1Y", "ALL"] = "1Y"


class CustomerSilverHistoryInput(StrictToolInput):
    start_date: date
    end_date: date
    entity_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_window(self):
        if self.end_date < self.start_date or (self.end_date - self.start_date).days > 30:
            raise ValueError("Silver history window must be ordered and no longer than 31 days.")
        return self


class LatestCustomerSilverMonthInput(StrictToolInput):
    """Request the latest calendar month for a customer or household cohort."""

    entity_id: int | None = Field(default=None, gt=0)


class LatestCommercialSilverMonthInput(StrictToolInput):
    """Request the latest available Silver month for a building or cohort."""

    entity_id: str | None = Field(default=None, min_length=1, max_length=120)


class BuildingDetailsInput(StrictToolInput):
    building_id: str = Field(min_length=1, max_length=120)


class RegionalInformationInput(StrictToolInput):
    region_id: str | None = Field(default=None, min_length=1, max_length=120)


class ForecastInput(StrictToolInput):
    persona: Literal["residential", "commercial", "government"]
    entity_id: str = Field(min_length=1, max_length=120)


class AnomalyInput(StrictToolInput):
    start_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    consumer_ids: list[int] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def validate_window(self):
        start, end = date.fromisoformat(self.start_date), date.fromisoformat(self.end_date)
        if end < start or (end - start).days > 30:
            raise ValueError("Anomaly date range must be ordered and at most 31 days.")
        if start < date(2019, 1, 1) or end > date(2019, 12, 31):
            raise ValueError("The approved synthetic anomaly source covers 2019 only.")
        return self


class SegmentationInput(StrictToolInput):
    scope: Literal["regional", "distribution", "consumer"] = "regional"
    region_id: str | None = Field(default=None, max_length=120)
    consumer_id: int | None = Field(default=None, gt=0)


class ModelMetadataInput(StrictToolInput):
    model_id: Literal["customer-bill-prediction", "commercial-building-forecast", "government-load-forecast", "anomaly-prediction", "government-customer-segmentation"]
