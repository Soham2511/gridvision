from __future__ import annotations

import csv
import json
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from ai.assistant.assistant import (
    _render_deterministic_facts,
    _ground_explicit_query_details,
    _explicit_grid_ids,
    handle_user_query,
    interpret_user_query,
    validate_request,
)
from ai.assistant.data import (
    CSV_COLUMNS,
    SimulationDataError,
    calculate_demand_solution,
    calculate_summary,
    load_simulation_json,
    retrieve_relevant_records,
)
from ai.assistant.providers import (
    GroqProvider,
    LLMProviderError,
    OllamaProvider,
    OpenRouterProvider,
    _read_key_file,
    initialize_llm,
)
from ai.assistant.render import generate_csv, generate_image
from ai.assistant.schemas import QueryRequest


def _request(
    *,
    intent: str = "plan",
    start: str | None = "2024-01-01T00:00:00",
    duration: int | None = 1,
    grid_ids: list[int] | None = None,
    forecast_date: str | None = "2024-01-01",
    formats: list[str] | None = None,
) -> QueryRequest:
    return QueryRequest.model_validate(
        {
            "intent": intent,
            "forecast_date": forecast_date,
            "start_timestamp": start,
            "duration_hours": duration,
            "grid_ids": grid_ids or [],
            "output_formats": formats or ["text", "csv", "image"],
            "needs_clarification": False,
            "clarification_question": None,
        }
    )


