# Government load prediction pipeline

This is the independent government-grid forecasting workflow. Airflow handles
the orchestration and feature-generation ETL; model fitting and prediction
code is maintained in `training/government_load/`. It aggregates building-level
consumption to hourly coarse-grid loads, constructs historical and calendar
features for 1- to 24-hour forecasts, and trains two LightGBM models. A
validation-selected routing table chooses the better model for each grid.

The customer workflow remains under `airflow/customer`. Both pipelines use the
shared source dataset:

```text
data/sample/training_sample_50000.parquet
```

The government DAG is `government_load_forecasting`. Automation runs it after
the customer DAG (unless only the customer data stage is skipped); it can also
be triggered manually. Its run and task results appear in the Airflow UI, with
training rows, validation metrics, routing counts, model path, and MLflow run
ID available in the training task's log and XCom. It writes intermediate and
training-ready files under
`data/airflow/government/`, leaving customer datasets and artifacts unchanged.
The source parquet currently contains about 420 million rows; ETL uses DuckDB
with configurable memory limits and disk spilling rather than loading the raw
file into pandas.

## CLI

Run from the repository root with the project's Python environment:

```powershell
$env:PYTHONPATH = "airflow\2_government_load_prediction"
python -m grid_forecasting_pipeline prepare
python -m grid_forecasting_pipeline train
python -m grid_forecasting_pipeline predict
```

`prepare` uses the shared raw dataset, and writes
`data/airflow/government/training_ready_2018.parquet`. `train` and `predict`
default to that ready dataset. `run` performs preparation and training in
sequence. Override individual paths when needed:

```powershell
python -m grid_forecasting_pipeline run `
  --input data\sample\training_sample_50000.parquet `
  --output data\airflow\government\training_ready_2018.parquet `
  --features mlflow\government\feature_columns_2018.joblib `
  --model-output data\airflow\government\hybrid_grid_2018.joblib
```

Available commands are `prepare`, `train`, `predict`, and `run`. Use
`--input`, `--output`, `--features`, `--model`, `--model-output`,
`--horizon-hours`, `--memory-limit`, `--threads`, `--estimators`, and
`--batch-size` to override defaults. Predictions are written in Arrow batches.

## Airflow configuration

Airflow DAGs are discovered from the repository's `airflow/` directory. The
government DAG imports its self-contained package from this directory and does
not require an editable package install. Configure the DAG with optional
environment variables:

| Variable | Default |
| --- | --- |
| `GOVERNMENT_PIPELINE_INPUT` | `data/sample/training_sample_50000.parquet` |
| `GOVERNMENT_PIPELINE_OUTPUT` | `data/airflow/government/training_ready_2018.parquet` |
| `GOVERNMENT_PIPELINE_FEATURES` | `mlflow/government/feature_columns_2018.joblib` |
| `GOVERNMENT_PIPELINE_MODEL` | `data/airflow/government/hybrid_grid_2018.joblib` |
| `GOVERNMENT_PIPELINE_MEMORY_LIMIT` | `4GB` |
| `GOVERNMENT_PIPELINE_THREADS` | `4` |
| `GOVERNMENT_PIPELINE_HORIZON_HOURS` | `24` |
| `GOVERNMENT_PIPELINE_BATCH_SIZE` | `100000` |
| `GOVERNMENT_PIPELINE_MAX_TRAINING_ROWS` | `1000000` |
| `GOVERNMENT_PIPELINE_MAX_VALIDATION_ROWS` | `250000` |
| `GOVERNMENT_PIPELINE_N_ESTIMATORS` | `1200` |
| `GOVERNMENT_PIPELINE_REUSE_PREPARED` | `0` |

These settings are intentionally namespaced so they cannot override the
customer pipeline's configuration. Training also requires `MLFLOW_TRACKING_URI`;
automation points it to the shared MLflow service.

Training uses deterministic reservoir samples capped at one million training
rows and 250,000 validation rows by default. This bounds memory use without
changing the prepared parquet. Adjust the caps with the environment variables
above or `--max-training-rows` and `--max-validation-rows` in the CLI.

Successful training logs original/log validation MAE metrics and the hybrid
joblib model artifact to the `gridvision-government-load-forecasting` MLflow
experiment. The run is available in the MLflow UI at the address printed by
automation.

To train from an existing prepared parquet without running automation or
reprocessing customer data, use the government CLI directly:

```bash
cd /mnt/d/Ps_Capstone_project/gridvision_2
source ~/.venvs/gridvision/bin/activate
export MLFLOW_TRACKING_URI=http://127.0.0.1:15001
PYTHONPATH=airflow/2_government_load_prediction \
  python -m grid_forecasting_pipeline train \
  --input data/airflow/government/training_ready_2018.parquet
```

For a successful Airflow run using that same prepared file, set
`GOVERNMENT_PIPELINE_REUSE_PREPARED=1` and run only the government DAG:

```bash
export AIRFLOW_HOME="$HOME/.gridvision-airflow"
export AIRFLOW__CORE__DAGS_FOLDER=/mnt/d/Ps_Capstone_project/gridvision_2/airflow
export AIRFLOW__CORE__LOAD_EXAMPLES=False
export AIRFLOW__LOGGING__BASE_LOG_FOLDER=/mnt/d/Ps_Capstone_project/gridvision_2/logs/airflow/task_logs
export MLFLOW_TRACKING_URI=http://127.0.0.1:15001
export GOVERNMENT_PIPELINE_REUSE_PREPARED=1
airflow dags test government_load_forecasting 2026-10-29
```

The prepare task verifies and reuses the existing file instead of rerunning
government ETL. Neither command runs the customer DAG. If MLflow is not already
running, start only that service with `docker compose up -d mlflow`.

## Feature/model assets and tests

`mlflow/government/` contains the ordered feature-column list, the supplied
hybrid model bundle, its December 2018 evaluation parquet, and the MLflow
logging utility. The bundle and feature list are trusted pickle-based joblib
files; only load them from a trusted source.

Run the focused tests from the repository root:

```powershell
pytest tests/airflow/test_government_load_pipeline.py
```

The Airflow runtime is supported on Linux/WSL rather than native Windows. The
CLI and focused tests can run in a local Python environment with the project's
declared dependencies installed.
