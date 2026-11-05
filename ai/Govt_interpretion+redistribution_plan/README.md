# Energy forecasting and redistribution package

This is the main guide for the `ai/` package. It documents what the package
does, how its files fit together, which files must sit beside it, how to move
it to another project, and where to configure paths.

The package forecasts hourly demand for 53 grids using the existing hybrid
model, optionally builds a synthetic supply scenario and direct-neighbor
redistribution plan, and provides an LLM assistant for plan and 2018 energy
analysis questions. It does not retrain or modify the model artifact.
Synthetic supply, connections, transfer limits, and losses are illustrative
assumptions, not actual measurements or electricity infrastructure.

## Quick start

Run commands from the **project root**, the directory containing the `ai/`
folder. Use the Python environment that has the dependencies from
[`requirements.txt`](./requirements.txt) installed.

Generate the next day's full 24-hour plan from a date-only origin:

```bash
python -m ai --origin 2018-09-24
```

Ask the assistant about a plan or historical/model-prediction data:

```bash
python -m ai.assistant --query \
  "Show the redistribution plan for 2018-09-25 at 2018-09-25T00:00:00"
python -m ai.assistant --query \
  "Compare historical and predicted demand for Grid 64 on 2018-09-25"
```

The default LLM provider is local Ollama. Start Ollama and make sure the
configured query and response models are available before running assistant
requests. See [assistant setup](./assistant/README.md) for providers,
environment variables, and conversation examples.

Check the package tests from the project root:

```bash
python -m pytest ai/test -q
```

## Folder map

```text
ai/
├── __init__.py, __main__.py       Forecast/redistribution CLI entry point
├── paths.py                       Central default and environment path config
├── redistribution.py              Saved-model forecast and synthetic planning
├── requirements.txt               Core Python dependencies
├── requirements-observability.txt Optional LangSmith tracing dependency
├── assistant/
│   ├── __main__.py                 Assistant CLI entry point
│   ├── assistant.py                Intent routing, orchestration, response flow
│   ├── analysis.py                 Historical/prediction data and accuracy metrics
│   ├── data.py                     Plan loading, filtering, and summaries
│   ├── providers.py                Ollama/Groq/OpenRouter adapters
│   ├── render.py                   Plan CSV and image generation
│   ├── tavily.py                   Optional external search
│   ├── schemas.py                  Validated request/intent schema
│   ├── README.md                   Assistant operation and usage
│   └── ARCHITECTURE.md             Assistant design and data flow
├── data/                           Local history and persisted synthetic networks
├── docs/                           Query examples and provider notes
├── key/                            Optional local credentials; never copy/share
├── logs/                           Assistant log output
├── output/                         Generated redistribution plans
└── test/                           Regression tests for the package
```

The assistant also writes analysis caches and generated CSV/images under
`ai/assistant/output/`. Runtime state and generated outputs are separate from
the Python source and can be relocated with the environment variables below.
Do not treat files under `data/`, `logs/`, `output/`, `assistant/output/`, or
`key/` as source code required to import the package.

## Required files outside `ai/`

The default paths follow this repository's Airflow government pipeline:

```text
project-root/
├── ai/Govt_interpretion+redistribution_plan/
├── data/
│   ├── sample/training_sample_50000.parquet
│   └── airflow/government/
│       ├── gold_grid_forecasting_2018.parquet
│       ├── grid_level_energy.parquet
│       └── training_ready_2018.parquet
├── mlflow/government/hybrid_grid_2018.joblib
└── Key_vault/
    ├── Groq/api.key
    ├── Openrouter/api.key
    ├── ollama/api.key
    ├── tavily/api.key
    └── langsmith/api.key
```

| File | Needed for | Notes |
|---|---|---|
| `mlflow/government/hybrid_grid_2018.joblib` | Forecasts and new redistribution plans | Existing trained hybrid model; keep it unchanged. |
| `data/airflow/government/gold_grid_forecasting_2018.parquet` | Forecasts and new redistribution plans | Airflow-generated forecast features and grid metadata. Required feature and origin rows must exist. |
| `data/airflow/government/grid_level_energy.parquet` | Historical analysis and actual-versus-predicted accuracy | Airflow-generated historical grid series. Not required for plan-only use. |
| `data/sample/training_sample_50000.parquet` | Airflow preparation/training input | Raw building-level source; the assistant reads the generated gold/history files, not this raw file directly. |

