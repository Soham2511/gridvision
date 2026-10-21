"""GridVision Flask Application Factory."""

from __future__ import annotations

import os
from flask import Flask, jsonify
from flask_cors import CORS

from app.config import BaseConfig, get_config
from app.utils.logging import setup_logging
from app.api.error_handlers import register_error_handlers
from app.api.v1 import api_v1_bp
from app.providers.sample_data_provider import SampleDataProvider
from app.providers.mock_model_provider import DevelopmentModelProvider
from app.providers.mlflow_adapter import MLflowModelAdapter
from app.services.health_service import HealthService
from app.services.forecast_service import ForecastService
from app.services.dashboard_service import DashboardService
from app.services.peak_service import PeakDemandService
from app.services.anomaly_service import AnomalyService
from app.services.customer_service import CustomerService
from app.services.insight_service import InsightService
from app.services.assistant_service import AssistantService


def create_app(config_class: type[BaseConfig] | None = None) -> Flask:
    """Create, configure, and initialize the GridVision Flask application."""
    app = Flask(__name__)

    # Load configuration
    cfg = config_class or get_config()
    app.config.from_object(cfg)

    # Initialize logging
    setup_logging()

    # Configure CORS
    CORS(
        app,
        resources={r"/api/*": {"origins": app.config.get("CORS_ORIGINS", "*")}},
        supports_credentials=True,
    )

    # Instantiate providers based on configuration
    model_provider_type = app.config.get("MODEL_PROVIDER", "development").lower()
    if model_provider_type == "mlflow":
        model_provider = MLflowModelAdapter(
            tracking_uri=app.config.get("MLFLOW_TRACKING_URI"),
            model_alias=app.config.get("MLFLOW_MODEL_ALIAS", "champion"),
            model_name=app.config.get("MLFLOW_MODEL_NAME", "customer-bill-prediction"),
            tariff_inr_per_kwh=app.config.get("CUSTOMER_TARIFF_INR_PER_KWH", 10.0),
        )
    else:
        model_provider = DevelopmentModelProvider()

    data_provider = SampleDataProvider(model_provider=model_provider)

    # Instantiate business services
    health_svc = HealthService(data_provider, model_provider)
    forecast_svc = ForecastService(data_provider, model_provider)
    dashboard_svc = DashboardService(data_provider)
    peak_svc = PeakDemandService(data_provider)
    anomaly_svc = AnomalyService(data_provider)
    customer_svc = CustomerService(data_provider)
    insight_svc = InsightService(data_provider)
    assistant_svc = AssistantService(data_provider)

    # Attach to app extensions
    app.extensions["data_provider"] = data_provider
    app.extensions["model_provider"] = model_provider
    app.extensions["health_service"] = health_svc
    app.extensions["forecast_service"] = forecast_svc
    app.extensions["dashboard_service"] = dashboard_svc
    app.extensions["peak_service"] = peak_svc
    app.extensions["anomaly_service"] = anomaly_svc
    app.extensions["customer_service"] = customer_svc
    app.extensions["insight_service"] = insight_svc
    app.extensions["assistant_service"] = assistant_svc

    # Register error handlers
    register_error_handlers(app)

    # Register API v1 blueprint
    app.register_blueprint(api_v1_bp, url_prefix=app.config.get("API_PREFIX", "/api/v1"))

    # Root service index
    @app.route("/", methods=["GET"])
    def root_index():
        return jsonify({
            "service": "GridVision REST API",
            "version": "1.0.0",
            "endpoints": {
                "health": f"{app.config.get('API_PREFIX')}/health",
                "ready": f"{app.config.get('API_PREFIX')}/ready",
                "platform_health": f"{app.config.get('API_PREFIX')}/platform/health",
                "overview": f"{app.config.get('API_PREFIX')}/overview",
                "forecast": f"{app.config.get('API_PREFIX')}/forecast/commercial/Panther_office_1",
                "dashboard": f"{app.config.get('API_PREFIX')}/dashboard/commercial",
                "historical": f"{app.config.get('API_PREFIX')}/historical",
                "peak": f"{app.config.get('API_PREFIX')}/peak-demand",
                "anomalies": f"{app.config.get('API_PREFIX')}/anomalies",
                "customers": f"{app.config.get('API_PREFIX')}/customers/segmentation-matrix",
                "insights": f"{app.config.get('API_PREFIX')}/energy-insights",
            },
        })

    return app
