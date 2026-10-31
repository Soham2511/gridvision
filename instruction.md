# GridVision: Clone and Run Instructions

This guide starts from a fresh Git clone. The application source is in Git, but
the source Parquet dataset and generated pipeline/model outputs are not. Supply
the source file before running the full workflow.

## Prerequisites

- Windows 10/11 with WSL2 and an Ubuntu distribution, or a supported Linux host.
- Python 3.10 in WSL/Linux. Airflow is not supported on native Windows.
- Docker Desktop with WSL integration enabled for the Ubuntu distribution, and
  Docker Compose available inside that distribution.
- Git. Node.js 20 is only needed if you run the frontend outside Docker.

## 1. Clone the repository

In PowerShell, clone the GitHub repository and enter its directory. Substitute
the repository URL and destination you use:

```powershell
git clone https://github.com/Soham2511/gridvision.git gridvision_2
cd gridvision_2
```

For WSL, open the same checkout through its mounted Windows drive. For example,
if it is at `D:\Ps_Capstone_project\gridvision_2`:

```bash
cd /mnt/d/Ps_Capstone_project/gridvision_2
```

Use the actual drive and folder you chose; commands below assume the terminal is
at the repository root.

## 2. Supply the source data

Create this folder in the checkout and copy the source file into it:

```text
data/
└── sample/
    └── training_sample_50000.parquet
```

The source Parquet file is required by the customer, commercial, and government
pipelines and is intentionally excluded from Git. Obtain it from the project
data owner or the approved dataset source. Keep the filename above, or set
`GRIDVISION_SOURCE_PATH` to its actual path before running `automation.py`.

You do not need to manually create the other data directories for a fresh full
run. Automation and the pipelines create Bronze, Silver, Gold, government
training-ready data, manifests, and reports. Previously generated data and
model artifacts can be reused only if you copy them into the same relative
locations and retain their matching quality manifests.

## 3. Prepare WSL/Linux Python dependencies

From the repository root in WSL/Linux:

```bash
python3.10 -m venv ~/.venvs/gridvision
source ~/.venvs/gridvision/bin/activate
python scripts/filter_requirements.py requirements.txt /tmp/gridvision-requirements.txt \
  --groups airflow model-serving
pip install -r /tmp/gridvision-requirements.txt \
  --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-2.10.5/constraints-3.10.txt"
```

The constraints file keeps Airflow's pinned dependencies compatible. Do not
install the separate `backend` dependency group into this environment; the
backend is built in Docker with its own dependency set.

Check Docker connectivity from the same WSL distribution:

```bash
docker --version
docker compose version
```

If `docker compose` is unavailable, enable Docker Desktop WSL integration for
that distribution or install the Compose plugin before continuing.

### If starting Docker Compose directly

`automation.py` sets the Compose variables for its own run. If you start the
services with `docker compose` yourself, create a root `.env` file first so
Compose knows where the data directory is and the backend has a private signing
key. From the repository root in WSL/Linux, run:

```bash
printf 'GRIDVISION_DATA_DIR=%s/data\nSECRET_KEY=%s\n' "$PWD" "$(openssl rand -hex 32)" > .env
```

The `.env` file is git-ignored. Keep the `SECRET_KEY` private and retain it
between restarts. Then start the services with:

```bash
docker compose up -d --build
```

## 4. Run the complete setup

With the source file in place and the WSL environment active:

```bash
python automation.py
```

The first full run prepares all persona datasets, trains and registers the
models, and builds/starts MLflow, Airflow, the backend, and frontend. Data
preparation and training can take a while. The script prints the service URLs
and a timed summary when it finishes.

If all persona datasets have already been prepared and their latest quality
manifests are present, you can skip ETL and retrain/register the models:

```bash
python automation.py --skip-all-data-pipelines
```

This option does not create missing data. For partial reuse, see
`python automation.py --help` and the pipeline guides under `airflow/` and
`mlflow/`.

## 5. Open the application

- Frontend: <http://localhost:8082>
- Backend health: <http://localhost:5000/api/v1/health>
- MLflow: <http://localhost:15001>
- Airflow: <http://localhost:8081>

Airflow's generated login details are in the `standalone.log` under the
configured `AIRFLOW_HOME` (by default `~/.gridvision-airflow/logs/standalone.log`
when automation runs in WSL).

## 6. Stop the services

Stop Docker services from the repository root:

```bash
docker compose down
```

Automation starts Airflow as a separate process. Stop it using the PID file
next to `standalone.log`; on WSL with the default Airflow home:

```bash
kill -TERM -- -$(cat ~/.gridvision-airflow/logs/standalone.pid)
```

## Optional: run the frontend in development mode

To run Vite on the host instead of the Compose frontend container, install
Node.js 20 and run:

```bash
cd frontend
npm ci
npm run dev
```

The frontend expects the backend at `http://localhost:8082/api/v1` by default;
set `VITE_API_BASE_URL` if your backend uses another address.
