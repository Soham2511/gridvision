"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from pathlib import Path
from report_generator.config import ReportGeneratorSettings

try:
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
except ImportError:
    pass


class BaseConfig:
    """Base application configuration."""

    PROJECT_ROOT = Path(__file__).resolve().parents[2]
    ASSISTANT_ALLOW_UNAUTHENTICATED_GOVERNMENT = False
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
    DATA_PROVIDER = os.getenv("DATA_PROVIDER", "sample").strip().lower()
    MODEL_PROVIDER = os.getenv("MODEL_PROVIDER", "development").strip().lower()
    APPROVED_DATA_SOURCES = tuple(
        value.strip()
        for value in os.getenv("APPROVED_DATA_SOURCES", "").split(",")
        if value.strip()
    )

    # AI infrastructure settings
    AI_ENABLED = os.getenv("AI_ENABLED", "false").strip().lower() in {"1", "true", "yes"}
    AI_DEMO_MODE = os.getenv("AI_DEMO_MODE", "false").strip().lower() in {"1", "true", "yes"}
    AI_GENERATION_PROVIDER = os.getenv("AI_GENERATION_PROVIDER", "none").strip().lower()
    AI_EMBEDDING_PROVIDER = os.getenv("AI_EMBEDDING_PROVIDER", "none").strip().lower()
    AI_TIMEOUT_SECONDS = float(os.getenv("AI_TIMEOUT_SECONDS", "20"))
    AI_MAX_RETRIES = int(os.getenv("AI_MAX_RETRIES", "1"))
    AI_MAX_OUTPUT_CHARS = int(os.getenv("AI_MAX_OUTPUT_CHARS", "5000"))
    AI_DATABASE_PATH = os.getenv(
        "AI_DATABASE_PATH", str(PROJECT_ROOT / "instance" / "gridvision_app.sqlite")
    )
    AI_PRIVATE_STORAGE_ROOT = os.getenv(
        "AI_PRIVATE_STORAGE_ROOT", str(PROJECT_ROOT / "instance" / "ai_private")
    )
    REPORT_EMAIL_DEFAULT_RECIPIENT = os.getenv(
        "REPORT_EMAIL_DEFAULT_RECIPIENT", "kanak.nagar64@gmail.com"
    )
    REPORT_EMAIL_SMTP_HOST = os.getenv("REPORT_EMAIL_SMTP_HOST", "")
    REPORT_EMAIL_SMTP_PORT = int(os.getenv("REPORT_EMAIL_SMTP_PORT", "587"))
    REPORT_EMAIL_SMTP_USERNAME = os.getenv("REPORT_EMAIL_SMTP_USERNAME", "")
    REPORT_EMAIL_SMTP_PASSWORD = os.getenv("REPORT_EMAIL_SMTP_PASSWORD", "")
    REPORT_EMAIL_FROM_ADDRESS = os.getenv("REPORT_EMAIL_FROM_ADDRESS", "")
    AI_ALLOWED_SOURCE_DOMAINS = tuple(
        value.strip().lower()
        for value in os.getenv("AI_ALLOWED_SOURCE_DOMAINS", "").split(",")
        if value.strip()
    )

    @staticmethod
    def _default_report_identity(req) -> str:
        return req.headers.get("X-User-Identity") or getattr(req, "remote_addr", None) or "gridvision-demo-user"

    REPORT_GENERATOR_SETTINGS = ReportGeneratorSettings.from_env()
    REPORT_GENERATOR_IDENTITY_RESOLVER = (
        staticmethod(_default_report_identity) if AI_DEMO_MODE else None
    )

    # LLM Assistant Settings (Ollama Active Runtime)
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL") or (
        "http://ollama:11434"
        if os.getenv("CONTAINERIZED", "false").lower() == "true" or os.path.exists("/.dockerenv")
        else "http://localhost:11434"
    )
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b")

    # Residential assistant Groq settings; other personas keep their own providers.
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
    GROQ_API_KEY_2 = os.getenv("GROQ_API_KEY_2", "")
    GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
    GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
    RESIDENTIAL_GROQ_FALLBACK_MODELS = tuple(
        dict.fromkeys(
            model.strip()
            for model in os.getenv(
                "RESIDENTIAL_GROQ_FALLBACK_MODELS",
                "openai/gpt-oss-20b,qwen/qwen3.8-27b,openai/gpt-oss-120b,"
                "allam-2-7b,meta-llama/llama-prompt-guard-2-22m,"
                "meta-llama/llama-prompt-guard-2-86m",
            ).split(",")
            if model.strip()
        )
    )
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
    GOVERNMENT_MLFLOW_MODEL_NAME = os.getenv(
        "GOVERNMENT_MLFLOW_MODEL_NAME", "gridvision-government-load-forecast"
    )
    COMMERCIAL_MLFLOW_MODEL_ALIAS = os.getenv(
        "COMMERCIAL_MLFLOW_MODEL_ALIAS", MLFLOW_MODEL_ALIAS
    )
    GOVERNMENT_MLFLOW_MODEL_ALIAS = os.getenv(
        "GOVERNMENT_MLFLOW_MODEL_ALIAS", MLFLOW_MODEL_ALIAS
    )

    # Domain Data & Model Artifact Paths
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
    CUSTOMER_SILVER_DATASET_PATH = Path(
        os.getenv(
            "CUSTOMER_SILVER_DATASET_PATH",
            PROJECT_ROOT / "data" / "silver" / "customer_silver.parquet",
        )
    )
    CUSTOMER_SILVER_METADATA_PATH = Path(
        os.getenv(
            "CUSTOMER_SILVER_METADATA_PATH",
            PROJECT_ROOT / "data" / "metadata" / "dataset_versions" / "customer_silver" / "latest.json",
        )
    )
    COMMERCIAL_SILVER_DATASET_PATH = Path(
        os.getenv(
            "COMMERCIAL_SILVER_DATASET_PATH",
            PROJECT_ROOT / "data" / "silver" / "commercial_silver.parquet",
        )
    )
    COMMERCIAL_SILVER_METADATA_PATH = Path(
        os.getenv(
            "COMMERCIAL_SILVER_METADATA_PATH",
            PROJECT_ROOT / "data" / "metadata" / "commercial" / "dataset_versions" / "silver" / "latest.json",
        )
    )
    CUSTOMER_MODEL_METADATA_PATH = Path(
        os.getenv(
            "CUSTOMER_MODEL_METADATA_PATH",
            PROJECT_ROOT
            / "models"
            / "customer_bill_prediction"
            / "metadata.json",
        )
    )
    CUSTOMER_MODEL_ARTIFACT_PATH = Path(
        os.getenv(
            "CUSTOMER_MODEL_ARTIFACT_PATH",
            PROJECT_ROOT
            / "models"
            / "customer_bill_prediction"
            / "customer_bill_pipeline.joblib",
        )
    )
    CUSTOMER_MODEL_RUNS_PATH = Path(
        os.getenv(
            "CUSTOMER_MODEL_RUNS_PATH",
            PROJECT_ROOT / "reports" / "customer_model_runs",
        )
    )
    COMMERCIAL_FORECAST_DATA_PATH = Path(
        os.getenv("COMMERCIAL_FORECAST_DATA_PATH", PROJECT_ROOT / "data" / "gold" / "commercial_gold.parquet")
    )
    COMMERCIAL_GOLD_METADATA_PATH = Path(
        os.getenv(
            "COMMERCIAL_GOLD_METADATA_PATH",
            PROJECT_ROOT / "data" / "metadata" / "commercial" / "dataset_versions" / "gold" / "latest.json",
        )
    )
    COMMERCIAL_FORECAST_MODEL_PATH = Path(
        os.getenv("COMMERCIAL_FORECAST_MODEL_PATH", PROJECT_ROOT / "models" / "commercial" / "building_forecast.joblib")
    )
    GOVERNMENT_FORECAST_DATA_PATH = Path(
        os.getenv(
            "GOVERNMENT_FORECAST_DATA_PATH",
            (
                PROJECT_ROOT / "data" / "airflow" / "government" / "training_ready_2018.parquet"
                if (PROJECT_ROOT / "data" / "airflow" / "government" / "training_ready_2018.parquet").exists()
                else PROJECT_ROOT / "data" / "airflow" / "government" / "features.parquet"
            ),
        )
    )
    GOVERNMENT_FORECAST_MODEL_PATH = Path(
        os.getenv(
            "GOVERNMENT_FORECAST_MODEL_PATH",
            (
                PROJECT_ROOT / "data" / "airflow" / "government" / "hybrid_grid_2018.joblib"
                if (PROJECT_ROOT / "data" / "airflow" / "government" / "hybrid_grid_2018.joblib").exists()
                else PROJECT_ROOT / "models" / "government" / "hybrid_model.joblib"
            ),
        )
    )
    SEGMENTATION_OUTPUT_DIR = Path(
        os.getenv(
            "SEGMENTATION_OUTPUT_DIR",
            PROJECT_ROOT / "data" / "segmentation",
        )
    )
    SEGMENTATION_REPORTS_DIR = Path(
        os.getenv(
            "SEGMENTATION_REPORTS_DIR",
            PROJECT_ROOT / "reports" / "segmentation",
        )
    )
    SEGMENTATION_API_MAX_PAGE_SIZE = int(
        os.getenv("SEGMENTATION_API_MAX_PAGE_SIZE", "200")
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


class DevelopmentConfig(BaseConfig):
    """Development configuration."""

    DEBUG = True
    TESTING = False
    AI_DEMO_MODE = os.getenv("AI_DEMO_MODE", "true").strip().lower() in {"1", "true", "yes"}
    REPORT_GENERATOR_SETTINGS = ReportGeneratorSettings.from_env(
        default_provider="ollama", default_enabled=True
    )
    REPORT_GENERATOR_IDENTITY_RESOLVER = staticmethod(
        BaseConfig._default_report_identity
    )
    APPROVED_DATA_SOURCES = tuple(
        value.strip()
        for value in os.getenv(
            "APPROVED_DATA_SOURCES",
            "customer_gold,customer_silver,commercial_silver,commercial_gold,government_2018,segmentation_2018,anomaly_synthetic_2019",
        ).split(",")
        if value.strip()
    )
    ASSISTANT_ALLOW_UNAUTHENTICATED_GOVERNMENT = (
        os.getenv("GRIDVISION_ALLOW_UNAUTHENTICATED_GOVERNMENT_ASSISTANT", "")
        .strip()
        .lower()
        in {"1", "true", "yes", "on"}
    )


class TestingConfig(BaseConfig):
    """Testing configuration with deterministic behaviors."""

    DEBUG = False
    TESTING = True
    AI_DEMO_MODE = True
    SECRET_KEY = "test-secret-key-deterministic"
    DATA_PROVIDER = "sample"
    MODEL_PROVIDER = "development"
    APPROVED_DATA_SOURCES = (
        "customer_gold",
        "customer_silver",
        "commercial_silver",
        "commercial_gold",
        "government_2018",
        "segmentation_2018",
        "anomaly_synthetic_2019",
    )


class ProductionConfig(BaseConfig):
    """Production configuration."""

    DEBUG = False
    TESTING = False
    DEVELOPMENT_AUTH_ENABLED = (
        os.getenv("DEVELOPMENT_AUTH_ENABLED", "false").lower() == "true"
        or os.getenv("AI_DEMO_MODE", "true").lower() == "true"
    )
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
