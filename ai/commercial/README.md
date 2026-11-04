# Commercial multi-agent workflow

This package implements the Commercial multi-agent workflow and read-only
analysis API. It does not replace Residential functionality or the Airflow
commercial data pipeline.

## Current scope

- Typed request, assignment, evidence, result, and validation contracts.
- A bounded LangGraph supervisor workflow with conditional specialist routing,
  parallel independent specialists, aggregation, optional optimization,
  validation, one bounded rework round, and finalization.
- An injectable tool protocol. The Operations tool uses a persistent, local
  hybrid RAG index over the configured Commercial documents. Peak Prediction uses
  the existing Commercial building forecast API, its Gold dataset and
  registered MLflow model; it refuses development/demo model outputs.
- A centralized Pydantic-validated tool registry with per-tool trusted
  principal allowlists, bounded JSON inputs/outputs, and explicit unavailable
  responses for unintegrated providers.
- A local stdio MCP server exposing the registry's read-oriented Commercial
  tool contracts. It does not expose file paths, document uploads/indexing,
  database access, secrets, or equipment-control actions.
- Renewable tools that use Tavily for cited research and deterministic solar,
  wind, and battery calculators. Sizing and cost/savings estimates require
  explicit user inputs; no default factory measurements are invented.
- An optional local Ollama supervisor classifier using strict structured
  output. It only selects typed specialists; tool authorization remains
  enforced in application code.
- Docling performs layout-aware PDF and Office-document extraction; scanned-only
  PDF pages use bounded local OCR. Provenance chunking, Markdown/text support,
  and persistent SQLite
  indexing are implemented. The index contains
  SQLite FTS5 BM25 data, offline feature-hash vectors, topic links, and a typed
  Operations Context Graph. Conservative extraction identifies explicitly
  labeled factory records, production lines, operations, energy sources,
  targets, maintenance procedures, guidelines, equipment-register rows,
  dependencies, and directive constraints. Entities and relationships retain
  source/page/section/chunk provenance and extraction confidence. Asset-ID
  and up-to-two-hop Neo4j matches add cited passages to the hybrid candidate
  set; results are combined with reciprocal-rank fusion.
- The default vectorizer is deterministic and offline, but lexical rather than
  a pretrained semantic embedding model. FastEmbed is an optional adapter and
  must be installed with the `commercial-rag-vector` group and configured with
  a model already present in its local cache (`local_files_only` is enabled).
- SQLite is the default persistence layer. When configured, local Neo4j mirrors
  topic and typed context-graph nodes and relationships and handles bounded
  graph traversal. Extraction is deterministic and label/rule based; it does
  not claim complete semantic graph extraction or community summarization.
- The supplied OCR-input PDF is image-only. When local OCR dependencies or the
  Tesseract executable are missing, its pages remain explicitly unavailable;
  no OCR text or factory facts are fabricated.

Time-series observations remain outside the knowledge graph. Retrieved
documents and test fixtures are evidence only, never instructions that grant
tool access or override application policy.

The default document list and allowed document root are configured in
`CommercialSettings`. They can be overridden using `COMMERCIAL_RAG_DOCUMENTS`
and `COMMERCIAL_RAG_ALLOWED_ROOT`; list paths use the platform path separator.
Ingestion enforces the configured roots, supported document formats, size,
page/character bounds, conversion timeout, and PDF encryption policy.
Authenticated demo uploads accept PDF, Markdown, TXT, DOCX, PPTX, XLSX, HTML,
and CSV up to 25 MB. They are stored under the persistent local RAG data
directory, indexed immediately, and searched alongside the fixed demo corpus.
Uploaded text is evidence, not instructions. The UI holds demo credentials in
memory only and sends them to the loopback API using Basic Auth.
The local index stores content hashes, extraction method, source/page/section
provenance, synthetic-source status, FTS5 terms, vectors, and heuristic topic
edges. Unchanged files are skipped; use `--force` to re-extract them, such as
after installing OCR. The index lives at
`data/commercial/rag/index.sqlite3` by default and is local-only.

