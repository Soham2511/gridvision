from __future__ import annotations

import pytest

from ai.anamoly.date_guardrails import dataset_date_bounds, validate_requested_dates


class FakeAnomalyService:
    def get_summary(self):
        return {
            "dataset": {
                "startDate": "2019-01-01T00:00:00",
                "endDate": "2019-12-31T23:00:00",
            }
        }


def test_bounds_are_derived_from_dataset_metadata():
    assert tuple(map(str, dataset_date_bounds(FakeAnomalyService()))) == (
        "2019-01-01",
        "2019-12-31",
    )


def test_validates_dataset_boundary_and_maximum_analysis_length():
    assert validate_requested_dates(
        FakeAnomalyService(), "2019-06-01", "2019-06-07"
    )
    with pytest.raises(ValueError, match="available dataset range"):
        validate_requested_dates(
            FakeAnomalyService(), "2020-01-01", "2020-01-01"
        )
    with pytest.raises(ValueError, match="at most 7 days"):
        validate_requested_dates(
            FakeAnomalyService(), "2019-06-01", "2019-06-08"
        )
