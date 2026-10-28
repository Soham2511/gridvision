# Customer bill model and MLflow

This directory is the customer model's MLflow entrypoint and operating guide.
The training, evaluation, model-card generation, and MLflow registry logic
remain in `training/train_bill_prediction.py`; this entrypoint calls that
single implementation so the workflow does not fork or duplicate model code.

## Run training and registration

From the repository root, with the project dependencies installed and the
customer gold dataset prepared:

```powershell
python mlflow\customer\train_and_register.py `
  --data-path data\gold\customer_gold.parquet `
  --tracking-uri http://127.0.0.1:15001 `
  --model-name customer-bill-prediction `
  --alias champion
```

The tracking URI can instead be supplied with `MLFLOW_TRACKING_URI`. The
model name and alias default to `customer-bill-prediction` and `champion` (or
their `MLFLOW_MODEL_NAME` and `MLFLOW_MODEL_ALIAS` environment-variable
overrides). Training refuses to proceed when the latest tracked gold dataset
quality report failed.

Training evaluates a chronological model-selection process, compares the
tuned estimator with the naive monthly projection baseline, and registers the
validation winner. The MLflow run records dataset lineage, package versions,
training parameters, validation and held-out metrics, model signature, and
artifacts including the model card and metadata. The registered model alias
is used by the backend's MLflow adapter.

The existing orchestration uses this entrypoint automatically:

```bash
python automation.py
```

Automation starts the shared MLflow service, prepares the customer dataset
with Airflow, then invokes this customer-specific MLflow entrypoint before
starting the backend and frontend. To retrain against the existing gold
dataset, use `python automation.py --skip-data-pipeline`.

## Artifact locations

- The tracking database and run artifacts are persisted by the shared MLflow
  service under `data/mlflow/`; they are runtime data, not source files in this
  directory.
- The exported local model and metadata are written to `models/`.
- Versioned model cards, metrics, and training summaries are written under
  `logs/` and are also logged to MLflow.
- The backend loads the registered `customer-bill-prediction@champion` model
  from the shared tracking service.

See the top-level README's customer bill prediction section for environment
setup, Airflow orchestration, and operational details.
