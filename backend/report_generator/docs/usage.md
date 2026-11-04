# Setup and usage

## Configuration

Development configuration defaults to the locally installed Ollama model
`gemma3:1b` at `http://127.0.0.1:11434`. Other environments keep report
generation disabled unless explicitly configured. Override the development
defaults as needed:

```dotenv
GRIDVISION_REPORT_GENERATOR_ENABLED=true
GRIDVISION_REPORT_LLM_PROVIDER=ollama
GRIDVISION_REPORT_LLM_MODEL=gemma3:1b
GRIDVISION_REPORT_LLM_BASE_URL=http://127.0.0.1:11434/api/chat
GRIDVISION_REPORT_LLM_TIMEOUT_SECONDS=30
GRIDVISION_REPORT_MAX_PROVIDER_RETRIES=1
```

Ollama requires no API key. Check installed models with `ollama list`; pull a
model with `ollama pull <model>` if it is missing. Start the service with
`ollama serve` when it is not already running. The default model above is
installed in the current GridVision development environment.

For Hugging Face use
`GRIDVISION_REPORT_LLM_PROVIDER=huggingface`; provide
`GRIDVISION_REPORT_LLM_MODEL` and `GRIDVISION_REPORT_LLM_API_KEY` (or `HF_TOKEN`).
`GRIDVISION_REPORT_LLM_BASE_URL` can override the OpenAI-compatible API root
(the `/chat/completions` route is appended) or provide the full endpoint; it
must use HTTPS and support JSON response mode. Hosted defaults to the OpenAI Chat Completions URL; Hugging Face
defaults to its compatible router URL. Never commit credentials.

The host must also inject a trusted callable using Flask config key
`REPORT_GENERATOR_IDENTITY_RESOLVER`. Its argument is the current Flask request;
it must return a stable authenticated principal string or `None`. The report
API returns 401 until a trusted resolver is configured.

For a local UI smoke test only, `scripts/run_report_generator_local.py` provides
a fixed test identity and binds strictly to `127.0.0.1`. It refuses to start
unless `GRIDVISION_REPORT_LOCAL_DEV_AUTH=true` is set. Do not use this runner in
production or expose it on a network interface.

Input defaults: 1 MB request, nesting depth 32, 50,000 JSON values, individual
strings up to 100,000 characters, and instructions up to 4,000 characters.
Prepared provider prompts are limited to 1,500,000 characters by default.
All limits can be adjusted within bounded ranges using `GRIDVISION_REPORT_*`
settings. PDF support uses the optional `report-generator` dependency group.

## Install and run

The full backend Docker build installs the report-generator dependency group.
For a local environment, install selected requirements with:

```bash
python scripts/filter_requirements.py requirements.txt /tmp/gridvision-report.txt --groups backend model-serving report-generator
pip install -r /tmp/gridvision-report.txt
python backend/run.py
```

The endpoints are available under `http://127.0.0.1:5000/api/v1/report-generator`.
The generic report-generator endpoints still require a trusted identity callback.

## Test in the frontend

From the repository root, start the local report backend in one terminal:

```bash
export GRIDVISION_REPORT_GENERATOR_ENABLED=true
export GRIDVISION_REPORT_LLM_PROVIDER=ollama
export GRIDVISION_REPORT_LLM_MODEL=gemma3:1b
export GRIDVISION_REPORT_LOCAL_DEV_AUTH=true
python3.10 scripts/run_report_generator_local.py
```

In a second terminal, start the Vite frontend:

```bash
cd frontend
npm ci
npm run dev
```

Open `http://localhost:5173`, select a persona, then open **JSON Report
Generator** in the sidebar. Keep the sample JSON or replace it, enter optional
instructions, choose whether to include PDF, and click **Generate report**.
When generation completes, use **Open HTML** or **Open PDF**. The page's
readiness panel should show the service enabled, provider configured, and
identity configured. With Ollama, report input is sent to the local Ollama
service. Hosted providers receive report input under their respective data
handling policies.

### Email a generated monthly report

The Reports and Notifications pages follow the household or building selected
in **Building Profile**. Household reports retrieve that entity's Silver
OBJECTID history; commercial reports use the selected Silver OBJECTID and its
latest month in `commercial_silver.parquet`. Saved reports,
notifications, downloads, and email actions stay scoped to the selected entity.

On the **Reports** page, click **Email report** on a generated report. The
backend sends the selected entity's report as a PDF attachment when available,
otherwise as HTML, to the same configured recipient for every entity. Delivery
is opt-in per report. Configure an SMTP submission server before using the
button:

```dotenv
REPORT_EMAIL_DEFAULT_RECIPIENT=kanak.nagar64@gmail.com
REPORT_EMAIL_SMTP_HOST=smtp.example.com
REPORT_EMAIL_SMTP_PORT=587
REPORT_EMAIL_SMTP_USERNAME=your-smtp-username
REPORT_EMAIL_SMTP_PASSWORD=your-smtp-password
REPORT_EMAIL_FROM_ADDRESS=reports@example.com
```

Set these in the backend process environment and restart the backend. Use an
SMTP provider's app password or SMTP credential, and keep it out of source
control. Without the SMTP host and sender address, the API returns
`EMAIL_NOT_CONFIGURED` and the page shows the delivery error.

## Test

```bash
python -m pytest tests/backend/test_report_generator_foundation.py tests/backend/test_report_generator_pipeline.py tests/backend/test_report_generator_api.py
```

Unit and API tests use a deterministic fake provider. They do not call an
external model.
