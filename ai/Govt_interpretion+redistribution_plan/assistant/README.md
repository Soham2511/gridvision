# Energy data and redistribution assistant

This assistant answers questions from redistribution-plan JSON files, analyzes
historical and model-predicted 2018 demand, and can retrieve cited external
references through Tavily. Python performs data filtering, calculations, CSV
generation, and plots; the assistant does not retrain or modify the saved
forecast model or the redistribution pipeline.

For the complete package folder map, data/model files required outside this
directory, copy-to-another-project instructions, and path override table, see
the [main AI package guide](../README.md). Default paths are centralized in
[`paths.py`](../paths.py); set environment overrides before starting Python.

Install the visualization dependency and start the interactive CLI from the
workspace root:

```bash
.venv/bin/python -m pip install -r ai/requirements.txt
.venv/bin/python -m ai.assistant
```

The default provider is local Ollama. Start Ollama first and keep its local
server running. The assistant checks that the configured models are downloaded:

```bash
ollama serve
ollama list
```

By default, the query interpreter uses `qwen3:8b` and the response generator
uses `batiai/gemma4-e2b:q4`. Both run locally; prompts are sent only to
`http://127.0.0.1:11434`, not an external provider. If needed, install the
query model with `ollama pull qwen3:8b`. To override the models, use
`--query-model`/`--response-model` or set `OLLAMA_QUERY_MODEL` and
`OLLAMA_RESPONSE_MODEL`. Local model loading and inference can be slower than
hosted APIs, so Ollama requests default to a 180-second timeout. Set
`OLLAMA_TIMEOUT_SECONDS` to a different positive number of seconds if needed.

One-shot example:

```bash
.venv/bin/python -m ai.assistant \
  --query "Show the next 3 hours of redistribution for grid 64"
```

Use `--provider groq` or `--provider openrouter` to select a hosted provider.
The Ollama key at `Key_vault/ollama/api.key` is not needed for local models;
it is used only if `OLLAMA_HOST` is explicitly configured as a remote HTTPS
Ollama endpoint.

The default Groq key file is `Key_vault/Groq/api.key`. Alternatively set
`GROQ_API_KEY`. The query model defaults to `openai/gpt-oss-120b`; the separate
response model defaults to `openai/gpt-oss-20b`. Each model ID is checked
against the authenticated provider model list before use. Override the IDs
with `ENERGY_QUERY_MODEL` and `ENERGY_RESPONSE_MODEL`. Groq free/developer
access and rate limits are account-dependent.

OpenRouter is also supported with its OpenAI-compatible API. Its default key
file is `Key_vault/Openrouter/api.key`. To use it, choose `--provider
openrouter`; model IDs can be set with `--query-model` and `--response-model`,
or `OPENROUTER_QUERY_MODEL` and `OPENROUTER_RESPONSE_MODEL`:

```bash
.venv/bin/python -m ai.assistant --provider openrouter \
  --query-model "openai/gpt-oss-120b" \
  --response-model "openai/gpt-oss-20b" \
  --query "Show the redistribution plan for 2018-09-25 at 2018-09-25T00:00:00"
```

The configured models are checked against the OpenRouter model list. Model
availability and account access can vary; choose IDs available to your
OpenRouter account. `OPENROUTER_API_KEY` overrides the key file when set.

HTTPS certificate verification stays enabled. If Python reports
`CERTIFICATE_VERIFY_FAILED` on macOS, first install/update the certificates for
the Python distribution used by `.venv` (for python.org Python, run its
`Install Certificates.command` in `/Applications/Python 3.x/`). If your
network uses a trusted corporate HTTPS inspection certificate, point
`ENERGY_ASSISTANT_CA_BUNDLE` to the organization's PEM CA bundle; this adds
that CA to Python's default trusted roots:

```bash
export ENERGY_ASSISTANT_CA_BUNDLE="/path/to/organization-ca.pem"
.venv/bin/python -m ai.assistant
```

Do not disable TLS certificate verification. Never use an untrusted CA file.

The default interactive history file is
`ai/data/assistant_history.json`. It keeps four recent turns and the last
successful request window and generated artifact paths. Follow-ups such as
"show the next two hours", "what about Grid 64?", and "make it simpler" reuse
the prior date/grid/time context when unambiguous. "Regenerate the last image"
reuses the exact forecast date, timestamps, and grid filter. Standard plan
queries generate PNG and CSV files; historical, prediction, and accuracy
analysis defaults to concise text. Artifact-only requests generate only the
requested file. Outputs are written to `ai/assistant/output/` by default.
Options include `--provider`,
`--query-model`, `--response-model`, `--simulations-dir`, `--artifacts-dir`,
and `--history`.

