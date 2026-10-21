"""Configuration management for GridVision Flask backend."""

from __future__ import annotations

import os
from pathlib import Path


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
    DATA_PROVIDER = os.getenv("DATA_PROVIDER", "sample")
    MODEL_PROVIDER = os.getenv("MODEL_PROVIDER", "development")

    # Optional customer bill prediction registry settings
    MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "")
    MLFLOW_MODEL_ALIAS = os.getenv("MLFLOW_MODEL_ALIAS", "champion")
    MLFLOW_MODEL_NAME = os.getenv(
        "MLFLOW_MODEL_NAME", "customer-bill-prediction"
    )
    CUSTOMER_TARIFF_INR_PER_KWH = float(
        os.getenv("CUSTOMER_TARIFF_INR_PER_KWH", "10.0")
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
