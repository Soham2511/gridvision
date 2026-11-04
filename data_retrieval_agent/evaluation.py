"""Offline metrics for representative query evaluation runs."""

from __future__ import annotations

from typing import Iterable


def evaluate_cases(cases: Iterable[dict], observed: dict[str, dict]) -> dict[str, float | int]:
    cases = list(cases)
    if not cases:
        return {"case_count": 0, "tool_selection_accuracy": 0.0, "retrieval_accuracy": 0.0, "tool_execution_success_rate": 0.0, "response_correctness": 0.0, "unnecessary_tool_rate": 0.0}
    selected_correct = retrieved_correct = execution_success = response_correct = unnecessary = total_calls = 0
    for case in cases:
        result = observed.get(case["id"], {})
        expected_tools, actual_tools = set(case.get("expected_tools", [])), set(result.get("tools", []))
        expected_sources, actual_sources = set(case.get("expected_sources", [])), set(result.get("sources", []))
        selected_correct += actual_tools == expected_tools
        retrieved_correct += expected_sources.issubset(actual_sources)
        execution_success += bool(result.get("execution_success", not expected_tools))
        response_correct += bool(result.get("answer_correct", False))
        unnecessary += len(actual_tools - expected_tools)
        total_calls += len(actual_tools)
    return {
        "case_count": len(cases),
        "tool_selection_accuracy": selected_correct / len(cases),
        "retrieval_accuracy": retrieved_correct / len(cases),
        "tool_execution_success_rate": execution_success / len(cases),
        "response_correctness": response_correct / len(cases),
        "unnecessary_tool_rate": unnecessary / max(1, total_calls),
    }
