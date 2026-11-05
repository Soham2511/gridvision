from data_retrieval_agent.evaluation import evaluate_cases


def test_evaluation_reports_selection_retrieval_and_unnecessary_calls():
    cases = [
        {"id": "a", "expected_tools": ["history"], "expected_sources": ["gold"]},
        {"id": "b", "expected_tools": [], "expected_sources": []},
    ]
    result = evaluate_cases(cases, {
        "a": {"tools": ["history"], "sources": ["gold"], "execution_success": True, "answer_correct": True},
        "b": {"tools": ["history"], "sources": [], "execution_success": True, "answer_correct": False},
    })
    assert result["tool_selection_accuracy"] == 0.5
    assert result["retrieval_accuracy"] == 1.0
    assert result["tool_execution_success_rate"] == 1.0
    assert result["response_correctness"] == 0.5
    assert result["unnecessary_tool_rate"] == 0.5
