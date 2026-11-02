# GridVision anomaly application integration

Anomaly prediction is served inside the existing Flask application and React
frontend. The standalone HTML/FastAPI application is not part of the parent
runtime.

## Runtime flow

```text
GridVision React /anomalies route
    │ shared JSON API client
    ▼
Flask /api/v1/models/anomaly-prediction/*
    ├── Loads the saved model bundle and parent-project parquet
    ├── Scores selected customer-hour records without ground-truth labels
    ├── Applies anomaly-type rules and H3/spatial-temporal localization
    ├── Classifies SINGLE_CUSTOMER, LOCAL_AREA, and MULTI_AREA scopes
    └── Persists the request, events, windows, metrics, and exports per run
```

Residential and commercial persona views show only alerts linked to the active
numeric model-customer ID; they do not display the government map or unrelated
customer records. Government & Utilities receives the monitoring map, normal
and anomalous customer markers, anomaly/scope/severity filters, localized
clusters, timeline, event details, model metrics, and analysis controls. Its
**Application Results** tab lists saved runs and downloads supported artifacts.

## Configuration

Defaults can be overridden with:

| Variable | Default | Purpose |
|---|---|---|
| `ANOMALY_DATASET_PATH` | `data/anomaly_prediction/synthetic_2019_normal.parquet` | Parquet source |
| `ANOMALY_MODEL_PATH` | `models/anomaly_prediction/gridvision_anomaly_model.joblib` | Saved bundle |
| `ANOMALY_RUNS_PATH` | `reports/anomaly_prediction/application_runs` | Persistent per-run output |

The source contains 87,600,000 hourly records across 10,000 customers. Each run
has a 2,100,000-row cap including the seven-day causal history and up to 12
hours of event context. Requested dates must be within the source range;
invalid customer IDs, missing/non-finite values, duplicate hours, and
irregular hourly intervals are rejected.

## API

| Method and route | Purpose |
|---|---|
| `GET /api/v1/models` | Model readiness and evaluation metadata |
| `GET /api/v1/models/anomaly-prediction/entities` | Paginated customer IDs and locations |
| `POST /api/v1/models/anomaly-prediction/predict` | Run inference and persist a completed analysis |
| `GET /api/v1/models/anomaly-prediction/runs` | List recent application runs |
| `GET /api/v1/models/anomaly-prediction/runs/{id}` | Read a run manifest and completed results |
| `GET /api/v1/models/anomaly-prediction/runs/{id}/download/{filename}` | Download an allow-listed output |

The prediction body accepts `customer_ids` (optional integer array),
`start_date`, `end_date`, `h3_resolution`, `spatial_radius_km`,
`maximum_start_time_difference_minutes`, `minimum_temporal_overlap`, and
`maximum_interval_gap_minutes`.

Downloadable run artifacts include event/window CSV and JSON, a full JSON
result, GeoJSON event points, and the saved model evaluation report. Download
paths are allow-listed and cannot access arbitrary files.

## Persisted outputs

Each run is stored under
`reports/anomaly_prediction/application_runs/<run-id>/`. It includes a
manifest, request/result metadata, run metrics, event summaries, customer-level
anomaly windows, affected customer IDs, CSV exports, GeoJSON, and model
evaluation metrics. Interrupted queued/running runs are marked failed on the
next service initialization.

GeoJSON features represent event-centroid points. A spatial extent drawn in the
frontend is a visual cluster indicator, not a verified feeder or outage
boundary. Saved evaluation results are based on synthetic injected test
patterns; live predictions on the normal-only source should not be described as
confirmed natural faults.

## Security and operating limits

The parent app currently has no authentication or server-side persona
authorization. Client-side filtering is a presentation boundary, not a security
boundary. Keep the service behind the existing trusted GridVision deployment
until authenticated account/customer mappings, authorization, durable job
queueing, and per-user result access are provided.
