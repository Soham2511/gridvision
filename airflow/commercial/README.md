# Commercial building forecast data pipeline

This package prepares the building-level commercial forecasting data from the
shared source Parquet file. The source file is the Bronze input; it is not
copied or modified. The DAG is
`commercial_building_forecasting_data_pipeline` in
`commercial_energy_dag.py`.

## Data contract

- Source/Bronze: `data/sample/training_sample_50000.parquet` by default.
- Silver: `data/silver/commercial_silver.parquet`, filtered to rows whose
  `GeneralUseType` is present and is not `Residential`.
- Gold: `data/gold/commercial_gold.parquet`, with one row per sampled
  `OBJECTID` × forecast-origin timestamp × horizon (1–24 hours). The local
  development default deterministically selects 100 building IDs to keep the
  feature transform within a modest memory budget.
- `id.grid.coarse` is preserved as the join key to the government model's
  regional grid forecast. It is not a commercial model feature.
- `OBJECTID`, timestamps, and the coarse-grid key are identifiers. Gold has
  exactly one `forecast_horizon_hours` column and `target_energy` as its label.
- The ordered LightGBM feature contract is defined in
  `training/commercial_forecast/features.py`.

Gold demand history, lag, and rolling features use observations at or before
the forecast origin. Calendar features are calculated from the target
timestamp. A label is emitted only when the building has an observed target
record at that timestamp.

## Stage validation and lineage

Bronze validation checks required source columns, null key counts, and that an
`OBJECTID` does not map to multiple coarse grids. Silver validation checks that
the result is non-empty, contains no residential rows, and retains the grid
key. Gold validation checks the feature contract, one horizon column, unique
building/origin/horizon keys, valid labels, and target timestamps after the
origin.

Each output writes a versioned Parquet snapshot and JSON report/manifest under
`data/metadata/commercial/dataset_versions/` and
`logs/data/quality_reports/commercial/`. DuckDB memory, thread, horizon, and
spill settings can be configured with `COMMERCIAL_DUCKDB_*` and
`COMMERCIAL_FORECAST_HORIZON_HOURS` environment variables.
Set `COMMERCIAL_SAMPLE_BUILDINGS` to increase the Gold sample; full-scale
training requires sufficient memory and storage.

## Run

From the project root, with Airflow dependencies available:

```powershell
airflow dags test commercial_building_forecasting_data_pipeline 2026-01-01
```

Run the fixture validations with:

```powershell
python -m pytest tests/airflow/test_commercial_data_pipeline.py
```
