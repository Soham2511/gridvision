"""LangGraph orchestration and sequential follow-up coverage."""

import pytest
from pydantic import BaseModel, ConfigDict

from data_retrieval_agent.context import AuthenticatedRequestContext, Persona
from data_retrieval_agent.graph import build_graph
from data_retrieval_agent.tools.base import ToolDefinition, ToolOutput, ToolRegistry


class EmptyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FakeLLM:
    def __init__(self):
        self.round = 0

    def plan(self, message, history, tools):
        self.round += 1
        if self.round == 1:
            return [
                {"name": "read_first", "arguments": {}},
                {"name": "read_parallel", "arguments": {}},
            ]
        if self.round == 2:
            assert any("Evidence already retrieved" in turn["content"] for turn in history)
            return [{"name": "read_second", "arguments": {}}]
        return []

    def answer(self, message, history, results):
        return "The retrieved value is 5 kWh."


def test_graph_runs_conditional_followup_and_validates_numeric_answer():
    langgraph = pytest.importorskip("langgraph")
    from langgraph.checkpoint.memory import InMemorySaver

    sequence = []
    registry = ToolRegistry()
    for name, value in (("read_first", 5), ("read_parallel", 6), ("read_second", 7)):
        def handler(args, ctx, n=name, v=value):
            if n == "read_second":
                assert {"read_first", "read_parallel"}.issubset(sequence)
            sequence.append(n)
            return ToolOutput(tool_name=n, data={"value": v}, source={"source_id": "fixture"})
        registry.register(ToolDefinition(
            name=name,
            description=f"Read {name}",
            input_schema=EmptyInput,
            output_schema=ToolOutput,
            required_permission=name,
            required_source=None,
            handler=handler,
        ))
    context = AuthenticatedRequestContext(
        principal_id="user", persona=Persona.RESIDENTIAL,
        permissions=frozenset({"read_first", "read_parallel", "read_second"}), entity_scopes={}, request_id="req",
    )
    checkpointer = InMemorySaver()
    graph = build_graph(registry=registry, llm=FakeLLM(), max_tool_calls=3, max_graph_steps=8, checkpointer=checkpointer)
    result = graph.invoke({
        "message": "retrieve values", "history": [], "results": [], "errors": [], "rounds": 0,
    }, {"configurable": {"thread_id": "thread-1"}, "recursion_limit": 8}, context={"context": context, "available_sources": set()})
    assert set(sequence) == {"read_first", "read_parallel", "read_second"}
    assert sequence.index("read_second") > sequence.index("read_first")
    assert sequence.index("read_second") > sequence.index("read_parallel")
    assert len(result["results"]) == 3
    assert result["answer"] == "The retrieved value is 5 kWh."
    saved = checkpointer.get_tuple({"configurable": {"thread_id": "thread-1"}})
    assert "context" not in saved.checkpoint["channel_values"]
    assert "available_sources" not in saved.checkpoint["channel_values"]


def test_graph_reports_source_unavailable_instead_of_asking_irrelevant_clarification():
    pytest.importorskip("langgraph")
    from langgraph.checkpoint.memory import InMemorySaver

    class NoCallLLM:
        def plan(self, *args):
            raise AssertionError("No tool should be exposed without an available source.")

        def answer(self, *args):
            raise AssertionError("No evidence should be sent to response generation.")

    context = AuthenticatedRequestContext(
        principal_id="user", persona=Persona.RESIDENTIAL,
        permissions=frozenset({"get_historical_consumption"}),
        entity_scopes={"consumer": frozenset({"101"})}, request_id="req-missing-source",
    )
    graph = build_graph(registry=ToolRegistry(), llm=NoCallLLM(), max_tool_calls=2, max_graph_steps=6, checkpointer=InMemorySaver())
    result = graph.invoke({"message": "show my consumption history", "history": [], "results": [], "errors": [], "rounds": 0},
                          {"configurable": {"thread_id": "thread-missing"}},
                          context={"context": context, "available_sources": set()})
    assert result["clarification"] is False
    assert "unavailable" in result["answer"]
