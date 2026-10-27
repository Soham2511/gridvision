# GridVision — Next-Generation Energy Analytics Platform

GridVision is an enterprise smart energy intelligence platform designed for grid planners, utilities, commercial facility operators, and regulators. It provides:

- **Demand Forecasting**: Multi-horizon projections for commercial buildings (hourly LightGBM), residential smart meters (month-end XGBoost), and regional government grids.
- **Peak Demand Planning & ADR Mitigation**: Coincident capacity monitoring, reserve margin tracking, and automated demand-response dispatch simulation.
- **Anomaly Detection**: Outlier detection across substations, commercial facilities, and residential feeders with triage workflows.
- **Customer Segmentation**: Behavioral load profiling, industry breakdown, and 24-hour diurnal load curves.
- **Actionable Business Takeaways**: Algorithmic recommendations for peak shaving and energy efficiency with quantified financial impacts.
- **Platform Telemetry & Health**: Dataset accumulation stats, model evaluation metrics (MSE, RMSE, R²), and operational liveness.

---

## Architecture Overview

```text
┌─────────────────────────────────────────────────────────────┐
│                 React SPA (TypeScript + Vite)               │
│               Configured via VITE_API_BASE_URL              │
└──────────────────────────────┬──────────────────────────────┘
                               │ HTTP / JSON REST APIs
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                 Modular Flask REST Backend                  │
│   ├── Application Factory (create_app) & Config System     │
│   ├── Blueprints: /api/v1 (health, forecast, peak, etc.)   │
│   ├── Centralized Error Handlers & Structured Logging      │
│   └── Business Services Layer                              │
└───────────────┬─────────────────────────────┬───────────────┘
                │                             │
                ▼                             ▼
┌───────────────────────────────┐ ┌───────────────────────────┐
│        Data Provider          │ │      Model Provider       │
│  - BaseDataProvider (ABC)     │ │  - BaseModelProvider (ABC)│
│  - SampleDataProvider (Active)│ │  - DevModelProvider (Demo)│
│  - [Future DB Adapter]        │ │  - MLflowAdapter (Customer bill) │
└───────────────────────────────┘ └───────────────────────────┘
```

---

## Directory Structure

```text
gridvision-app/
├── package.json                    # Workspace runner commands
├── README.md                       # Platform documentation
├── .venv/                          # Python virtual environment
├── backend/                        # Modular Flask REST API
│   ├── run.py                      # Development server runner
│   ├── .env.example                # Backend environment configuration template
│   ├── app/
│   │   ├── __init__.py             # Application factory & blueprint registration
│   │   ├── config.py               # Environment configuration (Dev, Test, Prod)
│   │   ├── models/                 # Model registry and independent model packages
│   │   │   ├── registry.py
│   │   │   └── customer_bill_prediction/
│   │   ├── api/
│   │   │   ├── error_handlers.py   # Centralized error handling & status codes
│   │   │   └── v1/                 # Versioned API routes
│   │   │       ├── health.py       # /health, /ready, /platform/health
│   │   │       ├── overview.py     # /overview executive KPIs
│   │   │       ├── entities.py     # /entities/commercial, residential, government
│   │   │       ├── forecast.py     # /forecast/* & on-demand inference
│   │   │       ├── models.py       # Model catalog & gold-backed predictions
│   │   │       ├── dashboard.py    # /dashboard/* telemetry across personas
│   │   │       ├── historical.py   # /historical rollups and curves
│   │   │       ├── peak.py         # /peak-demand & /peak-demand/curtail
│   │   │       ├── anomalies.py    # /anomalies & status updates
│   │   │       ├── customers.py    # /customers/segments, diurnal curves, matrix
│   │   │       ├── insights.py     # /energy-insights
│   │   │       └── assistant.py    # /assistant/chat domain answers
│   │   ├── services/               # Business logic services
│   │   │   ├── forecast_service.py
│   │   │   ├── dashboard_service.py
│   │   │   ├── peak_service.py
│   │   │   ├── anomaly_service.py
│   │   │   ├── customer_service.py
│   │   │   ├── insight_service.py
│   │   │   └── health_service.py
│   │   ├── providers/              # Provider interfaces & adapters
│   │   │   ├── data_provider.py    # BaseDataProvider abstract class
│   │   │   ├── sample_data_provider.py # Deterministic sample dataset provider
│   │   │   ├── model_provider.py   # BaseModelProvider abstract class
│   │   │   ├── mock_model_provider.py  # Development provider (explicit demo mode)
│   │   │   └── mlflow_adapter.py   # Registered customer-bill model adapter
│   │   └── utils/
│   │       ├── logging.py          # Centralized structured logging
│   │       ├── responses.py        # Consistent JSON response builders
│   │       └── validation.py       # Pydantic request schemas
├── airflow/customer/               # Customer-only bronze/silver/gold DAG
├── training/                       # Customer bill training and MLflow logging
├── tests/                          # All backend and training tests
├── requirements.txt                # Single Python dependency manifest
├── scripts/filter_requirements.py  # Selects backend groups for the Docker image
├── automation.py                   # Ordered ETL → training orchestration
├── Dockerfile.backend              # Flask API image
├── Dockerfile.frontend             # React/Nginx image
├── compose.yaml                    # MLflow + backend + frontend services
└── frontend/                       # React Single Page Application
    ├── .env                        # VITE_API_BASE_URL configuration
    ├── package.json
    ├── vite.config.ts
    └── src/
        ├── services/
        │   ├── apiClient.ts        # Centralized HTTP client
        │   ├── analyticsService.ts # API integration service layer
        │   └── modelService.ts    # Model catalog and prediction API
        ├── pages/                  # React dashboard pages
        │   └── CustomerBillModelPage.tsx
        └── types/analytics.ts      # TypeScript domain contracts
```

