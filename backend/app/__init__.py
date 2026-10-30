"""GridVision Flask Application Factory."""

from __future__ import annotations

import logging
import time
import uuid

from flask import Flask, Response, g, jsonify, request
from flask_cors import CORS

from app.config import BaseConfig, get_config
from app.utils.logging import setup_logging
from app.api.error_handlers import register_error_handlers
from app.api.v1 import api_v1_bp
from app.providers.sample_data_provider import SampleDataProvider
from app.providers.mock_model_provider import DevelopmentModelProvider
from app.providers.mlflow_adapter import MLflowModelAdapter
from app.providers.trained_forecast_provider import TrainedForecastProvider
from app.services.health_service import HealthService
from app.services.forecast_service import ForecastService
from app.services.dashboard_service import DashboardService
from app.services.peak_service import PeakDemandService
from app.services.anomaly_service import AnomalyService
from app.services.customer_service import CustomerService
from app.services.insight_service import InsightService
from app.services.assistant_service import AssistantService
from app.models.customer_bill_prediction import CustomerBillPredictionService


def create_app(config_class: type[BaseConfig] | None = None) -> Flask:
    """Create, configure, and initialize the GridVision Flask application."""
    app = Flask(__name__)

    # Load configuration
    cfg = config_class or get_config()
    app.config.from_object(cfg)

    # Initialize logging
    setup_logging()

    @app.before_request
    def start_request_log() -> None:
        g.request_started_at = time.perf_counter()
        g.request_id = uuid.uuid4().hex

    @app.after_request
    def write_request_log(response: Response) -> Response:
        started_at = getattr(g, "request_started_at", time.perf_counter())
        request_id = getattr(g, "request_id", uuid.uuid4().hex)
        response.headers["X-Request-ID"] = request_id
        logging.getLogger("gridvision.endpoints").info(
            "api_request",
            extra={
                "event": {
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.path,
                    "status_code": response.status_code,
                    "duration_ms": round((time.perf_counter() - started_at) * 1000, 3),
                }
            },
        )
        return response

    # Configure CORS
    CORS(
        app,
        resources={r"/api/*": {"origins": app.config.get("CORS_ORIGINS", "*")}},
        supports_credentials=True,
    )

    # Instantiate providers based on configuration
    data_provider = SampleDataProvider()

    model_provider_type = app.config.get("MODEL_PROVIDER", "development").lower()
    if model_provider_type == "mlflow":
        customer_model_provider = MLflowModelAdapter(
            tracking_uri=app.config.get("MLFLOW_TRACKING_URI"),
            model_alias=app.config.get("MLFLOW_MODEL_ALIAS", "champion"),
            model_name=app.config.get(
                "MLFLOW_MODEL_NAME", "customer-bill-prediction"
            ),
            tariff_inr_per_kwh=app.config.get(
                "CUSTOMER_TARIFF_INR_PER_KWH", 10.0
            ),
        )
        model_provider = TrainedForecastProvider(
            customer_provider=customer_model_provider,
            commercial_data=app.config["COMMERCIAL_FORECAST_DATA_PATH"],
            commercial_model=app.config["COMMERCIAL_FORECAST_MODEL_PATH"],
            government_data=app.config["GOVERNMENT_FORECAST_DATA_PATH"],
            government_model=app.config["GOVERNMENT_FORECAST_MODEL_PATH"],
            tracking_uri=app.config.get("MLFLOW_TRACKING_URI", ""),
            commercial_model_name=app.config["COMMERCIAL_MLFLOW_MODEL_NAME"],
            government_model_name=app.config["GOVERNMENT_MLFLOW_MODEL_NAME"],
            model_alias=app.config["MLFLOW_MODEL_ALIAS"],
        )
    else:
        model_provider = DevelopmentModelProvider()
        customer_model_provider = model_provider

    # Instantiate business services
    health_svc = HealthService(data_provider, model_provider)
    forecast_svc = ForecastService(data_provider, model_provider)
    dashboard_svc = DashboardService(data_provider)
    peak_svc = PeakDemandService(data_provider)
    anomaly_svc = AnomalyService(data_provider)
    customer_svc = CustomerService(data_provider)
    insight_svc = InsightService(data_provider)
    assistant_svc = AssistantService(data_provider)
    customer_bill_prediction_svc = CustomerBillPredictionService(
        dataset_path=app.config["CUSTOMER_GOLD_DATASET_PATH"],
        metadata_path=app.config["CUSTOMER_MODEL_METADATA_PATH"],
        artifact_path=app.config["CUSTOMER_MODEL_ARTIFACT_PATH"],
        model_provider=customer_model_provider,
        tariff_inr_per_kwh=app.config["CUSTOMER_TARIFF_INR_PER_KWH"],
    )

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
    app.extensions["customer_bill_prediction_service"] = (
        customer_bill_prediction_svc
    )

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
