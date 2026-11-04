"""Explicit-fixture-only mock tools for tests and local workflow development."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ai.commercial.schemas.communication import (
    AgentError,
    EvidenceRef,
    ToolObservation,
)


class MockCommercialTools:
    """Return no invented data unless an explicit fixture is provided."""

    def __init__(
        self,
        fixtures: Mapping[str, ToolObservation] | None = None,
    ) -> None:
        self._fixtures = dict(fixtures or {})

    def _observation(self, name: str) -> ToolObservation:
        fixture = self._fixtures.get(name)
        if fixture is None:
            return ToolObservation(
                status="unavailable",
                error=AgentError(
                    code="MOCK_DATA_UNAVAILABLE",
                    message=f"No {name} fixture or live provider is configured.",
                ),
            )
        return fixture.model_copy(
            update={
                "evidence_refs": tuple(
                    reference.model_copy(update={"synthetic": True})
                    for reference in fixture.evidence_refs
                )
            }
        )

    def get_peak_forecast(
        self,
        factory_id: str | None,
        goal: str,
        building_id: str | None = None,
    ) -> ToolObservation:
        del factory_id, goal, building_id
        return self._observation("peak_prediction")

    def get_commercial_buildings(self, limit: int = 20) -> ToolObservation:
        del limit
        return self._observation("commercial_buildings")

    def retrieve_operational_context(
        self, factory_id: str | None, goal: str
    ) -> ToolObservation:
        del factory_id, goal
        return self._observation("operations")

    def get_renewable_scenarios(
        self, factory_id: str | None, goal: str
    ) -> ToolObservation:
        del factory_id, goal
        return self._observation("renewable")

    def optimize(
        self, factory_id: str | None, inputs: dict[str, Any]
    ) -> ToolObservation:
        del factory_id, inputs
        return self._observation("cost_optimization")


def synthetic_fixture(
    *,
    source_id: str,
    finding: str,
    data: dict[str, Any] | None = None,
    locator: str | None = None,
) -> ToolObservation:
    """Create a visibly synthetic observation for isolated tests."""
    return ToolObservation(
        status="available",
        findings=(finding,),
        data=data or {},
        evidence_refs=(
            EvidenceRef(
                source_id=source_id,
                source_type="synthetic_test_fixture",
                locator=locator,
                excerpt=finding,
                synthetic=True,
            ),
        ),
    )