def _write_plan(path: Path, *, transfers: bool = True) -> Path:
    forecast_date = "2024-01-01"
    timestamps = [
        (datetime.fromisoformat(forecast_date) + timedelta(hours=hour)).isoformat()
        for hour in range(24)
    ]
    grids = [
        {
            "grid_id": grid_id,
            "centroid_latitude": 33.0 + grid_id * 0.01,
            "centroid_longitude": -118.0 + grid_id * 0.01,
        }
        for grid_id in range(53)
    ]
    connections = [
        {
            "grid_a_id": grid_id,
            "grid_b_id": (grid_id + 1) % 53,
            "distance_km": 5.0,
            "capacity_kwh_per_hour": 1000.0,
            "loss_pct": 0.015,
        }
        for grid_id in range(53)
    ]
    connections[0]["loss_pct"] = 0.05
    hourly_results = []
    transfer_rows = []
    for hour_index, timestamp in enumerate(timestamps):
        hour_grids = []
        for grid_id in range(53):
            demand = 100.0
            supply = 100.0
            initial_surplus = initial_deficit = 0.0
            sent = received = lost = remaining = unmet = 0.0
            if transfers and hour_index == 0 and grid_id == 0:
                supply = 110.0
                initial_surplus = 10.0
                sent = 10.0
                lost = 0.5
            if transfers and hour_index == 0 and grid_id == 1:
                supply = 90.0
                initial_deficit = 10.0
                received = 9.5
                unmet = 0.5
            hour_grids.append(
                {
                    "grid_id": grid_id,
                    "predicted_demand_kwh": demand,
                    "synthetic_supply_kwh": supply,
                    "supply_variation": 0.0,
                    "initial_surplus_kwh": initial_surplus,
                    "initial_deficit_kwh": initial_deficit,
                    "energy_sent_kwh": sent,
                    "energy_received_kwh": received,
                    "transmission_losses_kwh": lost,
                    "remaining_surplus_kwh": remaining,
                    "unmet_demand_kwh": unmet,
                }
            )
        hourly_results.append({"timestamp": timestamp, "grids": hour_grids})
        if transfers and hour_index == 0:
            transfer_rows.append(
                {
                    "timestamp": timestamp,
                    "source_grid_id": 0,
                    "destination_grid_id": 1,
                    "energy_sent_kwh": 10.0,
                    "energy_received_kwh": 9.5,
                    "energy_lost_kwh": 0.5,
                    "loss_pct": 0.05,
                }
            )
    payload: dict[str, Any] = {
        "simulation_metadata": {
            "forecast_date": forecast_date,
            "forecast_origin_timestamp": "2023-12-31T23:00:00",
            "run_timestamp": "2024-01-01T00:00:00Z",
            "grid_count": 53,
            "forecast_interval_count": 24,
            "assumptions": {"network_and_losses_are_synthetic": True},
        },
        "network": {
            "grid_count": 53,
            "connection_count": len(connections),
            "grids": grids,
            "configuration": {"neighbor_count": 3},
            "connections": connections,
        },
        "hourly_results": hourly_results,
        "transfers": transfer_rows,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


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


def _query_json(
    *,
    intent: str = "plan",
    start: str | None = "2024-01-01T00:00:00",
    duration: int | None = 1,
    grid_ids: list[int] | None = None,
    formats: list[str] | None = None,
    needs_clarification: bool = False,
    clarification_question: str | None = None,
) -> str:
    return json.dumps(
        {
            "intent": intent,
            "forecast_date": "2024-01-01",
            "start_timestamp": start,
            "duration_hours": duration,
            "grid_ids": grid_ids or [],
            "output_formats": formats or ["text", "csv", "image"],
            "needs_clarification": needs_clarification,
            "clarification_question": clarification_question,
        }
    )


def _qualitative_json() -> str:
    return json.dumps(
        {
            "overview": "Surplus areas support nearby deficit areas in this scenario.",
            "limitations": "The supply and network are synthetic planning assumptions.",
        }
    )


def test_request_validation_clarifies_unknown_grid_and_timestamp() -> None:
    available = {
        "available_forecast_dates": ["2024-01-01"],
        "timestamps_by_date": {"2024-01-01": ["2024-01-01T00:00:00"]},
        "grid_ids_by_date": {"2024-01-01": [0, 1, 2]},
    }
    unknown_grid = validate_request(
        _request(grid_ids=[500]),
        available=available,
    )
    assert unknown_grid.needs_clarification
    assert "not in this plan" in unknown_grid.clarification_question
    parsed = validate_request(
        _request(start="2024-01-01T02:00:00"),
        available=available,
    )
    assert parsed.needs_clarification
    assert "unavailable" in parsed.clarification_question


def _set_first_hour_balance(
    plan_path: Path,
    *,
    source_surplus: float,
    target_unmet: float,
) -> None:
    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    source = payload["hourly_results"][0]["grids"][0]
    source["synthetic_supply_kwh"] = 100.0 + source_surplus
    source["initial_surplus_kwh"] = source_surplus
    source["remaining_surplus_kwh"] = source_surplus
    target = payload["hourly_results"][0]["grids"][1]
    target["synthetic_supply_kwh"] = 100.0 - target_unmet
    target["initial_deficit_kwh"] = target_unmet
    target["unmet_demand_kwh"] = target_unmet
    payload["transfers"] = []
    plan_path.write_text(json.dumps(payload), encoding="utf-8")


def test_demand_solution_suggests_feasible_low_loss_direct_transfer(
    tmp_path: Path,
) -> None:
    plan_path = _write_plan(
        tmp_path / "redistribution_plan_2024-01-01.json",
        transfers=False,
    )
    _set_first_hour_balance(plan_path, source_surplus=20.0, target_unmet=10.0)
    records = retrieve_relevant_records(
        _request(intent="demand_solution", grid_ids=[1]),
        simulations_dir=tmp_path,
    )

    solution = calculate_demand_solution(records, [1])

    recommendation = solution["demand_solution_recommendations"][0]
    assert recommendation["source_grid_id"] == 0
    assert recommendation["destination_grid_id"] == 1
    assert recommendation["recommended_energy_sent_kwh"] == pytest.approx(
        10.0 / 0.95
    )
    assert recommendation["recommended_energy_received_kwh"] == pytest.approx(10.0)
    assert recommendation["estimated_energy_lost_kwh"] == pytest.approx(
        10.0 / 0.95 * 0.05
    )
    assert solution["demand_solution_unserved"] == []
    image_path = generate_image(
        records,
        recommended_transfers=solution["demand_solution_recommendations"],
        output_dir=tmp_path / "assets",
    )
    assert image_path.is_file()


def test_demand_solution_reports_residual_without_neighbor_surplus(
    tmp_path: Path,
) -> None:
    plan_path = _write_plan(
        tmp_path / "redistribution_plan_2024-01-01.json",
        transfers=False,
    )
    _set_first_hour_balance(plan_path, source_surplus=0.0, target_unmet=10.0)
    records = retrieve_relevant_records(
        _request(intent="demand_solution", grid_ids=[1]),
        simulations_dir=tmp_path,
    )

    solution = calculate_demand_solution(records, [1])

    assert solution["demand_solution_recommendations"] == []
    assert solution["demand_solution_unserved"] == [
        {
            "timestamp": "2024-01-01T00:00:00",
            "grid_id": 1,
            "unmet_demand_kwh": 10.0,
        }
    ]
    summary = calculate_summary(records)
    summary.update(solution)
    facts = _render_deterministic_facts(summary)
    assert "No feasible direct-neighbor transfer" in facts
    assert "10.00 kWh unmet" in facts


def test_demand_solution_respects_remaining_edge_capacity(
    tmp_path: Path,
) -> None:
    plan_path = _write_plan(
        tmp_path / "redistribution_plan_2024-01-01.json",
        transfers=False,
    )
    _set_first_hour_balance(plan_path, source_surplus=20.0, target_unmet=10.0)
    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    payload["network"]["connections"][0]["capacity_kwh_per_hour"] = 5.0
    plan_path.write_text(json.dumps(payload), encoding="utf-8")
    records = retrieve_relevant_records(
        _request(intent="demand_solution", grid_ids=[1]),
        simulations_dir=tmp_path,
    )

    solution = calculate_demand_solution(records, [1])

    recommendation = solution["demand_solution_recommendations"][0]
    assert recommendation["source_grid_id"] == 0
    assert recommendation["recommended_energy_sent_kwh"] == pytest.approx(5.0)
    assert recommendation["recommended_energy_received_kwh"] == pytest.approx(4.75)
    assert solution["demand_solution_unserved"][0]["unmet_demand_kwh"] == pytest.approx(
        5.25
    )


def test_basic_concept_query_needs_no_llm_and_logs_no_question(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "assistant.log"
    result = handle_user_query(
        "What does synthetic supply mean?",
        log_path=log_path,
        history_path=tmp_path / "history.json",
    )

    assert "not a measured electricity supply" in result.text
    assert "synthetic supply" not in log_path.read_text(encoding="utf-8")


def test_relative_next_uses_actual_hour_after_previous_window(
    tmp_path: Path,
) -> None:
    plan_path = _write_plan(tmp_path / "redistribution_plan_2024-01-01.json")
    available = {
        "available_forecast_dates": ["2024-01-01"],
        "timestamps_by_date": [
            (datetime(2024, 1, 1) + timedelta(hours=hour)).isoformat()
            for hour in range(24)
        ],
        "grid_ids_by_date": list(range(53)),
    }
    llm = FakeLLM(
        [
            _query_json(
                start=None,
                duration=2,
                needs_clarification=True,
                clarification_question="Which forecast hour do you mean?",
            )
        ]
    )
    previous = _request(start="2024-01-01T00:00:00", duration=2)

    interpreted = interpret_user_query(
        "Show the next 2 hours",
        llm,
        available={
            "available_forecast_dates": available["available_forecast_dates"],
            "timestamps_by_date": {"2024-01-01": available["timestamps_by_date"]},
            "grid_ids_by_date": {"2024-01-01": available["grid_ids_by_date"]},
        },
        history={
            "turns": [],
            "last_successful_request": previous,
        },
    )

    assert plan_path.is_file()
    assert interpreted.start_timestamp == "2024-01-01T02:00:00"
    sent_context = json.loads(llm.messages[0][1]["content"])
    assert "hourly_results" not in sent_context
    assert "path" not in json.dumps(sent_context)


def test_explicit_query_values_override_model_guess() -> None:
    available = {
        "available_forecast_dates": ["2018-09-25"],
        "timestamps_by_date": {
            "2018-09-25": ["2018-09-25T00:00:00", "2018-09-25T01:00:00"]
        },
        "grid_ids_by_date": {"2018-09-25": list(range(53))},
    }
    llm = FakeLLM(
        [
            json.dumps(
                {
                    "intent": "plan",
                    "forecast_date": "2018-09-25",
                    "start_timestamp": "2018-09-25T00:00:00",
                    "duration_hours": 24,
                    "grid_ids": list(range(53)),
                    "output_formats": ["text"],
                    "needs_clarification": False,
                    "clarification_question": None,
                }
            )
        ]
    )

    interpreted = interpret_user_query(
        "Show the redistribution plan for 2018-09-25 at 2018-09-25T00:00:00",
        llm,
        available=available,
    )

    assert interpreted.forecast_date == "2018-09-25"
    assert interpreted.start_timestamp == "2018-09-25T00:00:00"
    assert interpreted.duration_hours == 1
    assert interpreted.grid_ids == []
    assert interpreted.output_formats == ["text", "csv", "image"]


def test_unspecified_hour_requests_clarification(
    tmp_path: Path,
) -> None:
    _write_plan(tmp_path / "redistribution_plan_2024-01-01.json")
    available = {
        "available_forecast_dates": ["2024-01-01"],
        "timestamps_by_date": {
            "2024-01-01": [
                (datetime(2024, 1, 1) + timedelta(hours=hour)).isoformat()
                for hour in range(24)
            ]
        },
        "grid_ids_by_date": {"2024-01-01": list(range(53))},
    }
    llm = FakeLLM([_query_json(start=None, duration=1)])

    interpreted = interpret_user_query(
        "What are the transmission losses?",
        llm,
        available=available,
    )

    assert interpreted.needs_clarification
    assert "Which forecast hour" in interpreted.clarification_question


def test_loader_validates_balance_and_rejects_tampering(tmp_path: Path) -> None:
    path = _write_plan(tmp_path / "redistribution_plan_2024-01-01.json")

    loaded = load_simulation_json("2024-01-01", tmp_path)
    assert loaded["simulation_metadata"]["forecast_date"] == "2024-01-01"

    payload = json.loads(path.read_text())
    payload["hourly_results"][0]["grids"][0]["energy_sent_kwh"] = 20
    path.write_text(json.dumps(payload))
    with pytest.raises(SimulationDataError, match="Energy balance check failed"):
        load_simulation_json("2024-01-01", tmp_path)


def test_loader_enforces_combined_hourly_edge_capacity(tmp_path: Path) -> None:
    path = _write_plan(tmp_path / "redistribution_plan_2024-01-01.json")
    payload = json.loads(path.read_text())
    payload["network"]["connections"][0]["capacity_kwh_per_hour"] = 15.0
    payload["transfers"].append(dict(payload["transfers"][0]))
    path.write_text(json.dumps(payload))

    with pytest.raises(SimulationDataError, match="Combined transfers exceed edge capacity"):
        load_simulation_json("2024-01-01", tmp_path)


def test_retrieval_filters_hour_grid_and_keeps_transfer_endpoints(tmp_path: Path) -> None:
    _write_plan(tmp_path / "redistribution_plan_2024-01-01.json")
    records = retrieve_relevant_records(
        _request(grid_ids=[0]),
        simulations_dir=tmp_path,
    )
    summary = calculate_summary(records)

    assert len(records.hourly_records) == 1
    assert {grid["grid_id"] for grid in records.hourly_records[0]["grids"]} == {
        0,
        1,
        52,
    }
    assert len(records.transfers) == 1
    assert summary["energy_sent_total_kwh"] == pytest.approx(10)
    assert summary["energy_received_total_kwh"] == pytest.approx(9.5)
    assert summary["transmission_losses_total_kwh"] == pytest.approx(0.5)
    assert summary["unmet_demand_total_kwh"] == pytest.approx(0.0)
    assert summary["grid_count"] == 1
    assert [grid["grid_id"] for grid in summary["grid_totals"]] == [0]


def test_hour_comparison_reports_each_timestamp_separately(tmp_path: Path) -> None:
    _write_plan(tmp_path / "redistribution_plan_2024-01-01.json")
    records = retrieve_relevant_records(
        _request(
            intent="compare_hours",
            start="2024-01-01T00:00:00",
            duration=2,
        ),
        simulations_dir=tmp_path,
    )

    summary = calculate_summary(records)
    facts = _render_deterministic_facts(summary, intent="compare_hours")

    assert summary["grid_count"] == 53
    assert [hour["timestamp"] for hour in summary["hourly_totals"]] == [
        "2024-01-01T00:00:00",
        "2024-01-01T01:00:00",
    ]
    assert summary["hourly_totals"][0]["energy_sent_kwh"] == pytest.approx(10)
    assert summary["hourly_totals"][1]["energy_sent_kwh"] == pytest.approx(0)
    assert "2024-01-01T00:00:00" in facts
    assert "2024-01-01T01:00:00" in facts


def test_csv_has_fixed_columns_and_valid_header_when_no_transfers(tmp_path: Path) -> None:
    _write_plan(tmp_path / "redistribution_plan_2024-01-01.json", transfers=False)
    records = retrieve_relevant_records(
        _request(start="2024-01-01T01:00:00"),
        simulations_dir=tmp_path,
    )

    csv_path = generate_csv(records, output_dir=tmp_path / "assets")
    with csv_path.open(newline="", encoding="utf-8") as file:
        rows = list(csv.reader(file))
    assert rows == [CSV_COLUMNS]

    _write_plan(tmp_path / "redistribution_plan_2024-01-01.json", transfers=True)
    records = retrieve_relevant_records(
        _request(grid_ids=[0]),
        simulations_dir=tmp_path,
    )
    csv_path = generate_csv(records, output_dir=tmp_path / "assets")
    frame = pd.read_csv(csv_path)
    assert list(frame.columns) == CSV_COLUMNS
    assert frame.iloc[0]["from_grid"] == 0
    assert frame.iloc[0]["to_grid"] == 1
    assert frame.iloc[0]["energy_lost_kwh"] == pytest.approx(0.5)


def test_image_uses_network_and_selected_period(tmp_path: Path) -> None:
    _write_plan(tmp_path / "redistribution_plan_2024-01-01.json")
    records = retrieve_relevant_records(
        _request(grid_ids=[0]),
        simulations_dir=tmp_path,
    )

    image_path = generate_image(records, output_dir=tmp_path / "assets")

    assert image_path.is_file()
    assert image_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_handle_query_and_regenerate_image_reuses_prior_exact_window(
    tmp_path: Path,
) -> None:
    simulations = tmp_path / "plans"
    artifacts = tmp_path / "assets"
    history = tmp_path / "history.json"
    _write_plan(simulations / "redistribution_plan_2024-01-01.json")
    query_llm = FakeLLM(
        [
            _query_json(start="2024-01-01T03:00:00", duration=2),
            _query_json(
                intent="clarification",
                start=None,
                duration=None,
                formats=[],
                needs_clarification=True,
                clarification_question="Which forecast hour do you mean?",
            ),
        ]
    )
    response_llm = FakeLLM([_qualitative_json(), _qualitative_json()])

    first = handle_user_query(
        "Show the next two hours",
        query_llm=query_llm,
        response_llm=response_llm,
        simulations_dir=simulations,
        artifacts_dir=artifacts,
        history_path=history,
    )
    regenerated = handle_user_query(
        "Regenerate the image of the last query",
        query_llm=query_llm,
        response_llm=response_llm,
        simulations_dir=simulations,
        artifacts_dir=artifacts,
        history_path=history,
    )
    saved_history = json.loads(history.read_text())

    assert first.request is not None
    assert first.request.start_timestamp == "2024-01-01T00:00:00"
    assert regenerated.request is not None
    assert regenerated.request.start_timestamp == "2024-01-01T00:00:00"
    assert regenerated.request.duration_hours == 2
    assert regenerated.image_path == first.image_path
    assert regenerated.csv_path is None
    assert len(saved_history["turns"]) == 2
    assert saved_history["last_successful_request"]["start_timestamp"] == (
        "2024-01-01T00:00:00"
    )


def test_query_grounding_classifies_grid_scope_and_inherits_follow_up_context() -> None:
    previous = _request(start="2024-01-01T05:00:00", duration=3, grid_ids=[2])
    request = QueryRequest.model_validate_json(
        _query_json(
            intent="follow_up",
            start=None,
            duration=None,
            formats=[],
        )
    )
    grounded = _ground_explicit_query_details(
        "What about Grid 7?",
        request,
        history={
            "last_successful_request": previous,
        },
    )

    assert _explicit_grid_ids("Compare Grid64 and Grid 72") == [64, 72]
    assert grounded.intent == "grid_plan"
    assert grounded.grid_ids == [7]
    assert grounded.forecast_date == "2024-01-01"
    assert grounded.start_timestamp == "2024-01-01T05:00:00"
    assert grounded.duration_hours == 3


@pytest.mark.parametrize(
    ("query", "expected_intent", "expected_grids"),
    [
        (
            "Which grids supply Grid64 at 2024-01-01T00:00:00?",
            "transfers",
            [64],
        ),
        (
            "Show Grid 64's deficit at 2024-01-01T00:00:00",
            "surplus_deficit",
            [64],
        ),
        (
            "Compare Grid64 and Grid72 at 2024-01-01T00:00:00",
            "compare_grids",
            [64, 72],
        ),
    ],
)
def test_query_grounding_classifies_requested_grid_analysis(
    query: str,
    expected_intent: str,
    expected_grids: list[int],
) -> None:
    grounded = _ground_explicit_query_details(
        query,
        QueryRequest.model_validate_json(_query_json()),
    )

    assert grounded.intent == expected_intent
    assert grounded.grid_ids == expected_grids


@pytest.mark.parametrize(
    ("query", "intent", "formats", "artifact_kind"),
    [
        (
            "Generate an image for Grid 0 at 2024-01-01T00:00:00",
            "image_generation",
            ["image"],
            "image",
        ),
        (
            "Export CSV for Grid 0 at 2024-01-01T00:00:00",
            "csv_generation",
            ["csv"],
            "csv",
        ),
    ],
)
def test_artifact_only_requests_skip_explanation_and_other_artifact(
    tmp_path: Path,
    query: str,
    intent: str,
    formats: list[str],
    artifact_kind: str,
) -> None:
    simulations = tmp_path / "plans"
    _write_plan(simulations / "redistribution_plan_2024-01-01.json")
    query_llm = FakeLLM(
        [
            _query_json(
                intent=intent,
                start="2024-01-01T00:00:00",
                grid_ids=[0],
                formats=formats,
            )
        ]
    )
    response_llm = FakeLLM([])
    result = handle_user_query(
        query,
        query_llm=query_llm,
        response_llm=response_llm,
        simulations_dir=simulations,
        artifacts_dir=tmp_path / "artifacts",
        history_path=tmp_path / "history.json",
        log_path=tmp_path / "assistant.log",
    )

    assert result.request is not None
    assert result.request.output_formats == formats
    assert response_llm.messages == []
    assert (result.image_path is not None) == (artifact_kind == "image")
    assert (result.csv_path is not None) == (artifact_kind == "csv")
    saved_history = json.loads((tmp_path / "history.json").read_text())
    assert saved_history["last_generated_files"][artifact_kind]
    follow_up_file = handle_user_query(
        f"Where is the last {artifact_kind}?",
        history_path=tmp_path / "history.json",
        log_path=tmp_path / "assistant.log",
    )
    assert saved_history["last_generated_files"][artifact_kind] in follow_up_file.text


def test_response_numeric_claims_are_rejected(tmp_path: Path) -> None:
    from ai.assistant.assistant import generate_explanation

    llm = FakeLLM(
        [
            json.dumps(
                {
                    "overview": "Grid 4 has surplus.",
                    "limitations": "This is a synthetic scenario.",
                }
            )
        ]
    )
    with pytest.raises(ValueError, match="numerical claims"):
        generate_explanation({"summary": "filtered"}, llm)


def test_groq_model_verification_is_explicit_and_never_exposes_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[Any, dict[str, Any]]] = []

    class FakeResponse:
        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"data":[{"id":"openai/gpt-oss-20b"}]}'

    def fake_urlopen(*args: Any, **kwargs: Any) -> FakeResponse:
        calls.append((args[0], kwargs))
        return FakeResponse()

    monkeypatch.delenv("ENERGY_ASSISTANT_CA_BUNDLE", raising=False)
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = GroqProvider(model="openai/gpt-oss-20b", api_key="test-key")
    assert provider.model == "openai/gpt-oss-20b"
    assert "test-key" not in repr(provider)
    request, options = calls[0]
    assert request.get_header("Authorization") == "Bearer test-key"
    assert options["context"].check_hostname
    assert options["context"].verify_mode

    with pytest.raises(LLMProviderError, match="not available"):
        GroqProvider(model="missing-model", api_key="test-key")


