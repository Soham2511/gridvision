# Government customer segmentation operations

This guide covers the independent, behaviour-based segmentation workflow for
all consumer categories in the Bronze source. It is separate from the existing
residential customer bill-prediction workflow and does not alter that model.

## Current published run

The latest completed Airflow run is recorded in
`data/segmentation/reports/execution_summary.json`:

- DAG: `government_customer_segmentation`
- Airflow run: `manual__2026-11-01T19:08:16+00:00`
- Model version: `segmentation-v1-20261101T191639Z`
- Observation window: 2018-01-01 inclusive through 2019-01-01 exclusive
- Source: `data/bronze/training_sample_50000.parquet` (50,000 buildings,
  419,750,000 meter rows)
- Feature and assignment rows: 50,000 each; unassigned: 0

Source categories and building counts:

| Source category | Buildings | Model group |
|---|---:|---|
| Residential | 47,568 | Residential |
| Commercial | 1,585 | Commercial |
| Industrial | 819 | Industrial |
| Institutional | 27 | Shared small categories |
| Recreational | 1 | Shared small categories |

Institutional and Recreational use the same pooled clustering model because
their individual populations are below the category model-size threshold. The
published assignments and profiles preserve `GeneralUseType`, so UI/API filters
still show each source category separately. The pooled model profile describes
the combined model group.

## What the UI shows

Open **Building Behaviour Segments** in the Government navigation, or visit
`/app/government/segmentation`. The view includes category-filtered segment
counts and profiles, coarse/finer regional summaries, point/grid drilldown,
hourly/daily/monthly profiles, survey-priority regions, and paginated building
assignments. The category filter uses source `GeneralUseType`; model group is
shown separately.

Map coordinates are point locations and grid IDs are aggregation keys; they
are not administrative boundaries. Survey-priority scores use consumption
variability, peak intensity, and target-segment concentration. They do not
measure transformer overload, voltage instability, or network adequacy. Model
selection metrics are internal unsupervised-fit/stability measures, not
held-out predictive accuracy. The source sample covers 2018 and should not be
treated as a current inventory without refreshed data and a stability review.

