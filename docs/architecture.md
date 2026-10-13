# GridVision architecture

## Implemented local prototype

- `dashboard/` is the Streamlit presentation layer. Its shared API client calls
  the FastAPI service and displays explicit historical-replay and evaluation
  status.
- `app/api/` exposes health/readiness and three typed prediction routes.
- `app/services/prediction_service.py` validates exact model feature sets,
  rejects unseen Commercial categories, and runs one model row.
- `app/models/registry.py` loads only registry-configured local artifacts after
  checking file size, SHA-256, target, schema version, and feature ordering.
- `app/data_engineering/` creates Residential Bronze, long-format Silver, and
  daily Gold features. `scripts/build_dashboard_snapshots.py` reads the
  supplied Commercial/Government Gold files and extracts model-supported
  historical test-split rows.
- `scripts/notebook_exports/` contains compile-checked code-cell exports from
  the three substantive model-review notebooks. The notebooks remain
  unchanged; the exports are review copies and are not all execution-validated.

## Boundaries and limitations

The current prototype is local and unauthenticated. It does not provide a
production database, distributed storage, deployed secrets, live Commercial
or Government ingestion, model retraining, or a validated redistribution
optimizer. Model evaluation reports are still `not_evaluated`. Refer to the
architecture plan at the repository root for the broader target design and
remaining production work.