---

## Quickstart & Execution

### Start the full stack

1. Start Docker Desktop and enable its WSL integration for your Ubuntu distribution.
2. In Ubuntu, activate the Python 3.10 environment with the Airflow and model-serving dependencies installed.
3. From the project root, run:

   ```bash
   cd /mnt/d/GridVision
   source ~/.venvs/gridvision/bin/activate
   python automation.py
   ```

The script runs the customer ETL and training workflow, then starts the MLflow, Airflow, backend, and frontend services. It prints a timed summary and leaves the services running. See [Customer Bill Prediction: Data, Training, and Automation](#customer-bill-prediction-data-training-and-automation) for environment setup, output paths, and EC2 deployment steps.

On Windows, run `python automation.py` from the project root. It defaults `GRIDVISION_DATA_DIR` to `D:\GridVision\data` and generates a temporary development `SECRET_KEY` for the Compose services. The gold dataset is expected at `D:\GridVision\data\gold\customer_gold.parquet`.

If starting Compose directly instead of using the automation script, create a root `.env` file (it is git-ignored) with `GRIDVISION_DATA_DIR=D:\GridVision\data` and a private `SECRET_KEY`. Generate a strong key with:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Paste the generated value as `SECRET_KEY=...` in `.env`, then run `docker compose up -d --build backend frontend`. `SECRET_KEY` is Flask's private application-signing key; it is not the model or dataset key. Keep it private and stable between restarts so signed sessions remain valid.

---

## Testing & Verification

### Run All Python Tests (pytest)
```bash
source ~/.venvs/gridvision/bin/activate
python -m pytest tests
```
All backend and model tests are stored under the single root `tests/` folder.

### Run Frontend Typecheck & Build
```powershell
cd frontend
npm run build
```

### Run Frontend Linter
```powershell
cd frontend
npm run lint
```

---

## API Endpoints Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/health` | Process liveness check (`{ status: "alive" }`) |
| `GET` | `/api/v1/ready` | Operational readiness and provider status |
| `GET` | `/api/v1/platform/health` | Dataset accumulation & model evaluation telemetry |
| `GET` | `/api/v1/overview` | Executive summary KPIs, load, and alerts |
| `GET` | `/api/v1/entities/commercial` | Commercial buildings catalog |
| `GET` | `/api/v1/entities/residential` | Residential smart meters catalog |
| `GET` | `/api/v1/entities/government` | Regional government grid sites catalog |
| `GET` | `/api/v1/forecast/commercial/<id>` | Commercial building multi-horizon forecast |
| `GET` | `/api/v1/forecast/residential/<id>` | Residential month-end consumption forecast |
| `GET` | `/api/v1/forecast/government/<id>` | Regional grid site demand forecast |
| `POST` | `/api/v1/forecast/predict` | On-demand feature inference |
| `GET` | `/api/v1/dashboard/commercial` | Commercial telemetry (`1D`, `7D`, `1M`, `3M`, `1Y`) |
| `GET` | `/api/v1/dashboard/household` | Household daily consumption curves & targets |
| `GET` | `/api/v1/dashboard/government` | Regional and system-wide grid telemetry |
| `GET` | `/api/v1/dashboard/government/regions` | Regional zone summaries with sparklines |
| `GET` | `/api/v1/historical` | Historical rollups across personas (`30D`, `90D`, `1Y`, `ALL`) |
| `GET` | `/api/v1/peak-demand` | Peak capacity analysis, reserve margins, hourly distribution |
| `POST` | `/api/v1/peak-demand/curtail` | ADR curtailment dispatch simulation |
| `GET` | `/api/v1/anomalies` | Filtered anomaly detection events |
| `PATCH`| `/api/v1/anomalies/<event_id>` | Update anomaly status (`investigating`, `confirmed`, etc.) |
| `GET` | `/api/v1/customers/segments` | High-level customer segment breakdown |
| `GET` | `/api/v1/customers/segmentation-matrix`| Multi-dimensional customer segmentation |
| `GET` | `/api/v1/customers/diurnal-curves` | 24-hour diurnal curves across sectors |
| `GET` | `/api/v1/energy-insights` | Algorithmic optimization recommendations |
| `POST` | `/api/v1/assistant/chat` | Domain-grounded query answering |
| `GET` | `/api/v1/models` | Registered model catalog and gold dataset summary |
| `GET` | `/api/v1/models/customer-bill-prediction/records` | Page through customer entities in the gold dataset |
| `GET` | `/api/v1/models/customer-bill-prediction/records/<entity_id>` | Get a customer's available gold records |
| `GET` | `/api/v1/models/customer-bill-prediction/history` | Residential monthly usage and model projections from gold data |
| `POST` | `/api/v1/models/customer-bill-prediction/predict` | Run a customer bill prediction against a gold record |

### Customer bill model workbench

Open **Models** in the application sidebar to select a customer entity and gold record, run its prediction, and compare the estimated monthly energy and illustrative bill with the actuals. Each entity has multiple cutoff-day records in a month; the UI selects the cutoff day along with the month. Results are labeled as retrospective gold-data replays, not live meter telemetry or invoices.

The backend stores model-specific code in `backend/app/models/<model_name>/` and adds public metadata to `backend/app/models/registry.py`. Each package owns its data contract and inference logic. Add commercial peak-hour detection as a separate model package and registry entry when its artifact and feature contract are ready, without coupling it to customer bill prediction.

Docker Compose mounts `data/gold` and the customer model metadata read-only into the API container. Rebuild/restart the stack after changing application code or Compose mounts.

The Residential **Historical Insights** page reads the customer gold Parquet dataset directly. It removes duplicate entity-month snapshots by choosing the last available cutoff, then charts average monthly actual usage alongside the stored model projection. The dataset contains 1,000 modeled entities across 12 months in 2018; these are retrospective sample-cohort insights, not live readings. The page also displays the selected model's holdout metrics, training features, and dataset version.

---

## Switching From Sample Data & Mocks to Production (Real Data & Real Models)

The architecture is specifically decoupled so you can independently swap:
1. **The Data Provider** (historical records, building catalogs, actual sensor curves).
2. **The Model Provider** (MLflow-registered inference models).

Neither change requires modifying the React frontend or API route contracts.

```text
                               ┌──────────────────────────────────────────────┐
                               │                 Flask Routes                 │
                               └──────────────┬────────────────┬──────────────┘
                                              │                │
                        ┌─────────────────────┘                └─────────────────────┐
                        ▼                                                            ▼
         ┌──────────────────────────────┐                             ┌──────────────────────────────┐
         │     BaseDataProvider         │                             │     BaseModelProvider        │
         └───────┬──────────────┬───────┘                             └───────┬──────────────┬───────┘
                 │              │                                             │              │
      (Dev Mode) │              │ (Production)                     (Dev Mode) │              │ (Production)
                 ▼              ▼                                             ▼              ▼
     [SampleDataProvider]  [DatabaseDataProvider]                [DevModelProvider]   [MLflowModelAdapter]
     Deterministic Sample  TimescaleDB / PostgreSQL /             Explicit Demo Mode   Certified MLflow
     Datasets              Parquet Data Lake                      Simulations          Registry Models
```

---

### Step 1: Switching from Sample Data to Real Data

All data access is encapsulated in [`BaseDataProvider`](backend/app/providers/data_provider.py). Currently, [`SampleDataProvider`](backend/app/providers/sample_data_provider.py) serves deterministic development records.

To connect your real production database or data warehouse:

1. **Create a production provider** in `backend/app/providers/database_data_provider.py`:
   ```python
   from app.providers.data_provider import BaseDataProvider

   class DatabaseDataProvider(BaseDataProvider):
       def __init__(self, connection_string: str) -> None:
           self.engine = create_engine(connection_string)

       def get_commercial_buildings(self) -> list[dict]:
           with self.engine.connect() as conn:
               result = conn.execute(text("SELECT * FROM commercial_buildings_catalog"))
               return [dict(row._mapping) for row in result]

       # Implement remaining abstract methods (meters, sites, telemetry curves, anomalies)...
   ```

2. **Register it in the Application Factory** (`backend/app/__init__.py`):
   ```python
   data_provider_type = app.config.get("DATA_PROVIDER", "sample").lower()
   if data_provider_type in ("database", "production"):
       data_provider = DatabaseDataProvider(os.getenv("DATABASE_URL"))
   else:
       data_provider = SampleDataProvider()
   ```

3. **Configure your production environment** in `backend/.env`:
   ```bash
   DATA_PROVIDER=database
   DATABASE_URL=postgresql://user:password@timescale-db:5432/gridvision
   ```

---

### Step 2: Switching from Mock Models to Real MLflow Models

The direct local-development backend uses [`DevelopmentModelProvider`](backend/app/providers/mock_model_provider.py), which tags predictions with `"is_demo": true`.

The full `automation.py` workflow configures the Docker backend to use the registered customer bill model:

- Compose sets `MODEL_PROVIDER=mlflow` and points the backend to the MLflow container on its internal Docker network.
- MLflow serves artifacts through its tracking server, so training and backend containers do not depend on host-specific artifact paths.
- The application factory (`backend/app/__init__.py`) loads [`MLflowModelAdapter`](backend/app/providers/mlflow_adapter.py).
- If the tracking server or registered alias is unavailable, the adapter reports an error rather than silently falling back to demo predictions.
- The customer bill model accepts monthly cutoff features and returns estimated remaining and month-end kWh. The tariff is illustrative because the source data does not contain customer-specific billing plans.

The tracking server proxies artifacts from the persistent `/mlflow/artifacts` volume. New training runs use the `gridvision-customer-bill-prediction-v2` experiment so they receive proxy-backed artifact URIs; this avoids the host-specific artifact paths stored by the earlier experiment. Existing MLflow runs and model versions are preserved. After changing this configuration, rebuild the MLflow service and register a new model version before using the prediction endpoint.

---

## Customer Bill Prediction: Data, Training, and Automation

The current ML workflow is intentionally limited to **customer bill prediction**. Airflow creates one raw bronze copy, a deterministic residential-only silver sample, and `data/gold/customer_gold.parquet`. Training compares a chronological-tuned HistGradientBoosting model with a cutoff-safe monthly projection baseline; only the validation winner is registered to the `champion` alias. The existing notebook remains experimental. Docker Compose runs MLflow, the Flask API, and the React UI; the Airflow DAG and model training execute in the active Python environment.

### Install the local Python dependencies (Python 3.10, WSL2)

Apache Airflow does not support native Windows. Run the pipeline in a WSL2 Linux terminal (the repository can remain on the D: drive at `/mnt/d/GridVision`); use a Linux virtual environment rather than the Windows `.venv`:

```bash
cd /mnt/d/GridVision
python3.10 -m venv ~/.venvs/gridvision
source ~/.venvs/gridvision/bin/activate
python scripts/filter_requirements.py requirements.txt /tmp/gridvision-automation-requirements.txt \
  --groups airflow model-serving
pip install -r /tmp/gridvision-automation-requirements.txt \
  --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-2.10.5/constraints-3.10.txt"
```

Do not install the `backend` group in this WSL environment: Airflow's constraints pin Flask to 2.2.5, while the backend requires Flask 3 or newer. Docker Desktop must be running with WSL integration enabled. The automation command expects `data/sample/training_sample_50000.parquet`.

### Run the full local workflow

```bash
cd /mnt/d/GridVision
source ~/.venvs/gridvision/bin/activate
python automation.py
```

The script checks dependencies and Docker, starts the persistent MLflow container, runs the Airflow bronze → silver → gold DAG, trains and registers the model, starts the Airflow scheduler/UI, builds and starts the API/UI containers, checks service health, and prints elapsed times and URLs. It generates a development secret if `SECRET_KEY` is not set. The services remain running after the script exits.

For a functional, resource-conscious local run, the silver stage deterministically samples **100 residential entities** by default (down from 1,000). The sample size can be changed with `CUSTOMER_SAMPLE_BUILDINGS` before running automation. The silver transform discovers residential entity profiles with bounded Arrow batches, avoiding a full-file DuckDB profile aggregation. DuckDB is limited to 2 GB and two worker threads by default, and spills intermediate data to `~/.cache/gridvision/duckdb_temp` when needed. Ensure the WSL filesystem containing that directory has free space. You can tune the DuckDB limits with `CUSTOMER_DUCKDB_MEMORY_LIMIT` and `CUSTOMER_DUCKDB_THREADS`. This smaller sample is intended for functional development; increase it as resources and scaling work allow.

To retrain and rebuild the services using an already-generated gold dataset without rerunning the memory-intensive Airflow ETL, run `python automation.py --skip-data-pipeline`. This still trains a new model version and updates the `champion` alias.

Open the frontend at `http://localhost:8080`. Airflow is available at `http://localhost:8081`; its generated login details are in `logs/airflow/standalone.log`. The MLflow UI is at `http://localhost:15001` (host port configurable with `GRIDVISION_MLFLOW_HOST_PORT`). The API health endpoint is `http://localhost:5000/api/v1/health`. Stop the Docker services with `docker compose down`. To stop the Airflow process group started by automation, use its PID file: `kill -TERM -- -$(cat logs/airflow/standalone.pid)`.

### Data and model locations

| Output | Path |
|---|---|
| Raw source input | `data/sample/training_sample_50000.parquet` |
| Bronze (raw Parquet copy/link) | `data/bronze/training_sample_50000.parquet` |
| Silver (residential sample) | `data/silver/customer_silver.parquet` |
| Gold (engineered training data) | `data/gold/customer_gold.parquet` |
| Dataset quality reports (bronze/silver/gold) | `logs/data/quality_reports/` |
| Dataset version manifests and `latest.json` pointers | `data/metadata/dataset_versions/<dataset_name>/` |
| Dataset-version Parquet snapshots | `data/metadata/dataset_versions/<dataset_name>/<version>.parquet` |
| Training pickle and metadata sidecar | `models/customer_bill_prediction.pkl` and `models/customer_bill_prediction.metadata.json` |
| Model cards | `logs/model_cards/` |
| Model metrics and training summaries | `logs/model_metrics/` and `logs/training/` |
| API request events (JSON Lines) | `logs/endpoints/api.jsonl` |
| Pytest run summaries | `logs/testing/` |
| MLflow database | `data/mlflow/mlflow.db` |
| MLflow model/run artifacts | `data/mlflow/artifacts/` |
| Airflow standalone log/credentials and task logs | `logs/airflow/` |

The modular log tree is documented in [`logs/README.md`](logs/README.md). Set `GRIDVISION_LOG_DIR` to place it elsewhere; automation, Airflow, training, pytest, and the Docker backend use that same location. Runtime-generated files are ignored by Git while the directory layout is kept in the repository.

Each Airflow transformation writes a JSON quality report and a version manifest with row count, schema, parameters, check results, and parent dataset versions. If `MLFLOW_TRACKING_URI` is configured, each stage also creates a tagged MLflow data-quality run with check-count metrics and the report/manifest artifacts. Failed quality checks are recorded before the task fails, and training refuses a gold dataset whose latest quality result failed.

Versioned Parquet snapshots are hard links to the generated dataset files, so they retain prior outputs when this pipeline atomically replaces a stage file without duplicating the dataset's storage. The dataset and metadata directories must be on the same filesystem for hard links. These snapshots are intended to be immutable through this pipeline; do not modify a dataset file in place. Back up the data/version directories together.

Training logs the dataset version and lineage, split month ranges, package versions, candidate cross-validation results, validation and held-out metrics, model parameters, model signature, exported pickle, metadata, and model card to MLflow and the appropriate `logs/` folders. Each registered model version is tagged with its dataset version, selected estimator, and training run ID. The local metadata sidecar includes the exported pickle's SHA-256 checksum.

DuckDB spill files use `~/.cache/gridvision/duckdb_temp` by default so WSL stores temporary processing files on its Linux filesystem rather than the Windows-mounted project drive. Set `CUSTOMER_DUCKDB_TEMP_DIR` to override that location; ensure the chosen filesystem has sufficient free space. Check WSL memory and storage with `free -h` and `df -h ~ /mnt/d` if a transform reports an allocation or spill-write error.

The backend loads the registered MLflow alias from the same persistent `data/mlflow` directory mounted read-only inside its container. The pickle is a local training artifact; production inference uses the MLflow registry alias.

### Run the workflow on an AWS EC2 Ubuntu instance

1. Launch an Ubuntu 22.04 EC2 instance. Choose CPU, memory, and EBS storage based on the actual Parquet size and the intermediate datasets; check the source size with `ls -lh`. Allow enough free disk for bronze/silver/gold files and DuckDB spill data. In the security group, allow SSH (port 22) only from your IP and, for a temporary UI demo, port 8080 only from your IP. Do **not** expose ports 5000, 5001, or 8081 publicly.
2. SSH into the instance, install Docker Engine/Compose and Python 3.10, then log out/in after adding your user to the Docker group:

   ```bash
   sudo apt-get update
   sudo apt-get install -y ca-certificates curl python3.10 python3.10-venv python3-pip
   sudo install -m 0755 -d /etc/apt/keyrings
   sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
   sudo chmod a+r /etc/apt/keyrings/docker.asc
   echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
   sudo apt-get update
   sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
   sudo usermod -aG docker "$USER"
   ```

3. Clone this project onto the instance (replace the placeholder with your repository URL), then create the input directory:

   ```bash
   git clone YOUR_REPOSITORY_URL ~/GridVision
   mkdir -p ~/GridVision/data/sample
   ```

   Copy the source file into `data/sample/training_sample_50000.parquet`. The dataset may be too large for Git; use SCP or an S3 bucket. From your local Windows PowerShell, an example SCP command is:

   ```powershell
   scp -i C:\path\to\key.pem D:\GridVision\data\sample\training_sample_50000.parquet ubuntu@EC2_PUBLIC_IP:~/GridVision/data/sample/
   ```

4. After reconnecting over SSH, create and install the Python environment from the project root:

   ```bash
   cd ~/GridVision
   python3.10 -m venv ~/.venvs/gridvision
   source ~/.venvs/gridvision/bin/activate
   python -m pip install --upgrade pip
   python scripts/filter_requirements.py requirements.txt /tmp/gridvision-automation-requirements.txt \
     --groups airflow model-serving
   pip install -r /tmp/gridvision-automation-requirements.txt \
     --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-2.10.5/constraints-3.10.txt"
   ```

5. Run `python automation.py` from that activated environment. It builds and starts MLflow, runs ETL and training, starts Airflow, then builds and starts the API/UI. Visit `http://EC2_PUBLIC_IP:8080` from an allowed IP. Use a domain and HTTPS reverse proxy/load balancer before exposing this beyond a temporary demo. Keep `data/` on persistent EBS storage and back it up; it contains the trained data products and MLflow registry/artifacts.

To access Airflow and MLflow from your computer without opening their ports publicly, create an SSH tunnel:

```powershell
ssh -i C:\path\to\key.pem -L 8081:127.0.0.1:8081 -L 15001:127.0.0.1:15001 ubuntu@EC2_PUBLIC_IP
```

Then use `http://localhost:8081` for Airflow and `http://localhost:15001` for MLflow. The Airflow generated login details are on the instance in `logs/airflow/standalone.log`.
