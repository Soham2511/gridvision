"""Operations specialist node."""

from __future__ import annotations

from ai.commercial.agents.common import execute_specialist
from ai.commercial.schemas.state import CommercialState
from ai.commercial.tools.protocol import CommercialTools


def run_operations(
    state: CommercialState,
    tools: CommercialTools,
) -> dict:
    return execute_specialist(
        state,
        tools,
        "operations",
        lambda provider, factory_id, goal, _building_id: provider.retrieve_operational_context(
            factory_id,
            goal,
        ),
    )