The map requests tiles from the configured tile provider in each user's
browser. By default the frontend uses OpenStreetMap standard tiles and shows
the required attribution. Choose another compatible provider with
`VITE_MAP_TILE_URL` when your deployment needs a different service, availability
guarantee, or privacy arrangement. Standard OpenStreetMap tiles are best-effort
and subject to their [tile usage policy](https://operations.osmfoundation.org/policies/tiles/).

## Run the pipeline

Set the project `.env` values `GRIDVISION_DATA_DIR` and `SECRET_KEY` as described
in the root README, then start the required services:

```bash
docker compose up -d airflow mlflow
```

The full `python automation.py` workflow runs this DAG after the Government load
DAG, using the existing Bronze source and publishing to
`${GRIDVISION_DATA_DIR}/segmentation/`. Automation skips the DAG when the
source and validated outputs are unchanged; missing or changed data causes a
new run. By default, segmentation deterministically selects 10% of buildings
(about 5,000 of the 50,000-building source) before profiling, feature generation, and
clustering. Every hourly row for selected buildings is retained, and
Institutional and Recreational buildings are explicitly preserved because
those categories are rare. The feature schema and downstream outputs are
unchanged. Set `SEGMENTATION_BUILDING_SAMPLE_FRACTION` to a value in `(0, 1]`
to change the sample size; `1` processes the full source. The first sample
creation still scans the 3.6 GB Bronze Parquet once, but it caches the selected
rows in `source_sample.parquet`. Subsequent profiling and DAG runs reuse that
sample and its source/config manifest instead of scanning all 419 million
meter rows. The source profile is also cached. DuckDB defaults to 1 GB of memory
and one thread, spilling temporary work under
`/tmp/gridvision-segmentation-duckdb`; the limits can be adjusted with
`SEGMENTATION_DUCKDB_MEMORY_LIMIT` and
`SEGMENTATION_DUCKDB_THREADS`. Segmentation tasks do not retry automatically
after a failure, because retrying a memory-allocation failure without changing
resource limits cannot resolve it. To run segmentation by itself, the DAG can
also be triggered manually. If it is paused, unpause it once, then trigger:

```bash
docker compose exec airflow airflow dags unpause government_customer_segmentation
docker compose exec airflow airflow dags trigger government_customer_segmentation
```

Check progress in Airflow at `http://127.0.0.1:8081` or with:

```bash
docker compose exec airflow airflow dags list-runs -d government_customer_segmentation --output table
docker compose exec airflow airflow tasks states-for-dag-run government_customer_segmentation <RUN_ID>
```

The DAG profiles the sampled source, builds building-level features, fits
category models (pooling small categories), publishes regional/time/priority outputs,
validates the complete output set, and registers model bundles in MLflow. The
DAG has no automatic retries and allows one active run at a time. A successful run writes its
Airflow run ID and validation results to the execution summary.

The equivalent local CLI is `python -m training.customer_segmentation.cli`.
It supports `--source`, `--output-dir`, `--window-end`, `--window-months`,
`--minimum-coverage`, `--profile-only`, and `--no-mlflow`. Do not use
`--no-mlflow` when the intent is to register the current models.

The CLI prints timestamped progress for each major phase, periodic
"still working" messages during long phases, per-category clustering progress,
and elapsed/rough remaining-time estimates. The ETA is only a rough estimate
based on completed phases, whose durations can vary significantly; on the first
phase it is unavailable until timing data exists. A `--profile-only` run only
validates and profiles the source; it does not generate segmentation outputs.

## Published artifacts

Artifacts are written under `${GRIDVISION_DATA_DIR}/segmentation/` and mounted
read-only into the backend. Core outputs include:

- `building_features.parquet`, `consumer_assignments.parquet`
- `cluster_profiles.parquet`, `segment_distribution.parquet`
- `region_summary_coarse.parquet`, `region_summary_finer.parquet`
- `cluster_hourly_profile.parquet`, `cluster_daily_profile.parquet`,
  `cluster_monthly_profile.parquet`, `survey_priority.parquet`
- `model_metadata.json`, `model_selection_report.json`,
  `feature_diagnostics.json`, `models/*_model.joblib`
- `source_sample.parquet`, `reports/source_sample.json`,
- `reports/source_profile.json`, `reports/feature_generation.json`,
  `reports/geospatial_summary.json`, `reports/execution_summary.json`

`execution_summary.json` is the authoritative run record. Its output validation
contains each Parquet row count, assignment reconciliation, model categories,
and status. Airflow's native task logs are available from the Airflow UI and
inside its container under `/opt/airflow/logs/`; the standalone startup log is
`logs/airflow/standalone.log`.

## MLflow registry

The workflow uses the shared tracking server at `MLFLOW_TRACKING_URI` and the
dedicated experiment `gridvision-government-customer-segmentation`. Current
registered names use the prefix
`gridvision-government-customer-segmentation-` and suffixes `commercial`,
`industrial`, `residential`, and `shared_small_categories`. Registration is
idempotent per segmentation model version; inspect the execution summary and
MLflow registry for the exact registry version and run ID.

## Backend API

All endpoints are read-only and use the `/api/v1/government/segmentation`
prefix:

| Endpoint | Purpose |
|---|---|
| `/overview` | Current model version, counts, and observation period |
| `/profiles?category=<GeneralUseType>` | Segment profiles, filtered by source category |
| `/profiles/<segment_id>/time-series?period=hourly\|daily\|monthly` | Segment time profile |
| `/distribution?category=<GeneralUseType>` | Category-aware segment counts and shares |
| `/regions?level=coarse\|finer&category=<GeneralUseType>` | Regional segment summaries and pagination |
| `/regions/<level>/<region_id>?category=<GeneralUseType>` | Region detail and drilldown summary |
| `/assignments?category=<GeneralUseType>&page=1&page_size=50` | Building assignments |
| `/priorities?category=<GeneralUseType>&page=1&page_size=50` | Survey-priority regions and factors |
| `/model` | Model metadata and published version |

The older `/api/v1/customers/*` APIs remain the separate customer analytics and
bill-prediction experience.

## Serving code updates

After changing backend/frontend source or Compose mounts, rebuild those
services so the running stack serves the updated UI and API:

```bash
docker compose up -d --build backend frontend
docker compose ps backend frontend
curl --fail http://127.0.0.1:5000/api/v1/government/segmentation/overview
```

The frontend is served at `http://127.0.0.1:8082`. The segmentation page reads
published files through the API; page requests never retrain a model.