The supplied handbook and automotive-parts corpus are explicitly synthetic
demonstration material, not factory records. The only configured demo scope is
`automotive-parts-demo`; this is not authenticated customer tenancy. The query
planner refuses broad prompts that do not identify a
supported topic and returns `QUERY_NEEDS_CLARIFICATION`. Factory-specific
questions return `DATA_NOT_AVAILABLE` unless matching factory records are
configured. A no-match result never invents measurements, savings, or
recommendations.

## Run the local RAG pipeline

From the repository root, Install the Commercial RAG dependencies and index the configured
PDF/Markdown sources:

```powershell
python scripts/filter_requirements.py requirements.txt "$env:TEMP\gridvision-commercial.txt" --groups commercial-agent commercial-rag-docling commercial-rag-ocr
python -m pip install -r "$env:TEMP\gridvision-commercial.txt"
python -m ai.commercial.rag index
```

Inspect the local index or run a question through hybrid retrieval:

```powershell
python -m ai.commercial.rag status
python -m ai.commercial.rag query "How can compressed air leaks be reduced?"
```

The index command reports per-document extraction status without printing
document contents. To refresh after replacing a PDF or installing OCR:

```powershell
python -m ai.commercial.rag index --force
```

## Run the Commercial MCP server

Install the optional MCP SDK together with the Commercial agent, Docling, OCR,
and optimizer dependencies, then run the server from the repository root:

```powershell
python scripts/filter_requirements.py requirements.txt "$env:TEMP\gridvision-commercial-mcp.txt" --groups commercial-agent commercial-mcp commercial-rag-docling commercial-rag-ocr commercial-optimizer
python -m pip install -r "$env:TEMP\gridvision-commercial-mcp.txt"
python -m ai.commercial.mcp_server
```

The server uses stdio and opens no network listener. Its available tool
contracts and agent capabilities are documented in
[`Skills.md`](./Skills.md). Peak forecast calls return structured unavailability
when the trained-model provider is not ready. The optimizer uses the optional
OR-Tools CP-SAT solver and requires an explicit validated schedule. Renewable
scenarios use the configured Tavily API key for web research and always label
estimate assumptions. Peak forecasting requires the backend API and a valid
Commercial `building_id`; it never treats a `factory_id` as a building ID or
presents the backend's development model as a trained forecast. The
Operations tool searches only the fixed synthetic automotive-parts demo corpus.
The workflow endpoint requires the single demo account in `.env` and rejects
other factory IDs, but this lightweight Basic Auth gate is not production
authentication or customer tenant isolation. Compose publishes the backend
only on loopback; do not expose this demo over an untrusted network or use it
to protect customer records.

The frontend master agent calls `/commercial/workflow`, `/commercial/session`,
and the authenticated `/commercial/rag/documents` endpoints; it does not use
the legacy `/assistant/chat` endpoint. The supervisor uses local Ollama by
default: `qwen3:8b` classifies requests, with `gemma3:4b` as a fallback if the
primary request fails. Neither model receives tool permissions; the workflow
validates specialist assignments and enforces tool allowlists in application
code. The two models must be pulled into the WSL Ollama installation:

```bash
ollama pull qwen3:8b
ollama pull gemma3:4b
```

In `.env`, set `OLLAMA_HOST_BASE_URL` to the URL reachable from WSL (default
`http://127.0.0.1:11434`) and `COMMERCIAL_OLLAMA_BASE_URL` to the URL reachable
from the backend container (default `http://host.docker.internal:11434`).
If Docker cannot reach the WSL Ollama listener, configure Ollama to listen on
an interface accessible to Docker and set the latter URL accordingly.
`COMMERCIAL_OLLAMA_TIMEOUT_SECONDS` bounds each model request. The automation
preflight verifies Ollama is running and both configured model tags are
installed before starting the longer ETL/training workflow; it does not
download model weights automatically. Set `COMMERCIAL_LLM_PROVIDER=mock` only
to use deterministic routing without Ollama.

