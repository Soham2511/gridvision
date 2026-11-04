"""Tests for paired evaluation metrics using explicit synthetic fixtures."""

from __future__ import annotations

from ai.commercial.evaluation import EvaluationCase, evaluate_cases
from ai.commercial.schemas.communication import CommercialRequest
from ai.commercial.tools.mock_tools import MockCommercialTools, synthetic_fixture


def test_paired_evaluation_measures_baseline_and_multi_agent() -> None:
    tools = MockCommercialTools(
        {
            "operations": synthetic_fixture(
                source_id="fixture:compressed-air",
                finding="Synthetic test fixture: compressor leak procedure.",
            )
        }
    )
    case = EvaluationCase(
        case_id="operations-lookup",
        request=CommercialRequest(
            request_id="eval-1",
            factory_id="synthetic-factory",
            user_goal="Summarize compressed air leak reduction guidance.",
        ),
        expected_specialists=("operations",),
        expected_source_ids=("fixture:compressed-air",),
        expected_conflict=False,
    )

    comparison = evaluate_cases((case,), tools=tools)[0]

    assert comparison.single_agent.task_completed
    assert comparison.multi_agent.task_completed
    assert comparison.multi_agent.specialist_precision == 1
    assert comparison.multi_agent.specialist_recall == 1
    assert comparison.multi_agent.evidence_support_rate == 1
    assert comparison.multi_agent.graph_source_recall == 1
    assert comparison.multi_agent.tool_success_rate == 1
    assert comparison.multi_agent.conflict_expectation_met is True
    assert comparison.multi_agent.estimated_model_cost is None
