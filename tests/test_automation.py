from __future__ import annotations

import io
import subprocess
import json
from datetime import datetime

import pytest
import pyarrow as pa
import pyarrow.parquet as pq

import automation
from training.customer_segmentation.config import SegmentationSettings
from training.customer_segmentation.data_pipeline import _prepare_segmentation_source


def _write_anomaly_parquet(path, timestamps, *, include_customer=False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = {
        "timestamp": pa.array(
            [datetime.fromisoformat(value) for value in timestamps],
            type=pa.timestamp("ns"),
        ),
    }
    if include_customer:
        columns["OBJECTID"] = pa.array(range(len(timestamps)), type=pa.int64())
    pq.write_table(pa.table(columns), path)


def test_compose_command_includes_stdout_when_compose_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(automation.shutil, "which", lambda _: "/usr/bin/docker")
    monkeypatch.setattr(
        automation.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0],
            returncode=1,
            stdout="Enable Docker Desktop WSL integration for this distro.",
            stderr="",
        ),
    )

    with pytest.raises(RuntimeError) as error:
        automation._compose_command()

    message = str(error.value)
    assert "docker compose version" in message
    assert "exit code: 1" in message
    assert "Enable Docker Desktop WSL integration for this distro." in message


def test_segmentation_defaults_are_memory_constrained(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SEGMENTATION_DUCKDB_MEMORY_LIMIT", raising=False)
    monkeypatch.delenv("SEGMENTATION_DUCKDB_THREADS", raising=False)

    settings = SegmentationSettings.from_environment()

    assert settings.duckdb_memory_limit == "1GB"
    assert settings.duckdb_threads == 1


def test_segmentation_source_sample_is_cached_and_preserves_small_categories(
    tmp_path,
) -> None:
    source = tmp_path / "source.parquet"
    ids = list(range(100))
    categories = ["Residential"] * 98 + ["Institutional", "Recreational"]
    table = pa.table(
        {
            "OBJECTID": pa.array(ids, type=pa.int64()),
            "id.grid.coarse": ["coarse"] * 100,
            "id.grid.finer": ["finer"] * 100,
            "id.tract": ["tract"] * 100,
            "latitude": [1.0] * 100,
            "longitude": [2.0] * 100,
            "GeneralUseType": categories,
            "SpecificUseType": ["type"] * 100,
            "usetype": ["use"] * 100,
            "building.type": ["building"] * 100,
            "timestamp": ["2018-01-01 00:00:00"] * 100,
            "normalized_building_energy_kwh": [1.0] * 100,
        }
    )
    pq.write_table(table, source)
    settings = SegmentationSettings(
        source_path=source,
        output_dir=tmp_path / "segmentation",
        building_sample_fraction=0.1,
    )

    sample_path, manifest = _prepare_segmentation_source(settings)
    cached_path, cached_manifest = _prepare_segmentation_source(settings)

    assert cached_path == sample_path
    assert cached_manifest == manifest
    sample = pq.read_table(sample_path)
    assert sample.num_rows < table.num_rows
    assert set(sample.column("GeneralUseType").to_pylist()) == {
        "Residential",
        "Institutional",
        "Recreational",
    }


def test_main_records_keyboard_interrupt_as_interrupted(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setattr(automation, "DATA_ROOT", tmp_path / "data")
    monkeypatch.setattr(automation, "LOG_ROOT", tmp_path / "logs")
    monkeypatch.setattr(
        automation,
        "_compose_command",
        lambda: (_ for _ in ()).throw(KeyboardInterrupt()),
    )

    result = automation.main(["--skip-all-data-pipelines"])

    assert result == 130
    summaries = list((tmp_path / "logs" / "automation").glob("automation-*.json"))
    assert len(summaries) == 1
    summary = json.loads(summaries[0].read_text(encoding="utf-8"))
    assert summary["status"] == "INTERRUPTED"
    assert summary["steps"][0]["status"] == "INTERRUPTED"


def test_model_catalog_verification_requires_all_configured_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model_ids = [
        "customer-bill-prediction",
        "commercial-building-forecast",
        "government-load-forecast",
        "government-customer-segmentation",
        "anomaly-prediction",
    ]
    response_body = json.dumps(
        {
            "data": {
                "models": [
                    {
                        "modelId": model_id,
                        "name": model_id,
                        "modelVersion": "1",
                        "status": "configured",
                    }
                    for model_id in model_ids
                ]
            }
        }
    ).encode()

    class Response(io.BytesIO):
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_):
            self.close()

    monkeypatch.setattr(
        automation.urllib.request,
        "urlopen",
        lambda *args, **kwargs: Response(response_body),
    )

    result = automation._verify_model_catalog()

    assert len(result["configured_models"]) == 5
    assert {
        model["model_id"] for model in result["configured_models"]
    } == set(model_ids)


def test_compose_service_url_uses_published_host_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        assert command == ["docker", "compose", "port", "backend", "5000"]
        return subprocess.CompletedProcess(
            command, returncode=0, stdout="127.0.0.1:5017\n", stderr=""
        )

    monkeypatch.setattr(automation.subprocess, "run", fake_run)

    assert automation._compose_service_url(
        ["docker", "compose"], "backend", 5000, {}
    ) == "http://127.0.0.1:5017"


def test_compose_command_reports_empty_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(automation.shutil, "which", lambda _: "/usr/bin/docker")
    monkeypatch.setattr(
        automation.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0],
            returncode=1,
            stdout="",
            stderr="",
        ),
    )

    with pytest.raises(RuntimeError, match="Docker returned no diagnostic output"):
        automation._compose_command()