The forecast API adapter is loopback-only by default and has a bounded timeout
and response size. Configure `COMMERCIAL_FORECAST_API_BASE_URL` and
`COMMERCIAL_FORECAST_API_TIMEOUT_SECONDS` only for a trusted local backend.
The backend must use the trained MLflow Commercial provider, have the
configured `commercial_gold.parquet` dataset, and resolve the
`gridvision-commercial-building-forecast` alias. Forecast results are labeled
as historical Gold dataset replays, not live telemetry. The registered
`commercial_buildings_list` MCP tool returns available building IDs; select an
ID and pass it to `peak_forecast`. The current serving API exposes a bounded
sample of up to 100 dataset buildings; these IDs are not factory IDs or a
tenant registry.

Each Commercial assistant response includes a local LangGraph execution trace
in the chat UI. Expand **LangGraph orchestration** to see completed, warning,
and failed nodes with elapsed time; node exceptions include the failed step and
safe error type. This is per-request UI instrumentation and does not use
LangSmith.

Docling is installed through the `commercial-rag-docling` requirements group
and is included in the backend Docker image. Scanned-only pages use optional
local OCR: install the `commercial-rag-ocr` group and Tesseract; the backend
image includes the OCR engine. Docling's layout/table artifacts may require a
one-time local cache download; conversion itself uses local CPU processing and
does not call a remote document service. The application discovers Tesseract
on `PATH` or in the usual Windows Program Files and per-user install
directories; set `COMMERCIAL_TESSERACT_CMD` to override discovery. To install the optional
FastEmbed adapter, install the
`commercial-rag-vector` group and set
`COMMERCIAL_RAG_EMBEDDING_PROVIDER=fastembed`; the model must already be cached
locally. To enable the optional Neo4j graph mirror, install the
`commercial-rag-neo4j` group, run a local Neo4j instance, and configure
`COMMERCIAL_RAG_GRAPH_BACKEND=neo4j`, `COMMERCIAL_NEO4J_URI`,
`COMMERCIAL_NEO4J_USERNAME`, `COMMERCIAL_NEO4J_PASSWORD`, and optionally
`COMMERCIAL_NEO4J_DATABASE`. Only `bolt://localhost`/`neo4j://localhost` and
loopback IP endpoints are accepted; credentials are read from environment
variables and are not written to the index. If OCR or the embedding model is
unavailable, the pipeline reports the failure and does not silently substitute
remote services.
The retriever maps a specific natural-language question to relevant handbook
topics and a focused search query. Broad prompts such as "Check factory
operations" do not identify a handbook topic; they return
`QUERY_NEEDS_CLARIFICATION` with supported topics rather than arbitrary
passages.

## Run tests

From the repository root, run:

```powershell
python -m pytest tests/commercial
```

## Workflow limits

`CommercialSettings` bounds graph supersteps, tool calls, and rework rounds.
`build_commercial_graph` injects tools and settings so tests can exercise
workflow behavior without API keys or external services.

The default provider is local Ollama. Tests can inject deterministic tools and
select `COMMERCIAL_LLM_PROVIDER=mock`; Ollama failures are reported explicitly
after the configured Qwen/Gemma attempts and never silently switch to mock
planning.

The renewable tool reads `TAVILY_API_KEY` from the process environment or the
local `key_vault/tavily/api.key` file. In Docker Compose, that local file is
mounted read-only at `/run/secrets/tavily_api_key`; it is never copied into the
backend image.

Invalid requests and unexpected tool exceptions are surfaced rather than
converted to successful mock responses.

## Backend workflow API

The workflow is available at `POST /api/v1/commercial/workflow` and requires
HTTP Basic credentials from the ignored local `.env` file. Copy
`.env.example` if you do not already have a `.env`, then set a unique
`DEMO_PASSWORD` and the demo user ID before starting the backend or Compose.
Do not overwrite other existing `.env` settings or reuse this demo password
elsewhere.
Requests accept `user_goal`, optional `request_id`, optional `factory_id` (if
supplied, it must be `automotive-parts-demo`), and validated
`optimization_inputs`. `building_id` is rejected because no commercial
building forecast is mapped to this synthetic automotive demo.

