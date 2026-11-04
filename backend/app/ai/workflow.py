"""Typed LangGraph workflow helpers with lazy, optional dependency loading."""

from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence, TypedDict

from app.ai.contracts import AIOutput, EvidenceEnvelope


class WorkflowState(TypedDict, total=False):
    request_id: str
    evidence: EvidenceEnvelope
    output: AIOutput
    errors: list[str]


WorkflowNode = Callable[[WorkflowState], Mapping[str, Any]]
WorkflowEdge = tuple[str, str]
END = "__end__"


class WorkflowDependencyUnavailable(RuntimeError):
    pass


def build_workflow(
    nodes: Mapping[str, WorkflowNode],
    edges: Sequence[WorkflowEdge],
    *,
    entry_point: str,
):
    """Compile a small typed StateGraph; no provider or network is configured here."""
    if entry_point not in nodes:
        raise ValueError("Workflow entry point must name a declared node.")
    if not nodes:
        raise ValueError("A workflow must declare at least one node.")
    for source, target in edges:
        if source not in nodes or (target != END and target not in nodes):
            raise ValueError(f"Workflow edge references an unknown node: {source} -> {target}")
    try:
        from langgraph.graph import END as LANGGRAPH_END
        from langgraph.graph import StateGraph
    except ImportError as exc:
        raise WorkflowDependencyUnavailable(
            "LangGraph is optional; install requirements-ai.txt to enable workflows."
        ) from exc

    graph = StateGraph(WorkflowState)
    for name, node in nodes.items():
        graph.add_node(name, node)
    graph.set_entry_point(entry_point)
    for source, target in edges:
        graph.add_edge(source, LANGGRAPH_END if target == END else target)
    return graph.compile()

