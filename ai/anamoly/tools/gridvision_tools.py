"""Registered tools backed by GridVision's existing anomaly run services."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from ai.anamoly.date_guardrails import dataset_date_bounds, validate_requested_dates
from ai.anamoly.tools.registry import (
    ToolDefinition,
    ToolPermissionError,
    ToolRegistry,
)

GOVERNMENT_ONLY = frozenset({"government"})
ALL_PERSONAS = frozenset({"household", "commercial", "government"})
DEFAULT_ANALYSIS_PARAMETERS = {
    "h3_resolution": 8,
    "spatial_radius_km": 5.0,
    "maximum_start_time_difference_minutes": 30,
    "minimum_temporal_overlap": 0.25,
    "maximum_interval_gap_minutes": 60,
}


def _compatible_run_parameters(run: dict[str, Any]) -> bool:
    request = run.get("request", {})
    return all(
        request.get(key, default) == default
        for key, default in DEFAULT_ANALYSIS_PARAMETERS.items()
    )


def _service(context: dict[str, Any]) -> Any:
    service = context.get("anomaly_service")
    if service is None:
        raise RuntimeError("The GridVision anomaly analysis service is unavailable.")
    return service


def _selected_run(context: dict[str, Any], run_id: str) -> dict[str, Any]:
    run = _service(context).get_run(run_id)
    if run is None:
        raise ValueError(f"Anomaly run '{run_id}' was not found.")
    return run


def _authorized_customers(context: dict[str, Any], persona: str) -> set[int] | None:
    if persona == "government":
        return None
    allowed = context.get("authorized_customer_ids")
    if not isinstance(allowed, (set, list, tuple)) or not allowed:
        raise ToolPermissionError(
            "Customer-scoped anomaly data requires an authenticated customer "
            "authorization context."
        )
    return {int(customer_id) for customer_id in allowed}


def _run_items(run: dict[str, Any], key: str) -> list[dict[str, Any]]:
    items = run.get(key)
    return items if isinstance(items, list) else []


def _run_is_in_scope(run: dict[str, Any], context: dict[str, Any]) -> bool:
    if context["persona"] == "government":
        return True
    authorized = _authorized_customers(context, context["persona"])
    request = run.get("request", {})
    requested_ids = request.get("customer_ids")
    if isinstance(requested_ids, list) and authorized.intersection(
        int(value) for value in requested_ids
    ):
        return True
    return any(
        _filter_customer_records(_run_items(run, key), authorized)
        for key in ("events", "anomaly_windows")
    )


def _list_runs(args: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
    runs = _service(context).list_runs(
        limit=max(1, min(int(args.get("limit", 25)), 100))
    )
    if context["persona"] == "government":
        return runs
    visible_runs = []
    for run in runs:
        completed = _selected_run(context, str(run["analysis_id"])) if run.get("status") == "completed" else run
        if _run_is_in_scope(completed, context):
            visible_runs.append(run)
    return [
        {
            "analysis_id": run.get("analysis_id"),
            "status": run.get("status"),
            "created_at": run.get("created_at"),
            "updated_at": run.get("updated_at"),
            "start_date": run.get("request", {}).get("start_date"),
            "end_date": run.get("request", {}).get("end_date"),
        }
        for run in visible_runs
    ]


def _run_status(args: dict[str, Any], context: dict[str, Any]) -> dict[str, Any] | None:
    run = _service(context).analysis_store.get(args["run_id"])
    if run is None or context["persona"] == "government":
        return run
    if run.get("status") == "completed":
        run = _selected_run(context, args["run_id"])
    if not _run_is_in_scope(run, context):
        raise ToolPermissionError("This analysis run is outside the authenticated user's scope.")
    request = run.get("request", {})
    return {
        "analysis_id": run.get("analysis_id"),
        "status": run.get("status"),
        "created_at": run.get("created_at"),
        "updated_at": run.get("updated_at"),
        "request": {
            "start_date": request.get("start_date"),
            "end_date": request.get("end_date"),
        },
    }


def _filter_customer_records(
    records: list[dict[str, Any]],
    authorized_ids: set[int] | None,
    customer_key: str = "customer_id",
) -> list[dict[str, Any]]:
    if authorized_ids is None:
        return records
    filtered: list[dict[str, Any]] = []
    for record in records:
        candidate = record.get(customer_key)
        if candidate is None:
            candidate = record.get("customer_ids", [])
        if isinstance(candidate, list):
            matching_ids = [
                value for value in candidate if _is_authorized_customer(value, authorized_ids)
            ]
            intersects = bool(matching_ids)
        else:
            try:
                intersects = _is_authorized_customer(candidate, authorized_ids)
            except (TypeError, ValueError):
                intersects = False
        if intersects:
            safe_record = dict(record)
            if isinstance(candidate, list):
                safe_record["customer_ids"] = matching_ids
                if len(matching_ids) != len(candidate):
                    safe_record["affected_customer_count"] = len(matching_ids)
                    for key in (
                        "affected_customer_percentage",
                        "anomaly_type_distribution",
                        "spatial_cluster_count",
                        "spatial_cluster_ids",
                        "spatial_clusters",
                        "h3_cells",
                        "latitude_center",
                        "longitude_center",
                        "spatial_extent_km",
                    ):
                        safe_record.pop(key, None)
            filtered.append(safe_record)
    return filtered


def _is_authorized_customer(value: Any, authorized_ids: set[int]) -> bool:
    try:
        return int(value) in authorized_ids
    except (TypeError, ValueError):
        return False


def _make_tool(
    name: str,
    description: str,
    properties: dict[str, Any],
    handler: Any,
    *,
    required: list[str] | None = None,
    personas: frozenset[str] = GOVERNMENT_ONLY,
    side_effects: bool = False,
    confirm: bool = False,
    require_auth: bool = False,
) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description=description,
        input_schema={
            "type": "object",
            "properties": properties,
            "required": required or [],
            "additionalProperties": False,
        },
        handler=handler,
        allowed_personas=personas,
        side_effects=side_effects,
        user_confirmation_required=confirm,
        requires_authenticated_principal=require_auth,
    )


def build_registry() -> ToolRegistry:
    registry = ToolRegistry()

    registry.register(
        _make_tool(
            "list_available_runs",
            "List saved anomaly analysis runs and their statuses.",
            {"limit": {"type": "integer"}},
            _list_runs,
            personas=GOVERNMENT_ONLY,
        )
    )

    def find_run(args: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        target = date.fromisoformat(args["target_date"])
        start, end = dataset_date_bounds(_service(context))
        if target < start or target > end:
            raise ValueError(
                f"The available anomaly dataset covers {start.isoformat()} through "
                f"{end.isoformat()}; no run can be queried for {target.isoformat()}."
            )
        candidates = []
        for run in _service(context).list_runs(limit=100):
            scoped_run = (
                _selected_run(context, str(run["analysis_id"]))
                if run.get("status") == "completed"
                else run
            )
            if not _run_is_in_scope(scoped_run, context):
                continue
            request = run.get("request", {})
            try:
                run_start = date.fromisoformat(request["start_date"])
                run_end = date.fromisoformat(request["end_date"])
            except (KeyError, TypeError, ValueError):
                continue
            if run.get("status") == "completed" and run_start <= target <= run_end:
                candidates.append(
                    {
                        "run_id": run.get("analysis_id"),
                        "status": run.get("status"),
                        "start_date": run_start.isoformat(),
                        "end_date": run_end.isoformat(),
                    }
                )
        return {
            "target_date": target.isoformat(),
            "available": bool(candidates),
            "runs": candidates,
            "message": None if candidates else "No completed run covers this date.",
        }

    registry.register(
        _make_tool(
            "find_run_by_date",
            "Find completed saved analysis runs covering a dataset date.",
            {"target_date": {"type": "string"}},
            find_run,
            required=["target_date"],
            personas=GOVERNMENT_ONLY,
        )
    )

    def find_runs_for_period(
        args: dict[str, Any], context: dict[str, Any]
    ) -> dict[str, Any]:
        start, end = validate_requested_dates(
            _service(context), args["start_date"], args["end_date"]
        )
        intervals: list[tuple[date, date, str]] = []
        for summary in _service(context).list_runs(limit=1000):
            if summary.get("status") != "completed":
                continue
            run = _selected_run(context, str(summary["analysis_id"]))
            if not _compatible_run_parameters(run):
                continue
            if not _run_is_in_scope(run, context):
                continue
            request = run.get("request", {})
            try:
                run_start = date.fromisoformat(request["start_date"])
                run_end = date.fromisoformat(request["end_date"])
            except (KeyError, TypeError, ValueError):
                continue
            if run_start <= end and run_end >= start:
                intervals.append((run_start, run_end, str(summary["analysis_id"])))

        intervals.sort(key=lambda item: (item[0], item[1]))
        covered_through = start - timedelta(days=1)
        covering_ids: list[str] = []
        for run_start, run_end, run_id in intervals:
            if run_start > covered_through + timedelta(days=1):
                break
            if run_end > covered_through:
                covered_through = run_end
                covering_ids.append(run_id)
            if covered_through >= end:
                break

        complete = covered_through >= end
        return {
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "available": complete,
            "run_ids": covering_ids if complete else [],
            "message": None if complete else "No completed saved analysis covers the full requested period.",
        }

    registry.register(
        _make_tool(
            "find_runs_for_period",
            "Find completed saved analysis runs that collectively cover a date period.",
            {"start_date": {"type": "string"}, "end_date": {"type": "string"}},
            find_runs_for_period,
            required=["start_date", "end_date"],
            personas=GOVERNMENT_ONLY,
        )
    )
    registry.register(
        _make_tool(
            "get_run_details",
            "Return a completed run's detailed saved results.",
            {"run_id": {"type": "string"}},
            lambda args, ctx: _selected_run(ctx, args["run_id"]),
            required=["run_id"],
            personas=GOVERNMENT_ONLY,
        )
    )
    registry.register(
        _make_tool(
            "get_run_status",
            "Return the current persisted status of one analysis run.",
            {"run_id": {"type": "string"}},
            _run_status,
            required=["run_id"],
            personas=GOVERNMENT_ONLY,
        )
    )

    def run_query(args: dict[str, Any], context: dict[str, Any], record_key: str) -> dict[str, Any]:
        service = _service(context)
        start, end = validate_requested_dates(
            service, args["start_date"], args["end_date"], max_days=366
        )
        authorized = _authorized_customers(context, context["persona"])
        runs = sorted(
            service.list_runs(limit=1000),
            key=lambda item: str(item.get("created_at", "")),
            reverse=True,
        )
        matching = []
        records: list[dict[str, Any]] = []
        seen_records: set[tuple[str, ...]] = set()
        for summary in runs:
            request = summary.get("request", {})
            try:
                run_start = date.fromisoformat(request["start_date"])
                run_end = date.fromisoformat(request["end_date"])
            except (KeyError, TypeError, ValueError):
                continue
            if summary.get("status") != "completed" or run_start > end or run_end < start:
                continue
            run = _selected_run(context, str(summary["analysis_id"]))
            run_records = [
                item
                for item in _run_items(run, record_key)
                if start.isoformat()
                <= str(
                    item.get(
                        "start_time",
                        item.get(
                            "anomaly_start",
                            item.get("event_start", item.get("timestamp", "9999")),
                        ),
                    )
                )[:10]
                <= end.isoformat()
            ]
            run_records = _filter_customer_records(run_records, authorized)
            if run_records or authorized is None:
                matching.append(str(summary["analysis_id"]))
                for item in run_records:
                    if record_key == "events":
                        identity = (
                            str(item.get("event_start", "")),
                            str(item.get("event_end", "")),
                            str(item.get("event_scope", "")),
                            ",".join(sorted(str(value) for value in item.get("customer_ids", []))),
                            str(item.get("latitude_center", "")),
                            str(item.get("longitude_center", "")),
                            ",".join(sorted(str(value) for value in item.get("anomaly_types", []))),
                        )
                    else:
                        identity = (
                            str(item.get("customer_id", "")),
                            str(item.get("anomaly_start", item.get("start_time", ""))),
                            str(item.get("anomaly_end", item.get("end_time", ""))),
                            str(item.get("anomaly_type", "")),
                            str(item.get("latitude", "")),
                            str(item.get("longitude", "")),
                        )
                    if identity not in seen_records:
                        seen_records.add(identity)
                        records.append(
                            {**item, "run_id": str(summary["analysis_id"])}
                        )
        return {
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "run_ids": matching,
            "count": len(records),
            "items": records,
        }

    def limited_run_query(
        args: dict[str, Any], context: dict[str, Any], record_key: str
    ) -> dict[str, Any]:
        result = run_query(args, context, record_key)
        result["items"] = result["items"][
            : max(1, min(int(args.get("limit", 100)), 1000))
        ]
        return result

    for tool_name, record_key, description in (
        ("query_anomalies", "anomaly_windows", "Query saved anomaly windows for a date range."),
        ("query_events", "events", "Query saved localized anomaly events for a date range."),
    ):
        registry.register(
            _make_tool(
                tool_name,
                description,
                {
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                lambda args, ctx, key=record_key: limited_run_query(args, ctx, key),
                required=["start_date", "end_date"],
                personas=GOVERNMENT_ONLY,
            )
        )

    def get_event(args: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        run = _selected_run(context, args["run_id"])
        event = next(
            (
                item
                for item in _run_items(run, "events")
                if str(item.get("event_id", item.get("id", ""))) == args["event_id"]
            ),
            None,
        )
        if event is None:
            raise ValueError(f"Event '{args['event_id']}' was not found in this run.")
        permitted = _authorized_customers(context, context["persona"])
        filtered = _filter_customer_records([event], permitted)
        if not filtered:
            raise ToolPermissionError("This event is outside the authenticated user's scope.")
        return filtered[0]

    registry.register(
        _make_tool(
            "get_event_details",
            "Get a saved event from a specific completed run.",
            {"run_id": {"type": "string"}, "event_id": {"type": "string"}},
            get_event,
            required=["run_id", "event_id"],
            personas=GOVERNMENT_ONLY,
        )
    )

    def find_event(args: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        event_id = str(args["event_id"])
        matches: list[dict[str, Any]] = []
        for summary in _service(context).list_runs(limit=1000):
            if summary.get("status") != "completed":
                continue
            run_id = str(summary.get("analysis_id", ""))
            run = _selected_run(context, run_id)
            if not _compatible_run_parameters(run):
                continue
            event = next(
                (
                    item
                    for item in _run_items(run, "events")
                    if str(item.get("event_id", item.get("id", ""))) == event_id
                ),
                None,
            )
            if event is not None:
                request = run.get("request", {})
                matches.append(
                    {
                        **event,
                        "run_id": run_id,
                        "source_start_date": request.get("start_date"),
                        "source_end_date": request.get("end_date"),
                    }
                )
        if not matches:
            raise ValueError(
                f"Event '{event_id}' was not found in a compatible completed run."
            )
        if len(matches) > 1:
            raise ValueError(
                f"Event ID '{event_id}' exists in multiple runs. Include the "
                "saved run ID or date period to disambiguate it."
            )
        return matches[0]

    registry.register(
        _make_tool(
            "find_event_by_id",
            "Find a saved localized event by its event ID.",
            {"event_id": {"type": "string"}},
            find_event,
            required=["event_id"],
            personas=GOVERNMENT_ONLY,
        )
    )
    registry.register(
        _make_tool(
            "get_event_timeline",
            "Return saved anomaly windows associated with an event.",
            {"run_id": {"type": "string"}, "event_id": {"type": "string"}},
            lambda args, ctx: {
                "event": get_event(args, ctx),
                "timeline": [
                    window
                    for window in _filter_customer_records(
                        _run_items(_selected_run(ctx, args["run_id"]), "anomaly_windows"),
                        _authorized_customers(ctx, ctx["persona"]),
                    )
                    if str(window.get("event_id", "")) == args["event_id"]
                ],
            },
            required=["run_id", "event_id"],
            personas=GOVERNMENT_ONLY,
        )
    )

    def customer_impact(args: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        permitted = _authorized_customers(context, context["persona"])
        customer_id = int(args["customer_id"])
        if permitted is not None and customer_id not in permitted:
            raise ToolPermissionError("This customer is outside the authenticated user's scope.")
        run = _selected_run(context, args["run_id"])
        windows = _filter_customer_records(
            _run_items(run, "anomaly_windows"), {customer_id}
        )
        return {"run_id": args["run_id"], "customer_id": customer_id, "items": windows}

    registry.register(
        _make_tool(
            "query_customer_impact",
            "Query a customer’s impact records from a saved analysis run.",
            {"run_id": {"type": "string"}, "customer_id": {"type": "integer"}},
            customer_impact,
            required=["run_id", "customer_id"],
            personas=GOVERNMENT_ONLY,
        )
    )
    registry.register(
        _make_tool(
            "get_localization_metrics",
            "Return saved spatial-event localization metrics for a run.",
            {"run_id": {"type": "string"}},
            lambda args, ctx: {
                "run_id": args["run_id"],
                "metrics": _selected_run(ctx, args["run_id"]).get("metrics", {}),
                "metadata": _selected_run(ctx, args["run_id"]).get("metadata", {}),
            },
            required=["run_id"],
            personas=GOVERNMENT_ONLY,
        )
    )

    def execute_analysis(args: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        service = _service(context)
        start, end = validate_requested_dates(
            service, args["start_date"], args["end_date"]
        )
        request = {
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "customer_ids": args.get("customer_ids"),
            **{
                key: args[key]
                for key in (
                    "h3_resolution",
                    "spatial_radius_km",
                    "maximum_start_time_difference_minutes",
                    "minimum_temporal_overlap",
                    "maximum_interval_gap_minutes",
                )
                if key in args
            },
        }
        return service.run_analysis(request)

    registry.register(
        _make_tool(
            "execute_anomaly_analysis",
            "Execute an explicitly requested 1–7 day analysis using existing defaults.",
            {
                "start_date": {"type": "string"},
                "end_date": {"type": "string"},
                "customer_ids": {"type": "array"},
                "h3_resolution": {"type": "integer"},
                "spatial_radius_km": {"type": "number"},
                "maximum_start_time_difference_minutes": {"type": "integer"},
                "minimum_temporal_overlap": {"type": "number"},
                "maximum_interval_gap_minutes": {"type": "integer"},
            },
            execute_analysis,
            required=["start_date", "end_date"],
            side_effects=True,
            confirm=True,
            personas=GOVERNMENT_ONLY,
        )
    )
    registry.register(
        _make_tool(
            "get_analysis_progress",
            "Read progress and status for a persisted analysis run.",
            {"run_id": {"type": "string"}},
            lambda args, ctx: _service(ctx).analysis_store.get(args["run_id"]),
            required=["run_id"],
            personas=GOVERNMENT_ONLY,
        )
    )
    registry.register(
        _make_tool(
            "get_analysis_configuration",
            "Return the supported per-run localization defaults.",
            {},
            lambda _args, _ctx: {
                "maximum_run_days": 7,
                "spatial_radius_km": 5.0,
                "h3_resolution": 8,
                "maximum_start_time_difference_minutes": 30,
                "minimum_interval_overlap": 0.25,
                "maximum_interval_gap_minutes": 60,
            },
            personas=ALL_PERSONAS,
            require_auth=False,
        )
    )

    def search_knowledge(args: dict[str, Any], _context: dict[str, Any]) -> list[dict[str, Any]]:
        from ai.anamoly.vector_store.retriever import KnowledgeRetriever

        return KnowledgeRetriever().search(
            args["query"], limit=int(args.get("limit", 5))
        )

    registry.register(
        _make_tool(
            "search_knowledge_base",
            "Search locally indexed technical and regulatory reference documents.",
            {"query": {"type": "string"}, "limit": {"type": "integer"}},
            search_knowledge,
            required=["query"],
            personas=ALL_PERSONAS,
            require_auth=False,
        )
    )

    def graph_search(args: dict[str, Any], context: dict[str, Any]) -> Any:
        from ai.anamoly.graph.graph_retriever import GraphRetriever

        retriever = GraphRetriever()
        if args.get("run_id"):
            run = _selected_run(context, args["run_id"])
            permitted = _authorized_customers(context, context["persona"])
            return retriever.search_with_run(
                args["query"],
                _filter_customer_records(_run_items(run, "events"), permitted),
                _filter_customer_records(
                    _run_items(run, "anomaly_windows"), permitted
                ),
                limit=int(args.get("limit", 5)),
            )
        return retriever.search(args["query"], limit=int(args.get("limit", 5)))

    registry.register(
        _make_tool(
            "retrieve_graph_context",
            "Expand knowledge search through shared anomaly, grid, and safety entities.",
            {
                "query": {"type": "string"},
                "limit": {"type": "integer"},
                "run_id": {"type": "string"},
            },
            graph_search,
            required=["query"],
            personas=ALL_PERSONAS,
            require_auth=False,
        )
    )
    return registry
