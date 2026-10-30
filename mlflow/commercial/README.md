# Commercial building LightGBM model

The commercial model trains only on the building-level Gold dataset generated
by [`airflow/commercial`](../../airflow/commercial/README.md). It uses the
ordered 36-column contract in
[`training/commercial_forecast/features.py`](../../training/commercial_forecast/features.py),
predicts `target_energy`, and leaves `OBJECTID` and `id.grid.coarse` as
identifiers. The coarse-grid key remains available to join each building to
the government model's region forecast. Both pipelines preserve the
`id.grid.coarse` field from the shared Bronze source; the current source schema
uses `int64`, and the join utility rejects missing, non-integer, or mismatched
key types. Government ETL sums normalized building energy across all building
types, so joined regional forecasts are labeled **total grid demand**.

To join generated building predictions to government predictions, use
`scripts/join_commercial_region_forecasts.py`. The join uses
`id.grid.coarse`, `target_timestamp`, and `forecast_horizon_hours`; it never
uses sample UI labels such as “Panther” as grid IDs. It writes the joined
Parquet plus a JSON coverage report. Buildings without a government grid are
preserved with a null regional prediction and status
`missing_government_grid`; a known grid without that forecast timestamp/horizon
is marked `government_forecast_unavailable`.

```powershell
python scripts/join_commercial_region_forecasts.py `
  --commercial data/path/commercial_predictions.parquet `
  --government data/airflow/government/predictions_2018.parquet `
  --output data/gold/commercial_with_region_forecasts.parquet `
  --report logs/data/quality_reports/commercial/region_mapping.json
```

## Feature contract and lineage

The saved LightGBM input order (36 columns) is:

```text
GeneralUseType, SpecificUseType, usetype, building.type, idf.kw,
building.area.m2, FootprintArea.m2, EffectiveYearBuilt, latitude, longitude,
forecast_horizon_hours, energy_at_origin, energy_lag_1, energy_lag_24,
energy_lag_168, energy_lag_336, energy_lag_720, energy_rolling_mean_24h,
energy_rolling_std_24h, energy_observation_count_24h, energy_rolling_mean_7d,
energy_rolling_std_7d, energy_observation_count_7d, energy_rolling_mean_30d,
energy_rolling_std_30d, energy_observation_count_30d, target_hour,
target_day_of_week, target_month, target_is_weekend, target_day_of_month,
target_day_of_year, target_hour_sin, target_hour_cos, target_day_of_year_sin,
target_day_of_year_cos
```

`OBJECTID`, `id.grid.coarse`, `forecast_origin_timestamp`, and
`target_timestamp` are identifiers/metadata; `target_energy` is the label.
Identifiers and label are excluded from model inputs. Lineage is shared Bronze
Parquet → non-residential Silver → building-level Gold. History statistics use
records no later than forecast origin; target calendar values use the target
timestamp.

## Training and evaluation

Training splits on `target_timestamp` in chronological 70/15/15 portions.
Gold rows are sampled deterministically within each split to bound memory.
Each run fits and compares three learned candidates: direct-target LightGBM,
log1p-target LightGBM (with predictions inverse-transformed), and
`HistGradientBoostingRegressor`. The candidates share a preprocessing contract
that encodes the five string features (`GeneralUseType`, `SpecificUseType`,
`usetype`, `building.type`, and `idf.kw`). The `energy_at_origin` persistence
forecast is evaluated as a baseline, not selected as a learned champion.

Validation MAE selects one learned champion. RMSE and WAPE are reported as
supporting metrics; the WAPE threshold and improvement over the persistence
baseline are promotion checks. The selected champion alone is evaluated by
forecast horizon and `OBJECTID` on the held-out test split and packaged for
serving. Candidate metrics are retained for comparison.

MAE, RMSE, and WAPE are recorded for the train, validation, and test splits.
The test set also receives metrics by forecast horizon and by `OBJECTID`.
A persistence baseline (`energy_at_origin`) is evaluated with the same splits.
The model is clipped at zero for the non-negative energy domain.

Every run logs its evaluation, feature order, split ranges, dataset version,
quality manifest/report, model bundle, model card, and training summary to the
`gridvision-commercial-building-forecasting` MLflow experiment. It also writes
local summaries under:

- `logs/model_metrics/commercial/`
- `logs/model_cards/commercial/`
- `logs/training/commercial/`

The latest Gold quality manifest is required and must pass. The default
promotion gate requires finite metrics, validation WAPE no greater than 1.0,
and a validation MAE better than the persistence baseline. Failed runs and
their artifacts remain available in MLflow, but the model is not registered
or assigned the `champion` alias. Thresholds can be adjusted with
`COMMERCIAL_MAX_VALIDATION_WAPE` and
`COMMERCIAL_REQUIRE_BASELINE_IMPROVEMENT`.

## Run

After generating Silver and Gold, set `MLFLOW_TRACKING_URI` and run:

```powershell
python mlflow/commercial/train_and_log.py
```

Common environment overrides include `COMMERCIAL_GOLD_DATASET`,
`COMMERCIAL_GOLD_MANIFEST`, `COMMERCIAL_MODEL_PATH`,
`COMMERCIAL_MLFLOW_EXPERIMENT`, `COMMERCIAL_MLFLOW_MODEL_NAME`,
`COMMERCIAL_MLFLOW_MODEL_ALIAS`, `COMMERCIAL_MAX_TRAINING_ROWS`,
`COMMERCIAL_MAX_VALIDATION_ROWS`, `COMMERCIAL_MAX_TEST_ROWS`, and
`COMMERCIAL_LGBM_*` estimator settings.

## Automation, serving, and logs

`python automation.py` runs customer and government data workflows, the
commercial DAG and training, then customer training and service startup. The
commercial DAG id is `commercial_building_forecasting_data_pipeline`. To reuse
prepared commercial data while still training, run
`python automation.py --skip-commercial-data-pipeline`. Reuse verifies Silver,
Gold, and a passing `data/metadata/commercial/dataset_versions/gold/latest.json`
that points to the selected Gold. The existing `--skip-data-pipeline` flag
continues to skip only the customer DAG.

The paired endpoint is
`GET /api/v1/forecast/commercial/<building_id>/paired`; when both model
providers are configured and their artifacts are available, it returns distinct
commercial building and government total-grid demand forecast sources with
model/version and timestamp metadata. The UI labels both sources and provides
loading, empty-history, and mapping/model error states. API requests are JSONL
in `logs/endpoints/api.jsonl`; automation steps are in
`logs/automation/automation-*.json`. Stage quality reports/manifests are under
`logs/data/quality_reports/commercial/` and
`data/metadata/commercial/dataset_versions/`; training metrics, cards, and
summaries are under `logs/model_metrics/commercial/`, `logs/model_cards/commercial/`,
and `logs/training/commercial/`. Failed promotion checks remain recorded but
do not register/advance the champion model.

## Tests

```powershell
python -m pytest tests/training/test_commercial_forecast.py -q
```
