# GridVision — End-to-End System & Execution Instructions (Python 3.10)

This document provides definitive, step-by-step instructions for installing, configuring, running, testing, and deploying the **GridVision** Next-Generation Smart Energy Analytics Platform. It is fully analyzed and tailored for **Python 3.10**.

---

## 1. System Overview & Architecture

GridVision is an enterprise-grade smart energy intelligence platform catering to utilities, regional grid operators, commercial building managers, and residential consumers. It couples multi-horizon machine learning forecasting and anomaly detection with an agentic clean-architecture AI assistant.

### Platform Architecture

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                      React SPA (TypeScript + Vite)                      │
│            Configured via VITE_API_BASE_URL (Default: :8082 or :5173)   │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ HTTP / REST APIs
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       Modular Flask REST Backend                        │
│   ├── Application Factory (app/__init__.py) & Config System             │
│   ├── Clean Architecture Domain Engines (IS 732, BEE, CEA, TCO)        │
│   ├── LangChain Residential Assistant + Groq LLM Adapter                │
│   ├── Hybrid Document RAG Engine + In-Memory Vector / BM25 Index        │
│   ├── SQLite Reference Database (data/reference.db)                     │
│   └── Blueprints (/api/v1/health, forecast, peak, anomalies, etc.)      │
└───────────────┬─────────────────────────────┬───────────────────────────┘
                │                             │
                ▼                             ▼
