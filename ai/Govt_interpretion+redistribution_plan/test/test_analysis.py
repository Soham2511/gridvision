from __future__ import annotations

from datetime import datetime, timedelta
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest

from ai.assistant import analysis
from ai.assistant.assistant import (
    _ground_explicit_query_details,
    _langsmith_trace_inputs,
    _langsmith_trace_outputs,
    _multi_analysis_intents,
    handle_user_query,
    interpret_user_query,
)
from ai.assistant import assistant as assistant_module
from ai.assistant.schemas import QueryRequest


GRID_IDS = [
    9, 10, 11, 23, 24, 25, 30, 34, 35, 36, 37, 38, 39, 40, 41, 48, 49, 50,
    51, 52, 53, 54, 55, 62, 63, 64, 65, 66, 67, 68, 69, 76, 77, 78, 79, 80,
    82, 83, 91, 92, 93, 97, 105, 106, 107, 110, 111, 120, 121, 124, 125,
    135, 136,
]


class FakeLLM:
    provider = "fake"
    model = "test"

    def __init__(self, outputs: list[str]) -> None:
        self.outputs = list(outputs)
        self.messages: list[list[dict[str, str]]] = []

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        json_mode: bool = False,
    ) -> str:
        self.messages.append(messages)
        return self.outputs.pop(0)


def _request_json(
    *,
    intent: str,
    forecast_date: str | None = None,
    output_formats: list[str] | None = None,
) -> str:
    return json.dumps(
        {
            "intent": intent,
            "forecast_date": forecast_date,
            "start_timestamp": None,
            "duration_hours": None,
            "grid_ids": [],
            "output_formats": output_formats or ["text"],
            "needs_clarification": False,
            "clarification_question": None,
        }
    )


def _small_historical_parquet(path: Path) -> Path:
    rows = []
    start = datetime(2018, 9, 25, 1)
    for grid_id in GRID_IDS:
        for hour in range(23):
            rows.append(
                {
                    "id.grid.coarse": grid_id,
                    "timestamp": start + timedelta(hours=hour),
                    "total_normalized_building_energy_kwh": float(grid_id + hour),
                }
            )
    pd.DataFrame(rows).to_parquet(path, index=False)
    return path


def _forecast_frame() -> pd.DataFrame:
    start = datetime(2018, 9, 25)
    return pd.DataFrame(
        [
            {
                "id.grid.coarse": grid_id,
                "target_timestamp": start + timedelta(hours=hour),
                "predicted_demand_kwh": 100.0,
            }
            for grid_id in GRID_IDS
            for hour in range(24)
        ]
    )


def test_historical_summary_filters_to_requested_grid_and_date(
    tmp_path: Path,
) -> None:
    data_path = _small_historical_parquet(tmp_path / "historical.parquet")

    summary = analysis.historical_demand_summary(
        "2018-09-25",
        "2018-09-25",
        [64],
        historical_data_path=data_path,
    )

    assert summary["source"] == "historical_measurements"
    assert summary["grid_ids"] == [64]
    assert summary["grid_count"] == 1
    assert summary["interval_count"] == 23
    assert summary["total_demand_kwh"] == pytest.approx(sum(64 + hour for hour in range(23)))


def test_historical_summary_rejects_non_2018_data(tmp_path: Path) -> None:
    data_path = _small_historical_parquet(tmp_path / "historical.parquet")

    with pytest.raises(analysis.EnergyAnalysisError, match="Only energy data from 2018"):
        analysis.historical_demand_summary(
            "2019-01-01",
            "2019-01-01",
            historical_data_path=data_path,
        )


