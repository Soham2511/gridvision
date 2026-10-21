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
│  - [Future DB Adapter]        │ │  - MLflowAdapter (Future) │
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
│   ├── requirements.txt            # Python dependencies (Flask, Pydantic, pytest)
│   ├── pytest.ini                  # Pytest configuration
│   ├── .env.example                # Backend environment configuration template
│   ├── app/
│   │   ├── __init__.py             # Application factory & blueprint registration
│   │   ├── config.py               # Environment configuration (Dev, Test, Prod)
│   │   ├── api/
│   │   │   ├── error_handlers.py   # Centralized error handling & status codes
│   │   │   └── v1/                 # Versioned API routes
│   │   │       ├── health.py       # /health, /ready, /platform/health
│   │   │       ├── overview.py     # /overview executive KPIs
│   │   │       ├── entities.py     # /entities/commercial, residential, government
│   │   │       ├── forecast.py     # /forecast/* & on-demand inference
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
│   │   │   └── mlflow_adapter.py   # MLflow production adapter
│   │   └── utils/
│   │       ├── logging.py          # Centralized structured logging
│   │       ├── responses.py        # Consistent JSON response builders
│   │       └── validation.py       # Pydantic request schemas
│   └── tests/                      # Pytest test suite (36 tests, 94% coverage)
└── frontend/                       # React Single Page Application
    ├── .env                        # VITE_API_BASE_URL configuration
    ├── package.json
    ├── vite.config.ts
    └── src/
        ├── services/
        │   ├── apiClient.ts        # Centralized HTTP client
        │   └── analyticsService.ts # API integration service layer
        ├── pages/                  # React dashboard pages
        └── types/analytics.ts      # TypeScript domain contracts
```

---

## Quickstart & Execution

### Initial Setup (First Time Only)

#### 1. Setup Backend Environment
```powershell
# In D:\Projects\gridvision-app:
python -m venv .venv
.\.venv\Scripts\pip install -r backend\requirements.txt

# Create local environment config from template:
Copy-Item backend\.env.example backend\.env
```

#### 2. Setup Frontend Environment
```powershell
cd frontend
npm install

# Create local environment config from template:
Copy-Item .env.example .env
cd ..
```

---

### Running the Application

You will need **two terminal windows**:

#### Terminal 1: Start the Flask Backend
```powershell
# From project root (D:\Projects\gridvision-app):
.\.venv\Scripts\python.exe backend\run.py
```
- **Backend API**: [`http://127.0.0.1:5000/`](http://127.0.0.1:5000/)
- **Health Check**: [`http://127.0.0.1:5000/api/v1/health`](http://127.0.0.1:5000/api/v1/health)
- **Readiness Probe**: [`http://127.0.0.1:5000/api/v1/ready`](http://127.0.0.1:5000/api/v1/ready)

#### Terminal 2: Start the React Frontend
```powershell
# From project root (D:\Projects\gridvision-app):
npm run dev

# Or from the frontend directory:
cd frontend
npm run dev
```
- **Dashboard UI**: [`http://localhost:5173/`](http://localhost:5173/)

---

## Testing & Verification

### Run Backend Tests (pytest)
```powershell
# Execute pytest with coverage:
.\.venv\Scripts\pytest.exe backend --cov=backend/app --cov-report=term-missing
```
*Current test suite*: **36 passing tests**, **94% statement coverage**.

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

All data access is encapsulated in [`BaseDataProvider`](file:///d:/Projects/gridvision-app/backend/app/providers/data_provider.py). Currently, [`SampleDataProvider`](file:///d:/Projects/gridvision-app/backend/app/providers/sample_data_provider.py) serves deterministic development records.

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

Currently, the backend runs in development mode via [`DevelopmentModelProvider`](file:///d:/Projects/gridvision-app/backend/app/providers/mock_model_provider.py), which tags all predictions with `"is_demo": true`.

When your teammates finish training models and provide the MLflow tracking service:

1. **Configure MLflow settings** in `backend/.env`:
   ```bash
   MODEL_PROVIDER=mlflow
   MLFLOW_TRACKING_URI=http://mlflow-server:5000
   MLFLOW_MODEL_ALIAS=champion
   MLFLOW_COMMERCIAL_MODEL=commercial-demand-forecast
   MLFLOW_RESIDENTIAL_MODEL=residential-month-end-pipeline
   MLFLOW_GOVERNMENT_MODEL=government-regional-demand
   ```

2. **How it works automatically**:
   - The application factory (`backend/app/__init__.py`) reads `MODEL_PROVIDER=mlflow` and loads the [`MLflowModelAdapter`](file:///d:/Projects/gridvision-app/backend/app/providers/mlflow_adapter.py).
   - If the MLflow server is unreachable or unconfigured, it will explicitly report an error rather than silently returning mock predictions in production.
   - The React frontend automatically receives real inference outputs with the exact same JSON schema.