┌───────────────────────────────┐ ┌───────────────────────────────────────┐
│        Data Providers         │ │            Model Providers            │
│  - ParquetDataProvider (Lake) │ │  - MLflowModelAdapter (Certified Reg) │
│  - SampleDataProvider (Dev)   │ │  - TrainedForecastProvider (Paired)   │
│  - SQLite (data/reference.db) │ │  - DevelopmentModelProvider (Mocks)   │
└───────────────────────────────┘ └───────────────────────────────────────┘
```

---

## 2. Why Python 3.10 is Strictly Required

The entire data engineering and model serving infrastructure in GridVision is pinned to **Python 3.10**:

1. **Apache Airflow 2.10.5 Compatibility:**
   Airflow 2.10.5 constraint manifests (`constraints-2.10.5/constraints-3.10.txt`) are engineered for CPython 3.10. Newer Python versions (3.11, 3.12, 3.14) break dependency resolution, introduce conflicting transitive libraries, and fail with native POSIX signal discrepancies.
2. **MLflow 2.22.0 & SQLAlchemy Engine Boundary:**
   In Python 3.11+, unconstrained package installation brings SQLAlchemy >= 2.0.36, which removes internal symbols like `FallbackAsyncAdaptedQueuePool` required by MLflow 2.22.0's tracking store, breaking SQLite and PostgreSQL backends. Under Python 3.10 with the project constraint manifest, SQLAlchemy is pinned to a compatible version.
3. **Pre-compiled Binary Wheels:**
   `duckdb==1.1.3`, `pyarrow==16.1.0`, `pandas==2.1.4`, `lightgbm>=4.3,<5`, `scikit-learn>=1.5,<2`, `h3>=4.0`, `dill>=0.3.1.1`, and `PyWavelets>=1.4` provide optimized CPython 3.10 wheels, eliminating compiler toolchain failures on host machines.
4. **Platform Execution Boundary:**
   - **Airflow:** Apache Airflow relies on UNIX process management (`fork`, `SIGALRM`) and **cannot run natively on Windows**. It must run inside **WSL2 (Ubuntu)**, **Linux**, or **Docker/Podman containers**.
   - **Backend API & Tests:** Can run either natively on Windows (PowerShell) or inside WSL2/Linux/Docker under Python 3.10.

---

## 3. Directory Layout & Key Components

```text
gridvision-final/
├── automation.py                   # Automated ETL → MLflow → Airflow → Services orchestration
├── compose.yaml                    # Multi-container orchestration (Airflow, MLflow, Backend, Frontend)
├── Dockerfile.airflow              # Airflow 2.10.5 container (Python 3.10 base)
├── Dockerfile.backend              # Flask backend container (python:3.10-slim)
├── Dockerfile.frontend             # React Nginx production build
├── requirements.txt                # Single grouped project dependency manifest
├── scripts/
│   ├── filter_requirements.py      # Dependency group filter utility
│   └── join_commercial_region_forecasts.py # Pair building and regional forecasts
├── airflow/                        # Airflow DAGs
│   ├── customer/                   # Residential smart meter Bronze → Silver → Gold
│   ├── commercial/                 # Commercial building forecasting DAG & DuckDB ETL
│   ├── 2_government_load_prediction/ # Regional grid load forecasting DAG & CLI
│   ├── segmentation/               # Government customer behavioral segmentation DAG
│   └── anomaly_prediction/         # Wavelet + Isolation Forest training DAG
├── backend/                        # Modular Flask REST API
│   ├── run.py                      # Development server runner
│   └── app/
│       ├── __init__.py             # Application factory & provider assembly
│       ├── config.py               # Centralized configuration classes
│       ├── api/v1/                 # Versioned REST API endpoints
│       ├── services/               # Forecast, peak, anomaly, and segmentation services
│       ├── providers/              # Parquet, sample, and MLflow adapters
│       └── models/                 # Model registry and runtime prediction packages
├── ai/residential/                 # Residential assistant, RAG, and complaint features
│   ├── backend/app/                # Assistant, RAG, reference, complaint, and residential modules
│   ├── frontend/src/               # Assistant and complaint UI
│   ├── tests/                      # Residential AI and complaint tests
│   ├── docs/                       # Residential assistant documentation
│   └── backend/.env.example        # Residential backend environment template
├── data/                           # Data lake hierarchy
│   ├── sample/                     # Raw input Parquet (training_sample_50000.parquet)
│   ├── bronze/                     # Raw Parquet staging copies
│   ├── silver/                     # Filtered, cleansed intermediate Parquet datasets
│   ├── gold/                       # Engineered feature and training Parquet datasets
│   ├── reference.db                # SQLite database for BEE, CEA, and IS 732 standards
│   ├── metadata/                   # Quality reports, snapshots, and automation state
│   └── mlflow/                     # MLflow tracking SQLite DB and model artifact storage
├── models/                         # Serialized model joblib/pickle bundles and metadata JSON
├── frontend/                       # React 18 + TypeScript + Vite Single Page Application
├── logs/                           # Unified JSONL/JSON structured runtime logs & cards
└── tests/                          # 350+ unit, integration, and E2E test suites
```

---

## 4. Environment Setup & Dependency Installation

### Option A: Linux / WSL2 (Ubuntu 22.04 / 20.04) — Recommended Full Stack

From your WSL2 or Linux terminal:

#### 1. Install System Dependencies & Python 3.10
```bash
sudo apt-get update
sudo apt-get install -y python3.10 python3.10-venv python3.10-dev libgomp1 build-essential curl git
```

#### 2. Create and Activate Virtual Environment
```bash
cd /path/to/gridvision-final
python3.10 -m venv ~/.venvs/gridvision
source ~/.venvs/gridvision/bin/activate
python -m pip install --upgrade pip setuptools wheel
```

#### 3. Install All Project Dependencies Using Airflow Constraints
Use the included filter utility to extract the required dependency groups:
```bash
# For complete pipeline, Airflow, MLflow, and backend:
python scripts/filter_requirements.py requirements.txt /tmp/gridvision-all.txt \
  --groups backend airflow model-serving tests

pip install -r /tmp/gridvision-all.txt \
  --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-2.10.5/constraints-3.10.txt"
