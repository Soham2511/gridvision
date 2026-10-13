# GridVision

GridVision is a local prototype for residential month-end consumption estimates
and Commercial/Government hourly-demand model demonstrations. FastAPI serves
the supplied model artifacts; Streamlit provides the dashboards.

## Current data and model status

- The Residential raw snapshot is transformed into Bronze, Silver, and Gold
  Parquet layers. The source contains 370 meters, 15-minute interval kWh values,
  and ends on 2015-01-01.
- Commercial and Government use the supplied Gold Parquet datasets because
  their raw inputs were not supplied. Dashboard rows are restricted to the
  model-supported categories and latest rows in the historical test split.
- The executable code cells from the three substantive model-review notebooks
  are exported to `scripts/notebook_exports/` for review. The other notebooks
  contain no code cells; exported training/review cells are not all executed and
  are not production training commands.
- The prediction reports in `artifacts/models/*/metrics.json` are
  `not_evaluated`. A dashboard replay is not an evaluation report or a live
  forecast. The Residential notebook reports weaker performance than its
  recent-rate baseline.
- The Residential bill display uses the notebook's prototype flat tariff of
  ₹10/kWh; it is not a utility bill. Negative model output is explicitly flagged
  and no bill is calculated from it.
- Pickle artifacts can execute code while loading. Only run this application
  with the trusted artifacts supplied for this project. The model files and
  datasets are local inputs and are excluded from Git.

## Setup (Windows PowerShell)

From the project root:

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

If `.venv` already exists, skip the creation command.

## Prepare data

Build the customer Bronze, Silver, Gold, profile, quality, and lineage outputs:

```powershell
.\.venv\Scripts\python.exe -m scripts.validate_data
```

Create compact Commercial and Government dashboard inputs from the supplied
Gold files. These include only entities supported by the corresponding model
and the latest test-split record for each:

```powershell
.\.venv\Scripts\python.exe -m scripts.build_dashboard_snapshots
```

Both commands refuse to replace existing outputs. Pass `--overwrite` when
intentionally rebuilding them.

The three model-review notebooks with code cells have compile-checked Python
source exports. To regenerate those review copies without changing the
notebooks:

```powershell
.\.venv\Scripts\python.exe -m scripts.export_notebooks --overwrite
```

## Run the application

Open two PowerShell terminals in the project root.

Terminal 1 — API:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Terminal 2 — dashboard:

```powershell
.\.venv\Scripts\python.exe -m streamlit run dashboard\Home.py
```

Open the Streamlit URL printed in Terminal 2 (normally
`http://localhost:8501`). The API is available at `http://127.0.0.1:8000`;
interactive API documentation is at `/docs`. Set `GRIDVISION_API_URL` if the
dashboard must call the API at a different URL.

The API verifies the artifact file size, SHA-256 checksum, target, feature
schema version, and feature order before becoming ready. Readiness is reported
at `/api/v1/health/ready`. Prediction routes:

- `POST /api/v1/residential/predict`
- `POST /api/v1/commercial/predict`
- `POST /api/v1/government/predict`

Each request supplies an entity ID, forecast timestamp, and the exact ordered
feature contract in `artifacts/models/<model>/metadata.json`. Commercial
categorical values outside the stored LightGBM palettes are rejected.

## Validate

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_customer_gold.py tests\integration\test_prediction_flow.py
.\.venv\Scripts\ruff.exe check app dashboard scripts tests
```

The integration tests load the supplied local model artifacts. A successful
test run validates contract and inference plumbing, not model accuracy or
production readiness.
