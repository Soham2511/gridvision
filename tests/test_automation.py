from __future__ import annotations

import subprocess

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


def test_run_airflow_dag_test_executes_requested_dag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, returncode=0)

    monkeypatch.setattr(automation.subprocess, "run", fake_run)

    result = automation._run_airflow_dag_test(
        ["airflow"],
        automation.GOVERNMENT_DAG_ID,
        {"AIRFLOW_HOME": "/tmp/gridvision-airflow"},
    )

    assert result["dag_id"] == "government_load_forecasting"
    assert calls[0][0][:3] == ["airflow", "dags", "test"]
    assert calls[0][0][3] == "government_load_forecasting"
    assert calls[0][1]["check"] is True