def test_historical_summary_filters_an_explicit_hour_window(tmp_path: Path) -> None:
    data_path = _small_historical_parquet(tmp_path / "historical.parquet")

    summary = analysis.historical_demand_summary(
        "2018-09-25",
        "2018-09-25",
        [64],
        start_timestamp="2018-09-25T05:00:00",
        duration_hours=2,
        historical_data_path=data_path,
    )

    assert summary["interval_count"] == 2
    assert summary["covered_start_timestamp"] == "2018-09-25T05:00:00"
    assert summary["covered_end_timestamp"] == "2018-09-25T06:00:00"
    assert summary["total_demand_kwh"] == pytest.approx((64 + 4) + (64 + 5))


def test_analysis_image_is_created_from_selected_grid_rows(tmp_path: Path) -> None:
    data_path = _small_historical_parquet(tmp_path / "historical.parquet")
    summary = analysis.historical_demand_summary(
        "2018-09-25",
        "2018-09-25",
        [64],
        historical_data_path=data_path,
    )

    image_path = analysis.save_analysis_image(summary, output_dir=tmp_path / "charts")

    assert image_path.is_file()
    assert image_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_saved_model_forecast_is_cached_and_scoped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai import redistribution

    calls: list[datetime] = []
    monkeypatch.setattr(redistribution, "load_hybrid_model", lambda _path: object())

    def fake_generate_forecast(_model: Any, **kwargs: Any) -> pd.DataFrame:
        calls.append(kwargs["origin"])
        return _forecast_frame()

    monkeypatch.setattr(redistribution, "generate_forecast", fake_generate_forecast)
    result = analysis.forecast_demand_for_date(
        "2018-09-25",
        [64],
        start_timestamp="2018-09-25T05:00:00",
        duration_hours=2,
        simulations_dir=tmp_path / "no-plans",
        forecast_data_path=tmp_path / "features.parquet",
        model_path=tmp_path / "model.joblib",
        output_dir=tmp_path / "cache",
    )

    assert calls == [datetime(2018, 9, 24, 23)]
    assert result["grid_ids"] == [64]
    assert result["grid_count"] == 1
    assert result["interval_count"] == 2
    assert result["total_predicted_demand_kwh"] == pytest.approx(200)
    assert analysis._prediction_cache_path(
        datetime(2018, 9, 25).date(), tmp_path / "cache"
    ).is_file()


