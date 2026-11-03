# GridVision anomaly data and training workflow

The anomaly detector is integrated into the parent GridVision project and uses
the same configured MLflow service and model registry as the other models.
Training can run by itself or as an independent stage in the complete
automation:

```bash
# Independent anomaly workflow; does not launch customer/commercial/government jobs
python automation.py --anomaly-only

# Complete GridVision workflow, with anomaly prediction as an additional DAG stage
python automation.py

# Bypass saved-model reuse for an explicit retraining
python automation.py --anomaly-only --force-anomaly-retrain
```

The anomaly workflow requires both the `backend` and `model-serving`
requirements groups: inference initializes the Flask application, while model
preparation and training use the model-serving packages. Install both groups
into the active Python environment:

```bash
python scripts/filter_requirements.py requirements.txt /tmp/gridvision-anomaly-requirements.txt \
  --groups backend model-serving
python -m pip install -r /tmp/gridvision-anomaly-requirements.txt
```

Set `MLFLOW_TRACKING_URI` to the existing GridVision tracking service. The
anomaly experiment is `gridvision-anomaly-detection`; its registered model is
`gridvision-anomaly-detection` with the `champion` alias. Automation logs
preparation, training/reuse, evaluation, registration, and inference stages in
the normal structured automation summary under `logs/automation/`.

## Data layers and model inputs

The immutable source is
`data/anomaly_prediction/synthetic_2019_normal.parquet`. Preparation writes:

- `data/silver/synthetic_2019_silver.parquet` — bounded
  Arrow-batch copy with the complete original schema retained for audit.
- `data/gold/gridvision_model_features.parquet` — sampled,
  causal model features, including time-domain, FFT, and Haar-wavelet features.

The data and feature code lives in
`backend/app/models/anomaly_prediction/runtime/gridvision_data.py`; the
detector, customer splits, leakage-safe feature computation, synthetic-event
training, and evaluation live in `gridvision_pipeline.py` in the same runtime
package. Source anomaly labels and metadata are excluded from model features.

Training partitions customers into disjoint train/validation/test groups,
splits time chronologically, injects explicitly synthetic events into
appropriate histories, fits the detector on training data, selects an
operating threshold on validation, and evaluates the frozen detector and
anomaly-type rules on held-out data. The saved inference-compatible artifact is
`models/anomaly_prediction/gridvision_anomaly_model.joblib`.

An existing Silver/Gold feature file is reused when present. A saved model is
reused only when both the model bundle and its evaluation report are present
and the bundle passes its feature-contract loader. Its saved metrics and model
are still logged to the shared MLflow server and the registry alias is updated.
Use `--force-anomaly-retrain` to retrain deliberately.

## Airflow integration

The unscheduled DAG `gridvision_anomaly_training` is
`airflow/anomaly_prediction/gridvision_training.py`. It runs bronze-to-silver
preparation, gold feature generation, and tracked model training or artifact
reuse as dependent tasks. It uses parent-project paths and the existing Airflow
and MLflow services. It does not import from or execute the legacy standalone
module.

The complete `automation.py` workflow runs this DAG after the existing
customer, government, commercial, and customer-model stages. The `--anomaly-only`
mode uses the same root training entry point and executes real inference,
spatial localization, event-scope classification, and persisted result
generation without starting the other workflows or services.

In the complete workflow, data-producing Airflow DAGs are skipped when their
source file fingerprint (resolved path, size, and modification time) and
previously generated outputs are unchanged. The successful fingerprints are
stored in `data/metadata/automation/airflow_dataset_state.json`. A missing
output or changed source causes the corresponding DAG to run again. Use
`python automation.py --force-airflow-dags` to rerun those DAGs explicitly.
On the first run, complete existing outputs with their required quality
manifests or evaluation reports are adopted as the baseline rather than rebuilt.
Before reusing anomaly layers, automation also verifies that Silver matches
the source row count, schema, and timestamp range, and that Gold covers the
same timestamp range. Stale layers are rebuilt even when their file
fingerprints have not changed.

## Tracking and artifacts

Training/reuse logs finite evaluation metrics, configuration and source
provenance, the saved model, and evaluation reports to the shared experiment.
The model registration name and alias can be configured with
`ANOMALY_MLFLOW_MODEL_NAME` and `ANOMALY_MLFLOW_MODEL_ALIAS`.

Local evaluation outputs are retained under `reports/anomaly_prediction/`,
including training reports and visualizations. Application runs are persisted
under `reports/anomaly_prediction/application_runs/<run-id>/` as CSV, JSON,
GeoJSON, metadata, metrics, and evaluation artifacts. Previous standalone
MLflow run files and database are retained under
`mlflow/anomaly_prediction/archive/` for historical reference only; that
directory is not used as a tracking store.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `GRIDVISION_SOURCE_DATA` | `data/anomaly_prediction/synthetic_2019_normal.parquet` | Bronze source |
| `GRIDVISION_SILVER_DATA` | `data/silver/synthetic_2019_silver.parquet` | Prepared source |
| `GRIDVISION_GOLD_DATA` | `data/gold/gridvision_model_features.parquet` | Engineered features |
| `GRIDVISION_MODEL_PATH` | `models/anomaly_prediction/gridvision_anomaly_model.joblib` | Saved model bundle |
| `GRIDVISION_REPORT_DIR` | `reports/anomaly_prediction/training` | Training reports |
| `ANOMALY_DATASET_PATH` | `data/anomaly_prediction/synthetic_2019_normal.parquet` | Flask inference source |
| `ANOMALY_MODEL_PATH` | `models/anomaly_prediction/gridvision_anomaly_model.joblib` | Flask inference model |
| `ANOMALY_RUNS_PATH` | `reports/anomaly_prediction/application_runs` | Persisted analysis runs |
| `MLFLOW_TRACKING_URI` | `http://127.0.0.1:15001` | Existing GridVision tracking service |

## Validation and limitations

Run migrated anomaly tests and adjacent regressions with:

```bash
python -m pytest -q tests/anomaly_prediction
python -m pytest -q tests/backend/test_models.py tests/training
```

The source contains 87.6 million hourly records across 10,000 customers and is
normal-only; its labels are not used in inference. The saved evaluation metrics
were produced on synthetic injected patterns and should not be interpreted as
real-world fault accuracy. Interactive inference has a 2.1-million-row bound
including causal history and event context.
