"""Run ETL, train/register the model, and start the complete GridVision stack."""

from __future__ import annotations

import argparse
from collections import deque
from dataclasses import replace
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
SEGMENTATION_DAG_ID = "government_customer_segmentation"
ANOMALY_DAG_ID = "gridvision_anomaly_training"
DEFAULT_MODEL_NAME = "customer-bill-prediction"
DEFAULT_ALIAS = "champion"
AUTOMATION_APPROVED_DATA_SOURCES = (
    "customer_gold",
    "commercial_gold",
    "government_2018",
    "segmentation_2018",
    "anomaly_synthetic_2019",
)
MLFLOW_HOST_PORT = os.getenv("GRIDVISION_MLFLOW_HOST_PORT", "15001")
MLFLOW_HOST_URI = os.getenv("MLFLOW_TRACKING_URI", f"http://127.0.0.1:{MLFLOW_HOST_PORT}")
MLFLOW_CONTAINER_URI = "http://mlflow:5001"
FRONTEND_URL = "http://127.0.0.1:8082"
BACKEND_HEALTH_URL = "http://127.0.0.1:5000/api/v1/health"
BACKEND_MODEL_CATALOG_URL = "http://127.0.0.1:5000/api/v1/models"
AIRFLOW_HOST_PORT = os.getenv("GRIDVISION_AIRFLOW_HOST_PORT", "8081")
AIRFLOW_URL = f"http://127.0.0.1:{AIRFLOW_HOST_PORT}"
steps: list[dict[str, Any]] = []


def run_step(name: str, action: Callable[[], Any]) -> Any:
    started = time.perf_counter()
    print(f"\n[RUNNING] {name}", flush=True)
    try:
        result = action()
    except KeyboardInterrupt:
        elapsed = time.perf_counter() - started
        steps.append(
            {
                "name": name,
                "status": "INTERRUPTED",
                "seconds": round(elapsed, 2),
                "error": "Cancelled by user.",
            }
        )
        print(f"[INTERRUPTED] {name} after {elapsed:.2f}s", flush=True)
        raise
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


def _airflow_command(compose_command: list[str] | None = None) -> list[str]:
    if platform.system() == "Darwin":
        if not compose_command:
            raise RuntimeError(
                "Docker Compose is required to run Airflow on macOS. "
                "Start Docker Desktop and install the Compose plugin."
            )
        return compose_command + [
            "run",
            "--rm",
            "--no-deps",
            "airflow",
            "airflow",
        ]
    if platform.system() == "Windows":
        raise RuntimeError(
            "Apache Airflow is not supported on native Windows. Run automation.py "
            "from WSL2 or use Docker Desktop with WSL integration."
        )
    executable = shutil.which("airflow")
    if executable:
        return [executable]
    raise FileNotFoundError(
        "Airflow CLI was not found. Install the airflow and model-serving groups "
        "from the root requirements.txt using the Airflow constraints URL "
        "documented in the README."
    )