Copying only the assistant package does **not** copy these data/model assets.
Forecast generation needs the model and Airflow-generated forecast-feature
parquet; historical analysis additionally needs the generated historical
parquet. The raw source is used by Airflow to produce those files.

## Moving `ai/` into another project

1. Copy the complete `ai/` source folder into the destination project. Keep
   package files and subfolders together; run the module from the directory
   containing `ai/`.
2. Provide the required model and parquet files using the layout above, or set
   the environment variables in the next section. Use absolute paths if the
   files live elsewhere.
3. Install dependencies into the destination project's Python environment:

   ```bash
   python -m pip install -r ai/requirements.txt
   ```

4. Configure optional providers through environment variables. Do not copy
   API-key files into source control. Provider key-file paths can be set with
   their `*_API_KEY_FILE` variables; alternatively use the provider's
   environment key.
5. From the destination project root, run `python -m ai --origin ...` or
   `python -m ai.assistant --query ...`, then run `python -m pytest ai/test -q`.

The package root defaults to the parent of the copied `ai/` directory. Set
`ENERGY_PROJECT_ROOT` **before starting Python** if the data/model root differs.
Relative path overrides in the table below are resolved against that root;
absolute overrides are used as supplied. The package keeps current default
locations when no override is set.

In assistant questions, slash dates with a year use month/day/year when both
leading values could be months (`5/3/2018` means May 3); an unambiguous
day-first date such as `13/3/2018` is accepted as well. ISO dates
(`2018-05-03`) avoid ambiguity and are recommended for scripts.

| Environment variable | Default path | Used for |
|---|---|---|
| `ENERGY_PROJECT_ROOT` | Repository root containing `ai/`, `data/`, and `mlflow/` | Root for default model/data/key paths and relative overrides. |
| `ENERGY_MODEL_PATH` | `<project-root>/mlflow/government/hybrid_grid_2018.joblib` | Saved hybrid model artifact. |
| `ENERGY_FORECAST_DATA_PATH` | `<project-root>/data/airflow/government/gold_grid_forecasting_2018.parquet` | Airflow-generated saved forecast features. |
| `ENERGY_HISTORICAL_DATA_PATH` | `<project-root>/data/airflow/government/grid_level_energy.parquet` | Airflow-generated historical observations. |
| `ENERGY_SIMULATIONS_DIR` | `<package>/output` | Generated/read redistribution plan JSON. |
| `ENERGY_NETWORK_PATH` | `<package>/data/grid_network.json` | Persisted synthetic network; keep the same file to preserve edges. |
| `ENERGY_ASSISTANT_OUTPUT_DIR` | `<package>/assistant/output` | Assistant CSV/images and cached prediction parquet files. |
| `ENERGY_ASSISTANT_HISTORY_PATH` | `<package>/data/assistant_history.json` | Conversation context and generated-file history. |
| `ENERGY_ASSISTANT_LOG_PATH` | `<package>/logs/assistant.log` | Assistant log file. |

Optional credential files also have path overrides. Leave key files out of the
copied package and source control; prefer the provider's environment key where
possible.

| Environment variable | Default key-file path | Provider |
|---|---|---|
| `GROQ_API_KEY_FILE` | `<project-root>/Key_vault/Groq/api.key` | Groq |
| `OPENROUTER_API_KEY_FILE` | `<project-root>/Key_vault/Openrouter/api.key` | OpenRouter |
| `OLLAMA_API_KEY_FILE` | `<project-root>/Key_vault/ollama/api.key` | Remote Ollama only |
| `TAVILY_API_KEY_FILE` | `<project-root>/Key_vault/tavily/api.key` | Tavily web search |
| `LANGSMITH_API_KEY_FILE` | `<project-root>/Key_vault/langsmith/api.key` | Optional tracing |

