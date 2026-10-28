"""Run ETL, train/register the model, and start the complete GridVision stack."""

from __future__ import annotations

import argparse
import os
import platform
import secrets
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import date
from importlib.util import find_spec
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parent
SOURCE_PATH = Path(
    os.getenv(
        "GRIDVISION_SOURCE_PATH",
        PROJECT_ROOT / "data" / "sample" / "training_sample_50000.parquet",
    )
).resolve()
DATA_ROOT = Path(os.getenv("GRIDVISION_DATA_DIR", PROJECT_ROOT / "data")).resolve()
LOG_ROOT = Path(
    os.getenv("GRIDVISION_LOG_DIR", PROJECT_ROOT / "logs")
).resolve()
LOG_SUBDIRECTORIES = (
    "airflow",
    "data/quality_reports",
    "endpoints",
    "model_cards",
    "model_metrics",
    "testing",
    "training",
)
DAG_ID = "customer_energy_data_pipeline"
GOVERNMENT_DAG_ID = "government_load_forecasting"
DEFAULT_MODEL_NAME = "customer-bill-prediction"
DEFAULT_ALIAS = "champion"
MLFLOW_HOST_PORT = os.getenv("GRIDVISION_MLFLOW_HOST_PORT", "15001")
MLFLOW_HOST_URI = f"http://127.0.0.1:{MLFLOW_HOST_PORT}"
MLFLOW_CONTAINER_URI = "http://mlflow:5001"
FRONTEND_URL = "http://127.0.0.1:8080"
BACKEND_HEALTH_URL = "http://127.0.0.1:5000/api/v1/health"
AIRFLOW_URL = "http://127.0.0.1:8081"
steps: list[dict[str, Any]] = []


def run_step(name: str, action: Callable[[], Any]) -> Any:
    started = time.perf_counter()
    print(f"\n[RUNNING] {name}", flush=True)
    try:
        result = action()
    except Exception as exc:
        elapsed = time.perf_counter() - started
        steps.append(
            {
                "name": name,
                "status": "FAILED",
                "seconds": round(elapsed, 2),
                "error": str(exc),
            }
        )
        print(f"[FAILED] {name} after {elapsed:.2f}s: {exc}", flush=True)
        raise
    elapsed = time.perf_counter() - started
    steps.append(
        {
            "name": name,
            "status": "SUCCESS",
            "seconds": round(elapsed, 2),
            "result": result,
        }
    )
    print(f"[SUCCESS] {name} in {elapsed:.2f}s", flush=True)
    return result


def _airflow_command() -> list[str]:
    if platform.system() == "Windows":
        raise RuntimeError(
            "Apache Airflow is not supported on native Windows. Run automation.py "
            "from WSL2 with the Airflow dependencies installed in the WSL Python environment."
        )
    executable = shutil.which("airflow")
    if executable:
        return [executable]
    raise FileNotFoundError(
        "Airflow CLI was not found. Install the airflow and model-serving groups "
        "from the root requirements.txt in WSL2, using the Airflow constraints "
        "URL documented in the README."
    )


def _compose_command() -> list[str]:
    docker = shutil.which("docker")
    if not docker:
        raise FileNotFoundError(
            "Docker CLI was not found. Install/start Docker Desktop with WSL "
            "integration enabled, or install Docker Engine and Compose on Linux."
        )
    command = [docker, "compose", "version"]
    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        details = "\n".join(
            output.strip()
            for output in (result.stdout, result.stderr)
            if output.strip()
        )
        if not details:
            details = "Docker returned no diagnostic output."
        raise RuntimeError(
            "Docker Compose could not run. Check Docker Desktop WSL integration "
            "for this distro or install the Docker Compose plugin. "
            f"Command: {' '.join(command)}; exit code: {result.returncode}. "
            f"Details:\n{details}"
        )
    return [docker, "compose"]


def _compose(compose: list[str], arguments: list[str], env: dict[str, str]) -> None:
    subprocess.run(
        compose + arguments,
        cwd=PROJECT_ROOT,
        env=env,
        check=True,
    )


def _run_airflow_dag_test(
    airflow_command: list[str],
    dag_id: str,
    env: dict[str, str],
) -> dict[str, str]:
    execution_date = date.today().isoformat()
    subprocess.run(
        airflow_command + ["dags", "test", dag_id, execution_date],
        cwd=PROJECT_ROOT,
        env=env,
        check=True,
    )
    result = {"dag_id": dag_id, "execution_date": execution_date}
    print(
        f"Airflow DAG run completed: {dag_id} ({execution_date}). "
        f"Inspect the run and task XComs at {AIRFLOW_URL}.",
        flush=True,
    )
    return result