def test_default_groq_key_path_reads_file_without_exposing_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key_path = tmp_path / "api.key"
    key_path.write_text("test-key\n", encoding="utf-8")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setattr("ai.assistant.providers.DEFAULT_GROQ_KEY_PATH", key_path)

    assert _read_key_file() == "test-key"


def test_openrouter_initialization_uses_its_key_file_and_endpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key_path = tmp_path / "openrouter-api.key"
    key_path.write_text("test-openrouter-key\n", encoding="utf-8")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_BASE_URL", raising=False)
    monkeypatch.setattr(
        "ai.assistant.providers.DEFAULT_OPENROUTER_KEY_PATH",
        key_path,
    )
    requests: list[Any] = []

    class ModelListResponse:
        def __enter__(self) -> ModelListResponse:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"data":[{"id":"openai/gpt-oss-20b"}]}'

    def fake_urlopen(request: Any, **_kwargs: Any) -> ModelListResponse:
        requests.append(request)
        return ModelListResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = initialize_llm("openrouter", "openai/gpt-oss-20b")

    assert isinstance(provider, OpenRouterProvider)
    assert provider.base_url == "https://openrouter.ai/api/v1"
    assert requests[0].full_url == "https://openrouter.ai/api/v1/models"
    assert requests[0].get_header("Authorization") == "Bearer test-openrouter-key"
    assert "test-openrouter-key" not in repr(provider)