All internal calculations, date/grid validation, transfer filtering, CSV
generation, and visualization are performed locally. Only the user's question
and a compact set of relevant Python-calculated records are sent to the
configured LLM provider; the full simulation JSON is not sent. For an explicit
web-research request, Tavily receives the search query and returned source
snippets are supplied to the LLM for a qualitative summary; citations are
rendered from the returned source URLs. Do not put secrets or personal
information in questions.

## Historical and predicted demand

The internal energy dataset contains 2018 observations only. Ask for a date or
date range, for example:

```text
Summarize historical demand for Grid 64 from 2018-09-01 to 2018-09-30.
Show the model-predicted demand for Grid 64 on 2018-09-25.
Compare historical and predicted demand for Grid 64 on 2018-09-25.
```

Historical reports use `grid_level_energy.parquet` and clearly label observed
dataset values. Model-predicted reports reuse `hybrid_grid_2018.joblib` and
the existing saved feature/routing pipeline, forecast one 2018 calendar day
(24 intervals) at a time, and cache new day forecasts below
`ai/assistant/output/predictions/`. A target date is predicted from the prior
day's 23:00 feature origin; if those saved features are unavailable, the
assistant reports that rather than substituting another date. Historical
versus predicted comparisons use only timestamps present in both sources,
because historical coverage can omit hours. Reports disclose missing hours,
matched grid/timestamp pairs, and incomplete coverage. Accuracy includes
network and per-grid MAE, RMSE, MAPE, and WAPE; MAPE excludes zero-actual rows,
and WAPE is the primary percentage metric. Specific-grid reports and artifacts
contain only the selected grids. Explicitly multipart requests can combine
historical analysis, a saved-model forecast, and an actual-versus-predicted
comparison for one date; Python performs each calculation independently.

If a requested 2018 redistribution date has no saved plan, the assistant
reuses cached model predictions when available and sends the validated forecast
to the existing redistribution pipeline. The generated plan is saved for later
queries. A date-only plan request covers the full day; hour-specific requests
keep their exact window. No dates or hours are silently substituted.
Slash dates such as `5/3/2018` are interpreted as month/day/year when both
components could be months, matching the assistant's English-language date
convention; an unambiguous day-first date such as `13/3/2018` is also accepted.

These queries do not create or alter synthetic supply, connections, transfers,
or losses. Those remain available only through the redistribution-plan flow.
The historical data is separate from the model's future demand output.

## External research and optional tracing

For external facts, explicitly ask for web research. Tavily is contacted only
for those requests. Set `TAVILY_API_KEY` or store the key in
`Key_vault/tavily/api.key`; alternatively set `TAVILY_API_KEY_FILE`. Search
errors are sanitized and results include title, excerpt, and source URL.
External snippets are treated as untrusted text and are not represented as
internal energy measurements.

LangSmith tracing is optional and disabled by default. To enable it, install
`ai/requirements-observability.txt` with
`.venv/bin/python -m pip install -r ai/requirements-observability.txt`, set
`LANGSMITH_TRACING=true` and either `LANGSMITH_API_KEY` or
`LANGSMITH_API_KEY_FILE` (defaults to `Key_vault/langsmith/api.key`), then
start a new assistant process. The key file is read only when tracing is
enabled. Trace payloads include question length and completion/artifact status
only; query text, numerical analysis, source content, and generated response
text are redacted. LangChain is not required because the existing deterministic
Python router and provider adapters provide the needed orchestration without
an additional runtime layer.

See [ARCHITECTURE.md](./ARCHITECTURE.md) for the architecture, data flow,
trust boundaries, request schema, time resolution, model choices, and output
details. The assistant describes supply, network, transfer, and loss values
as synthetic assumptions, not actual power infrastructure or measurements.

The [AI documentation index](../docs/README.md) links the architecture,
[16 runnable example questions](../docs/QUERY_EXAMPLES.md), and the
[provider/model integration contract](../docs/PROVIDER_INTEGRATION.md).

For technical “how can this grid's demand problem be reduced?” questions, name
the grid and forecast hour. Python checks only its direct neighbors' remaining
synthetic surplus and unused edge capacity, then suggests feasible transfers
in lowest-loss order. Any remaining deficit is reported. This describes
technical feasibility only, not economic benefit or real-world operation.

The assistant distinguishes network-wide results from selected-grid results.
Grid-specific balance totals contain only the named grid(s); their directly
connected synthetic neighbors appear only where needed for connection context
and plotting. Queries that explicitly request only an image or CSV generate
only that artifact and skip response generation. Full-day summaries aggregate
the selected forecast day's available intervals; ambiguous grid/date/hour
references trigger clarification instead of using model guesses.

The rotating local log defaults to `ai/logs/assistant.log` (2 MB per file and
three backups). Override it with `--log-file` or `--log-level`; the level can
also be set through `ENERGY_ASSISTANT_LOG_LEVEL`. Logs contain event metadata,
not questions, simulation values, API keys, or credentials.

Run isolated tests without provider API calls:

```bash
.venv/bin/python -m pytest ai/test -q
```