Use the corresponding environment key (`GROQ_API_KEY`,
`OPENROUTER_API_KEY`, `OLLAMA_API_KEY`, `TAVILY_API_KEY`, or `LANGSMITH_API_KEY`)
instead of a key file when possible. Government-assistant tracing is scoped by
`GOVT_ASSISTANT_LANGSMITH_TRACING=true` and uses the
`GridVision-Government-Assistant` project by default. Tavily is contacted only
for explicit web-research requests.

Example setup for this repository (Airflow must produce the gold and history
Parquet files before the assistant can create uncached forecasts):

```bash
export ENERGY_PROJECT_ROOT="/Users/sidgupta8/Desktop/Grid_vision/gridvision"
export ENERGY_MODEL_PATH="$ENERGY_PROJECT_ROOT/mlflow/government/hybrid_grid_2018.joblib"
export ENERGY_FORECAST_DATA_PATH="$ENERGY_PROJECT_ROOT/data/airflow/government/gold_grid_forecasting_2018.parquet"
export ENERGY_HISTORICAL_DATA_PATH="$ENERGY_PROJECT_ROOT/data/airflow/government/grid_level_energy.parquet"
python -m ai --origin 2018-09-24
```

The paths module is the only place to change the default layout in future.
If the package is integrated with a new application, first set its project root
and data/output environment paths; code changes should not be needed when the
files still follow the documented interfaces.

## Generated files and persistence

- Redistribution plans: `ai/output/redistribution_plan_<date>.json`.
- Persisted default network: `ai/data/grid_network.json`.
- Assistant context: `ai/data/assistant_history.json`.
- Assistant logs: `ai/logs/assistant.log`.
- Analysis cache and assistant CSV/images: `ai/assistant/output/`.

The network file is persistent by design. Reuse it to keep synthetic
connections fixed. To intentionally create a new scenario, set
`ENERGY_NETWORK_PATH` or use the redistribution CLI's `--network` option to
choose a different file. Existing simulation plans and assistant history are
runtime state; copy them only when that state should follow the package.

The default `.gitignore` in this folder excludes credentials stored under
`ai/key/`, Python caches, logs, generated outputs, and local assistant history.
Key files under a project-root `Key_vault/` are outside this folder and must
be ignored by that project's own version-control rules. Keep generated files
outside version control unless there is a specific reason to check in a
fixture or sample.

## Relevant files by change type

| If you need to change... | Start with... | Also check... |
|---|---|---|
| Default project/data/output locations | [`paths.py`](./paths.py) | This file's path table and path tests. |
| Forecast features, model routing, or redistribution math | [`redistribution.py`](./redistribution.py) | [`test_redistribution.py`](./test/test_redistribution.py), model artifact contract. |
| Historical coverage or forecast accuracy metrics | [`analysis.py`](./assistant/analysis.py) | [`test_analysis.py`](./test/test_analysis.py), query examples. |
| User intent, follow-ups, response/action routing | [`assistant.py`](./assistant/assistant.py) | [`schemas.py`](./assistant/schemas.py), [`test_analysis.py`](./test/test_analysis.py), [`test_assistant.py`](./test/test_assistant.py). |
| Reading/filtering plans or computing plan summaries | [`data.py`](./assistant/data.py) | [`test_assistant.py`](./test/test_assistant.py). |
| Provider behavior or credentials | [`providers.py`](./assistant/providers.py) | [`PROVIDER_INTEGRATION.md`](./docs/PROVIDER_INTEGRATION.md), [`test_assistant.py`](./test/test_assistant.py). |
| CSV/image output | [`render.py`](./assistant/render.py) | [`test_assistant.py`](./test/test_assistant.py), output path config. |
| Assistant workflow/design | [`ARCHITECTURE.md`](./assistant/ARCHITECTURE.md) | [`QUERY_EXAMPLES.md`](./docs/QUERY_EXAMPLES.md). |

For assistant-specific usage and provider setup, continue to
[`assistant/README.md`](./assistant/README.md). For query patterns, see
[`docs/QUERY_EXAMPLES.md`](./docs/QUERY_EXAMPLES.md); for provider contracts,
see [`docs/PROVIDER_INTEGRATION.md`](./docs/PROVIDER_INTEGRATION.md).
