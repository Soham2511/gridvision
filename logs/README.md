# Runtime logs and reports

GridVision writes generated output beneath this directory. Set `GRIDVISION_LOG_DIR` to use another location. JSON files are UTF-8, indented objects; endpoint events use newline-delimited JSON (`.jsonl`) so the append-only stream can be processed incrementally.

| Folder | Contents |
|---|---|
| `airflow/` | Airflow standalone startup log and task logs |
| `automation/` | One JSON execution summary with ordered steps, timings, result, and errors per automation invocation |
| `data/quality_reports/<domain>/` | Domain-grouped Bronze, Silver, and Gold transformation quality reports, including commercial region mapping coverage |
| `endpoints/` | Structured Flask request events (`api.jsonl`, with rotation) |
| `model_cards/<domain>/` | Markdown cards for each registered model version |
| `model_metrics/<domain>/` | Parameters, validation/test metrics, horizon/building breakdowns, and dataset lineage |
| `testing/` | One JSON test-run summary and per-test outcomes per pytest invocation |
| `training/<domain>/` | One JSON execution summary per MLflow training run |

Dataset manifests and versioned Parquet snapshots are kept separately under `data/metadata/`; they are lineage records and data assets rather than log files. Commercial stage reports are JSON, and commercial training summaries include candidate, champion, baseline, split, feature order, and promotion-gate outcomes. MLflow retains its own run history and artifacts under the configured tracking store. Airflow task logs retain native Airflow formatting; request events, automation summaries, data-quality reports, and training summaries are structured JSON.
