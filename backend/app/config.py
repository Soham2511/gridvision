"""Configuration management for GridVision Flask backend."""

from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

# Automatically load environment variables from ai/residential/backend/.env or root .env
load_dotenv(
    Path(__file__).resolve().parents[2]
    / "ai"
    / "residential"
    / "backend"
    / ".env"
)
load_dotenv(Path(__file__).resolve().parents[2] / ".env")
load_dotenv()


class BaseConfig:
    """Base application configuration."""

    PROJECT_ROOT = Path(__file__).resolve().parents[2]
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-gridvision-2026")
    API_PREFIX = "/api/v1"
    TESTING: bool = False

    # Centralized Initial Residential OBJECTID Mapping (Single Source of Truth)
    INITIAL_RESIDENTIAL_OBJECTID = os.getenv("INITIAL_RESIDENTIAL_OBJECTID", "2254213")

    # Centralized Authentication & JWT / Session Settings
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", os.getenv("SECRET_KEY", "dev-secret-key-gridvision-2026"))
    JWT_ACCESS_TOKEN_EXPIRES_SECONDS = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES_SECONDS", "3600"))
    JWT_REFRESH_TOKEN_EXPIRES_DAYS = int(os.getenv("JWT_REFRESH_TOKEN_EXPIRES_DAYS", "14"))
    AUTH_COOKIE_NAME = os.getenv("AUTH_COOKIE_NAME", "gv_refresh_token")
    AUTH_COOKIE_SECURE = os.getenv("AUTH_COOKIE_SECURE", "false").lower() == "true"
    AUTH_COOKIE_SAMESITE = os.getenv("AUTH_COOKIE_SAMESITE", "Lax")
    CORS_ORIGINS = [
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8082,http://127.0.0.1:8082"
        ).split(",")
        if origin.strip()
    ]
    DATA_PROVIDER = os.getenv("DATA_PROVIDER", "parquet")
    MODEL_PROVIDER = os.getenv("MODEL_PROVIDER", "development")

    # LLM Assistant Settings (Ollama Active Runtime)
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL") or (
        "http://ollama:11434"
        if os.getenv("CONTAINERIZED", "false").lower() == "true" or os.path.exists("/.dockerenv")
        else "http://localhost:11434"
    )
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b")

    # Inactive Groq Settings (Retained for manual switch-back)
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
    GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
    GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
    ASSISTANT_TEMPERATURE = float(os.getenv("ASSISTANT_TEMPERATURE", "0.2"))
    ASSISTANT_MAX_TOKENS = int(os.getenv("ASSISTANT_MAX_TOKENS", "800"))
    ASSISTANT_TIMEOUT_SECONDS = float(os.getenv("ASSISTANT_TIMEOUT_SECONDS", "60.0"))
    ASSISTANT_COMPLEX_TIMEOUT_SECONDS = float(os.getenv("ASSISTANT_COMPLEX_TIMEOUT_SECONDS", "75.0"))
    ASSISTANT_MAX_RETRIES = int(os.getenv("ASSISTANT_MAX_RETRIES", "0"))

    # Server-side authorized residential meters based on real OBJECTIDs
    AUTHORIZED_RESIDENTIAL_METERS = [
        m.strip()
        for m in os.getenv(
            "AUTHORIZED_RESIDENTIAL_METERS",
            "METER-2254213,METER-293861,METER-537421,METER-679900,2254213,293861,537421,679900,METER-1000,METER-1001,METER-1002,METER-1003",
        ).split(",")
        if m.strip()
    ]
    DEVELOPMENT_AUTH_ENABLED = os.getenv("DEVELOPMENT_AUTH_ENABLED", "true").lower() == "true"
    DEV_USER_METER_MAPPING = {
        # Primary OBJECTID-based accounts
        "2254213": ["2254213", "METER-2254213", "1000", "METER-1000"],
        "293861": ["293861", "METER-293861", "1001", "METER-1001"],
        "537421": ["537421", "METER-537421", "1002", "METER-1002"],
        "679900": ["679900", "METER-679900", "1003", "METER-1003"],
        # Username aliases
        "OBJECTID 2254213": ["2254213", "METER-2254213", "1000", "METER-1000"],
        "OBJECTID 293861": ["293861", "METER-293861", "1001", "METER-1001"],
        "OBJECTID 537421": ["537421", "METER-537421", "1002", "METER-1002"],
        "OBJECTID 679900": ["679900", "METER-679900", "1003", "METER-1003"],
        "usr-resident-2254213": ["2254213", "METER-2254213", "1000", "METER-1000"],
        "usr-resident-293861": ["293861", "METER-293861", "1001", "METER-1001"],
        "usr-resident-537421": ["537421", "METER-537421", "1002", "METER-1002"],
        "usr-resident-679900": ["679900", "METER-679900", "1003", "METER-1003"],
        # Backward-compatibility aliases
        "usr-resident-1000": ["METER-1000", "1000", "2254213", "METER-2254213"],
        "usr-resident-1001": ["METER-1001", "1001", "293861", "METER-293861"],
        "usr-resident-1002": ["METER-1002", "1002", "537421", "METER-537421"],
        "usr-resident-1003": ["METER-1003", "1003", "679900", "METER-679900"],
        "1000": ["METER-1000", "1000", "2254213", "METER-2254213"],
    }
    DEV_DEFAULT_USER = "2254213"

    # Model Registries & MLflow Settings
    MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "")
    MLFLOW_MODEL_ALIAS = os.getenv("MLFLOW_MODEL_ALIAS", "champion")
    MLFLOW_MODEL_NAME = os.getenv(
        "MLFLOW_MODEL_NAME", "customer-bill-prediction"
    )
    COMMERCIAL_MLFLOW_MODEL_NAME = os.getenv(
        "COMMERCIAL_MLFLOW_MODEL_NAME", "gridvision-commercial-building-forecast"
    )
    COMMERCIAL_MLFLOW_MODEL_ALIAS = os.getenv(
        "COMMERCIAL_MLFLOW_MODEL_ALIAS", MLFLOW_MODEL_ALIAS
    )
    GOVERNMENT_MLFLOW_MODEL_NAME = os.getenv(
        "GOVERNMENT_MLFLOW_MODEL_NAME", "gridvision-government-load-forecast"
    )
    GOVERNMENT_MLFLOW_MODEL_ALIAS = os.getenv(
        "GOVERNMENT_MLFLOW_MODEL_ALIAS", MLFLOW_MODEL_ALIAS
    )
    CUSTOMER_TARIFF_INR_PER_KWH = float(
        os.getenv("CUSTOMER_TARIFF_INR_PER_KWH", "10.0")
    )
    CUSTOMER_CARE_PHONE = os.getenv("CUSTOMER_CARE_PHONE", None)
    CUSTOMER_GOLD_DATASET_PATH = Path(
        os.getenv(
            "CUSTOMER_GOLD_DATASET_PATH",
            PROJECT_ROOT / "data" / "gold" / "customer_gold.parquet",
        )
    )
    CUSTOMER_MODEL_METADATA_PATH = Path(
        os.getenv(
            "CUSTOMER_MODEL_METADATA_PATH",
            PROJECT_ROOT / "models" / "customer_bill_prediction.metadata.json",
        )
    )
    CUSTOMER_MODEL_ARTIFACT_PATH = Path(
        os.getenv(
            "CUSTOMER_MODEL_ARTIFACT_PATH",
            PROJECT_ROOT / "models" / "customer_bill_prediction.pkl",
        )
    )
    ANOMALY_DATASET_PATH = Path(
        os.getenv(
            "ANOMALY_DATASET_PATH",
            PROJECT_ROOT / "data" / "anomaly_prediction" / "synthetic_2019_normal.parquet",
        )
    )
    ANOMALY_MODEL_PATH = Path(
        os.getenv(
            "ANOMALY_MODEL_PATH",
            PROJECT_ROOT / "models" / "anomaly_prediction" / "gridvision_anomaly_model.joblib",
        )
    )
    ANOMALY_RUNS_PATH = Path(
        os.getenv(
            "ANOMALY_RUNS_PATH",
            PROJECT_ROOT / "reports" / "anomaly_prediction" / "application_runs",
        )
    )
    COMMERCIAL_FORECAST_DATA_PATH = Path(
        os.getenv("COMMERCIAL_FORECAST_DATA_PATH", PROJECT_ROOT / "data" / "gold" / "commercial_gold.parquet")
    )
    COMMERCIAL_FORECAST_MODEL_PATH = Path(
        os.getenv("COMMERCIAL_FORECAST_MODEL_PATH", PROJECT_ROOT / "models" / "commercial" / "building_forecast.joblib")
    )
    GOVERNMENT_FORECAST_DATA_PATH = Path(
        os.getenv("GOVERNMENT_FORECAST_DATA_PATH", PROJECT_ROOT / "data" / "airflow" / "government" / "training_ready_2018.parquet")
    )
    GOVERNMENT_FORECAST_MODEL_PATH = Path(
        os.getenv("GOVERNMENT_FORECAST_MODEL_PATH", PROJECT_ROOT / "data" / "airflow" / "government" / "hybrid_grid_2018.joblib")
    )
    SEGMENTATION_OUTPUT_DIR = Path(
        os.getenv(
            "SEGMENTATION_OUTPUT_DIR",
            PROJECT_ROOT / "data" / "segmentation",
        )
    )
    SEGMENTATION_FEATURE_PATH = Path(
        os.getenv(
            "SEGMENTATION_FEATURE_PATH",
            PROJECT_ROOT / "data" / "gold" / "customer_segmentation_features.parquet",
        )
    )
    SEGMENTATION_MODEL_DIR = Path(
        os.getenv("SEGMENTATION_MODEL_DIR", PROJECT_ROOT / "models" / "segmentation")
    )
    SEGMENTATION_REPORTS_DIR = Path(
        os.getenv(
            "SEGMENTATION_REPORTS_DIR",
            PROJECT_ROOT / "docs" / "customer_segmentation" / "reports",
        )
    )
    SEGMENTATION_API_MAX_PAGE_SIZE = int(
        os.getenv("SEGMENTATION_API_MAX_PAGE_SIZE", "200")
    )


class DevelopmentConfig(BaseConfig):
    """Development environment configuration."""

    DEBUG = True
    TESTING = False


class TestingConfig(BaseConfig):
    """Testing configuration with deterministic behaviors."""

    DEBUG = False
    TESTING = True
    SECRET_KEY = "test-secret-key-deterministic"
    DATA_PROVIDER = "sample"
    MODEL_PROVIDER = "development"


class ProductionConfig(BaseConfig):
    """Production configuration."""

    DEBUG = False
    TESTING = False
    DEVELOPMENT_AUTH_ENABLED = False
    SECRET_KEY = os.getenv("SECRET_KEY")

    def __init__(self) -> None:
        if not self.SECRET_KEY:
            raise ValueError("SECRET_KEY must be set in production.")


CONFIG_MAP = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(env_name: str | None = None) -> type[BaseConfig]:
    """Retrieve configuration class by environment name."""
    env = env_name or os.getenv("FLASK_ENV", "development").lower()
    return CONFIG_MAP.get(env, DevelopmentConfig)