"""Configuration management for GridVision Flask backend."""

from __future__ import annotations

import os
from pathlib import Path

from report_generator.config import ReportGeneratorSettings


class BaseConfig:
    """Base application configuration."""

    PROJECT_ROOT = Path(__file__).resolve().parents[2]
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-gridvision-2026")
    API_PREFIX = "/api/v1"
    CORS_ORIGINS = [
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
        ).split(",")
        if origin.strip()
    ]
    # Runtime must fail closed. Sample/development providers are enabled only by
    # TestingConfig, never by an unset environment variable.
    DATA_PROVIDER = os.getenv("DATA_PROVIDER", "unavailable").strip().lower()
    MODEL_PROVIDER = os.getenv("MODEL_PROVIDER", "unavailable").strip().lower()
    APPROVED_DATA_SOURCES = tuple(
        value.strip()
        for value in os.getenv("APPROVED_DATA_SOURCES", "").split(",")
        if value.strip()
    )

    # AI infrastructure is inert by default. Paths remain unset until explicitly
    # configured; app startup never initializes local persistence or calls providers.
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

    # Generic JSON report generation remains disabled and provider-free unless
    # explicitly configured. Resolver must be supplied by the trusted host app.
    REPORT_GENERATOR_SETTINGS = ReportGeneratorSettings.from_env()
    REPORT_GENERATOR_IDENTITY_RESOLVER = (
        staticmethod(_default_report_identity) if AI_DEMO_MODE else None
    )

    # Optional customer bill prediction registry settings
    MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "")
    MLFLOW_MODEL_ALIAS = os.getenv("MLFLOW_MODEL_ALIAS", "champion")
    MLFLOW_MODEL_NAME = os.getenv(
        "MLFLOW_MODEL_NAME", "customer-bill-prediction"
    )
    MLFLOW_MODEL_ALIAS = os.getenv("MLFLOW_MODEL_ALIAS", "champion")
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
    AI_DEMO_MODE = os.getenv("AI_DEMO_MODE", "true").strip().lower() in {"1", "true", "yes"}
    REPORT_GENERATOR_SETTINGS = ReportGeneratorSettings.from_env(
        default_provider="ollama", default_enabled=True
    )
    REPORT_GENERATOR_IDENTITY_RESOLVER = staticmethod(
        BaseConfig._default_report_identity
    )
    # Enable only owner-approved sources with a verified existing serving path.
    # Forecast model inference remains separately controlled by MODEL_PROVIDER.
    APPROVED_DATA_SOURCES = tuple(
        value.strip()
        for value in os.getenv(
            "APPROVED_DATA_SOURCES",
            "customer_gold,customer_silver,commercial_silver,commercial_gold,government_2018,segmentation_2018,anomaly_synthetic_2019",
        ).split(",")
        if value.strip()
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