def test_comparison_uses_only_matching_observed_and_predicted_hours(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_path = _small_historical_parquet(tmp_path / "historical.parquet")
    monkeypatch.setattr(analysis, "DEFAULT_HISTORICAL_DATA_PATH", data_path)
    monkeypatch.setattr(
        analysis,
        "_forecast_frame_for_date",
        lambda *_args, **_kwargs: _forecast_frame(),
    )

    result = analysis.compare_historical_and_predicted_demand(
        "2018-09-25",
        [64],
    )

    grid = result["grid_totals"][0]
    assert result["grid_ids"] == [64]
    assert result["interval_count"] == 23
    assert grid["interval_count"] == 23
    assert grid["historical_demand_kwh"] == pytest.approx(sum(64 + hour for hour in range(23)))
    assert grid["predicted_demand_kwh"] == pytest.approx(2300)
    assert result["coverage_complete"] is False
    assert result["matched_grid_timestamp_pairs"] == 23
    assert result["missing_grid_timestamp_pair_count"] == 1
    assert result["network_accuracy"]["coverage_complete"] is False
    assert result["network_accuracy"]["wape_pct"] == pytest.approx(
        sum(abs(100 - (64 + hour)) for hour in range(23))
        / sum(64 + hour for hour in range(23))
        * 100
    )
    assert grid["mae_kwh"] == pytest.approx(
        sum(abs(100 - (64 + hour)) for hour in range(23)) / 23
    )
    assert grid["rmse_kwh"] == pytest.approx(
        (sum((100 - (64 + hour)) ** 2 for hour in range(23)) / 23) ** 0.5
    )


def test_comparison_handles_zero_actual_values_without_percentage_metrics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_path = tmp_path / "zero_actuals.parquet"
    pd.DataFrame(
        [
            {
                "id.grid.coarse": grid_id,
                "timestamp": datetime(2018, 9, 25),
                "total_normalized_building_energy_kwh": (
                    0.0 if grid_id == 64 else float(grid_id)
                ),
            }
            for grid_id in GRID_IDS
        ]
    ).to_parquet(data_path, index=False)
    monkeypatch.setattr(analysis, "DEFAULT_HISTORICAL_DATA_PATH", data_path)
    monkeypatch.setattr(
        analysis,
        "_forecast_frame_for_date",
        lambda *_args, **_kwargs: _forecast_frame(),
    )

    result = analysis.compare_historical_and_predicted_demand(
        "2018-09-25",
        [64],
    )

    grid = result["grid_totals"][0]
    assert grid["mape_pct"] is None
    assert grid["wape_pct"] is None
    assert grid["mape_valid_interval_count"] == 0
    assert grid["mae_kwh"] == pytest.approx(100)
    assert result["network_accuracy"]["mape_pct"] is None
    assert result["network_accuracy"]["wape_pct"] is None
    assert result["coverage_complete"] is False
    assert result["missing_grid_timestamp_pair_count"] == 23


def test_slim_cached_forecast_reuses_predictions_and_restores_plan_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target_date = datetime(2018, 9, 25).date()
    cache_dir = tmp_path / "cache"
    cache_path = analysis._prediction_cache_path(target_date, cache_dir)
    cache_path.parent.mkdir(parents=True)
    cached = _forecast_frame()
    cached.to_parquet(cache_path, index=False)

    origin = datetime(2018, 9, 24, 23)
    feature_rows = []
    for grid_id in GRID_IDS:
        for horizon in range(1, 25):
            feature_rows.append(
                {
                    "id.grid.coarse": grid_id,
                    "forecast_origin_timestamp": origin,
                    "target_timestamp": origin + timedelta(hours=horizon),
                    "forecast_horizon_hours": horizon,
                    "centroid_latitude": 40.0 + grid_id / 1000,
                    "centroid_longitude": -75.0 - grid_id / 1000,
                }
            )
    features_path = tmp_path / "features.parquet"
    pd.DataFrame(feature_rows).to_parquet(features_path, index=False)
    model = SimpleNamespace(routing={grid_id: "original" for grid_id in GRID_IDS})
    monkeypatch.setattr(analysis, "_load_hybrid_model", lambda _path: model)

    restored = analysis._forecast_frame_for_date(
        target_date,
        simulations_dir=tmp_path / "plans",
        forecast_data_path=features_path,
        model_path=tmp_path / "model.joblib",
        output_dir=cache_dir,
    )

    assert len(restored) == 53 * 24
    assert set(restored["selected_model"]) == {"original"}
    assert set(restored["forecast_horizon_hours"]) == set(range(1, 25))
    assert restored["predicted_demand_kwh"].tolist() == cached[
        "predicted_demand_kwh"
    ].tolist()
    assert restored["centroid_latitude"].notna().all()


def test_analysis_period_respects_explicit_until_dates_and_slash_dates() -> None:
    from ai.assistant.assistant import _parse_analysis_period

    assert _parse_analysis_period(
        "Compare historical and predicted demand from 2018-09-25 until 2018-09-27"
    ) == ("2018-09-25", "2018-09-27")
    assert _parse_analysis_period("Historical demand on 04/04/2018") == (
        "2018-04-04",
        "2018-04-04",
    )


def test_date_only_redistribution_plan_resolves_to_full_day() -> None:
    query_llm = FakeLLM([_request_json(intent="plan")])

    request = interpret_user_query(
        "Show the redistribution plan for 04/04/2018",
        query_llm,
        available={
            "available_forecast_dates": [],
            "timestamps_by_date": {},
            "grid_ids_by_date": {},
            "historical_data": {"grid_ids": GRID_IDS},
        },
    )

    assert request.intent == "summary"
    assert request.forecast_date == "2018-04-04"
    assert request.duration_hours == 24
    assert not request.needs_clarification


def test_missing_date_plan_ignores_available_date_clarification_and_routes_for_generation() -> None:
    clarification = json.dumps(
        {
            "intent": "clarification",
            "forecast_date": "2018-05-03",
            "start_timestamp": None,
            "duration_hours": None,
            "grid_ids": [],
            "output_formats": ["text"],
            "needs_clarification": True,
            "clarification_question": (
                "The requested date is not available in the simulation data."
            ),
        }
    )
    query_llm = FakeLLM([clarification])
    available = {
        "available_forecast_dates": ["2018-09-25"],
        "timestamps_by_date": {
            "2018-09-25": [
                f"2018-09-25T{hour:02d}:00:00" for hour in range(24)
            ]
        },
        "grid_ids_by_date": {"2018-09-25": GRID_IDS},
        "historical_data": {"grid_ids": GRID_IDS},
    }

    request = interpret_user_query(
        "Can you give me info about 5/3/2018 redistributuoion plan?",
        query_llm,
        available=available,
    )

    assert request.forecast_date == "2018-05-03"
    assert request.intent == "summary"
    assert request.duration_hours == 24
    assert not request.needs_clarification


def test_slash_dates_prefer_month_day_when_both_values_are_valid_months() -> None:
    from ai.assistant.assistant import _parse_date_token

    assert _parse_date_token("5/3/2018") == datetime(2018, 5, 3).date()
    assert _parse_date_token("13/3/2018") == datetime(2018, 3, 13).date()


def test_plan_generation_follow_up_uses_pending_clarification_context() -> None:
    from ai.assistant.assistant import _is_pending_plan_follow_up

    pending = QueryRequest(
        intent="plan",
        forecast_date="2018-05-03",
        start_timestamp=None,
        duration_hours=24,
        grid_ids=[],
        output_formats=["text"],
        needs_clarification=True,
        clarification_question="The date is not in the saved plans.",
    )
    history = {
        "turns": [{"request": pending.model_dump(mode="json")}],
    }

    assert _is_pending_plan_follow_up(
        "Please generate date for 5/3/2018 then give me info",
        history,
    )


def test_plan_generation_follow_up_resolves_from_pending_chat_turn() -> None:
    pending = QueryRequest(
        intent="plan",
        forecast_date="2018-05-03",
        start_timestamp=None,
        duration_hours=24,
        grid_ids=[],
        output_formats=["text"],
        needs_clarification=True,
        clarification_question="The date is not in the saved plans.",
    )
    clarification = json.dumps(
        {
            "intent": "clarification",
            "forecast_date": None,
            "start_timestamp": None,
            "duration_hours": None,
            "grid_ids": [],
            "output_formats": ["text"],
            "needs_clarification": True,
            "clarification_question": "Which date should I use?",
        }
    )

    request = interpret_user_query(
        "Please generate date for 5/3/2018 then give me info",
        FakeLLM([clarification]),
        available={
            "available_forecast_dates": ["2018-09-25"],
            "timestamps_by_date": {
                "2018-09-25": [
                    f"2018-09-25T{hour:02d}:00:00" for hour in range(24)
                ]
            },
            "grid_ids_by_date": {"2018-09-25": GRID_IDS},
            "historical_data": {"grid_ids": GRID_IDS},
        },
        history={
            "turns": [{"request": pending.model_dump(mode="json")}],
            "last_successful_request": None,
        },
    )

    assert request.intent == "summary"
    assert request.forecast_date == "2018-05-03"
    assert request.duration_hours == 24
    assert not request.needs_clarification


def test_new_plan_date_is_generated_then_used_to_answer_query(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai.assistant.data import RetrievedRecords

    clarification = json.dumps(
        {
            "intent": "clarification",
            "forecast_date": "2018-05-03",
            "start_timestamp": None,
            "duration_hours": None,
            "grid_ids": [],
            "output_formats": ["text"],
            "needs_clarification": True,
            "clarification_question": "That date is not in the saved plans.",
        }
    )
    timestamps = [f"2018-05-03T{hour:02d}:00:00" for hour in range(24)]
    initial_available = {
        "available_forecast_dates": ["2018-09-25"],
        "timestamps_by_date": {
            "2018-09-25": [
                f"2018-09-25T{hour:02d}:00:00" for hour in range(24)
            ]
        },
        "grid_ids_by_date": {"2018-09-25": GRID_IDS},
        "historical_data": {"grid_ids": GRID_IDS},
    }
    generated_available = {
        **initial_available,
        "available_forecast_dates": ["2018-05-03", "2018-09-25"],
        "timestamps_by_date": {
            **initial_available["timestamps_by_date"],
            "2018-05-03": timestamps,
        },
        "grid_ids_by_date": {
            **initial_available["grid_ids_by_date"],
            "2018-05-03": GRID_IDS,
        },
    }
    context_calls = 0
    generation_calls: list[tuple[str, Path]] = []

    def available_context(_directory: str | Path) -> dict[str, Any]:
        nonlocal context_calls
        context_calls += 1
        return initial_available if context_calls == 1 else generated_available

    grids_per_hour = [
        {
            "grid_id": grid_id,
            "predicted_demand_kwh": 10.0,
            "synthetic_supply_kwh": 10.0,
            "initial_surplus_kwh": 0.0,
            "initial_deficit_kwh": 0.0,
            "energy_sent_kwh": 0.0,
            "energy_received_kwh": 0.0,
            "transmission_losses_kwh": 0.0,
            "remaining_surplus_kwh": 0.0,
            "unmet_demand_kwh": 0.0,
        }
        for grid_id in GRID_IDS
    ]
    records = RetrievedRecords(
        forecast_date="2018-05-03",
        intent="summary",
        requested_grid_ids=(),
        hourly_records=[
            {"timestamp": timestamp, "grids": grids_per_hour}
            for timestamp in timestamps
        ],
        transfers=[],
        network={},
        simulation_metadata={},
    )
    monkeypatch.setattr(assistant_module, "_available_context", available_context)
    monkeypatch.setattr(
        assistant_module,
        "_ensure_simulation_plan",
        lambda target, directory: (
            generation_calls.append((target, Path(directory)))
            or tmp_path / "redistribution_plan_2018-05-03.json"
        ),
    )
    monkeypatch.setattr(
        assistant_module,
        "retrieve_relevant_records",
        lambda *_args, **_kwargs: records,
    )
    monkeypatch.setattr(
        assistant_module,
        "generate_explanation",
        lambda *_args, **_kwargs: "Here is the requested simulated daily plan.",
    )
    monkeypatch.setattr(
        assistant_module,
        "generate_csv",
        lambda *_args, **_kwargs: tmp_path / "plan.csv",
    )
    monkeypatch.setattr(
        assistant_module,
        "generate_image",
        lambda *_args, **_kwargs: tmp_path / "plan.png",
    )

    result = handle_user_query(
        "Can you give me info about 5/3/2018 redistributuoion plan?",
        query_llm=FakeLLM([clarification]),
        response_llm=FakeLLM([]),
        simulations_dir=tmp_path / "plans",
        artifacts_dir=tmp_path / "artifacts",
        history_path=tmp_path / "history.json",
        log_path=tmp_path / "assistant.log",
    )

    assert generation_calls == [
        ("2018-05-03", tmp_path / "plans"),
    ]
    assert result.request is not None
    assert result.request.forecast_date == "2018-05-03"
    assert result.request.intent == "summary"
    assert not result.clarification_needed
    assert "requested simulated daily plan" in result.text
    assert "2018-05-03" in result.text


def test_history_grid_follow_up_keeps_analysis_range() -> None:
    previous = QueryRequest(
        intent="historical_analysis",
        forecast_date=None,
        start_timestamp=None,
        duration_hours=None,
        grid_ids=[64],
        output_formats=["text"],
        needs_clarification=False,
        clarification_question=None,
        analysis_start_date="2018-09-01",
        analysis_end_date="2018-09-30",
    )
    current = QueryRequest(
        intent="follow_up",
        forecast_date=None,
        start_timestamp=None,
        duration_hours=None,
        grid_ids=[],
        output_formats=["text"],
        needs_clarification=False,
        clarification_question=None,
    )
    grounded = _ground_explicit_query_details(
        "What about Grid 64?",
        current,
        history={"last_successful_request": previous},
    )

    assert grounded.intent == "historical_analysis"
    assert grounded.grid_ids == [64]
    assert grounded.analysis_start_date == "2018-09-01"
    assert grounded.analysis_end_date == "2018-09-30"


def test_analytical_follow_up_does_not_require_a_redistribution_plan() -> None:
    previous = QueryRequest(
        intent="historical_analysis",
        forecast_date=None,
        start_timestamp=None,
        duration_hours=None,
        grid_ids=[23],
        output_formats=["text"],
        needs_clarification=False,
        clarification_question=None,
        analysis_start_date="2018-09-01",
        analysis_end_date="2018-09-30",
    )
    query_llm = FakeLLM(
        [
            _request_json(
                intent="follow_up",
                output_formats=["text"],
            )
        ]
    )

    request = interpret_user_query(
        "What about Grid 64?",
        query_llm,
        available={
            "available_forecast_dates": [],
            "timestamps_by_date": {},
            "grid_ids_by_date": {},
        },
        history={"turns": [], "last_successful_request": previous},
    )

    assert not request.needs_clarification
    assert request.intent == "historical_analysis"
    assert request.grid_ids == [64]
    assert request.analysis_start_date == "2018-09-01"
    assert request.analysis_end_date == "2018-09-30"


def test_langsmith_trace_payloads_exclude_query_and_response_content() -> None:
    query = "Review Grid 64 demand for 2018-09-25"
    trace_inputs = _langsmith_trace_inputs({"query": query, "provider": "ollama"})

    class Result:
        csv_path = Path("/private/path.csv")
        image_path = None
        clarification_needed = False
        text = "Sensitive response content"

    trace_outputs = _langsmith_trace_outputs(Result())

    assert trace_inputs == {"query_length": len(query)}
    assert query not in repr(trace_inputs)
    assert "Sensitive response content" not in repr(trace_outputs)
    assert trace_outputs == {
        "status": "completed",
        "has_csv": True,
        "has_image": False,
        "needs_clarification": False,
    }


def test_optional_langsmith_wrapper_uses_redacted_payloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_traceable(**options: Any) -> Any:
        def decorate(handler: Any) -> Any:
            def traced(*args: Any, **kwargs: Any) -> Any:
                captured["inputs"] = options["process_inputs"](
                    {"args": args, "kwargs": kwargs}
                )
                output = handler(*args, **kwargs)
                captured["outputs"] = options["process_outputs"](output)
                return output

            return traced

        return decorate

    class FakeClient:
        def __init__(self, *, api_key: str) -> None:
            captured["client_key"] = api_key

    @contextmanager
    def fake_tracing_context(**options: Any) -> Any:
        captured["trace_context"] = options
        yield

    monkeypatch.setitem(
        sys.modules,
        "langsmith",
        SimpleNamespace(
            Client=FakeClient,
            traceable=fake_traceable,
            tracing_context=fake_tracing_context,
        ),
    )
    monkeypatch.setenv("GOVT_ASSISTANT_LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-langsmith-key")
    monkeypatch.setattr(assistant_module, "_LANGSMITH_TRACE_HANDLER", None)
    monkeypatch.setattr(assistant_module, "_LANGSMITH_TRACE_CONTEXT", None)
    monkeypatch.setattr(assistant_module, "_LANGSMITH_CLIENT", None)
    traced_handler = assistant_module._with_optional_langsmith_trace(
        lambda query: assistant_module.AssistantResult(
            text=f"response contains: {query}"
        )
    )

    traced_handler("private question")

    assert captured["inputs"] == {"query_length": len("private question")}
    assert "private question" not in repr(captured)
    assert captured["client_key"] == "test-langsmith-key"
    assert captured["trace_context"]["enabled"] is True
    assert captured["trace_context"]["project_name"] == "GridVision-Government-Assistant"
    assert captured["outputs"]["status"] == "completed"


def test_optional_langsmith_wrapper_reads_key_file_only_when_enabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key_path = tmp_path / "langsmith.key"
    key_path.write_text("test-langsmith-key\n", encoding="utf-8")
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    monkeypatch.setenv("GOVT_ASSISTANT_LANGSMITH_TRACING", "true")
    monkeypatch.setattr(assistant_module, "DEFAULT_LANGSMITH_KEY_PATH", key_path)
    monkeypatch.setattr(assistant_module, "_LANGSMITH_TRACE_HANDLER", None)
    monkeypatch.setattr(assistant_module, "_LANGSMITH_TRACE_CONTEXT", None)
    monkeypatch.setattr(assistant_module, "_LANGSMITH_CLIENT", None)
    observed: dict[str, Any] = {}

    class FakeClient:
        def __init__(self, *, api_key: str) -> None:
            observed["key"] = api_key

    @contextmanager
    def fake_tracing_context(**_options: Any) -> Any:
        yield

    def fake_traceable(**_options: Any) -> Any:
        def decorate(handler: Any) -> Any:
            return handler

        return decorate

    monkeypatch.setitem(
        sys.modules,
        "langsmith",
        SimpleNamespace(
            Client=FakeClient,
            traceable=fake_traceable,
            tracing_context=fake_tracing_context,
        ),
    )
    handler = assistant_module._with_optional_langsmith_trace(
        lambda: assistant_module.AssistantResult(text="complete")
    )

    handler()

    assert observed["key"] == "test-langsmith-key"
    assert "LANGSMITH_API_KEY" not in os.environ
    assert "test-langsmith-key" not in repr(
        assistant_module._langsmith_trace_outputs(
            assistant_module.AssistantResult(text="complete")
        )
    )


def test_multi_part_analysis_detects_independent_data_actions() -> None:
    assert _multi_analysis_intents(
        "Give a historical analysis, generate a forecast, then compare actual "
        "and predicted demand with WAPE."
    ) == [
        "historical_analysis",
        "predicted_analysis",
        "demand_comparison",
    ]


def test_multi_part_analysis_calculates_each_action_independently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai.assistant.assistant import _handle_multi_analysis_request

    calls: list[str] = []

    def fake_calculate(
        request: QueryRequest,
        *,
        simulations_dir: str | Path,
    ) -> dict[str, str]:
        calls.append(request.intent)
        assert simulations_dir == "simulations"
        return {"source": request.intent}

    monkeypatch.setattr(
        assistant_module,
        "_analysis_data_for_request",
        fake_calculate,
    )
    monkeypatch.setattr(
        assistant_module,
        "format_analysis_report",
        lambda result: f"Verified: {result['source']}",
    )
    request = QueryRequest(
        intent="demand_comparison",
        forecast_date="2018-09-25",
        start_timestamp=None,
        duration_hours=None,
        grid_ids=[64],
        output_formats=["text"],
        needs_clarification=False,
        clarification_question=None,
        analysis_start_date="2018-09-25",
        analysis_end_date="2018-09-25",
    )
    llm = FakeLLM(
        ['{"overview":"The requested views are ready.","limitations":"Coverage varies."}']
    )

    result = _handle_multi_analysis_request(
        "Run each analysis",
        request,
        ["historical_analysis", "predicted_analysis", "demand_comparison"],
        response_llm=llm,
        provider="ollama",
        response_model=None,
        artifacts_dir="artifacts",
        simulations_dir="simulations",
    )

    assert calls == [
        "historical_analysis",
        "predicted_analysis",
        "demand_comparison",
    ]
    assert "Verified: historical_analysis" in result.text
    assert "Verified: predicted_analysis" in result.text
    assert "Verified: demand_comparison" in result.text


def test_missing_plan_uses_saved_forecast_and_existing_redistribution_api(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai import redistribution

    model = object()
    forecast = pd.DataFrame(
        {
            "id.grid.coarse": [64],
            "target_timestamp": [datetime(2018, 9, 25)],
            "predicted_demand_kwh": [100.0],
        }
    )
    calls: dict[str, Any] = {}
    plan_path = tmp_path / "redistribution_plan_2018-09-25.json"
    monkeypatch.setattr(
        assistant_module.analysis,
        "_forecast_frame_for_date",
        lambda *_args, **_kwargs: forecast,
    )
    monkeypatch.setattr(
        assistant_module.analysis,
        "_load_hybrid_model",
        lambda _path: model,
    )
    monkeypatch.setattr(
        "ai.assistant.data.load_simulation_json",
        lambda *_args, **_kwargs: {},
    )

    def fake_run_simulation(origin: str, **kwargs: Any) -> Path:
        calls["origin"] = origin
        calls.update(kwargs)
        return plan_path

    monkeypatch.setattr(redistribution, "run_simulation", fake_run_simulation)

    generated = assistant_module._ensure_simulation_plan(
        "2018-09-25",
        tmp_path,
    )

    assert generated == plan_path
    assert calls["origin"] == "2018-09-24"
    assert calls["forecast_frame"] is forecast
    assert calls["hybrid_model"] is model


def test_csv_only_historical_query_creates_scoped_csv_without_explanation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result_data = {
        "source": "historical_measurements",
        "is_synthetic": False,
        "start_date": "2018-09-25",
        "end_date": "2018-09-25",
        "grid_count": 1,
        "interval_count": 1,
        "total_demand_kwh": 64.0,
        "average_network_demand_kwh": 64.0,
        "peak_network_demand_kwh": 64.0,
        "peak_network_timestamp": "2018-09-25T01:00:00",
        "grid_ids": [64],
        "covered_start_timestamp": "2018-09-25T01:00:00",
        "covered_end_timestamp": "2018-09-25T01:00:00",
        "grid_totals": [
            {
                "grid_id": 64,
                "interval_count": 1,
                "total_demand_kwh": 64.0,
                "average_hourly_demand_kwh": 64.0,
                "minimum_hourly_demand_kwh": 64.0,
                "maximum_hourly_demand_kwh": 64.0,
                "peak_timestamp": "2018-09-25T01:00:00",
            }
        ],
    }
    monkeypatch.setattr(
        "ai.assistant.assistant.historical_demand_summary",
        lambda *_args, **_kwargs: result_data,
    )
    query_llm = FakeLLM(
        [
            _request_json(
                intent="historical_analysis",
                output_formats=["csv"],
            )
        ]
    )
    response_llm = FakeLLM([])
    result = handle_user_query(
        "Export only CSV of historical demand for Grid 64 on 2018-09-25",
        query_llm=query_llm,
        response_llm=response_llm,
        simulations_dir=tmp_path / "no-plans",
        artifacts_dir=tmp_path / "artifacts",
        history_path=tmp_path / "history.json",
        log_path=tmp_path / "assistant.log",
    )

    assert result.request is not None
    assert result.request.intent == "historical_analysis"
    assert result.request.grid_ids == [64]
    assert result.csv_path is not None
    assert result.image_path is None
    assert response_llm.messages == []
    assert pd.read_csv(result.csv_path)["grid_id"].tolist() == [64]
