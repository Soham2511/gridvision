"""Renewable scenario specialist node."""

from __future__ import annotations

from ai.commercial.agents.common import execute_specialist
from ai.commercial.schemas.state import CommercialState
from ai.commercial.tools.protocol import CommercialTools


def run_renewable(
    state: CommercialState,
    tools: CommercialTools,
) -> dict:
    return execute_specialist(
        state,
        tools,
        "renewable",
        lambda provider, factory_id, goal, _building_id: provider.get_renewable_scenarios(
            factory_id,
            goal,
        ),
    )