def test_ollama_local_provider_checks_tags_and_uses_json_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[Any, dict[str, Any]]] = []

    class ModelListResponse:
        def __enter__(self) -> ModelListResponse:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"models":[{"name":"qwen3:8b"}]}'

    class ChatResponse:
        def __enter__(self) -> ChatResponse:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"message":{"content":"{\\"intent\\":\\"plan\\"}"}}'

    def fake_urlopen(request: Any, **kwargs: Any) -> Any:
        calls.append((request, kwargs))
        if request.full_url.endswith("/api/tags"):
            return ModelListResponse()
        return ChatResponse()

    monkeypatch.setenv("OLLAMA_TIMEOUT_SECONDS", "12")
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = OllamaProvider("qwen3:8b")
    schema = {"type": "object", "properties": {"intent": {"type": "string"}}}
    result = provider.complete(
        [{"role": "user", "content": "test"}],
        json_mode=True,
        response_schema=schema,
    )

    assert result == '{"intent":"plan"}'
    assert provider.timeout_seconds == 12
    assert calls[0][0].full_url == "http://127.0.0.1:11434/api/tags"
    assert calls[0][1]["timeout"] == 12
    chat_request = calls[1][0]
    assert chat_request.full_url == "http://127.0.0.1:11434/api/chat"
    chat_payload = json.loads(chat_request.data)
    assert chat_payload["format"] == schema
    assert chat_payload["stream"] is False
    assert chat_request.get_header("Authorization") is None


