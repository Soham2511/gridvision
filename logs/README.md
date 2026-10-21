# Runtime logs and reports

GridVision writes generated output beneath this directory. Set `GRIDVISION_LOG_DIR` to use another location. JSON files are UTF-8, indented objects; endpoint events use newline-delimited JSON (`.jsonl`) so the append-only stream can be processed incrementally.

| Folder | Contents |
|---|---|
| `airflow/` | Airflow standalone startup log and task logs |
| `data/quality_reports/` | Bronze, silver, and gold transformation quality reports |
| `endpoints/` | Structured Flask request events (`api.jsonl`, with rotation) |
| `model_cards/` | Markdown cards for each registered model version |
| `model_metrics/` | Parameters, cross-validation results, validation and test metrics, and dataset lineage |
| `testing/` | One JSON test-run summary and per-test outcomes per pytest invocation |
| `training/` | One JSON execution summary per MLflow training run |

Dataset manifests and versioned Parquet snapshots are kept separately under `data/metadata/dataset_versions/`; they are lineage records and data assets rather than log files. MLflow retains its own run history and artifacts under `data/mlflow/`.