def _compose_command() -> list[str]:
    docker = shutil.which("docker")
    if not docker and platform.system() == "Darwin":
        for candidate in (
            Path.home() / ".docker" / "bin" / "docker",
            Path("/Applications/Docker.app/Contents/Resources/bin/docker"),
        ):
            if candidate.is_file() and os.access(candidate, os.X_OK):
                docker = str(candidate)
                break
    if not docker:
        raise FileNotFoundError(
            "Docker CLI was not found. Install and start Docker Desktop, or install "
            "Docker Engine and Compose on Linux."
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
        if platform.system() == "Linux":
            docker_exe = shutil.which("docker.exe")
            if docker_exe and docker_exe != docker:
                windows_result = subprocess.run(
                    [docker_exe, "compose", "version"],
                    cwd=PROJECT_ROOT,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                if windows_result.returncode == 0:
                    return [docker_exe, "compose"]
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
            "Docker Compose could not run. Check that Docker Desktop or Docker "
            "Engine is running and install Docker Compose (the Docker Compose "
            "plugin or the standalone docker-compose command). "
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
    shutil.copy2(PROJECT_ROOT / "Dockerfile.airflow", root / "Dockerfile.airflow")
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
    shutil.copytree(
        PROJECT_ROOT / "training" / "anomaly_prediction",
        training / "anomaly_prediction",
        ignore=ignored_python_cache,
    )
    shutil.copytree(
        PROJECT_ROOT / "training" / "customer_segmentation",
        training / "customer_segmentation",
        ignore=ignored_python_cache,
    )
    shutil.copytree(
        PROJECT_ROOT / "airflow",
        root / "airflow",
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


def _compose_service_url(
    compose: list[str],
    service: str,
    container_port: int,
    env: dict[str, str],
) -> str:
    command = compose + ["port", service, str(container_port)]
    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    address = result.stdout.strip()
    if result.returncode or not address or "\n" in address:
        details = "\n".join(
            output.strip()
            for output in (result.stdout, result.stderr)
            if output.strip()
        ) or "Docker Compose returned no published port."
        raise RuntimeError(
            f"Unable to resolve the published port for {service}:{container_port} "
            f"(exit {result.returncode}): {details}"
        )
    return f"http://{address}"


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


def _dag_dataset_paths(
    dag_id: str, env: dict[str, str]
) -> tuple[list[Path], list[Path]]:
    """Resolve source and generated dataset paths for a data-producing DAG."""
    data_root = Path(env.get("GRIDVISION_DATA_DIR", DATA_ROOT)).expanduser().resolve()
    if dag_id == DAG_ID:
        source = Path(env.get("GRIDVISION_SOURCE_PATH", SOURCE_PATH)).expanduser().resolve()
        return [source], [
            data_root / "bronze" / source.name,
            data_root / "silver" / "customer_silver.parquet",
            data_root / "gold" / "customer_gold.parquet",
        ]
    if dag_id == GOVERNMENT_DAG_ID:
        source = Path(
            env.get(
                "GOVERNMENT_PIPELINE_INPUT",
                data_root / "sample" / SOURCE_PATH.name,
            )
        ).expanduser().resolve()
        return [source], [
            Path(
                env.get(
                    "GOVERNMENT_PIPELINE_OUTPUT",
                    data_root / "airflow" / "government" / "training_ready_2018.parquet",
                )
            ).expanduser().resolve(),
            Path(
                env.get(
                    "GOVERNMENT_PIPELINE_MODEL",
                    data_root / "airflow" / "government" / "hybrid_grid_2018.joblib",
                )
            ).expanduser().resolve(),
        ]
    if dag_id == COMMERCIAL_DAG_ID:
        source = Path(env.get("GRIDVISION_SOURCE_PATH", SOURCE_PATH)).expanduser().resolve()
        return [source], [
            Path(
                env.get(
                    "COMMERCIAL_SILVER_DATASET",
                    data_root / "silver" / "commercial_silver.parquet",
                )
            ).expanduser().resolve(),
            Path(
                env.get(
                    "COMMERCIAL_GOLD_DATASET",
                    data_root / "gold" / "commercial_gold.parquet",
                )
            ).expanduser().resolve(),
        ]
    if dag_id == SEGMENTATION_DAG_ID:
        source = Path(
            env.get(
                "SEGMENTATION_SOURCE_PATH",
                data_root / "bronze" / SOURCE_PATH.name,
            )
        ).expanduser().resolve()
        output_dir = Path(
            env.get("SEGMENTATION_OUTPUT_DIR", data_root / "segmentation")
        ).expanduser().resolve()
        # Keep the automation freshness check aligned with the locations used by
        # the DAG and by SegmentationSettings.validate_outputs(). The published
        # assignments and metadata live in output_dir, while features, reports,
        # and model bundles have independently configurable shared locations.
        from training.customer_segmentation.config import SegmentationSettings

        settings = replace(
            SegmentationSettings.from_environment(),
            output_dir=output_dir,
            feature_path=Path(
                env.get(
                    "SEGMENTATION_FEATURE_PATH",
                    data_root / "gold" / "customer_segmentation_features.parquet",
                )
            ).expanduser().resolve(),
            model_dir=Path(
                env.get("SEGMENTATION_MODEL_DIR", PROJECT_ROOT / "models" / "segmentation")
            ).expanduser().resolve(),
            reports_dir=Path(
                env.get(
                    "SEGMENTATION_REPORTS_DIR",
                    PROJECT_ROOT / "docs" / "customer_segmentation" / "reports",
                )
            ).expanduser().resolve(),
        )
        outputs = [
            settings.feature_path,
            output_dir / "consumer_assignments.parquet",
            output_dir / "cluster_profiles.parquet",
            output_dir / "segment_distribution.parquet",
            output_dir / "region_summary_coarse.parquet",
            output_dir / "region_summary_finer.parquet",
            output_dir / "survey_priority.parquet",
            output_dir / "cluster_hourly_profile.parquet",
            output_dir / "cluster_daily_profile.parquet",
            output_dir / "cluster_monthly_profile.parquet",
            output_dir / "model_metadata.json",
            settings.reports_dir / "model_selection_report.json",
            settings.reports_dir / "feature_diagnostics.json",
            settings.reports_dir / "source_profile.json",
            settings.reports_dir / "feature_generation.json",
            settings.reports_dir / "geospatial_summary.json",
        ]
        if float(env.get("SEGMENTATION_BUILDING_SAMPLE_FRACTION", "0.1")) < 1:
            outputs.extend(
                [
                    output_dir / "source_sample.parquet",
                    output_dir / "reports" / "source_sample.json",
                ]
            )
        metadata_path = output_dir / "model_metadata.json"
        if metadata_path.is_file():
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            outputs.extend(
                settings.model_dir
                / f"{model['model_category'].lower()}_model.joblib"
                for model in metadata.get("trained_models", [])
            )
        return [source], outputs
    if dag_id == ANOMALY_DAG_ID:
        source = Path(
            env.get(
                "GRIDVISION_SOURCE_DATA",
                data_root / "anomaly_prediction" / "synthetic_2019_normal.parquet",
            )
        ).expanduser().resolve()
        return [source], [
            Path(
                env.get(
                    "GRIDVISION_SILVER_DATA",
                    data_root / "silver" / "synthetic_2019_silver.parquet",
                )
            ).expanduser().resolve(),
            Path(
                env.get(
                    "GRIDVISION_GOLD_DATA",
                    data_root / "gold" / "gridvision_model_features.parquet",
                )
            ).expanduser().resolve(),
            Path(
                env.get(
                    "GRIDVISION_MODEL_PATH",
                    PROJECT_ROOT
                    / "models"
                    / "anomaly_prediction"
                    / "gridvision_anomaly_model.joblib",
                )
            ).expanduser().resolve(),
        ]
    raise ValueError(f"No dataset freshness configuration for Airflow DAG {dag_id!r}.")


def _file_fingerprint(path: Path) -> dict[str, int | str]:
    stat = path.stat()
    return {
        "path": str(path.resolve()),
        "size_bytes": stat.st_size,
        "modified_ns": stat.st_mtime_ns,
    }


def _anomaly_prepared_data_error(
    source: Path, silver: Path, gold: Path
) -> str | None:
    """Return why anomaly layers cannot be reused for this source, if any."""
    import pyarrow.parquet as pq

    source_parquet = pq.ParquetFile(source)
    silver_parquet = pq.ParquetFile(silver)
    gold_parquet = pq.ParquetFile(gold)

    if source_parquet.metadata.num_rows != silver_parquet.metadata.num_rows:
        return (
            "Silver row count does not match the anomaly source "
            f"({silver_parquet.metadata.num_rows} != "
            f"{source_parquet.metadata.num_rows})"
        )
    if source_parquet.schema.names != silver_parquet.schema.names:
        return "Silver columns do not match the anomaly source"

    def timestamp_bounds(parquet: Any) -> tuple[Any, Any] | None:
        column_index = parquet.schema_arrow.get_field_index("timestamp")
        if column_index < 0:
            return None
        statistics = [
            row_group.column(column_index).statistics
            for row_group in (
                parquet.metadata.row_group(index)
                for index in range(parquet.metadata.num_row_groups)
            )
        ]
        bounds = [
            (stats.min, stats.max)
            for stats in statistics
            if stats is not None and stats.has_min_max
        ]
        if not bounds:
            return None
        return min(bound[0] for bound in bounds), max(bound[1] for bound in bounds)

    source_bounds = timestamp_bounds(source_parquet)
    silver_bounds = timestamp_bounds(silver_parquet)
    gold_bounds = timestamp_bounds(gold_parquet)
    if source_bounds is None:
        return "Anomaly source has no usable timestamp statistics"
    if silver_bounds is None:
        return "Silver has no usable timestamp statistics"
    if gold_bounds is None:
        return "Gold has no usable timestamp statistics"
    if source_bounds != silver_bounds:
        return (
            "Silver timestamp range does not match the anomaly source "
            f"({silver_bounds} != {source_bounds})"
        )
    if gold_bounds != source_bounds:
        return (
            "Gold timestamp range does not match the anomaly source "
            f"({gold_bounds} != {source_bounds})"
        )
    return None


def _existing_dag_outputs_are_reusable(
    dag_id: str,
    env: dict[str, str],
    outputs: list[Path],
) -> bool:
    """Adopt complete outputs from earlier automation runs as the initial baseline."""
    if not outputs or any(not path.is_file() or path.stat().st_size == 0 for path in outputs):
        return False
    if dag_id == DAG_ID:
        try:
            _customer_gold_is_reusable(env)
        except (FileNotFoundError, ValueError, json.JSONDecodeError):
            return False
    elif dag_id == COMMERCIAL_DAG_ID:
        try:
            _commercial_gold_is_reusable(env)
        except (FileNotFoundError, ValueError, json.JSONDecodeError):
            return False
    elif dag_id == SEGMENTATION_DAG_ID:
        try:
            source, _ = _dag_dataset_paths(dag_id, env)
            source_path = source[0].resolve()
            source_stat = source_path.stat()
            from training.customer_segmentation.config import SegmentationSettings

            data_root = Path(
                env.get("GRIDVISION_DATA_DIR", DATA_ROOT)
            ).expanduser().resolve()
            settings = replace(
                SegmentationSettings.from_environment(),
                output_dir=Path(
                    env.get("SEGMENTATION_OUTPUT_DIR", data_root / "segmentation")
                ).expanduser().resolve(),
                feature_path=Path(
                    env.get(
                        "SEGMENTATION_FEATURE_PATH",
                        data_root / "gold" / "customer_segmentation_features.parquet",
                    )
                ).expanduser().resolve(),
                model_dir=Path(
                    env.get("SEGMENTATION_MODEL_DIR", PROJECT_ROOT / "models" / "segmentation")
                ).expanduser().resolve(),
                reports_dir=Path(
                    env.get(
                        "SEGMENTATION_REPORTS_DIR",
                        PROJECT_ROOT / "docs" / "customer_segmentation" / "reports",
                    )
                ).expanduser().resolve(),
            )
            source_profile = settings.reports_dir / "source_profile.json"
            profile = json.loads(source_profile.read_text(encoding="utf-8"))
            expected_source_paths = {str(source_path)}
            try:
                source_relative_to_data = source_path.relative_to(data_root)
            except ValueError:
                pass
            else:
                expected_source_paths.add(
                    str(Path("/opt/gridvision/data") / source_relative_to_data)
                )
            if (
                profile.get("source_path") not in expected_source_paths
                or profile.get("source_bytes") != source_stat.st_size
                or profile.get("source_mtime_ns") != source_stat.st_mtime_ns
                or profile.get("building_sample_fraction")
                != float(env.get("SEGMENTATION_BUILDING_SAMPLE_FRACTION", "0.1"))
            ):
                return False
            from training.customer_segmentation.pipeline import validate_outputs

            validate_outputs(
                replace(
                    settings,
                    output_dir=Path(
                        env.get(
                            "SEGMENTATION_OUTPUT_DIR",
                            Path(env.get("GRIDVISION_DATA_DIR", DATA_ROOT))
                            / "segmentation",
                        )
                    )
                    .expanduser()
                    .resolve(),
                )
            )
        except (FileNotFoundError, ValueError, KeyError, json.JSONDecodeError):
            return False
    elif dag_id == ANOMALY_DAG_ID:
        source, _ = _dag_dataset_paths(dag_id, env)
        if _anomaly_prepared_data_error(source[0], outputs[0], outputs[1]):
            return False
        report = Path(
            env.get(
                "GRIDVISION_REPORT_DIR",
                PROJECT_ROOT / "reports" / "anomaly_prediction" / "training",
            )
        ).expanduser().resolve() / "evaluation_metrics.json"
        if not report.is_file() or report.stat().st_size == 0:
            return False
    elif dag_id == GOVERNMENT_DAG_ID:
        feature_columns = Path(
            env.get(
                "GOVERNMENT_PIPELINE_FEATURES",
                PROJECT_ROOT / "mlflow" / "government" / "feature_columns_2018.joblib",
            )
        ).expanduser().resolve()
        if not feature_columns.is_file():
            return False
    else:
        raise ValueError(f"No dataset freshness configuration for Airflow DAG {dag_id!r}.")
    return True


def _write_dag_dataset_state(
    state_path: Path,
    state: dict[str, Any],
    dag_id: str,
    inputs: list[dict[str, int | str]],
    outputs: list[Path],
) -> None:
    state[dag_id] = {
        "inputs": inputs,
        "outputs": [_file_fingerprint(path) for path in outputs],
    }
    state_path.parent.mkdir(parents=True, exist_ok=True)
    staged_state = state_path.with_name(f"{state_path.name}.{os.getpid()}.stage")
    staged_state.write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(staged_state, state_path)


def _run_airflow_dag_if_dataset_changed(
    airflow_command: list[str],
    dag_id: str,
    env: dict[str, str],
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Skip a DAG when its recorded input and generated datasets are unchanged."""
    inputs, outputs = _dag_dataset_paths(dag_id, env)
    missing_inputs = [str(path) for path in inputs if not path.is_file()]
    if missing_inputs:
        raise FileNotFoundError(
            f"Cannot check freshness for {dag_id}; source dataset is missing: "
            + ", ".join(missing_inputs)
        )

    input_fingerprints = [_file_fingerprint(path) for path in inputs]
    if dag_id == SEGMENTATION_DAG_ID:
        input_fingerprints.append(
            {
                "path": "SEGMENTATION_BUILDING_SAMPLE_FRACTION",
                "size": int(
                    float(env.get("SEGMENTATION_BUILDING_SAMPLE_FRACTION", "0.1"))
                    * 1_000_000_000
                ),
                "mtime_ns": 0,
            }
        )
    state_path = (
        Path(env.get("GRIDVISION_DATA_DIR", DATA_ROOT)).expanduser().resolve()
        / "metadata"
        / "automation"
        / "airflow_dataset_state.json"
    )
    state: dict[str, Any] = {}
    if state_path.is_file():
        state = json.loads(state_path.read_text(encoding="utf-8"))
    previous = state.get(dag_id, {})
    outputs_exist = all(path.is_file() for path in outputs)
    current_output_fingerprints = (
        [_file_fingerprint(path) for path in outputs] if outputs_exist else []
    )
    inputs_unchanged = previous.get("inputs") == input_fingerprints
    outputs_unchanged = previous.get("outputs") == current_output_fingerprints
    if dag_id == ANOMALY_DAG_ID:
        inputs_unchanged = inputs_unchanged or _fingerprints_match_after_relocation(
            previous.get("inputs", []), input_fingerprints
        )
        outputs_unchanged = outputs_unchanged or _fingerprints_match_after_relocation(
            previous.get("outputs", []), current_output_fingerprints
        )
        if outputs_exist:
            source_mismatch = _anomaly_prepared_data_error(
                inputs[0], outputs[0], outputs[1]
            )
            if source_mismatch:
                outputs_unchanged = False
                print(
                    f"[STALE] Anomaly prepared data will be rebuilt: "
                    f"{source_mismatch}",
                    flush=True,
                )

    if (
        not force
        and not previous
        and outputs_exist
        and _existing_dag_outputs_are_reusable(dag_id, env, outputs)
    ):
        _write_dag_dataset_state(
            state_path, state, dag_id, input_fingerprints, outputs
        )
        print(
            f"[SKIPPED] Airflow DAG {dag_id}: adopting existing validated "
            "datasets as the freshness baseline",
            flush=True,
        )
        return {
            "dag_id": dag_id,
            "skipped": True,
            "reason": "existing datasets adopted as the freshness baseline",
        }

    if (
        not force
        and outputs_exist
        and inputs_unchanged
        and outputs_unchanged
    ):
        _write_dag_dataset_state(
            state_path, state, dag_id, input_fingerprints, outputs
        )
        print(
            f"[SKIPPED] Airflow DAG {dag_id}: source and generated datasets "
            "are unchanged",
            flush=True,
        )
        return {
            "dag_id": dag_id,
            "skipped": True,
            "reason": "source and generated datasets are unchanged",
        }

    dag_env = env.copy()
    if dag_id == ANOMALY_DAG_ID:
        dag_env["ANOMALY_FORCE_PREPARE"] = "1"
        dag_env["ANOMALY_FORCE_RETRAIN"] = "1"
    result = _run_airflow_dag_test(airflow_command, dag_id, dag_env)
    if dag_id == SEGMENTATION_DAG_ID:
        _, outputs = _dag_dataset_paths(dag_id, env)
    missing_outputs = [
        str(path)
        for path in outputs
        if not path.is_file() or path.stat().st_size == 0
    ]
    if missing_outputs:
        raise FileNotFoundError(
            f"Airflow DAG {dag_id} succeeded but expected datasets are missing: "
            + ", ".join(missing_outputs)
        )
    _write_dag_dataset_state(
        state_path, state, dag_id, input_fingerprints, outputs
    )
    return {**result, "skipped": False}


def _fingerprints_match_after_relocation(
    previous: list[dict[str, Any]], current: list[dict[str, Any]]
) -> bool:
    """Match moved files by stable basename, size, and mtime during path migrations."""
    return bool(previous) and len(previous) == len(current) and all(
        Path(old.get("path", "")).name == Path(new.get("path", "")).name
        and old.get("size_bytes") == new.get("size_bytes")
        and old.get("modified_ns") == new.get("modified_ns")
        for old, new in zip(previous, current)
    )


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
    airflow_command: list[str],
    env: dict[str, str],
    *,
    skip_data_pipeline: bool = False,
    force_airflow: bool = False,
) -> dict[str, Any]:
    """Prepare commercial Gold (or validate it for reuse), then train its model."""
    if skip_data_pipeline:
        prepared = _commercial_gold_is_reusable(env)
        print("[SKIPPED] Commercial DAG; reusing validated prepared Silver/Gold", flush=True)
    else:
        prepared = _run_airflow_dag_if_dataset_changed(
            airflow_command,
            COMMERCIAL_DAG_ID,
            env,
            force=force_airflow,
        )
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


def _run_anomaly_inference(env: dict[str, str]) -> dict[str, Any]:
    """Run real saved-model inference and persist event-level application outputs."""
    runtime_path = (
        PROJECT_ROOT
        / "backend"
        / "app"
        / "models"
        / "anomaly_prediction"
        / "runtime"
    )
    backend_path = PROJECT_ROOT / "backend"
    if str(backend_path) not in sys.path:
        sys.path.insert(0, str(backend_path))
    if str(runtime_path) not in sys.path:
        sys.path.insert(0, str(runtime_path))
    from app.models.anomaly_prediction import AnomalyPredictionService

    service = AnomalyPredictionService(
        dataset_path=env["ANOMALY_DATASET_PATH"],
        model_path=env["ANOMALY_MODEL_PATH"],
        project_root=PROJECT_ROOT,
        runs_path=env["ANOMALY_RUNS_PATH"],
    )
    model_metadata = service.get_model_metadata()
    start_date = env.get("ANOMALY_START_DATE") or model_metadata["source_start"][:10]
    end_date = env.get("ANOMALY_END_DATE") or start_date
    configured_ids = env.get("ANOMALY_CUSTOMER_IDS", "").strip()
    customer_ids = None
    if configured_ids:
        pieces = [value.strip() for value in configured_ids.split(",")]
        if any(not value.isdigit() or int(value) < 1 for value in pieces):
            raise ValueError("ANOMALY_CUSTOMER_IDS must contain positive integer IDs.")
        customer_ids = [int(value) for value in pieces]
    result = service.run_analysis(
        {
            "customer_ids": customer_ids,
            "start_date": start_date,
            "end_date": end_date,
        }
    )
    return {
        "run_id": result["run_id"],
        "status": result["status"],
        "metrics": result["metrics"],
    }


def _run_anomaly_training(env: dict[str, str]) -> dict[str, Any]:
    command = [
        sys.executable,
        str(PROJECT_ROOT / "training" / "anomaly_prediction" / "train.py"),
    ]
    result = subprocess.run(
        command, cwd=PROJECT_ROOT, env=env, check=False, capture_output=True, text=True
    )
    if result.stdout:
        print(result.stdout.rstrip(), flush=True)
    if result.stderr:
        print(result.stderr.rstrip(), file=sys.stderr, flush=True)
    if result.returncode:
        raise RuntimeError(
            "Anomaly preparation/training/MLflow tracking failed "
            f"(exit {result.returncode})."
        )
    return {"command": command, "stdout": result.stdout}


def _run_anomaly_only_mode(env: dict[str, str]) -> int:
    """Run anomaly preparation, tracking, inference, and exports without other services."""
    started = time.perf_counter()
    run_started_at = datetime.now(timezone.utc).isoformat()
    status = 0
    try:
        (LOG_ROOT / "automation").mkdir(parents=True, exist_ok=True)

        def validate_anomaly_inputs() -> dict[str, str]:
            dataset = Path(env["ANOMALY_DATASET_PATH"])
            if not dataset.is_file():
                raise FileNotFoundError(f"Anomaly source data is missing: {dataset}")
            missing_modules = [
                module
                for module in ("flask_cors", "h3", "pywt", "pyarrow", "sklearn")
                if find_spec(module) is None
            ]
            if missing_modules:
                raise RuntimeError(
                    "Required anomaly modules are missing: "
                    + ", ".join(missing_modules)
                )
            return {
                "dataset": str(dataset),
                "model": env["ANOMALY_MODEL_PATH"],
                "tracking_uri": env["MLFLOW_TRACKING_URI"],
            }

        run_step(
            "Validate anomaly model dependencies and source data",
            validate_anomaly_inputs,
        )
        run_step(
            "Prepare anomaly data, evaluate, and track/register the model",
            lambda: _run_anomaly_training(env),
        )
        run_step(
            "Run anomaly inference, spatial localization, event generation, and storage",
            lambda: _run_anomaly_inference(env),
        )
    except Exception as exc:
        print(f"\nAnomaly automation stopped: {exc}", flush=True)
        status = 1
    finally:
        total = time.perf_counter() - started
        summary_path = (
            LOG_ROOT
            / "automation"
            / f"anomaly-automation-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{os.getpid()}.json"
        )
        summary_path.write_text(
            json.dumps(
                {
                    "started_at": run_started_at,
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                    "elapsed_seconds": round(total, 3),
                    "status": "SUCCESS" if status == 0 else "FAILED",
                    "steps": steps,
                },
                indent=2,
                sort_keys=True,
                default=str,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"Anomaly automation summary: {summary_path}", flush=True)
    return status


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


def _verify_model_catalog(
    catalog_url: str = BACKEND_MODEL_CATALOG_URL,
) -> dict[str, Any]:
    """Fail automation if the deployed API does not expose every trained model."""
    with urllib.request.urlopen(catalog_url, timeout=30) as response:
        payload = json.load(response)
    models = payload.get("data", {}).get("models")
    if not isinstance(models, list):
        raise RuntimeError("Backend model catalog response has no models list.")

    required_ids = {
        "customer-bill-prediction",
        "commercial-building-forecast",
        "government-load-forecast",
        "government-customer-segmentation",
        "anomaly-prediction",
    }
    catalog = {
        str(model.get("modelId")): model
        for model in models
        if isinstance(model, dict) and model.get("modelId")
    }
    missing = sorted(required_ids.difference(catalog))
    unavailable = {
        model_id: (
            f"{catalog[model_id].get('error', 'status is unavailable')} "
            f"(provider={catalog[model_id].get('provider', 'unknown')}, "
            f"version={catalog[model_id].get('modelVersion', 'unknown')}, "
            f"selected={catalog[model_id].get('selectedModel', 'unknown')})"
        )
        for model_id in sorted(required_ids.intersection(catalog))
        if catalog[model_id].get("status") != "configured"
    }
    if missing or unavailable:
        details = []
        if missing:
            details.append(f"missing model entries: {', '.join(missing)}")
        if unavailable:
            details.append(
                "unavailable models: "
                + "; ".join(
                    f"{model_id}: {reason}"
                    for model_id, reason in unavailable.items()
                )
            )
        raise RuntimeError(
            "The deployed model catalog does not match the completed pipelines ("
            + " | ".join(details)
            + ")."
        )

    return {
        "configured_models": [
            {
                "model_id": model_id,
                "name": catalog[model_id].get("name"),
                "model_version": catalog[model_id].get("modelVersion"),
                "run_summary": catalog[model_id].get("runSummary"),
            }
            for model_id in sorted(required_ids)
        ]
    }


def _backend_stack_environment(env: dict[str, str]) -> dict[str, str]:
    """Configure the backend for model and data outputs prepared by automation."""
    stack_env = env.copy()
    stack_env["MODEL_PROVIDER"] = "mlflow"
    stack_env["MLFLOW_TRACKING_URI"] = MLFLOW_CONTAINER_URI
    stack_env.setdefault(
        "APPROVED_DATA_SOURCES",
        ",".join(AUTOMATION_APPROVED_DATA_SOURCES),
    )
    return stack_env


def _start_airflow_ui(
    airflow_command: list[str],
    env: dict[str, str],
    compose_command: list[str] | None = None,
) -> dict[str, str]:
    health_url = f"{AIRFLOW_URL}/health"
    if platform.system() == "Darwin":
        if not compose_command:
            raise RuntimeError("Docker Compose is required to start Airflow on macOS.")
        _compose(compose_command, ["up", "-d", "airflow"], env)
        _wait_for_http(health_url, "Airflow UI", timeout=240)
        return {
            "url": AIRFLOW_URL,
            "log": str(LOG_ROOT / "airflow" / "standalone.log"),
            "status": "running in Docker",
        }

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
            "Reuse validated prepared data for customer, government, commercial, "
            "and segmentation; still train/register customer and commercial models "
            "and start services."
        ),
    )
    parser.add_argument(
        "--skip-data-pipeline",
        action="store_true",
        help=(
            "Reuse the existing customer gold dataset and skip its bronze-to-gold "
            "DAG. Government load forecasting and customer segmentation still run."
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
    parser.add_argument(
        "--force-airflow-dags",
        action="store_true",
        help="Run data-producing Airflow DAGs even when their datasets are unchanged.",
    )
    parser.add_argument(
        "--anomaly-only",
        action="store_true",
        help=(
            "Run only anomaly preparation/training or artifact reuse, MLflow tracking, "
            "inference, localization, and result storage."
        ),
    )
    parser.add_argument(
        "--force-anomaly-retrain",
        action="store_true",
        help="Retrain the anomaly detector instead of reusing a valid saved artifact.",
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
    env["GRIDVISION_SOURCE_FILENAME"] = SOURCE_PATH.name
    env.setdefault(
        "SEGMENTATION_SOURCE_PATH",
        str(DATA_ROOT / "bronze" / SOURCE_PATH.name),
    )
    env.setdefault("SEGMENTATION_OUTPUT_DIR", str(DATA_ROOT / "segmentation"))
    env.setdefault(
        "GRIDVISION_SOURCE_DATA",
        str(DATA_ROOT / "anomaly_prediction" / "synthetic_2019_normal.parquet"),
    )
    env.setdefault(
        "GRIDVISION_SILVER_DATA",
        str(DATA_ROOT / "silver" / "synthetic_2019_silver.parquet"),
    )
    env.setdefault(
        "GRIDVISION_GOLD_DATA",
        str(DATA_ROOT / "gold" / "gridvision_model_features.parquet"),
    )
    env.setdefault(
        "GRIDVISION_MODEL_PATH",
        str(PROJECT_ROOT / "models" / "anomaly_prediction" / "gridvision_anomaly_model.joblib"),
    )
    env.setdefault(
        "GRIDVISION_REPORT_DIR",
        str(PROJECT_ROOT / "reports" / "anomaly_prediction" / "training"),
    )
    env.setdefault(
        "ANOMALY_DATASET_PATH",
        str(DATA_ROOT / "anomaly_prediction" / "synthetic_2019_normal.parquet"),
    )
    env.setdefault(
        "ANOMALY_MODEL_PATH",
        str(PROJECT_ROOT / "models" / "anomaly_prediction" / "gridvision_anomaly_model.joblib"),
    )
    env.setdefault(
        "ANOMALY_RUNS_PATH",
        str(PROJECT_ROOT / "reports" / "anomaly_prediction" / "application_runs"),
    )
    env.setdefault("ANOMALY_MLFLOW_MODEL_NAME", "gridvision-anomaly-detection")
    env.setdefault("ANOMALY_MLFLOW_MODEL_ALIAS", "champion")
    if arguments.force_anomaly_retrain:
        env["ANOMALY_FORCE_RETRAIN"] = "1"
    if hasattr(os, "getuid"):
        env.setdefault("AIRFLOW_UID", str(os.getuid()))
    env.setdefault("SECRET_KEY", secrets.token_urlsafe(48))
    env.setdefault("MLFLOW_MODEL_NAME", DEFAULT_MODEL_NAME)
    env.setdefault("MLFLOW_MODEL_ALIAS", DEFAULT_ALIAS)
    env.setdefault(
        "COMMERCIAL_MLFLOW_MODEL_NAME",
        "gridvision-commercial-building-forecast",
    )
    env.setdefault(
        "COMMERCIAL_MLFLOW_MODEL_ALIAS", env["MLFLOW_MODEL_ALIAS"]
    )
    env.setdefault(
        "GOVERNMENT_MLFLOW_MODEL_NAME",
        "gridvision-government-load-forecast",
    )
    env.setdefault(
        "GOVERNMENT_MLFLOW_MODEL_ALIAS", env["MLFLOW_MODEL_ALIAS"]
    )
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
    env.setdefault("GIT_PYTHON_REFRESH", "quiet")
    env.setdefault("MLFLOW_TRACKING_URI", MLFLOW_HOST_URI)
    env.setdefault("COMMERCIAL_SILVER_DATASET", str(DATA_ROOT / "silver" / "commercial_silver.parquet"))
    env.setdefault("COMMERCIAL_GOLD_DATASET", str(DATA_ROOT / "gold" / "commercial_gold.parquet"))
    env.setdefault("COMMERCIAL_GOLD_MANIFEST", str(DATA_ROOT / "metadata" / "commercial" / "dataset_versions" / "gold" / "latest.json"))
    if arguments.anomaly_only:
        steps.clear()
        return _run_anomaly_only_mode(env)

    try:
        for directory in LOG_SUBDIRECTORIES:
            (LOG_ROOT / directory).mkdir(parents=True, exist_ok=True)

        def check_prerequisites() -> dict[str, Any]:
            if not arguments.skip_all_data_pipelines and not SOURCE_PATH.is_file():
                raise FileNotFoundError(
                    f"Required raw source dataset is missing: {SOURCE_PATH}"
                )
            compose = _compose_command()
            docker_directory = str(Path(compose[0]).expanduser().resolve().parent)
            path_entries = env.get("PATH", "").split(os.pathsep)
            if docker_directory not in path_entries:
                env["PATH"] = os.pathsep.join(
                    [docker_directory, *path_entries]
                )
            airflow = _airflow_command(compose)
            required_modules = [
                "duckdb",
                "lightgbm",
                "mlflow",
                "pandas",
                "pyarrow",
                "pywt",
                "sklearn",
            ]
            if platform.system() != "Darwin":
                required_modules.append("airflow")
            missing_modules = [
                module for module in required_modules if find_spec(module) is None
            ]
            if missing_modules:
                install_hint = (
                    "Install the model-serving group from requirements.txt; "
                    "Airflow runs in Docker on macOS."
                    if platform.system() == "Darwin"
                    else "Install the airflow and model-serving groups from "
                    "requirements.txt using the Airflow constraints URL documented "
                    "in the README."
                )
                raise RuntimeError(
                    "Required Python modules are missing: "
                    f"{', '.join(missing_modules)}. {install_hint}"
                )
            return {
                "airflow": airflow,
                "docker_compose": compose,
                "source": str(SOURCE_PATH) if SOURCE_PATH.is_file() else None,
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
        airflow_command = airflow
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
            if not _existing_dag_outputs_are_reusable(
                SEGMENTATION_DAG_ID,
                env,
                _dag_dataset_paths(SEGMENTATION_DAG_ID, env)[1],
            ):
                raise FileNotFoundError(
                    "Cannot reuse customer segmentation data; published "
                    "segmentation outputs are missing or incomplete. Run "
                    "automation.py without --skip-all-data-pipelines to create them."
                )
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
                lambda: _run_airflow_dag_if_dataset_changed(
                    airflow_command,
                    DAG_ID,
                    env,
                    force=arguments.force_airflow_dags,
                ),
            )
        run_step(
            "Run government load forecasting Airflow DAG",
            lambda: _run_airflow_dag_if_dataset_changed(
                airflow_command,
                GOVERNMENT_DAG_ID,
                env,
                force=arguments.force_airflow_dags,
            )
        )
        run_step(
            "Generate and publish Government customer segmentation outputs",
            lambda: _run_airflow_dag_if_dataset_changed(
                airflow_command,
                SEGMENTATION_DAG_ID,
                env,
                force=arguments.force_airflow_dags,
            ),
        )
        run_step(
            "Prepare commercial Gold and train/evaluate/register commercial champion",
            lambda: _run_commercial_workflow(
                airflow_command, env,
                skip_data_pipeline=skip_commercial_pipeline,
                force_airflow=arguments.force_airflow_dags,
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
        run_step(
            "Prepare, evaluate, and register anomaly model through Airflow",
            lambda: _run_airflow_dag_if_dataset_changed(
                airflow_command,
                ANOMALY_DAG_ID,
                env,
                force=arguments.force_airflow_dags,
            ),
        )
        run_step(
            "Run anomaly inference, spatial localization, event generation, and storage",
            lambda: _run_anomaly_inference(env),
        )

        airflow_service = run_step(
            "Start Airflow scheduler and web UI",
            lambda: _start_airflow_ui(airflow_command, env, compose),
        )
        stack_env = _backend_stack_environment(env)
        run_step(
            "Build and start Flask backend and React frontend containers",
            lambda: _compose(
                compose,
                ["up", "--build", "-d", "backend", "frontend"],
                stack_env,
            ),
        )
        backend_base_url = run_step(
            "Resolve the deployed backend endpoint",
            lambda: _compose_service_url(compose, "backend", 5000, stack_env),
        )
        run_step(
            "Verify backend health",
            lambda: _wait_for_http(
                f"{backend_base_url}/api/v1/health",
                "GridVision backend",
                timeout=180,
            ),
        )
        run_step(
            "Verify configured models are published in the backend catalog",
            lambda: _verify_model_catalog(f"{backend_base_url}/api/v1/models"),
        )
        run_step(
            "Verify frontend",
            lambda: _wait_for_http(FRONTEND_URL, "GridVision frontend", timeout=180),
        )

        print("\nGridVision services are running:", flush=True)
        print(f"  Frontend: {FRONTEND_URL}", flush=True)
        print(f"  Backend API health: {backend_base_url}/api/v1/health", flush=True)
        print(f"  Airflow UI: {AIRFLOW_URL}", flush=True)
        print(
            "  Airflow login details: "
            + airflow_service.get("log", str(_airflow_process_log_path(env))),
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
    except KeyboardInterrupt:
        print("\nAutomation interrupted by user.", flush=True)
        result_code = 130
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
                "status": (
                    "SUCCESS"
                    if result_code == 0
                    else "INTERRUPTED"
                    if result_code == 130
                    else "FAILED"
                ),
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
            "Overall result: "
            + (
                "SUCCESS"
                if result_code == 0
                else "INTERRUPTED"
                if result_code == 130
                else "FAILED"
            ),
            flush=True,
        )
    return result_code


if __name__ == "__main__":
    raise SystemExit(main())
