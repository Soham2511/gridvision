# Government model tracking with MLflow

This directory contains the government model's MLflow entrypoint, the supplied
hybrid grid-load model, its ordered feature list, the December 2018 evaluation
dataset, and a legacy evaluator for the supplied model bundle. The feature and
model files use joblib/pickle serialization; only load these artifacts if they
came from a trusted source.

See [model_card.md](model_card.md) for the feature contract, hybrid routing
description, and historical evaluation results supplied with the artifact.

Install the project's Python dependencies, prepare the government parquet, and
run the same full training-and-tracking implementation used by its Airflow DAG:

```bash
cd /mnt/d/GridVision
source ~/.venvs/gridvision/bin/activate
export MLFLOW_TRACKING_URI=http://127.0.0.1:15001
python mlflow/government/train_and_log.py \
  --input data/airflow/government/training_ready_2018.parquet
```

The entrypoint accepts the government `train` CLI options, including
`--input`, `--features`, `--model-output`, `--threads`, `--estimators`,
`--max-training-rows`, and `--max-validation-rows`. Set
`GOVERNMENT_PIPELINE_*` variables to control the equivalent settings. MLflow
records the original, log-target, validation-selected hybrid, and persistence
baseline metrics where the prepared data provides `energy_at_origin`.

## Tracked metrics and artifacts

The experiment is `gridvision-government-load-forecasting`. Each run records
15 summary metrics: validation MAE, RMSE, and R² for the original, log-target,
hybrid, and persistence models, plus hybrid WAPE, RMSLE, and negative
prediction rate. Detailed training/validation diagnostics and per-grid and
per-horizon evaluation tables remain available as artifacts, without cluttering
the MLflow metric list.

The hybrid joblib bundle, native LightGBM component models, ordered feature
list, grid routing table, feature importance, training feature profile,
validation predictions with errors, per-grid/per-horizon evaluation tables,
model metadata, model card, metrics JSON, and training summary are available
as MLflow run artifacts. Matching local run files are stored under
`logs/training/government/<run_id>/`, with the model card in `logs/model_cards/`,
metrics in `logs/model_metrics/`, and summary in `logs/training/`.

The older `log_model_mlflow.py` script remains available to evaluate the
supplied December 2018 model bundle; its metrics cover the original-target
estimator only and do not replace the full hybrid training workflow above.