```

---

### Option B: Windows Native (PowerShell) — Backend, AI Assistant & Tests

*Note: Native Windows supports the Backend, Frontend, Residential AI Assistant, RAG Engine, and Test Suites. Airflow DAGs must run in WSL2, Docker, or Podman.*

#### 1. Install Python 3.10 (64-bit)
Verify Python 3.10 is installed and accessible:
```powershell
py -3.10 --version
# Output should be: Python 3.10.x
```

#### 2. Create and Activate Virtual Environment
```powershell
cd D:\Projects\gridvision-final
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
```

#### 3. Install Backend & Model-Serving Dependencies
```powershell
python scripts/filter_requirements.py requirements.txt requirements-win.txt --groups backend model-serving tests
pip install -r requirements-win.txt
```

---

## 5. Configuration & Environment Variables

### 1. Root `.env` (Docker & Automation Orchestration)
Create a `.env` file in the project root:
```bash
# Data and log mounts
GRIDVISION_DATA_DIR=/path/to/gridvision-final/data
GRIDVISION_LOG_DIR=/path/to/gridvision-final/logs

# Flask application signing key
SECRET_KEY=gridvision-insecure-dev-secret-key-change-in-production-min32chars

# Ports
GRIDVISION_FRONTEND_HOST_PORT=8082
GRIDVISION_BACKEND_HOST_PORT=5000
GRIDVISION_AIRFLOW_HOST_PORT=8081
GRIDVISION_MLFLOW_HOST_PORT=15001

# Providers
MODEL_PROVIDER=mlflow
DATA_PROVIDER=parquet
```

### 2. Backend `.env` (`ai/residential/backend/.env`)
Configure the Flask API server and the Residential Assistant:
```bash
FLASK_ENV=development
FLASK_DEBUG=1
HOST=127.0.0.1
PORT=5000
SECRET_KEY=gridvision-insecure-dev-secret-key-change-in-production-min32chars

# CORS allowed origins
CORS_ORIGINS=http://localhost:8082,http://127.0.0.1:8082,http://localhost:5173,http://127.0.0.1:5173

# Data & Model Providers ('sample' or 'parquet'; 'development' or 'mlflow')
DATA_PROVIDER=parquet
MODEL_PROVIDER=mlflow
MLFLOW_TRACKING_URI=http://127.0.0.1:15001
MLFLOW_MODEL_ALIAS=champion

# Residential Assistant LLM (Ollama)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3:8b
ASSISTANT_TEMPERATURE=0.2
ASSISTANT_MAX_TOKENS=800

# Security & Principal Resolution
DEVELOPMENT_AUTH_ENABLED=true
AUTHORIZED_RESIDENTIAL_METERS=METER-1000,METER-1001,METER-1002,METER-1003
CUSTOMER_TARIFF_INR_PER_KWH=10.0
```

### 3. Frontend `.env` (`frontend/.env`)
```bash
VITE_API_BASE_URL=http://localhost:5000/api/v1
VITE_MAP_TILE_URL=https://tile.openstreetmap.org/{z}/{x}/{y}.png
```

---

## 6. Source Data Preparation

GridVision requires the benchmark source dataset for training and ETL pipelines:

1. Create the `data/sample/` directory:
   ```bash
   mkdir -p data/sample
   ```
2. Place the raw 3.6 GB Parquet file into:
   ```text
   data/sample/training_sample_50000.parquet
   ```
3. For anomaly detection, place the synthetic dataset at:
   ```text
   data/anomaly_prediction/synthetic_2019_normal.parquet
   ```

*Note: The Medallion pipeline (`automation.py` or Airflow) will automatically generate the Bronze, Silver, Gold, and segmentation datasets from this raw sample.*

---

## 7. Execution Method 1: Automated Full Stack (`automation.py`)

Run this from **WSL2 (Ubuntu)** or a **Linux host** with Python 3.10 and Docker/Podman running.

### 1. Execute Full Orchestration
```bash
source ~/.venvs/gridvision/bin/activate
python automation.py
```

What `automation.py` executes in order:
1. Validates Python 3.10 environment and Docker/Podman availability.
2. Starts the persistent MLflow server container (`http://localhost:15001`).
3. Runs Customer Bill Medallion ETL (Bronze → Silver 100 sample → Gold).
4. Runs Government Grid Load ETL & builds `training_ready_2018.parquet`.
5. Runs Commercial Building Forecast ETL & Gold feature generation.
6. Runs Government Customer Behavioral Segmentation DAG.
7. Trains & evaluates candidate models; logs parameters, metrics, and models to MLflow; tags the champion model version with alias `champion`.
8. Starts the Airflow scheduler & webserver (`http://localhost:8081`).
9. Builds & deploys the Flask backend container (`http://localhost:5000`).
10. Builds & serves the React frontend container (`http://localhost:8082`).
11. Performs liveness & readiness health checks across all endpoints.

