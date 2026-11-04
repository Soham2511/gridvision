"""Peak forecast specialist node."""

from __future__ import annotations

from ai.commercial.agents.common import execute_specialist
from ai.commercial.schemas.state import CommercialState
from ai.commercial.tools.protocol import CommercialTools


def run_peak_prediction(
    state: CommercialState,
    tools: CommercialTools,
) -> dict:
    return execute_specialist(
        state,
        tools,
        "peak_prediction",
        lambda provider, factory_id, goal, building_id: provider.get_peak_forecast(
            factory_id,
            goal,
            building_id,
        ),
    )
