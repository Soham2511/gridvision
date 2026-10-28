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
    executable = shutil.which("airflow")
    if executable and platform.system() != "Windows":
        return [executable]

    # Native direct Python execution: fastest, completely offline, zero container build or network issues
    return ["python-direct-runner"]


def _compose_command() -> list[str]:
    cli = shutil.which("docker") or shutil.which("podman")
    if not cli:
        raise FileNotFoundError(
            "Neither Docker nor Podman CLI was found. Install Docker Desktop or Podman."
        )
    command = [cli, "compose", "version"]
    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        if "podman" in Path(cli).name.lower() and shutil.which("podman-compose"):
            return [shutil.which("podman-compose")]
        details = "\n".join(
            output.strip()
            for output in (result.stdout, result.stderr)
            if output.strip()
        )
        if not details:
            details = f"{cli} returned no diagnostic output."
        raise RuntimeError(
            f"Compose could not run with {cli}. "
            f"Command: {' '.join(command)}; exit code: {result.returncode}. "
            f"Details:\n{details}"
        )
    return [cli, "compose"]


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
    is_etl_only: bool = False,
) -> dict[str, str]:
    execution_date = date.today().isoformat()
    os.environ.update(env)
    if airflow_command == ["python-direct-runner"]:
        if dag_id == DAG_ID:
            from airflow.customer.data_pipeline import (
                SOURCE_PATH,
                BRONZE_PATH,
                SILVER_PATH,
                GOLD_PATH,
                create_bronze,
                create_customer_silver,
                build_customer_bill_gold,
            )
            create_bronze(SOURCE_PATH, BRONZE_PATH)
            create_customer_silver(BRONZE_PATH, SILVER_PATH)
            build_customer_bill_gold(SILVER_PATH, GOLD_PATH)
        elif dag_id == GOVERNMENT_DAG_ID:
            gov_dir = PROJECT_ROOT / "airflow" / "2_government_load_prediction"
            for p in (PROJECT_ROOT, gov_dir):
                if str(p) not in sys.path:
                    sys.path.insert(0, str(p))
            from training.government_load.config import PipelineSettings
            settings = PipelineSettings.from_environment()
            ready_file = settings.output_path.expanduser().resolve()
            reuse = os.getenv("GOVERNMENT_PIPELINE_REUSE_PREPARED", "").strip().lower() in {"1", "true", "yes"}
            if not (reuse and ready_file.is_file()):
                from grid_forecasting_pipeline.etl import prepare_training_data
                prepare_training_data(settings)
            if not is_etl_only and env.get("MLFLOW_TRACKING_URI"):
                from training.government_load.modeling import train_hybrid_model
                training_settings = PipelineSettings(
                    **{
                        **settings.model_dump(),
                        "input_path": ready_file,
                    }
                )
                train_hybrid_model(training_settings)
    else:
        subprocess.run(
            airflow_command + ["dags", "test", dag_id, execution_date],
            cwd=PROJECT_ROOT,
            env=env,
            check=True,
        )
    result = {"dag_id": dag_id, "execution_date": execution_date}
    print(
        f"Airflow DAG run completed: {dag_id} ({execution_date}).",
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
    parser.add_argument(
        "--remote-mlflow",
        default=os.getenv("MLFLOW_TRACKING_URI"),
        help=(
            "Remote MLflow tracking server URI (e.g. http://127.0.0.1:15001 via SSH tunnel or EC2 IP). "
            "Skips starting a local MLflow container."
        ),
    )
    parser.add_argument(
        "--pipeline-only",
        action="store_true",
        help=(
            "Run local ETL and model training only, logging to MLflow and "
            "registering the champion model, then exit without starting local containers."
        ),
    )
    parser.add_argument(
        "--etl-only",
        action="store_true",
        help=(
            "Run local Airflow ETL only to create the gold dataset and government features, "
            "without needing MLflow or EC2 running."
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

    is_remote_mlflow = bool(arguments.remote_mlflow)
    effective_mlflow_uri = arguments.remote_mlflow or MLFLOW_HOST_URI
    if not arguments.etl_only:
        env["MLFLOW_TRACKING_URI"] = effective_mlflow_uri
        os.environ["MLFLOW_TRACKING_URI"] = effective_mlflow_uri
    else:
        env.pop("MLFLOW_TRACKING_URI", None)
        os.environ.pop("MLFLOW_TRACKING_URI", None)

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
                    f"{', '.join(missing_modules)}. Install the required dependencies."
                )
            return {
                "airflow": airflow[0],
                "docker_compose": " ".join(compose),
                "source": str(SOURCE_PATH),
            }

        prerequisites = run_step(
            "Check source data, Python dependencies, and Container runtime",
            check_prerequisites,
        )
        compose = prerequisites["docker_compose"].split()

        if not arguments.etl_only:
            if is_remote_mlflow:
                run_step(
                    f"Verify connection to remote MLflow ({effective_mlflow_uri})",
                    lambda: _wait_for_http(
                        f"{effective_mlflow_uri}/health",
                        "Remote MLflow tracking service",
                        timeout=30,
                    ),
                )
            else:
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

        if airflow_command != ["python-direct-runner"] and not arguments.etl_only:
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
                "\n[SKIPPED] Reusing the existing customer gold dataset and government features",
                flush=True,
            )
            os.environ["GOVERNMENT_PIPELINE_REUSE_PREPARED"] = "1"
            env["GOVERNMENT_PIPELINE_REUSE_PREPARED"] = "1"
        else:
            run_step(
                "Run customer bronze → silver → gold Airflow DAG",
                lambda: _run_airflow_dag_test(
                    airflow_command, DAG_ID, env, is_etl_only=arguments.etl_only
                ),
            )

        run_step(
            "Run government load forecasting Airflow DAG",
            lambda: _run_airflow_dag_test(
                airflow_command,
                GOVERNMENT_DAG_ID,
                env,
                is_etl_only=arguments.etl_only,
            ),
        )

        if arguments.etl_only:
            print("\n[SUCCESS] Local ETL completed successfully!", flush=True)
            print(f"  Customer Gold Dataset: {DATA_ROOT / 'gold' / 'customer_gold.parquet'}", flush=True)
            print(f"  Government Features:   {DATA_ROOT / 'airflow' / 'government'}", flush=True)
            print("  You can now start EC2 whenever you are ready and run model training.", flush=True)
            return 0

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
                    effective_mlflow_uri,
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

        if arguments.pipeline_only:
            print("\n[SUCCESS] Local ETL and candidate model training complete!", flush=True)
            print(f"  Target MLflow: {effective_mlflow_uri}", flush=True)
            print(
                f"  Registered Model: {env['MLFLOW_MODEL_NAME']}@{env['MLFLOW_MODEL_ALIAS']}",
                flush=True,
            )
            print("  EC2 Flask service will dynamically load this champion version.", flush=True)
            return 0

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
        print(f"  MLflow UI: {effective_mlflow_uri}", flush=True)
        print(
            f"  Registered model: {env['MLFLOW_MODEL_NAME']}@{env['MLFLOW_MODEL_ALIAS']}",
            flush=True,
        )
        print("  Stop containers with: podman compose down (or docker compose down)", flush=True)
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
