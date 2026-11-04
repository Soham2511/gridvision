from __future__ import annotations

from types import SimpleNamespace

import pytest

from ai.anamoly.graph.graph_retriever import GraphRetriever
from ai.anamoly.tools.gridvision_tools import (
    _filter_customer_records,
    _list_runs,
    _run_status,
    build_registry,
)
from ai.anamoly.tools.registry import ToolPermissionError


class _VectorRetriever:
    def search(self, query: str, limit: int = 5) -> list[dict]:
        return [
            {
                "id": "doc-1",
                "text": "A spike anomaly can indicate a transformer outage.",
                "metadata": {
                    "title": "Transformer outage guidance",
                    "source_url": "https://example.test/guidance",
                },
            }
        ][:limit]


def _service(run: dict) -> SimpleNamespace:
    return SimpleNamespace(
        list_runs=lambda limit: [run][:limit],
        get_run=lambda run_id: dict(run) if run_id == run["analysis_id"] else None,
        analysis_store=SimpleNamespace(
            get=lambda run_id: dict(run) if run_id == run["analysis_id"] else None
        ),
    )


def test_customer_run_list_is_scoped_and_sanitized():
    run = {
        "analysis_id": "run-1",
        "status": "completed",
        "created_at": "2025-01-01",
        "updated_at": "2025-01-01",
        "request": {
            "customer_ids": [10],
            "start_date": "2025-01-01",
            "end_date": "2025-01-02",
        },
        "events": [{"event_id": "event-1", "customer_ids": [10]}],
        "anomaly_windows": [{"event_id": "event-1", "customer_id": 10}],
        "error": "internal details",
    }
    context = {
        "persona": "household",
        "authorized_customer_ids": {10},
        "anomaly_service": _service(run),
    }

    listed = _list_runs({"limit": 25}, context)

    assert listed == [
        {
            "analysis_id": "run-1",
            "status": "completed",
            "created_at": "2025-01-01",
            "updated_at": "2025-01-01",
            "start_date": "2025-01-01",
            "end_date": "2025-01-02",
        }
    ]


def test_customer_cannot_read_status_for_another_customers_run():
    run = {
        "analysis_id": "run-1",
        "status": "running",
        "request": {"customer_ids": [20]},
    }
    context = {
        "persona": "household",
        "authorized_customer_ids": {10},
        "anomaly_service": _service(run),
    }

    with pytest.raises(ToolPermissionError, match="outside"):
        _run_status({"run_id": "run-1"}, context)


def test_run_data_tools_are_restricted_to_government_persona():
    registry = build_registry()
    context = {
        "principal": "trusted-user",
        "authenticated_persona": "household",
    }

    for tool_name, arguments in (
        ("get_run_details", {"run_id": "run-1"}),
        ("get_localization_metrics", {"run_id": "run-1"}),
        (
            "execute_anomaly_analysis",
            {"start_date": "2019-04-03", "end_date": "2019-04-03"},
        ),
    ):
        with pytest.raises(ToolPermissionError, match="not permitted"):
            registry.execute(
                tool_name,
                arguments,
                persona="household",
                context=context,
            )


def test_find_event_by_id_returns_saved_event_and_source_run():
    run = {
        "analysis_id": "run-1",
        "status": "completed",
        "request": {
            "start_date": "2019-01-01",
            "end_date": "2019-01-04",
        },
        "events": [
            {
                "event_id": "EVT_001",
                "event_scope": "MULTI_AREA",
                "dominant_anomaly_type": "zero_block",
            }
        ],
    }
    service = _service(run)
    service.get_run = lambda run_id: dict(run) if run_id == "run-1" else None
    registry = build_registry()
    result = registry.execute(
        "find_event_by_id",
        {"event_id": "EVT_001"},
        persona="government",
        context={
            "persona": "government",
            "principal": "trusted-user",
            "authenticated_persona": "government",
            "anomaly_service": service,
        },
    )

    assert result["event_scope"] == "MULTI_AREA"
    assert result["dominant_anomaly_type"] == "zero_block"
    assert result["run_id"] == "run-1"
    assert result["source_start_date"] == "2019-01-01"
    assert result["source_end_date"] == "2019-01-04"


def test_customer_scoped_event_redacts_other_customers_and_aggregates():
    event = {
        "event_id": "event-1",
        "customer_ids": [10, 20],
        "affected_customer_count": 2,
        "affected_customer_percentage": 50.0,
        "spatial_cluster_ids": ["area-1"],
    }

    filtered = _filter_customer_records([event], {10})

    assert filtered == [
        {
            "event_id": "event-1",
            "customer_ids": [10],
            "affected_customer_count": 1,
        }
    ]


def test_query_anomalies_uses_supported_dates_and_customer_scope():
    run = {
        "analysis_id": "run-1",
        "status": "completed",
        "request": {"start_date": "2025-01-01", "end_date": "2025-01-02"},
        "anomaly_windows": [
            {"customer_id": 10, "anomaly_start": "2025-01-01T04:00:00Z"},
            {"customer_id": 20, "anomaly_start": "2025-01-01T05:00:00Z"},
            {"customer_id": 10, "anomaly_start": "2025-01-03T00:00:00Z"},
        ],
    }
    service = _service(run)
    service.get_summary = lambda: {
        "dataset": {"startDate": "2025-01-01", "endDate": "2025-01-10"}
    }
    context = {
        "persona": "household",
        "authorized_customer_ids": {10},
        "anomaly_service": service,
    }
    handler = build_registry()._tools["query_anomalies"].handler

    result = handler(
        {"start_date": "2025-01-01", "end_date": "2025-01-02", "limit": 10},
        context,
    )

    assert result["count"] == 1
    assert result["run_ids"] == ["run-1"]
    assert result["items"] == [
        {"customer_id": 10, "anomaly_start": "2025-01-01T04:00:00Z"}
    ]


def test_graph_retrieval_links_events_customers_areas_and_documents():
    retriever = GraphRetriever(vector_retriever=_VectorRetriever())

    result = retriever.search_with_run(
        "spike outage",
        [
            {
                "event_id": "event-1",
                "event_scope": "localized",
                "event_start": "2025-01-01T00:00:00Z",
                "customer_ids": [10],
                "dominant_anomaly_type": "spike",
            }
        ],
        [
            {
                "event_id": "event-1",
                "customer_id": 10,
                "event_spatial_cluster_id": "area-1",
            }
        ],
    )

    node_types = {node["type"] for node in result["nodes"]}
    relations = {edge["relation"] for edge in result["edges"]}
    assert node_types == {"event", "customer", "area", "entity", "document"}
    assert {"affects", "located_in", "shares_entity", "mentions"} <= relations


def test_graph_retrieval_expands_to_documents_sharing_anchor_entities():
    class _RelatedVectorRetriever:
        def search(self, query: str, limit: int = 5) -> list[dict]:
            if query == "spike outage":
                return [
                    {
                        "id": "anchor",
                        "text": "A spike anomaly.",
                        "metadata": {"title": "Spike guide"},
                    }
                ]
            if query == "spike":
                return [
                    {
                        "id": "related",
                        "text": "Spike detection procedures.",
                        "metadata": {"title": "Detection guide"},
                    }
                ]
            return []

    results = GraphRetriever(vector_retriever=_RelatedVectorRetriever()).search(
        "spike outage"
    )

    assert [item["id"] for item in results] == ["anchor", "related"]