def _http_healthy(url: str, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


def _wait_for_http(url: str, label: str, timeout: float = 180.0) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _http_healthy(url):
            return url
        time.sleep(2)
    raise TimeoutError(
        f"{label} did not become healthy within {timeout:.0f} seconds: {url}"
    )


def _start_airflow_ui(
    airflow_command: list[str], env: dict[str, str]
) -> dict[str, str]:
    health_url = f"{AIRFLOW_URL}/health"
    if _http_healthy(health_url):
        return {"url": AIRFLOW_URL, "status": "already running"}

    log_path = LOG_ROOT / "airflow" / "standalone.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("ab") as log_file:
        process = subprocess.Popen(
            airflow_command + ["standalone"],
            cwd=PROJECT_ROOT,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    pid_path = log_path.with_name("standalone.pid")
    pid_path.write_text(f"{process.pid}\n", encoding="ascii")
    os.chmod(log_path, 0o600)
    os.chmod(pid_path, 0o600)

    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                "Airflow standalone exited before becoming healthy. "
                f"Inspect its log at {log_path}."
            )
        if _http_healthy(health_url):
            return {"url": AIRFLOW_URL, "log": str(log_path)}
        time.sleep(2)
    raise TimeoutError(
        f"Airflow UI did not become healthy within 120 seconds. Inspect {log_path}."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-data-pipeline",
        action="store_true",
        help=(
            "Reuse the existing customer gold dataset and skip its bronze-to-gold "
            "DAG. The government load DAG still runs."
        ),
    )
    arguments = parser.parse_args(argv)
    started = time.perf_counter()
    result_code = 0
    env = os.environ.copy()
    env["GRIDVISION_DATA_DIR"] = str(DATA_ROOT)
    env["GRIDVISION_LOG_DIR"] = str(LOG_ROOT)
    env["GRIDVISION_SOURCE_PATH"] = str(SOURCE_PATH)
    env.setdefault("SECRET_KEY", secrets.token_urlsafe(48))
    env.setdefault("MLFLOW_MODEL_NAME", DEFAULT_MODEL_NAME)
    env.setdefault("MLFLOW_MODEL_ALIAS", DEFAULT_ALIAS)
    env.setdefault("AIRFLOW_HOME", str(Path.home() / ".gridvision-airflow"))
    env["AIRFLOW__CORE__DAGS_FOLDER"] = str(PROJECT_ROOT / "airflow")
    env["AIRFLOW__CORE__LOAD_EXAMPLES"] = "False"
    env["AIRFLOW__LOGGING__BASE_LOG_FOLDER"] = str(
        LOG_ROOT / "airflow" / "task_logs"
    )
    env["AIRFLOW__WEBSERVER__WEB_SERVER_HOST"] = "127.0.0.1"
    env["AIRFLOW__WEBSERVER__WEB_SERVER_PORT"] = "8081"
    env["MLFLOW_TRACKING_URI"] = MLFLOW_HOST_URI

    try:
        for directory in LOG_SUBDIRECTORIES:
            (LOG_ROOT / directory).mkdir(parents=True, exist_ok=True)

        def check_prerequisites() -> dict[str, str]:
            if not SOURCE_PATH.is_file():
                raise FileNotFoundError(
                    f"Required raw source dataset is missing: {SOURCE_PATH}"
                )
            airflow = _airflow_command()
            compose = _compose_command()
            required_modules = (
                "duckdb",
                "lightgbm",
                "mlflow",
                "pandas",
                "pyarrow",
                "sklearn",
            )
            missing_modules = [
                module for module in required_modules if find_spec(module) is None
            ]
            if missing_modules:
                raise RuntimeError(
                    "Required Python modules are missing: "
                    f"{', '.join(missing_modules)}. Install the airflow and "
                    "model-serving groups from the root requirements.txt in WSL2, "
                    "using the Airflow constraints URL documented in the README."
                )
            return {
                "airflow": airflow[0],
                "docker_compose": " ".join(compose),
                "source": str(SOURCE_PATH),
            }

        prerequisites = run_step(
            "Check source data, Python dependencies, and Docker Compose",
            check_prerequisites,
        )
        compose = prerequisites["docker_compose"].split()

        run_step(
            "Build and start persistent MLflow tracking service",
            lambda: _compose(compose, ["up", "--build", "-d", "mlflow"], env),
        )
        run_step(
            "Wait for MLflow tracking service",
            lambda: _wait_for_http(
                f"{MLFLOW_HOST_URI}/health", "MLflow", timeout=180
            ),
        )

        airflow = prerequisites["airflow"]
        airflow_command = [airflow]
        run_step(
            "Initialize Airflow metadata database",
            lambda: subprocess.run(
                airflow_command + ["db", "migrate"],
                cwd=PROJECT_ROOT,
                env=env,
                check=True,
            ).returncode,
        )
        if arguments.skip_data_pipeline:
            print(
                "\n[SKIPPED] Reusing the existing customer gold dataset",
                flush=True,
            )
        else:
            run_step(
                "Run customer bronze → silver → gold Airflow DAG",
                lambda: _run_airflow_dag_test(airflow_command, DAG_ID, env),
            )
        run_step(
            "Run government load forecasting Airflow DAG",
            lambda: _run_airflow_dag_test(
                airflow_command,
                GOVERNMENT_DAG_ID,
                env,
            )
        )
        run_step(
            "Train, evaluate, and register customer bill model with MLflow",
            lambda: subprocess.run(
                [
                    sys.executable,
                    str(
                        PROJECT_ROOT
                        / "mlflow"
                        / "customer"
                        / "train_and_register.py"
                    ),
                    "--data-path",
                    str(DATA_ROOT / "gold" / "customer_gold.parquet"),
                    "--tracking-uri",
                    MLFLOW_HOST_URI,
                    "--model-name",
                    env["MLFLOW_MODEL_NAME"],
                    "--alias",
                    env["MLFLOW_MODEL_ALIAS"],
                ],
                cwd=PROJECT_ROOT,
                env=env,
                check=True,
            ).returncode,
        )

        airflow_service = run_step(
            "Start Airflow scheduler and web UI",
            lambda: _start_airflow_ui(airflow_command, env),
        )
        stack_env = env.copy()
        stack_env["MODEL_PROVIDER"] = "mlflow"
        stack_env["MLFLOW_TRACKING_URI"] = MLFLOW_CONTAINER_URI
        run_step(
            "Build and start Flask backend and React frontend containers",
            lambda: _compose(
                compose,
                ["up", "--build", "-d", "backend", "frontend"],
                stack_env,
            ),
        )
        run_step(
            "Verify backend health",
            lambda: _wait_for_http(
                BACKEND_HEALTH_URL, "GridVision backend", timeout=180
            ),
        )
        run_step(
            "Verify frontend",
            lambda: _wait_for_http(FRONTEND_URL, "GridVision frontend", timeout=180),
        )

        print("\nGridVision services are running:", flush=True)
        print(f"  Frontend: {FRONTEND_URL}", flush=True)
        print(f"  Backend API health: {BACKEND_HEALTH_URL}", flush=True)
        print(f"  Airflow UI: {AIRFLOW_URL}", flush=True)
        print(
            f"  Airflow login details: {LOG_ROOT / 'airflow' / 'standalone.log'}",
            flush=True,
        )
        if "log" in airflow_service:
            print(
                f"  Airflow process ID: {LOG_ROOT / 'airflow' / 'standalone.pid'}",
                flush=True,
            )
        print(f"  Structured logs: {LOG_ROOT}", flush=True)
        print(f"  MLflow UI: {MLFLOW_HOST_URI}", flush=True)
        print(
            f"  Registered model: {env['MLFLOW_MODEL_NAME']}@{env['MLFLOW_MODEL_ALIAS']}",
            flush=True,
        )
        print("  Stop containers with: docker compose down", flush=True)
    except Exception as exc:
        print(f"\nAutomation stopped: {exc}", flush=True)
        result_code = 1
    finally:
        total = time.perf_counter() - started
        print("\nAutomation summary:", flush=True)
        for step in steps:
            suffix = f" — {step['error']}" if "error" in step else ""
            print(
                f"  {step['status']}: {step['name']} "
                f"({step['seconds']:.2f}s){suffix}",
                flush=True,
            )
        print(f"Total elapsed time: {total:.2f}s", flush=True)
        print(
            f"Overall result: {'SUCCESS' if result_code == 0 else 'FAILED'}",
            flush=True,
        )
    return result_code


if __name__ == "__main__":
    raise SystemExit(main())
