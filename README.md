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

---

## Podman Containerization Guide

GridVision is fully containerized using **Podman** and **Podman Compose** with production-grade WSGI (Gunicorn) and reverse proxying (Nginx).

### Container Architecture & Same-Origin Routing

```text
  Browser / Phone / Client
            │
            │ HTTP Port 3000 (or 80)
            ▼
┌────────────────────────────────────────────────────────┐
│ gridvision-frontend (Nginx Alpine)                     │
│  ├── /                → Serves React SPA (HTML/JS/CSS) │
│  ├── /assets/         → Static asset cache (1y)        │
│  ├── /nginx-health    → Container liveness (200 OK)    │
│  └── /api/            → Reverse Proxy Pass ────────────┼──┐
└────────────────────────────────────────────────────────┘  │
                                                            │ (Internal Bridge Network:
                                                            │  gridvision-net)
                                                            ▼
┌────────────────────────────────────────────────────────┐
│ gridvision-backend (Python 3.11-slim + Gunicorn)       │
│  ├── /api/v1/health   → API liveness check             │
│  ├── /api/v1/ready    → Readiness check                │
│  ├── /api/v1/...      → Forecast, Peak, Anomalies      │
│  └── Port 5000        → Kept private inside network    │
└────────────────────────────────────────────────────────┘
```

**Why Same-Origin Routing?**
- Eliminates CORS errors completely.
- Avoids leaking internal container hostnames (`backend`) to the client browser.
- Universal routing: the application works seamlessly on `localhost`, across local LANs (e.g. `http://192.168.0.x:3000`), or on AWS EC2 without rebuilding or hardcoding IP addresses.

---

### Prerequisites & Podman Setup on Windows

Ensure Podman Engine and the Podman WSL machine are installed and running:

```powershell
podman version
podman machine list
```

#### Windows WSL2 Netavark Configuration (Important)
Microsoft's WSL2 kernel uses a standard firewall stack that does not include full nftables NAT tables. To ensure Podman container port publishing works reliably:

```powershell
# Restore nft binary and configure netavark firewall driver to none
podman machine ssh "if [ -f /usr/sbin/nft.real ]; then sudo mv -f /usr/sbin/nft.real /usr/sbin/nft; fi"
podman machine ssh "sudo mkdir -p /etc/containers/containers.conf.d && echo -e '[network]\nfirewall_driver = \"none\"' | sudo tee /etc/containers/containers.conf.d/99-firewall.conf"
```

---

### Container Commands (Podman & Podman Compose)

#### 1. Configuration Setup
Copy the environment template:
```powershell
Copy-Item .env.example .env
```

#### 2. Build Container Images
Build both images using Podman Compose:
```powershell
podman compose build
```
Or build individually:
```powershell
podman build -t gridvision-backend:latest ./backend
podman build -t gridvision-frontend:latest --build-arg VITE_API_BASE_URL=/api/v1 ./frontend
```

#### 3. Start Containers
Run both containers in detached mode:
```powershell
podman compose up -d
```

#### 4. Monitor Health & Status
```powershell
podman ps
podman compose ps
```

#### 5. View Logs
View combined or service-specific logs:
```powershell
podman compose logs -f
podman logs -f gridvision-backend
podman logs -f gridvision-frontend
```

#### 6. Stop and Clean Up
```powershell
podman compose down
```

---

### End-to-End API Verification

With containers running on port 3000, run the automated verification script:

```powershell
python tests/verify_container_api.py http://localhost:3000
```

This verifies:
- Frontend SPA routing and static assets
- Health and readiness probes (`/api/v1/health`, `/api/v1/ready`, `/api/v1/platform/health`)
- All 15+ data endpoints (commercial, residential, government, forecast, anomalies, peak demand, customer matrix, AI chat)
- Error handling (404, 405, 422 validation failure)

---

### Accessing From Other Devices on the LAN

To access GridVision from your smartphone, tablet, or another computer on the same Wi-Fi network:

1. **Find your Windows LAN IP**:
   ```powershell
   ipconfig
   # Note the IPv4 Address under Wireless LAN adapter Wi-Fi (e.g. 192.168.0.102)
   ```
2. **Open Windows Defender Firewall for Port 3000**:
   ```powershell
   New-NetFirewallRule -DisplayName "GridVision Web" -Direction Inbound -LocalPort 3000 -Protocol TCP -Action Allow
   ```
3. **Open browser on phone or client device**:
   ```text
   http://192.168.0.102:3000
   ```
   All API calls will automatically resolve to `http://192.168.0.102:3000/api/v1/...` through the reverse proxy!

---

### AWS EC2 Deployment Guide

To deploy GridVision on a clean AWS EC2 instance:

1. **Launch EC2 Instance**:
   - AMI: Ubuntu 24.04 LTS or Amazon Linux 2023 (t3.small or t3.medium recommended)
   - Security Group Inbound Rules:
     - SSH (Port 22) from your IP
     - HTTP (Port 80) from `0.0.0.0/0`
     - HTTPS (Port 443) from `0.0.0.0/0` (if terminating SSL)

2. **Install Podman**:
   ```bash
   sudo apt-get update && sudo apt-get install -y podman podman-compose
   ```

3. **Clone Repository & Configure Environment**:
   ```bash
   git clone <your-repo-url> gridvision-app
   cd gridvision-app
   cp .env.example .env
   # Set FRONTEND_PORT=80 and a secure random SECRET_KEY in .env
   ```

4. **Build and Launch**:
   ```bash
   podman compose up -d --build
   ```

5. **Verify**:
   ```bash
   curl -I http://localhost/nginx-health
   curl http://localhost/api/v1/health
   python3 tests/verify_container_api.py http://localhost
   ```

6. **Production HTTPS Recommendation**:
   For production public deployments, place an AWS Application Load Balancer (ALB) or Caddy/Certbot in front of port 80 to terminate TLS/HTTPS.