### 2. Fast Retrain / Reuse (Skip ETL)
If the Gold and Silver datasets have already been generated:
```bash
python automation.py --skip-all-data-pipelines
```

---

## 8. Execution Method 2: Multi-Container Stack (Docker / Podman Compose)

If data preparation has already completed or you want to launch the containerized services directly:

```bash
# 1. Ensure root .env exists
# 2. Build and start MLflow, Backend, and Frontend
docker compose up -d --build mlflow backend frontend

# Or using Podman:
podman compose up -d --build mlflow backend frontend
```

Check running containers:
```bash
docker compose ps
```

---

## 9. Execution Method 3: Component-by-Component Manual Execution

For active development, run individual components on host machines.

### 1. Running the Flask Backend Standalone
Make sure your Python 3.10 virtual environment is active:

**In PowerShell (Windows):**
```powershell
$env:PYTHONPATH="backend;.;tests"
python backend/run.py
```

**In Bash (Linux / WSL2):**
```bash
export PYTHONPATH="backend:.:tests"
python backend/run.py
```
*Backend runs on `http://127.0.0.1:5000`.*  
Verify health:
```bash
curl http://127.0.0.1:5000/api/v1/health
```

### 2. Running the React Frontend Standalone
Requires Node.js 20+:
```bash
cd frontend
npm install
npm run dev
```
*Frontend runs on `http://localhost:5173`.*

The frontend expects the backend at  by default;
set  if your backend uses another address.

### 3. Running MLflow Tracking Server Standalone
```bash
python -m mlflow server \
  --backend-store-uri sqlite:///data/mlflow/mlflow.db \
  --serve-artifacts \
  --artifacts-destination file:///data/mlflow/artifacts \
  --host 127.0.0.1 \
  --port 15001
```

### 4. Running Airflow Standalone (WSL2 / Linux Only)
```bash
export AIRFLOW_HOME=~/.gridvision-airflow
export AIRFLOW__CORE__DAGS_FOLDER="$(pwd)/airflow"
export AIRFLOW__CORE__LOAD_EXAMPLES=False
airflow db migrate
airflow standalone
```
*Credentials will be printed to terminal and logged in `standalone.log`.*

---

## 10. Training & Model Management Workflows

### 1. Customer Bill Prediction Model
Evaluates `HistGradientBoostingRegressor` vs. `MonthlyProjectionBaseline`:
```bash
python mlflow/customer/train_and_register.py \
  --data-path data/gold/customer_gold.parquet \
  --tracking-uri http://127.0.0.1:15001 \
  --model-name customer-bill-prediction \
  --alias champion
```

### 2. Commercial Building Forecast (LightGBM)
Fits 3 candidate models on 36-feature contract across 24 hourly horizons:
```bash
python mlflow/commercial/train_and_log.py
```
To pair commercial predictions with regional government grid demand:
```bash
python scripts/join_commercial_region_forecasts.py \
  --commercial data/gold/commercial_gold.parquet \
  --government data/airflow/government/training_ready_2018.parquet \
  --output data/gold/commercial_with_region_forecasts.parquet \
  --report logs/data/quality_reports/commercial/region_mapping.json
```

### 3. Government Grid Load Forecast
Trains hybrid model (original + log-target + persistence):
```bash
python mlflow/government/train_and_log.py \
  --input data/airflow/government/training_ready_2018.parquet
```

### 4. Customer Behavioral Segmentation CLI
```bash
python -m training.customer_segmentation.cli \
  --source data/bronze/training_sample_50000.parquet \
  --output-dir data/segmentation \
  --sample-fraction 0.1
```

