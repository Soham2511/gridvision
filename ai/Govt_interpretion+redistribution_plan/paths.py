"""Central path configuration for the energy forecasting package.

Environment path overrides may be absolute or relative to ``PROJECT_ROOT``.
Set ``ENERGY_PROJECT_ROOT`` before starting Python to relocate the project root.
"""

from __future__ import annotations

import os
from pathlib import Path

AI_DIR = Path(__file__).resolve().parent


def project_root_from_environment(ai_dir: Path = AI_DIR) -> Path:
    """Resolve the repository root from this nested package or an explicit override."""
    default_root = (
        ai_dir.parent.parent
        if ai_dir.parent.name.lower() == "ai"
        else ai_dir.parent
    )
    root = Path(os.environ.get("ENERGY_PROJECT_ROOT", str(default_root))).expanduser()
    return root.resolve()


PROJECT_ROOT = project_root_from_environment()


def configured_path(environment_name: str, default: Path) -> Path:
    """Resolve an optional path override relative to the configured project root."""
    override = os.environ.get(environment_name, "").strip()
    path = Path(override).expanduser() if override else default
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


MODEL_PATH = configured_path(
    "ENERGY_MODEL_PATH",
    PROJECT_ROOT / "mlflow" / "government" / "hybrid_grid_2018.joblib",
)
FORECAST_DATA_PATH = configured_path(
    "ENERGY_FORECAST_DATA_PATH",
    PROJECT_ROOT
    / "data"
    / "airflow"
    / "government"
    / "gold_grid_forecasting_2018.parquet",
)
HISTORICAL_DATA_PATH = configured_path(
    "ENERGY_HISTORICAL_DATA_PATH",
    PROJECT_ROOT
    / "data"
    / "airflow"
    / "government"
    / "grid_level_energy.parquet",
)
SIMULATIONS_DIR = configured_path("ENERGY_SIMULATIONS_DIR", AI_DIR / "output")
NETWORK_PATH = configured_path(
    "ENERGY_NETWORK_PATH",
    AI_DIR / "data" / "grid_network.json",
)
ASSISTANT_OUTPUT_DIR = configured_path(
    "ENERGY_ASSISTANT_OUTPUT_DIR",
    AI_DIR / "assistant" / "output",
)
ASSISTANT_HISTORY_PATH = configured_path(
    "ENERGY_ASSISTANT_HISTORY_PATH",
    AI_DIR / "data" / "assistant_history.json",
)
ASSISTANT_LOG_PATH = configured_path(
    "ENERGY_ASSISTANT_LOG_PATH",
    AI_DIR / "logs" / "assistant.log",
)

GROQ_API_KEY_PATH = configured_path(
    "GROQ_API_KEY_FILE",
    PROJECT_ROOT / "Key_vault" / "Groq" / "api.key",
)
OPENROUTER_API_KEY_PATH = configured_path(
    "OPENROUTER_API_KEY_FILE",
    PROJECT_ROOT / "Key_vault" / "Openrouter" / "api.key",
)
OLLAMA_API_KEY_PATH = configured_path(
    "OLLAMA_API_KEY_FILE",
    PROJECT_ROOT / "Key_vault" / "ollama" / "api.key",
)
TAVILY_API_KEY_PATH = configured_path(
    "TAVILY_API_KEY_FILE",
    PROJECT_ROOT / "Key_vault" / "tavily" / "api.key",
)
LANGSMITH_API_KEY_PATH = configured_path(
    "LANGSMITH_API_KEY_FILE",
    PROJECT_ROOT / "Key_vault" / "langsmith" / "api.key",
)