def test_remote_ollama_requires_https_and_reads_key_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key_path = tmp_path / "ollama-api.key"
    key_path.write_text("test-ollama-key\n", encoding="utf-8")
    monkeypatch.setattr(
        "ai.assistant.providers.DEFAULT_OLLAMA_KEY_PATH",
        key_path,
    )
    calls: list[Any] = []

    class ModelListResponse:
        def __enter__(self) -> ModelListResponse:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"models":[{"name":"gemma4:cloud"}]}'

    def fake_urlopen(request: Any, **_kwargs: Any) -> ModelListResponse:
        calls.append(request)
        return ModelListResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = OllamaProvider("gemma4:cloud", base_url="https://ollama.com")

    assert provider.api_key == "test-ollama-key"
    assert calls[0].get_header("Authorization") is not None
    with pytest.raises(ValueError, match="Remote Ollama hosts must use HTTPS"):
        OllamaProvider("qwen3:8b", base_url="http://ollama.example")


def test_provider_403_error_identifies_model_list_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def deny_model_list(*_args: Any, **_kwargs: Any) -> Any:
        raise urllib.error.HTTPError(
            "https://api.groq.com/openai/v1/models",
            403,
            "Forbidden",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr("urllib.request.urlopen", deny_model_list)
    with pytest.raises(LLMProviderError, match="denied access to its model list"):
        GroqProvider(model="openai/gpt-oss-20b", api_key="test-key")


def test_provider_403_error_identifies_completion_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ModelListResponse:
        def __enter__(self) -> ModelListResponse:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"data":[{"id":"openai/gpt-oss-20b"}]}'

    def allow_model_list_then_deny_completion(
        request: Any,
        **_kwargs: Any,
    ) -> ModelListResponse:
        if request.full_url.endswith("/models"):
            return ModelListResponse()
        raise urllib.error.HTTPError(
            request.full_url,
            403,
            "Forbidden",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr(
        "urllib.request.urlopen",
        allow_model_list_then_deny_completion,
    )
    provider = GroqProvider(model="openai/gpt-oss-20b", api_key="test-key")

    with pytest.raises(LLMProviderError, match="requested model or endpoint"):
        provider.complete([{"role": "user", "content": "test"}])


def test_openrouter_402_error_identifies_endpoint_and_credit_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ModelListResponse:
        def __enter__(self) -> ModelListResponse:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"data":[{"id":"openai/gpt-oss-20b"}]}'

    def allow_model_list_then_require_payment(
        request: Any,
        **_kwargs: Any,
    ) -> ModelListResponse:
        if request.full_url.endswith("/models"):
            return ModelListResponse()
        raise urllib.error.HTTPError(
            request.full_url,
            402,
            "Payment Required",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr(
        "urllib.request.urlopen",
        allow_model_list_then_require_payment,
    )
    provider = OpenRouterProvider(
        model="openai/gpt-oss-20b",
        api_key="test-key",
    )

    with pytest.raises(
        LLMProviderError,
        match=r"credits.*chat/completions",
    ):
        provider.complete([{"role": "user", "content": "test"}])


def test_openrouter_429_error_identifies_endpoint_and_retry_delay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ModelListResponse:
        def __enter__(self) -> ModelListResponse:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"data":[{"id":"openai/gpt-oss-20b"}]}'

    def allow_model_list_then_rate_limit(
        request: Any,
        **_kwargs: Any,
    ) -> ModelListResponse:
        if request.full_url.endswith("/models"):
            return ModelListResponse()
        raise urllib.error.HTTPError(
            request.full_url,
            429,
            "Too Many Requests",
            hdrs={"Retry-After": "30"},
            fp=None,
        )

    monkeypatch.setattr(
        "urllib.request.urlopen",
        allow_model_list_then_rate_limit,
    )
    provider = OpenRouterProvider(
        model="openai/gpt-oss-20b",
        api_key="test-key",
    )

    with pytest.raises(
        LLMProviderError,
        match=r"chat/completions.*retry after 30 seconds",
    ):
        provider.complete([{"role": "user", "content": "test"}])