When a feasible schedule is produced, the response includes an immutable
`schedule_proposal` with a pending status and proposal hash. Review the result,
then record an approval or rejection using
`POST /api/v1/commercial/schedules/<proposal_id>/approval`. This endpoint only
records a local demo-user decision; approval does not execute or send commands
to equipment. Real equipment integration still requires a vendor interface,
site safety interlocks, authorization roles, and operational commissioning.

Install the solver group when optimization is needed:

```powershell
python scripts/filter_requirements.py requirements.txt "$env:TEMP\gridvision-commercial-optimize.txt" --groups commercial-agent commercial-optimizer
python -m pip install -r "$env:TEMP\gridvision-commercial-optimize.txt"
```

Provide a complete schedule explicitly; the optimizer does not infer a job
list, tariff, or factory constraints from prose. This example reads credentials
from the ignored `.env` file without printing them:

```powershell
$body = @{
  user_goal = "Optimize the supplied production schedule."
  optimization_inputs = @{
    horizon_hours = 3
    prices_inr_per_kwh = @(10, 2, 8)
    jobs = @(@{
      job_id = "batch-1"
      machine_id = "press-1"
      power_kw = 10
      duration_hours = 1
      deadline_hour = 3
    })
    maintenance_windows = @(@{
      machine_id = "press-1"
      start_hour = 0
      end_hour = 1
    })
    battery = @{
      capacity_kwh = 20
      initial_soc_kwh = 10
      min_soc_kwh = 2
      terminal_soc_kwh = 10
      max_charge_kw = 5
      max_discharge_kw = 5
      charge_efficiency = 0.9
      discharge_efficiency = 0.9
    }
  }
} | ConvertTo-Json -Depth 8
$demo = @{}
Get-Content .env | ForEach-Object {
  if ($_ -match '^(DEMO_USER_ID|DEMO_PASSWORD)=(.*)$') {
    $null = $demo[$matches[1]] = $matches[2]
  }
}
$pair = "$($demo.DEMO_USER_ID):$($demo.DEMO_PASSWORD)"
$authorization = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($pair))
$headers = @{ Authorization = "Basic $authorization" }
$result = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:5000/api/v1/commercial/workflow" -Headers $headers -ContentType "application/json" -Body $body
$result.data.schedule_proposal
$approval = @{ decision = "approved"; note = "Reviewed demo proposal." } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:5000/api/v1/commercial/schedules/$($result.data.schedule_proposal.proposal_id)/approval" -Headers $headers -ContentType "application/json" -Body $approval
```

The CP-SAT solver enforces job windows, precedence, single-job machine
capacity, machine maintenance windows, optional grid demand limits, and
optional battery state-of-charge, charge/discharge power, efficiency, and
terminal SOC constraints. It calculates schedule cost from supplied hourly
rates and job power. Savings are returned only when a complete, feasible
baseline schedule is supplied. The local approval ledger records an
acknowledgment only; it is not an equipment-control integration.

## Tracing and evaluation

Structured logs record request, workflow-node, and tool-call IDs/statuses,
durations, and counters; prompts, evidence text, tool arguments, and
credentials are not logged. LangGraph can use LangSmith tracing when the
`commercial-tracing` group is installed and `LANGSMITH_TRACING=true` plus
`LANGSMITH_API_KEY` are configured. Without tracing credentials, local
structured logs remain available. Model cost is reported as unknown unless a
tracing provider supplies usage and billing data.

`ai.commercial.evaluation.evaluate_cases` runs annotated requests through both
a sequential single-agent baseline and the multi-agent workflow using the
same provider fixtures. It reports completion, specialist-selection
precision/recall, evidence support, expected-source retrieval, tool success,
conflict expectations, schedule feasibility, recovery, loop bounds, latency,
and model cost when available. Expected labels must come from reviewed
evaluation data; the repository does not fabricate a production benchmark.