### 5. Anomaly Detection Training & Localization
```bash
python training/anomaly_prediction/train.py
```

---

## 11. Residential Energy Assistant & Regulatory RAG

The residential assistant is a clean-architecture conversational AI subsystem:

### Key Technical Capabilities:
- **Server-Side Identity Isolation:** Enforces zero client trust. Validates `entity_id` against authenticated session meter mappings.
- **Regulatory Reference Engines (IS 732 & BEE Standards):** Calculates circuit sizing, maximum lighting power density (LPD $\le 10\text{ W/m}^2$), cooling degree hours, and 7-year TCO appliance payback.
- **Deterministic RAG Grounding:** Document retriever with parent-child chunking indexes regulatory standards, DISCOM MYT tariffs, and appliance guidelines into an in-memory vector/BM25 hybrid store.
- **Groq LLM Integration:** Uses `qwen/qwen3.8-27b` with retry resilience. When API limits or network timeouts occur, the system automatically transitions to a grounded deterministic mathematical fallback.

### Verification of Chatbot Endpoint:
```bash
curl -X POST http://127.0.0.1:5000/api/v1/assistant/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Why is my electricity bill higher this month?", "entity_id": "METER-1000"}'
```

---

## 12. Testing & Verification Suite

All unit, integration, boundary, and E2E tests are organized in `tests/`:

| Test Suite | Scope | Command |
|---|---|---|
| **E2E Reference & Isolation** | 203 opaque-box tests covering R1–R5, BEE/CEA data, SSRF protection, and zero-regression isolation | `python -m unittest discover -s tests/e2e_reference` |
| **Backend API Suite** | 89 tests covering all REST blueprints, error handlers, and Clean Architecture assistant | `python -m unittest discover -s tests/backend` |
| **Document Knowledge & RAG** | 154 tests verifying document extraction, SQLite persistence, and agentic RAG scenarios | `python -m unittest discover -s tests/reference && python -m unittest discover -s tests/rag` |
| **Anomaly Prediction Suite** | Event localization, GeoJSON export, and spatial triage tests | `python -m unittest discover -s tests/anomaly_prediction` |
| **ML & Training Suite** | Commercial forecast, customer bill, and MLflow tracking artifact tests | `python -m unittest discover -s tests/training` |

### Running the Entire Suite with Coverage:
```powershell
# PowerShell:
$env:PYTHONPATH="backend;.;tests"
pytest --maxfail=5 --durations=10
```

```bash
# Bash:
export PYTHONPATH="backend:.:tests"
pytest --maxfail=5 --durations=10
```

---

## 13. Service Endpoints & Health Check Reference

| Service | Host URL | Port | Health / Verification URL |
|---|---|---|---|
| **Frontend Application** | `http://localhost:8082` (Container) / `:5173` (Vite) | 8082 / 5173 | Visual Dashboard |
| **Flask REST Backend** | `http://localhost:5000` | 5000 | `/api/v1/health` |
| **Backend Model Catalog** | `http://localhost:5000` | 5000 | `/api/v1/models` |
| **Platform Telemetry** | `http://localhost:5000` | 5000 | `/api/v1/platform/health` |
| **Airflow Web UI** | `http://localhost:8081` | 8081 | `/health` |
| **MLflow Tracking UI** | `http://localhost:15001` | 15001 | `/health` |

---

## 14. Common Troubleshooting & Python 3.10 Diagnostics

### 1. `ImportError: cannot import name 'FallbackAsyncAdaptedQueuePool'`
- **Cause:** Running on Python 3.11+ where modern SQLAlchemy (>2.0.35) incompatible with MLflow 2.22.0 is installed.
- **Fix:** Switch your virtual environment to **Python 3.10** and reinstall requirements with the Airflow constraints file.

### 2. `libgomp.so.1: cannot open shared object file` (LightGBM Error)
- **Cause:** Missing OpenMP runtime library required by LightGBM on Linux/WSL2.
- **Fix:** `sudo apt-get install -y libgomp1`.

