# API contracts

FastAPI exposes the prediction interface; Streamlit calls it through
`dashboard/clients/api_client.py`.

## Health

- `GET /api/v1/health/live` reports process liveness.
- `GET /api/v1/health/ready` returns HTTP 200 only when all configured artifacts
  are loaded and their file size, SHA-256, target, schema version, and feature
  order match the local registry.

## Predictions

- `POST /api/v1/residential/predict`
- `POST /api/v1/commercial/predict`
- `POST /api/v1/government/predict`

Each body contains:

```json
{
  "entity_id": "example",
  "forecast_timestamp": "2017-12-31T23:00:00",
  "features": {},
  "context": "retrospective_gold_replay",
  "actual_kwh_so_far": null
}
```

The `features` object must contain exactly the ordered names in the model's
`metadata.json`. Commercial categorical values must belong to the palettes
stored in the LightGBM artifact. Government site and season encodings are
specified in Government metadata. Invalid or missing inputs return HTTP 422.

Responses include the raw model `prediction`, target name and unit, model
version/checksum, evaluation status, prediction validity, data-quality status,
context, and caveats. Residential responses also include actual month-to-date
consumption and a month-end usage/bill estimate when the model output is
nonnegative. A negative energy output is explicitly marked invalid and does not
produce a bill estimate.

Current artifact evaluation reports are `not_evaluated`. The
`retrospective_gold_replay` context explicitly identifies history; it must not
be represented as a current forecast. Model inference alone does not calculate
redistribution recommendations, utility tariffs, or cost-shifting decisions.
