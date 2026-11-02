# GridVision anomaly prediction

The anomaly detector is an independent model package inside the main GridVision
application. The Flask API loads the saved bundle from the parent model/data
directories; the React application presents persona-scoped alerts and a
government monitoring workspace. There is no separate anomaly web application.

## Parent-project layout

- Runtime inference, feature pipeline, data preparation, event localization,
  MLflow tracking, and run storage:
  `backend/app/models/anomaly_prediction/`
- Saved detector:
  `models/anomaly_prediction/gridvision_anomaly_model.joblib`
- Bronze, silver, and gold inputs:
  `data/anomaly_prediction/`
- Training entry point:
  `training/anomaly_prediction/train.py`
- MLflow training entry point:
  `mlflow/anomaly_prediction/train_and_log.py`
- Airflow DAG:
  `airflow/anomaly_prediction/gridvision_training.py`
- Evaluation and application-run artifacts:
  `reports/anomaly_prediction/`
- Migrated tests:
  `tests/anomaly_prediction/`
- Model research and methodology:
  `docs/models/anomaly_prediction/` and
  `notebooks/gridvision_anomaly_detection.ipynb`

Previous MLflow run artifacts are retained under
`mlflow/anomaly_prediction/archive/`; this is an inactive archive, not a second
tracking server or registry. Active training uses GridVision's configured
`MLFLOW_TRACKING_URI` and registers `gridvision-anomaly-detection@champion`.

## Run independently

Configure `MLFLOW_TRACKING_URI` to the existing GridVision MLflow service, then:

```bash
python automation.py --anomaly-only
```

The command validates the migrated source and dependencies, reuses Silver/Gold
features and the saved detector when their artifacts are present, otherwise
prepares/trains them, logs evaluation artifacts to MLflow, registers the model,
then runs inference and spatial localization and persists an application run.
Use `--force-anomaly-retrain` to explicitly retrain. `ANOMALY_START_DATE` and
`ANOMALY_END_DATE` can set the inclusive inference range; by default the
workflow runs the first source day.

For the complete GridVision stack, `python automation.py` runs the anomaly DAG
as an additional independent stage beside the existing customer, commercial,
and government workflows. The anomaly Airflow DAG is named
`gridvision_anomaly_training` and remains unscheduled for the static annual
source dataset.

## Integrated API

The endpoints are served from the parent Flask API under `/api/v1`:

- `GET /models` — model readiness, source range, features, and evaluation
  metrics.
- `GET /models/anomaly-prediction/entities?offset=0&limit=10000` — paginated
  source customer IDs and locations (the dashboard loads the available 10,000
  customer coordinates for its canvas map).
- `POST /models/anomaly-prediction/predict` — run model inference, spatial
  localization, event-scope classification, and persistence.
- `GET /models/anomaly-prediction/runs` and
  `GET /models/anomaly-prediction/runs/{run_id}` — application-run history and
  result details.
- `GET /models/anomaly-prediction/runs/{run_id}/download/{filename}` — allow-
  listed run-specific CSV, JSON, GeoJSON, and evaluation artifacts.

The React route `/anomalies` shows linked-entity alerts to residential and
commercial personas. Government & Utilities users receive the interactive
customer/event map, filters, timeline, event details, model metrics, analysis
configuration, and the dedicated **Application Results** tab. Results are
rendered only from completed API runs; the frontend does not generate mock
predictions. The map uses source coordinates in a Web Mercator projection over
OpenStreetMap's standard tile service, with visible OpenStreetMap attribution.
Deployments can set `VITE_OSM_TILE_URL` to a compatible tile URL template
containing `{z}`, `{x}`, and `{y}`. The public OpenStreetMap tile service is
subject to its usage policy and is not intended for bulk or high-volume
traffic; use a suitable tile provider for production traffic. If tiles cannot
be loaded, customer and event overlays remain available on the plain map
background. Local and multi-area events show separate estimated impact circles
for their spatial clusters; affected customers are highlighted and listed in the
selected event details. These circles are based on observed customer
coordinates, not verified electrical infrastructure boundaries. Detailed
per-class metrics, confusion matrices, and synthetic split counts remain in the
downloadable `evaluation_metrics.json` instead of the monitoring view.

Application Results downloads include `anomaly_records.csv`,
`spatial_temporal_events.csv`, `geographic_clusters.csv`,
`evaluation_metrics.json`, `event_localization_evaluation.json`, and
`events.geojson`. Run manifests are the status source of truth. If the server
restarts after result payloads are durably written but before the final
completed-status update, it reconciles the run to `completed`; interrupted
runs without persisted result payloads are marked `failed`.

## Data and inference notes

The source parquet is `data/anomaly_prediction/synthetic_2019_normal.parquet`.
Inference reads only `OBJECTID`, `timestamp`,
`normalized_building_energy_kwh`, `latitude`, and `longitude`. It does not use
source anomaly labels or event metadata. The 87.6-million-row parquet contains
10,000 customers; the per-run input limit is 2.1 million rows, including causal
history and event context.

The four anomaly types (`spike`, `drop`, `zero_block`, and `flatline`) are
independent of the three event scopes (`SINGLE_CUSTOMER`, `LOCAL_AREA`, and
`MULTI_AREA`). Localized clusters describe geographic correlation; without
feeder, transformer, or substation identifiers, they do not represent verified
electrical asset boundaries.

The saved evaluation uses injected synthetic patterns. It is not evidence of
real-world outage accuracy. Persona-specific account/building notifications
require an account-to-model-customer mapping; the UI hides alerts when no
numeric model customer ID is linked. The current platform does not provide
authentication or server-side user authorization, so it must not be exposed as
a multi-tenant public service without adding those controls.

## Validation

```bash
python -m pytest -q tests/anomaly_prediction
python -m pytest -q tests/backend/test_models.py tests/training
cd frontend && npm run build
```

Full project automation additionally requires the existing Docker, Airflow,
MLflow, and non-anomaly customer/commercial/government source datasets.
