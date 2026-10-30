"""Run ETL, train/register the model, and start the complete GridVision stack."""

from __future__ import annotations

import argparse
from collections import deque
import json
import os
import platform
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
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
    "automation",
)
DAG_ID = "customer_energy_data_pipeline"
GOVERNMENT_DAG_ID = "government_load_forecasting"
COMMERCIAL_DAG_ID = "commercial_building_forecasting_data_pipeline"
DEFAULT_MODEL_NAME = "customer-bill-prediction"
DEFAULT_ALIAS = "champion"
MLFLOW_HOST_PORT = os.getenv("GRIDVISION_MLFLOW_HOST_PORT", "15001")
MLFLOW_HOST_URI = os.getenv("MLFLOW_TRACKING_URI", f"http://127.0.0.1:{MLFLOW_HOST_PORT}")
MLFLOW_CONTAINER_URI = "http://mlflow:5001"
FRONTEND_URL = "http://127.0.0.1:8082"
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
        standalone = shutil.which("docker-compose")
        if standalone:
            standalone_result = subprocess.run(
                [standalone, "version"],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            if standalone_result.returncode == 0:
                return [standalone]
        details = "\n".join(
            output.strip()
            for output in (result.stdout, result.stderr)
            if output.strip()
        )
        if not details:
            details = "Docker returned no diagnostic output."
        raise RuntimeError(
            "Docker Compose could not run. Check Docker Desktop WSL integration "
            "for this distro or install Docker Compose (the Docker Compose plugin "
            "or the standalone docker-compose command). "
            f"Command: {' '.join(command)}; exit code: {result.returncode}. "
            f"Details:\n{details}"
        )
    return [docker, "compose"]


def _stage_wsl_build_context() -> tempfile.TemporaryDirectory[str] | None:
    """Stage only Docker build inputs off DrvFS, where BuildKit xattrs can fail."""
    if platform.system() != "Linux" or not PROJECT_ROOT.as_posix().startswith("/mnt/"):
        return None

    context = tempfile.TemporaryDirectory(prefix="gridvision-docker-context-")
    root = Path(context.name)
    shutil.copy2(PROJECT_ROOT / "Dockerfile.backend", root / "Dockerfile.backend")
    shutil.copy2(PROJECT_ROOT / "Dockerfile.frontend", root / "Dockerfile.frontend")
    shutil.copy2(PROJECT_ROOT / "requirements.txt", root / "requirements.txt")
    ignored_python_cache = shutil.ignore_patterns("__pycache__", "*.pyc")
    shutil.copytree(
        PROJECT_ROOT / "scripts", root / "scripts", ignore=ignored_python_cache
    )
    shutil.copytree(
        PROJECT_ROOT / "backend" / "app",
        root / "backend" / "app",
        ignore=ignored_python_cache,
    )
    # The backend unpickles the commercial prediction pipeline from this package.
    # Stage just that inference package; the rest of training/ can be large and is
    # not needed by the serving image.
    training = root / "training"
    training.mkdir()
    shutil.copy2(PROJECT_ROOT / "training" / "__init__.py", training / "__init__.py")
    shutil.copytree(
        PROJECT_ROOT / "training" / "commercial_forecast",
        training / "commercial_forecast",
        ignore=ignored_python_cache,
    )
    shutil.copytree(
        PROJECT_ROOT / "training" / "government_load",
        training / "government_load",
        ignore=ignored_python_cache,
    )
    shutil.copy2(PROJECT_ROOT / "backend" / "run.py", root / "backend" / "run.py")

    frontend = root / "frontend"
    frontend.mkdir()
    for filename in (
        "package.json",
        "package-lock.json",
        "index.html",
        "nginx.conf",
        "vite.config.ts",
        "tsconfig.json",
        "tsconfig.app.json",
        "tsconfig.node.json",
    ):
        shutil.copy2(PROJECT_ROOT / "frontend" / filename, frontend / filename)
    for directory in ("src", "public"):
        shutil.copytree(PROJECT_ROOT / "frontend" / directory, frontend / directory)
    return context


def _compose(compose: list[str], arguments: list[str], env: dict[str, str]) -> None:
    command = compose + arguments
    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.stdout:
        print(result.stdout.rstrip(), flush=True)
    if result.stderr:
        print(result.stderr.rstrip(), file=sys.stderr, flush=True)
    if result.returncode:
        details = "\n".join(
            output.strip()
            for output in (result.stdout, result.stderr)
            if output.strip()
        ) or "Docker Compose returned no diagnostic output."
        raise RuntimeError(
            f"Docker Compose command failed (exit {result.returncode}): "
            f"{' '.join(command)}\n{details}"
        )


def _run_airflow_dag_test(
    airflow_command: list[str],
    dag_id: str,
    env: dict[str, str],
) -> dict[str, str]:
    execution_date = date.today().isoformat()
    command = airflow_command + ["dags", "test", dag_id, execution_date]
    process = subprocess.Popen(
        command,
        cwd=PROJECT_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    output_tail: deque[str] = deque(maxlen=120)
    assert process.stdout is not None
    for line in process.stdout:
        print(line, end="", flush=True)
        output_tail.append(line)
    return_code = process.wait()
    if return_code:
        details = "".join(output_tail).strip()
        raise RuntimeError(
            f"Airflow DAG test failed (exit {return_code}): {' '.join(command)}"
            + (f"\nLast task output:\n{details}" if details else "")
        )
    result = {"dag_id": dag_id, "execution_date": execution_date}
    print(
        f"Airflow DAG run completed: {dag_id} ({execution_date}). "
        f"Inspect the run and task XComs at {AIRFLOW_URL}.",
        flush=True,
    )
    return result


def _commercial_gold_is_reusable(env: dict[str, str]) -> dict[str, str]:
    """Require current Silver/Gold files and a passing manifest before reuse."""
    data_root = Path(env["GRIDVISION_DATA_DIR"])
    gold = Path(env.get("COMMERCIAL_GOLD_DATASET", data_root / "gold" / "commercial_gold.parquet"))
    silver = Path(env.get("COMMERCIAL_SILVER_DATASET", data_root / "silver" / "commercial_silver.parquet"))
    manifest_path = Path(env.get(
        "COMMERCIAL_GOLD_MANIFEST",
        data_root / "metadata" / "commercial" / "dataset_versions" / "gold" / "latest.json",
    ))
    missing = [str(path) for path in (silver, gold, manifest_path) if not path.is_file()]
    if missing:
        raise FileNotFoundError("Cannot reuse commercial prepared data; missing: " + ", ".join(missing))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not manifest.get("quality_passed"):
        raise ValueError(f"Cannot reuse commercial Gold with failed quality manifest: {manifest_path}")
    if not _manifest_dataset_matches(manifest.get("dataset_path", ""), gold):
        raise ValueError("Commercial Gold manifest points to a different dataset than the configured Gold path.")
    return {"silver": str(silver), "gold": str(gold), "manifest": str(manifest_path)}


def _manifest_dataset_matches(manifest_path: str, configured_path: Path) -> bool:
    """Accept manifests recorded under the equivalent Windows or WSL mount path."""
    if not manifest_path:
        return False
    recorded = Path(manifest_path)
    if recorded.resolve() == configured_path.resolve():
        return True
    try:
        project_relative = configured_path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return False
    return manifest_path.replace("\\", "/").endswith("/" + project_relative)


def _customer_gold_is_reusable(env: dict[str, str]) -> dict[str, str]:
    """Require the customer Gold dataset and its latest passing manifest."""
    data_root = Path(env["GRIDVISION_DATA_DIR"])
    gold = data_root / "gold" / "customer_gold.parquet"
    manifest_path = data_root / "metadata" / "dataset_versions" / "customer_gold" / "latest.json"
    missing = [str(path) for path in (gold, manifest_path) if not path.is_file()]
    if missing:
        raise FileNotFoundError("Cannot reuse customer prepared data; missing: " + ", ".join(missing))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not manifest.get("quality_passed"):
        raise ValueError(f"Cannot reuse customer Gold with failed quality manifest: {manifest_path}")
    if not _manifest_dataset_matches(manifest.get("dataset_path", ""), gold):
        raise ValueError("Customer Gold manifest points to a different dataset than the configured Gold path.")
    return {"gold": str(gold), "manifest": str(manifest_path)}


def _government_training_data_path(env: dict[str, str]) -> Path:
    """Resolve the same prepared government-data path used by its Airflow DAG."""
    configured = env.get("GOVERNMENT_PIPELINE_OUTPUT")
    if configured:
        return Path(configured).expanduser().resolve()
    return (DATA_ROOT / "airflow" / "government" / "training_ready_2018.parquet").resolve()


def _airflow_process_log_path(env: dict[str, str]) -> Path:
    """Keep Airflow process logs and PID on Linux storage when the repo is on DrvFS."""
    if platform.system() == "Linux" and PROJECT_ROOT.as_posix().startswith("/mnt/"):
        return Path(env["AIRFLOW_HOME"]).expanduser() / "logs" / "standalone.log"
    return LOG_ROOT / "airflow" / "standalone.log"


def _run_commercial_workflow(
    airflow_command: list[str], env: dict[str, str], *, skip_data_pipeline: bool = False,
) -> dict[str, Any]:
    """Prepare commercial Gold (or validate it for reuse), then train its model."""
    if skip_data_pipeline:
        prepared = _commercial_gold_is_reusable(env)
        print("[SKIPPED] Commercial DAG; reusing validated prepared Silver/Gold", flush=True)
    else:
        prepared = _run_airflow_dag_test(airflow_command, COMMERCIAL_DAG_ID, env)
    training = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "mlflow" / "commercial" / "train_and_log.py")],
        cwd=PROJECT_ROOT, env=env, check=False, capture_output=True, text=True,
    )
    if training.stdout:
        print(training.stdout.rstrip(), flush=True)
    if training.stderr:
        print(training.stderr.rstrip(), file=sys.stderr, flush=True)
    if training.returncode:
        # Exit code 2 means the run was evaluated and failed its promotion gate.
        # The MLflow run and local reports remain recorded; no model is promoted.
        raise RuntimeError(
            f"Commercial model training/evaluation failed (exit {training.returncode}); "
            "inspect logs/training/commercial and the commercial MLflow experiment."
        )
    return {"prepared_data": prepared, "training_stdout": training.stdout}


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

    log_path = _airflow_process_log_path(env)
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
        "--skip-all-data-pipelines",
        action="store_true",
        help=(
            "Reuse validated prepared data for customer, government, and commercial; "
            "still train/register all models and start services."
        ),
    )
    parser.add_argument(
        "--skip-data-pipeline",
        action="store_true",
        help=(
            "Reuse the existing customer gold dataset and skip its bronze-to-gold "
            "DAG. The government load DAG still runs."
        ),
    )
    parser.add_argument(
        "--skip-commercial-data-pipeline",
        action="store_true",
        help=(
            "Reuse existing commercial Silver/Gold data after verifying both files "
            "and the latest passing Gold quality manifest; commercial training still runs."
        ),
    )
    arguments = parser.parse_args(argv)
    steps.clear()
    started = time.perf_counter()
    run_started_at = datetime.now(timezone.utc).isoformat()
    result_code = 0
    staged_build_context: tempfile.TemporaryDirectory[str] | None = None
    env = os.environ.copy()
    env["GRIDVISION_DATA_DIR"] = str(DATA_ROOT)
    env["GRIDVISION_LOG_DIR"] = str(LOG_ROOT)
    env["GRIDVISION_SOURCE_PATH"] = str(SOURCE_PATH)
    env.setdefault("SECRET_KEY", secrets.token_urlsafe(48))
    env.setdefault("MLFLOW_MODEL_NAME", DEFAULT_MODEL_NAME)
    env.setdefault("MLFLOW_MODEL_ALIAS", DEFAULT_ALIAS)
    env.setdefault("AIRFLOW_HOME", str(Path.home() / ".gridvision-airflow"))
    if platform.system() == "Linux" and PROJECT_ROOT.as_posix().startswith("/mnt/"):
        airflow_home = Path(env["AIRFLOW_HOME"]).expanduser()
        if airflow_home.as_posix().startswith("/mnt/"):
            env["AIRFLOW_HOME"] = str(Path.home() / ".gridvision-airflow")
    env["AIRFLOW__CORE__DAGS_FOLDER"] = str(PROJECT_ROOT / "airflow")
    env["AIRFLOW__CORE__LOAD_EXAMPLES"] = "False"
    env["AIRFLOW__LOGGING__BASE_LOG_FOLDER"] = str(
        (Path(env["AIRFLOW_HOME"]).expanduser() / "logs" / "task_logs")
        if platform.system() == "Linux" and PROJECT_ROOT.as_posix().startswith("/mnt/")
        else (LOG_ROOT / "airflow" / "task_logs")
    )
    env["AIRFLOW__WEBSERVER__WEB_SERVER_HOST"] = "127.0.0.1"
    env["AIRFLOW__WEBSERVER__WEB_SERVER_PORT"] = "8081"
    env["MLFLOW_TRACKING_URI"] = MLFLOW_HOST_URI
    env.setdefault("COMMERCIAL_SILVER_DATASET", str(DATA_ROOT / "silver" / "commercial_silver.parquet"))
    env.setdefault("COMMERCIAL_GOLD_DATASET", str(DATA_ROOT / "gold" / "commercial_gold.parquet"))
    env.setdefault("COMMERCIAL_GOLD_MANIFEST", str(DATA_ROOT / "metadata" / "commercial" / "dataset_versions" / "gold" / "latest.json"))

    try:
        for directory in LOG_SUBDIRECTORIES:
            (LOG_ROOT / directory).mkdir(parents=True, exist_ok=True)

        def check_prerequisites() -> dict[str, Any]:
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
                "docker_compose": compose,
                "source": str(SOURCE_PATH),
            }

        prerequisites = run_step(
            "Check source data, Python dependencies, and Docker Compose",
            check_prerequisites,
        )
        compose = prerequisites["docker_compose"]
        staged_build_context = _stage_wsl_build_context()
        if staged_build_context:
            env["GRIDVISION_BUILD_CONTEXT"] = staged_build_context.name

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
        skip_customer_pipeline = arguments.skip_data_pipeline or arguments.skip_all_data_pipelines
        skip_commercial_pipeline = arguments.skip_commercial_data_pipeline or arguments.skip_all_data_pipelines
        if arguments.skip_all_data_pipelines:
            customer_data = _customer_gold_is_reusable(env)
            government_data = _government_training_data_path(env)
            if not government_data.is_file():
                raise FileNotFoundError(
                    "Cannot reuse government prepared data; missing: "
                    f"{government_data}"
                )
            commercial_data = _commercial_gold_is_reusable(env)
            env["GOVERNMENT_PIPELINE_REUSE_PREPARED"] = "1"
            print(
                "\n[REUSE] Validated prepared data for all personas: "
                f"customer={customer_data['gold']}, government={government_data}, "
                f"commercial={commercial_data['gold']}",
                flush=True,
            )
        run_step(
            "Initialize Airflow metadata database",
            lambda: subprocess.run(
                airflow_command + ["db", "migrate"],
                cwd=PROJECT_ROOT,
                env=env,
                check=True,
            ).returncode,
        )
        if skip_customer_pipeline:
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
            "Prepare commercial Gold and train/evaluate/register commercial champion",
            lambda: _run_commercial_workflow(
                airflow_command, env,
                skip_data_pipeline=skip_commercial_pipeline,
            ),
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
            f"  Airflow login details: {_airflow_process_log_path(env)}",
            flush=True,
        )
        if "log" in airflow_service:
            print(
                f"  Airflow process ID: {_airflow_process_log_path(env).with_name('standalone.pid')}",
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
        if staged_build_context:
            staged_build_context.cleanup()
        total = time.perf_counter() - started
        summary_path = LOG_ROOT / "automation" / f"automation-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{os.getpid()}.json"
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(
            json.dumps({
                "started_at": run_started_at,
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "elapsed_seconds": round(total, 3),
                "status": "SUCCESS" if result_code == 0 else "FAILED",
                "steps": steps,
            }, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        print("\nAutomation summary:", flush=True)
        for step in steps:
            suffix = f" — {step['error']}" if "error" in step else ""
            print(
                f"  {step['status']}: {step['name']} "
                f"({step['seconds']:.2f}s){suffix}",
                flush=True,
            )
        print(f"Total elapsed time: {total:.2f}s", flush=True)
        print(f"Structured automation summary: {summary_path}", flush=True)
        print(
            f"Overall result: {'SUCCESS' if result_code == 0 else 'FAILED'}",
            flush=True,
        )
    return result_code


if __name__ == "__main__":
    raise SystemExit(main())
