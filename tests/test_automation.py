from __future__ import annotations

import subprocess
import json

import pytest

import automation


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


def test_commercial_workflow_runs_dag_before_training(monkeypatch, tmp_path) -> None:
    calls: list[str] = []

    def fake_dag(command, dag_id, env):
        calls.append(f"dag:{dag_id}")
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