def test_compose_command_falls_back_to_windows_cli_on_linux(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []

    def fake_which(command: str) -> str | None:
        return {
            "docker": "/mnt/c/Docker/resources/bin/docker",
            "docker.exe": "/mnt/c/Docker/resources/bin/docker.exe",
        }.get(command)

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        commands.append(command)
        return subprocess.CompletedProcess(
            command,
            returncode=1 if command[0].endswith("/docker") else 0,
            stdout="",
            stderr="",
        )

    monkeypatch.setattr(automation.platform, "system", lambda: "Linux")
    monkeypatch.setattr(automation.shutil, "which", fake_which)
    monkeypatch.setattr(automation.subprocess, "run", fake_run)

    assert automation._compose_command() == [
        "/mnt/c/Docker/resources/bin/docker.exe",
        "compose",
    ]
    assert commands == [
        ["/mnt/c/Docker/resources/bin/docker", "compose", "version"],
        ["/mnt/c/Docker/resources/bin/docker.exe", "compose", "version"],
    ]


def test_airflow_command_uses_compose_container_on_macos(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(automation.platform, "system", lambda: "Darwin")

    command = automation._airflow_command(["docker", "compose"])

    assert command == [
        "docker",
        "compose",
        "run",
        "--rm",
        "--no-deps",
        "airflow",
        "airflow",
    ]


def test_main_keeps_complete_airflow_command_on_macos(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    source_path = tmp_path / "training_sample.parquet"
    source_path.touch()
    monkeypatch.setattr(automation.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(automation, "SOURCE_PATH", source_path)
    monkeypatch.setattr(automation, "DATA_ROOT", tmp_path / "data")
    monkeypatch.setattr(automation, "LOG_ROOT", tmp_path / "logs")
    monkeypatch.setattr(
        automation,
        "_compose_command",
        lambda: ["docker", "compose"],
    )
    monkeypatch.setattr(automation, "_compose", lambda *args, **kwargs: None)
    monkeypatch.setattr(automation, "_wait_for_http", lambda *args, **kwargs: "healthy")
    monkeypatch.setattr(automation, "find_spec", lambda _: object())

    commands: list[list[str]] = []

    def stop_after_capture(command, **kwargs):
        commands.append(command)
        raise RuntimeError("stop after capturing migration command")

    monkeypatch.setattr(automation.subprocess, "run", stop_after_capture)

    assert automation.main([]) == 1
    assert commands == [
        [
            "docker",
            "compose",
            "run",
            "--rm",
            "--no-deps",
            "airflow",
            "airflow",
            "db",
            "migrate",
        ]
    ]


def test_start_airflow_ui_starts_compose_service_on_macos(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[list[str], list[str]]] = []

    def fake_compose(command, arguments, env):
        calls.append((command, arguments))

    monkeypatch.setattr(automation.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(automation, "_compose", fake_compose)
    monkeypatch.setattr(automation, "_wait_for_http", lambda *args, **kwargs: args[0])

    result = automation._start_airflow_ui(
        ["docker", "compose", "run"],
        {},
        ["docker", "compose"],
    )

    assert calls == [(["docker", "compose"], ["up", "-d", "airflow"])]
    assert result["status"] == "running in Docker"
    assert result["log"] == str(automation.LOG_ROOT / "airflow" / "standalone.log")


def test_run_airflow_dag_test_executes_requested_dag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    class FakeProcess:
        stdout = iter(["DAG test completed\n"])

        def wait(self) -> int:
            return 0

    def fake_popen(command: list[str], **kwargs: object) -> FakeProcess:
        calls.append((command, kwargs))
        return FakeProcess()

    monkeypatch.setattr(automation.subprocess, "Popen", fake_popen)

    result = automation._run_airflow_dag_test(
        ["airflow"],
        automation.GOVERNMENT_DAG_ID,
        {"AIRFLOW_HOME": "/tmp/gridvision-airflow"},
    )

    assert result["dag_id"] == "government_load_forecasting"
    assert calls[0][0][:3] == ["airflow", "dags", "test"]
    assert calls[0][0][3] == "government_load_forecasting"
    assert calls[0][1]["env"] == {"AIRFLOW_HOME": "/tmp/gridvision-airflow"}


def test_airflow_dataset_check_skips_unchanged_data_and_reruns_on_source_change(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    data_root = tmp_path / "data"
    source = tmp_path / "source.parquet"
    source.write_bytes(b"first source")
    monkeypatch.setattr(automation, "DATA_ROOT", data_root)
    monkeypatch.setattr(automation, "SOURCE_PATH", source)
    env = {
        "GRIDVISION_DATA_DIR": str(data_root),
        "GRIDVISION_SOURCE_PATH": str(source),
    }
    calls: list[str] = []

    def fake_run_dag(command, dag_id, run_env):
        calls.append(dag_id)
        _, outputs = automation._dag_dataset_paths(dag_id, run_env)
        for output in outputs:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"generated")
        return {"dag_id": dag_id, "execution_date": "2026-11-02"}

    monkeypatch.setattr(automation, "_run_airflow_dag_test", fake_run_dag)

    first = automation._run_airflow_dag_if_dataset_changed(
        ["airflow"], automation.DAG_ID, env
    )
    unchanged = automation._run_airflow_dag_if_dataset_changed(
        ["airflow"], automation.DAG_ID, env
    )
    source.write_bytes(b"updated source")
    changed = automation._run_airflow_dag_if_dataset_changed(
        ["airflow"], automation.DAG_ID, env
    )

    assert first["skipped"] is False
    assert unchanged["skipped"] is True
    assert changed["skipped"] is False
    assert calls == [automation.DAG_ID, automation.DAG_ID]


def test_airflow_dataset_check_adopts_existing_validated_outputs(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    data_root = tmp_path / "data"
    source = tmp_path / "source.parquet"
    source.write_bytes(b"existing source")
    outputs = [
        data_root / "bronze" / source.name,
        data_root / "silver" / "customer_silver.parquet",
        data_root / "gold" / "customer_gold.parquet",
    ]
    for output in outputs:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"persisted dataset")
    manifest = (
        data_root
        / "metadata"
        / "dataset_versions"
        / "customer_gold"
        / "latest.json"
    )
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps({"quality_passed": True, "dataset_path": str(outputs[-1])}),
        encoding="utf-8",
    )
    monkeypatch.setattr(automation, "DATA_ROOT", data_root)
    monkeypatch.setattr(automation, "SOURCE_PATH", source)
    env = {
        "GRIDVISION_DATA_DIR": str(data_root),
        "GRIDVISION_SOURCE_PATH": str(source),
    }

    def unexpected_dag(*args, **kwargs):
        raise AssertionError("Existing validated outputs should be adopted")

    monkeypatch.setattr(automation, "_run_airflow_dag_test", unexpected_dag)

    result = automation._run_airflow_dag_if_dataset_changed(
        ["airflow"], automation.DAG_ID, env
    )

    assert result["skipped"] is True
    state_path = (
        data_root / "metadata" / "automation" / "airflow_dataset_state.json"
    )
    assert state_path.is_file()
    assert json.loads(state_path.read_text(encoding="utf-8"))[automation.DAG_ID]


def test_airflow_dataset_check_reruns_if_generated_dataset_is_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    data_root = tmp_path / "data"
    source = tmp_path / "source.parquet"
    source.write_bytes(b"source")
    monkeypatch.setattr(automation, "DATA_ROOT", data_root)
    monkeypatch.setattr(automation, "SOURCE_PATH", source)
    env = {
        "GRIDVISION_DATA_DIR": str(data_root),
        "GRIDVISION_SOURCE_PATH": str(source),
    }
    calls = 0

    def fake_run_dag(command, dag_id, run_env):
        nonlocal calls
        calls += 1
        _, outputs = automation._dag_dataset_paths(dag_id, run_env)
        for output in outputs:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"generated")
        return {"dag_id": dag_id, "execution_date": "2026-11-02"}

    monkeypatch.setattr(automation, "_run_airflow_dag_test", fake_run_dag)
    automation._run_airflow_dag_if_dataset_changed(
        ["airflow"], automation.DAG_ID, env
    )
    _, outputs = automation._dag_dataset_paths(automation.DAG_ID, env)
    outputs[-1].unlink()

    result = automation._run_airflow_dag_if_dataset_changed(
        ["airflow"], automation.DAG_ID, env
    )

    assert result["skipped"] is False
    assert calls == 2


def test_segmentation_dag_paths_use_bronze_source_and_published_output_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    data_root = tmp_path / "data"
    source = data_root / "bronze" / "training_sample.parquet"
    output_dir = data_root / "segmentation"
    monkeypatch.setattr(automation, "DATA_ROOT", data_root)
    monkeypatch.setattr(automation, "SOURCE_PATH", data_root / "sample" / source.name)
    env = {
        "GRIDVISION_DATA_DIR": str(data_root),
        "SEGMENTATION_SOURCE_PATH": str(source),
        "SEGMENTATION_OUTPUT_DIR": str(output_dir),
    }

    inputs, outputs = automation._dag_dataset_paths(
        automation.SEGMENTATION_DAG_ID, env
    )

    assert inputs == [source.resolve()]
    assert output_dir / "consumer_assignments.parquet" in outputs
    assert output_dir / "reports" / "geospatial_summary.json" in outputs


def test_segmentation_dag_runs_when_published_outputs_are_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    data_root = tmp_path / "data"
    source = data_root / "bronze" / "training_sample.parquet"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"bronze source")
    env = {
        "GRIDVISION_DATA_DIR": str(data_root),
        "SEGMENTATION_SOURCE_PATH": str(source),
        "SEGMENTATION_OUTPUT_DIR": str(data_root / "segmentation"),
    }
    calls: list[str] = []

    def fake_run_dag(command, dag_id, run_env):
        calls.append(dag_id)
        _, outputs = automation._dag_dataset_paths(dag_id, run_env)
        for output in outputs:
            output.parent.mkdir(parents=True, exist_ok=True)
            if output.name == "model_metadata.json":
                output.write_text(
                    json.dumps({"trained_models": []}), encoding="utf-8"
                )
            else:
                output.write_bytes(b"published output")
        return {"dag_id": dag_id, "execution_date": "2026-11-03"}

    monkeypatch.setattr(automation, "_run_airflow_dag_test", fake_run_dag)

    result = automation._run_airflow_dag_if_dataset_changed(
        ["airflow"], automation.SEGMENTATION_DAG_ID, env
    )

    assert result["skipped"] is False
    assert calls == [automation.SEGMENTATION_DAG_ID]


def test_segmentation_dag_adopts_complete_current_outputs_without_running(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    data_root = tmp_path / "data"
    source = data_root / "bronze" / "training_sample.parquet"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"bronze source")
    output_dir = data_root / "segmentation"
    reports = output_dir / "reports"
    reports.mkdir(parents=True)
    source_stat = source.stat()
    (reports / "source_profile.json").write_text(
        json.dumps(
            {
                "source_path": str(source.resolve()),
                "source_bytes": source_stat.st_size,
                "source_mtime_ns": source_stat.st_mtime_ns,
                "building_sample_fraction": 0.1,
            }
        ),
        encoding="utf-8",
    )
    (output_dir / "model_metadata.json").write_text(
        json.dumps({"trained_models": [{"model_category": "Residential"}]}),
        encoding="utf-8",
    )
    _, outputs = automation._dag_dataset_paths(
        automation.SEGMENTATION_DAG_ID,
        {
            "GRIDVISION_DATA_DIR": str(data_root),
            "SEGMENTATION_SOURCE_PATH": str(source),
            "SEGMENTATION_OUTPUT_DIR": str(output_dir),
        },
    )
    for output in outputs:
        output.parent.mkdir(parents=True, exist_ok=True)
        if not output.is_file():
            output.write_bytes(b"published artifact")

    import training.customer_segmentation.pipeline as segmentation_pipeline

    monkeypatch.setattr(
        segmentation_pipeline,
        "validate_outputs",
        lambda settings: {"status": "complete"},
    )
    monkeypatch.setattr(
        automation,
        "_run_airflow_dag_test",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("Complete current outputs should be reused")
        ),
    )
    env = {
        "GRIDVISION_DATA_DIR": str(data_root),
        "SEGMENTATION_SOURCE_PATH": str(source),
        "SEGMENTATION_OUTPUT_DIR": str(output_dir),
    }

    result = automation._run_airflow_dag_if_dataset_changed(
        ["airflow"], automation.SEGMENTATION_DAG_ID, env
    )

    assert result["skipped"] is True
    assert result["reason"] == "existing datasets adopted as the freshness baseline"


def test_changed_anomaly_dataset_forces_preparation_and_retraining(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    data_root = tmp_path / "data"
    source = tmp_path / "anomaly.parquet"
    source.write_bytes(b"source")
    outputs = [
        data_root / "silver.parquet",
        data_root / "gold.parquet",
        tmp_path / "model.joblib",
    ]
    env = {
        "GRIDVISION_DATA_DIR": str(data_root),
        "GRIDVISION_SOURCE_DATA": str(source),
        "GRIDVISION_SILVER_DATA": str(outputs[0]),
        "GRIDVISION_GOLD_DATA": str(outputs[1]),
        "GRIDVISION_MODEL_PATH": str(outputs[2]),
    }

    def fake_run_dag(command, dag_id, run_env):
        assert run_env["ANOMALY_FORCE_PREPARE"] == "1"
        assert run_env["ANOMALY_FORCE_RETRAIN"] == "1"
        for output in outputs:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"generated")
        return {"dag_id": dag_id, "execution_date": "2026-11-02"}

    monkeypatch.setattr(automation, "_run_airflow_dag_test", fake_run_dag)

    result = automation._run_airflow_dag_if_dataset_changed(
        ["airflow"], automation.ANOMALY_DAG_ID, env
    )

    assert result["skipped"] is False
    assert "ANOMALY_FORCE_PREPARE" not in env
    assert "ANOMALY_FORCE_RETRAIN" not in env


def test_anomaly_dataset_paths_use_shared_silver_and_gold_directories(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    data_root = tmp_path / "data"
    source = data_root / "anomaly_prediction" / "synthetic_2019_normal.parquet"
    source.parent.mkdir(parents=True)
    source.touch()
    monkeypatch.setattr(automation, "DATA_ROOT", data_root)

    inputs, outputs = automation._dag_dataset_paths(
        automation.ANOMALY_DAG_ID, {"GRIDVISION_DATA_DIR": str(data_root)}
    )

    assert inputs == [source.resolve()]
    assert outputs[:2] == [
        (data_root / "silver" / "synthetic_2019_silver.parquet").resolve(),
        (data_root / "gold" / "gridvision_model_features.parquet").resolve(),
    ]


def test_anomaly_freshness_state_accepts_relocated_prepared_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    data_root = tmp_path / "data"
    source = data_root / "anomaly_prediction" / "synthetic_2019_normal.parquet"
    timestamps = [
        "2019-01-01T00:00:00",
        "2019-01-01T01:00:00",
    ]
    _write_anomaly_parquet(source, timestamps, include_customer=True)
    outputs = [
        data_root / "silver" / "synthetic_2019_silver.parquet",
        data_root / "gold" / "gridvision_model_features.parquet",
        tmp_path / "model.joblib",
    ]
    _write_anomaly_parquet(outputs[0], timestamps, include_customer=True)
    _write_anomaly_parquet(outputs[1], timestamps)
    outputs[2].parent.mkdir(parents=True, exist_ok=True)
    outputs[2].write_bytes(b"generated-model")
    old_inputs = [
        {
            **automation._file_fingerprint(source),
            "path": str(data_root / "anamoly_prediction" / source.name),
        }
    ]
    old_outputs = [
        {
            **automation._file_fingerprint(outputs[0]),
            "path": str(
                data_root
                / "anomaly_prediction"
                / "silver"
                / outputs[0].name
            ),
        },
        {
            **automation._file_fingerprint(outputs[1]),
            "path": str(
                data_root
                / "anomaly_prediction"
                / "gold"
                / outputs[1].name
            ),
        },
        automation._file_fingerprint(outputs[2]),
    ]
    state_path = (
        data_root / "metadata" / "automation" / "airflow_dataset_state.json"
    )
    state_path.parent.mkdir(parents=True)
    state_path.write_text(
        json.dumps(
            {
                automation.ANOMALY_DAG_ID: {
                    "inputs": old_inputs,
                    "outputs": old_outputs,
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(automation, "DATA_ROOT", data_root)
    monkeypatch.setattr(automation, "PROJECT_ROOT", tmp_path)
    env = {
        "GRIDVISION_DATA_DIR": str(data_root),
        "GRIDVISION_SOURCE_DATA": str(source),
        "GRIDVISION_SILVER_DATA": str(outputs[0]),
        "GRIDVISION_GOLD_DATA": str(outputs[1]),
        "GRIDVISION_MODEL_PATH": str(outputs[2]),
    }

    def unexpected_dag(*args, **kwargs):
        raise AssertionError("Relocated datasets should not rerun the DAG")

    monkeypatch.setattr(automation, "_run_airflow_dag_test", unexpected_dag)

    result = automation._run_airflow_dag_if_dataset_changed(
        ["airflow"], automation.ANOMALY_DAG_ID, env
    )

    assert result["skipped"] is True
    updated = json.loads(state_path.read_text(encoding="utf-8"))[
        automation.ANOMALY_DAG_ID
    ]
    assert updated["outputs"][0]["path"] == str(outputs[0].resolve())


def test_anomaly_freshness_rebuilds_layers_from_a_different_dataset(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    data_root = tmp_path / "data"
    source = data_root / "anomaly_prediction" / "synthetic_2019_normal.parquet"
    silver = data_root / "silver" / "synthetic_2019_silver.parquet"
    gold = data_root / "gold" / "gridvision_model_features.parquet"
    model = tmp_path / "model.joblib"
    source_timestamps = ["2019-01-01T00:00:00", "2019-01-01T01:00:00"]
    _write_anomaly_parquet(source, source_timestamps, include_customer=True)
    _write_anomaly_parquet(
        silver,
        ["2018-01-01T00:00:00", "2018-01-01T01:00:00"],
        include_customer=True,
    )
    _write_anomaly_parquet(gold, source_timestamps)
    model.parent.mkdir(parents=True, exist_ok=True)
    model.write_bytes(b"existing-model")
    outputs = [silver, gold, model]
    monkeypatch.setattr(automation, "DATA_ROOT", data_root)
    env = {
        "GRIDVISION_DATA_DIR": str(data_root),
        "GRIDVISION_SOURCE_DATA": str(source),
        "GRIDVISION_SILVER_DATA": str(silver),
        "GRIDVISION_GOLD_DATA": str(gold),
        "GRIDVISION_MODEL_PATH": str(model),
    }
    state_path = (
        data_root / "metadata" / "automation" / "airflow_dataset_state.json"
    )
    automation._write_dag_dataset_state(
        state_path,
        {},
        automation.ANOMALY_DAG_ID,
        [automation._file_fingerprint(source)],
        outputs,
    )
    calls = 0

    def rebuild_dag(command, dag_id, run_env):
        nonlocal calls
        calls += 1
        assert run_env["ANOMALY_FORCE_PREPARE"] == "1"
        _write_anomaly_parquet(silver, source_timestamps, include_customer=True)
        _write_anomaly_parquet(gold, source_timestamps)
        model.write_bytes(b"rebuilt-model")
        return {"dag_id": dag_id, "execution_date": "2026-11-03"}

    monkeypatch.setattr(automation, "_run_airflow_dag_test", rebuild_dag)

    result = automation._run_airflow_dag_if_dataset_changed(
        ["airflow"], automation.ANOMALY_DAG_ID, env
    )

    assert result["skipped"] is False
    assert calls == 1
    assert automation._anomaly_prepared_data_error(source, silver, gold) is None


def test_commercial_workflow_runs_dag_before_training(monkeypatch, tmp_path) -> None:
    calls: list[str] = []

    def fake_dag(command, dag_id, env):
        calls.append(f"dag:{dag_id}")
        _, outputs = automation._dag_dataset_paths(dag_id, env)
        for output in outputs:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"generated")
        return {"dag_id": dag_id}

    def fake_run(command, **kwargs):
        calls.append("training")
        assert command[-1].endswith("mlflow\\commercial\\train_and_log.py") or command[-1].endswith("mlflow/commercial/train_and_log.py")
        return subprocess.CompletedProcess(command, 0, stdout='{"promotion_passed": true}', stderr="")

    monkeypatch.setattr(automation, "_run_airflow_dag_test", fake_dag)
    monkeypatch.setattr(automation.subprocess, "run", fake_run)
    result = automation._run_commercial_workflow(["airflow"], {"GRIDVISION_DATA_DIR": str(tmp_path)})
    assert calls == [f"dag:{automation.COMMERCIAL_DAG_ID}", "training"]
    assert result["prepared_data"]["dag_id"] == automation.COMMERCIAL_DAG_ID


def test_commercial_reuse_skips_dag_but_trains(monkeypatch, tmp_path) -> None:
    data = tmp_path / "data"
    gold, silver, manifest_path = data / "gold" / "commercial_gold.parquet", data / "silver" / "commercial_silver.parquet", data / "metadata" / "commercial" / "dataset_versions" / "gold" / "latest.json"
    for path in (gold, silver, manifest_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    gold.write_bytes(b"gold")
    silver.write_bytes(b"silver")
    manifest_path.write_text(json.dumps({"quality_passed": True, "dataset_path": str(gold)}), encoding="utf-8")
    env = {"GRIDVISION_DATA_DIR": str(data)}
    calls: list[str] = []

    def unexpected_dag(*args, **kwargs):
        raise AssertionError("DAG should be skipped when reusing prepared data")

    def fake_run(command, **kwargs):
        calls.append("training")
        return subprocess.CompletedProcess(command, 0, stdout="trained", stderr="")

    monkeypatch.setattr(automation, "_run_airflow_dag_test", unexpected_dag)
    monkeypatch.setattr(automation.subprocess, "run", fake_run)
    result = automation._run_commercial_workflow(["airflow"], env, skip_data_pipeline=True)
    assert calls == ["training"]
    assert result["prepared_data"]["gold"] == str(gold)


def test_commercial_reuse_rejects_failed_quality_manifest(tmp_path) -> None:
    data = tmp_path / "data"
    gold, silver, manifest_path = data / "gold" / "commercial_gold.parquet", data / "silver" / "commercial_silver.parquet", data / "metadata" / "commercial" / "dataset_versions" / "gold" / "latest.json"
    for path in (gold, silver, manifest_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    gold.touch()
    silver.touch()
    manifest_path.write_text(json.dumps({"quality_passed": False, "dataset_path": str(gold)}), encoding="utf-8")
    with pytest.raises(ValueError, match="failed quality"):
        automation._commercial_gold_is_reusable({"GRIDVISION_DATA_DIR": str(data)})