### 3. DuckDB Out-Of-Memory / Temp Spill Errors
- **Cause:** Scanning large Parquet datasets exceeds memory threshold on constrained environments.
- **Fix:** Configure `CUSTOMER_DUCKDB_MEMORY_LIMIT=2GB` and set `CUSTOMER_DUCKDB_TEMP_DIR` to a fast local disk (e.g. `~/.cache/gridvision/duckdb_temp`) rather than a network or slow mount.

### 4. Airflow Fails to Start on Windows
- **Cause:** Apache Airflow does not support Windows natively due to missing POSIX signal handlers (`SIGALRM`).
- **Fix:** Run Airflow inside WSL2 (Ubuntu) or use Docker Compose (`docker compose up -d airflow`).

### 5. Groq API Rate Limit or Timeout
- **Behavior:** The Residential Assistant automatically detects rate limits (HTTP 429) or timeouts, retries with exponential backoff, and if still unavailable, triggers the deterministic context fallback.
- **Fix:** Verify Ollama is running, `OLLAMA_BASE_URL` points to the Ollama server, and `OLLAMA_MODEL` is available. For Docker Compose, use `http://host.docker.internal:11434` to reach host Ollama.

---

The frontend expects the backend at `http://localhost:8082/api/v1` by default;
set `VITE_API_BASE_URL` if your backend uses another address.


## Generated Outputs from `automation.py`

Running the following command:

```bash
python automation.py
```

creates or updates generated data, model artifacts, reports, and logs within the project.

The exact set of outputs depends on:
- Whether individual pipelines are skipped.
- Whether existing outputs are already up to date.
- Whether custom path overrides are provided.

## 1. Main Data and Model Artifacts

The following outputs are generated in their default locations.

### Customer ETL

```text
data/
├── bronze/
├── silver/
│   └── customer_silver.parquet
└── gold/
    └── customer_gold.parquet
```

### Commercial ETL

```text
data/
├── silver/
│   └── commercial_silver.parquet
└── gold/
    └── commercial_gold.parquet
```

### Government Workflow

```text
data/
└── airflow/
    └── government/
        ├── prepared training data
        └── model artifact
```

Includes prepared training data and a trained model artifact.

### Customer Segmentation

**Feature dataset:**

```text
data/gold/customer_segmentation_features.parquet
```

**Generated outputs:**

```text
data/segmentation/
├── assignments
├── cluster profiles
├── summaries
└── source_sample.parquet
```

With the default sampling configuration, `source_sample.parquet` may also be generated.

### Segmentation Reports and Models

```text
docs/customer_segmentation/reports/
models/segmentation/
```

Contains generated segmentation reports and model files.

### Customer Model Export

```text
models/
├── customer_bill_prediction.pkl
└── customer_bill_prediction metadata sidecar
```

Contains the exported customer bill prediction model and its metadata sidecar.

### Dataset Manifests and Versioned Snapshots

```text
data/metadata/
```

Contains dataset manifests and versioned snapshots.

## 2. Logs and Runtime Records

Automation creates the following log directories:

```text
logs/
├── automation/
├── airflow/
├── data/
│   └── quality_reports/
├── training/
└── model_cards/
```

- **`logs/automation/`** – Contains a timestamped JSON summary for each automation run.
- **`logs/airflow/`** – Contains Airflow-related logs.
- **`logs/data/quality_reports/`** – Contains data quality reports.
- **`logs/training/`** – Contains training-related logs.
- **`logs/model_cards/`** – Contains model card records.

Airflow and training workflows may generate additional logs and reports.

## 3. MLflow Artifacts

MLflow stores its tracking database and run artifacts under:

```text
data/mlflow/
```

## 4. Input Data (Not Generated)

The source Parquet files under:

```text
data/sample/
```

are input datasets used by the pipelines. They are not normally created by `automation.py run`.

## 5. Non-Default Log Path

The following path:

```text
logs/segmentation/bronze_validation.log
```

is not a default output path referenced by the current `automation.py` implementation.

It may have been generated by another tool or through a different run configuration.

---

**Note:** All paths mentioned above represent default locations. Actual output locations may differ when custom path overrides are used.