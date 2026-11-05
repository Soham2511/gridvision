"""GridVision Flask Application Factory."""

from __future__ import annotations

import logging
import os
import time
import uuid
from pathlib import Path

_RESIDENTIAL_APP_ROOT = next(
    (
        parent / "ai" / "residential" / "backend" / "app"
        for parent in Path(__file__).resolve().parents
        if (parent / "ai" / "residential" / "backend" / "app").is_dir()
    ),
    Path(__file__).resolve().parents[2]
    / "ai"
    / "residential"
    / "backend"
    / "app",
)
if _RESIDENTIAL_APP_ROOT.is_dir():
    __path__.append(str(_RESIDENTIAL_APP_ROOT))


def _extend_residential_package_path(
    package_path: list[str], relative_path: str
) -> None:
    """Keep moved residential modules importable through the existing app namespace."""
    candidate = _RESIDENTIAL_APP_ROOT / relative_path
    candidate_text = str(candidate)
    if candidate.is_dir() and candidate_text not in package_path:
        package_path.append(candidate_text)
from pathlib import Path

from flask import Flask, Response, g, jsonify, request
from flask_cors import CORS

from app.config import BaseConfig, get_config
from app.utils.logging import setup_logging
from app.api.error_handlers import register_error_handlers
from app.api.v1 import api_v1_bp
from app.providers.parquet_data_provider import ParquetDataProvider
from app.providers.unavailable_data_provider import UnavailableDataProvider
from app.providers.unavailable_model_provider import UnavailableModelProvider
from app.providers.mlflow_adapter import MLflowModelAdapter
from app.providers.trained_forecast_provider import TrainedForecastProvider
from app.services.health_service import HealthService
from app.services.forecast_service import ForecastService
from app.services.dashboard_service import DashboardService
from app.services.peak_service import PeakDemandService
from app.services.anomaly_service import AnomalyService
from app.services.customer_service import CustomerService
from app.services.customer_silver_history_service import CustomerSilverHistoryService
from app.services.commercial_silver_history_service import CommercialSilverHistoryService
from app.services.insight_service import InsightService
from app.services.assistant_service import AssistantService
from app.providers.llm import OllamaLLMAdapter, GroqLLMAdapter
from app.models.customer_bill_prediction import CustomerBillPredictionService
from app.services.segmentation_service import SegmentationService
from app.models.anomaly_prediction import AnomalyPredictionService
from app.ai.application_store import AIApplicationStore
from app.ai.persistence import SQLiteAuditRepository
from app.ai.rag import ApprovedCorpus
from app.ai.service import AIService
from app.ai.storage import PrivateFileStore
from data_retrieval_agent.agent import DataRetrievalAgent
from data_retrieval_agent.config import AgentSettings
from report_generator.services.llm_provider import provider_from_environment
from report_generator.services.report_generator import JSONReportGenerator
from report_generator.storage.report_storage import ReportRepository
from ai.commercial.graph import build_commercial_graph
from ai.commercial.approvals import ScheduleApprovalStore
from ai.commercial.config.settings import CommercialSettings
from ai.commercial.tools.document_rag_tools import DocumentRAGCommercialTools


def create_app(config_class: type[BaseConfig] | None = None) -> Flask:
    """Create, configure, and initialize the GridVision Flask application."""
    app = Flask(__name__)

    # Load configuration
    cfg = config_class or get_config()
    app.config.from_object(cfg)
    # These are lazy path-based objects; no files or providers are touched at startup.
    audit_repository = SQLiteAuditRepository(app.config["AI_DATABASE_PATH"])
    app.extensions["ai_service"] = AIService.from_config(
        app.config, audit_repository=audit_repository
    )
    app.extensions["ai_application_store"] = AIApplicationStore(
        app.config["AI_DATABASE_PATH"]
    )
    app.extensions["ai_private_storage"] = PrivateFileStore(
        app.config["AI_PRIVATE_STORAGE_ROOT"],
        forbidden_roots=(app.config["PROJECT_ROOT"] / "data", app.config["PROJECT_ROOT"] / "frontend" / "public"),
    )
    report_settings = app.config["REPORT_GENERATOR_SETTINGS"]
    app.extensions["report_generator"] = JSONReportGenerator(
        settings=report_settings,
        provider=provider_from_environment(report_settings.provider),
        repository=ReportRepository(app.config["AI_DATABASE_PATH"]),
        artifact_store=app.extensions["ai_private_storage"],
    )
    report_identity_resolver = app.config.get("REPORT_GENERATOR_IDENTITY_RESOLVER")
    if callable(report_identity_resolver):
        app.extensions["report_generator_identity_resolver"] = report_identity_resolver
    app.extensions["ai_rag_corpus"] = ApprovedCorpus(
        [], allowed_domains=set(app.config.get("AI_ALLOWED_SOURCE_DOMAINS", ()))
    )

    # Initialize logging
    setup_logging()
    app.config.setdefault("MAX_CONTENT_LENGTH", 26 * 1024 * 1024)

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
        expose_headers=["X-Request-ID"],
    )

    # Select providers explicitly. Test fixtures are never runtime fallbacks.
    data_provider_type = str(app.config.get("DATA_PROVIDER", "unavailable")).lower()
    if data_provider_type == "sample" and app.testing:
        from app.providers.sample_data_provider import SampleDataProvider

        data_provider = SampleDataProvider()
    elif data_provider_type == "parquet":
        data_provider = ParquetDataProvider()
    elif data_provider_type == "sample":
        from app.providers.sample_data_provider import SampleDataProvider

        data_provider = SampleDataProvider()
    elif data_provider_type == "unavailable":
        data_provider = UnavailableDataProvider()
    else:
        data_provider = UnavailableDataProvider(
            "The configured data provider is unsupported or is restricted to isolated tests."
        )

    model_provider_type = str(app.config.get("MODEL_PROVIDER", "unavailable")).lower()
    forecast_sources_approved = app.testing or set(
        app.config.get("APPROVED_DATA_SOURCES", ())
    ).issuperset({"commercial_gold", "government_2018", "customer_gold"})

    if model_provider_type == "mlflow" and forecast_sources_approved:
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
            commercial_model_alias=app.config["COMMERCIAL_MLFLOW_MODEL_ALIAS"],
            government_model_alias=app.config["GOVERNMENT_MLFLOW_MODEL_ALIAS"],
            commercial_metadata=app.config["COMMERCIAL_GOLD_METADATA_PATH"],
        )
    elif model_provider_type == "development" and app.testing:
        from app.providers.mock_model_provider import DevelopmentModelProvider

        model_provider = DevelopmentModelProvider()
        customer_model_provider = model_provider
    else:
        reason = (
            "The configured forecast models are unavailable or their source provenance is not approved."
            if model_provider_type == "mlflow"
            else "No approved forecast model provider is configured."
        )
        model_provider = UnavailableModelProvider(reason)
        customer_model_provider = model_provider

    # Historical Commercial Gold access reuses the existing forecast provider's
    # bounded SQL aggregation without enabling model inference or MLflow.
    if isinstance(model_provider, TrainedForecastProvider):
        commercial_history_provider = model_provider
    else:
        history_customer_provider = MLflowModelAdapter(
            tracking_uri=app.config.get("MLFLOW_TRACKING_URI"),
            model_alias=app.config.get("MLFLOW_MODEL_ALIAS", "champion"),
            model_name=app.config.get(
                "MLFLOW_MODEL_NAME", "customer-bill-prediction"
            ),
            tariff_inr_per_kwh=app.config.get(
                "CUSTOMER_TARIFF_INR_PER_KWH", 10.0
            ),
        )
        commercial_history_provider = TrainedForecastProvider(
            customer_provider=history_customer_provider,
            commercial_data=app.config["COMMERCIAL_FORECAST_DATA_PATH"],
            commercial_model=app.config["COMMERCIAL_FORECAST_MODEL_PATH"],
            government_data=app.config["GOVERNMENT_FORECAST_DATA_PATH"],
            government_model=app.config["GOVERNMENT_FORECAST_MODEL_PATH"],
            tracking_uri=app.config.get("MLFLOW_TRACKING_URI", ""),
            commercial_model_name=app.config["COMMERCIAL_MLFLOW_MODEL_NAME"],
            government_model_name=app.config["GOVERNMENT_MLFLOW_MODEL_NAME"],
            model_alias=app.config["MLFLOW_MODEL_ALIAS"],
            commercial_model_alias=app.config["COMMERCIAL_MLFLOW_MODEL_ALIAS"],
            government_model_alias=app.config["GOVERNMENT_MLFLOW_MODEL_ALIAS"],
            commercial_metadata=app.config["COMMERCIAL_GOLD_METADATA_PATH"],
        )

    # This provider is injected into the residential assistant service only.
    assistant_provider = app.config.get(
        "RESIDENTIAL_ASSISTANT_PROVIDER", "groq"
    ).strip().lower()
    if assistant_provider == "groq":
        llm_provider = GroqLLMAdapter(
            api_key=app.config.get("GROQ_API_KEY", ""),
            base_url=app.config.get("GROQ_BASE_URL"),
            model=app.config.get(
                "RESIDENTIAL_GROQ_MODEL", "openai/gpt-oss-20b"
            ),
            timeout=app.config.get("ASSISTANT_COMPLEX_TIMEOUT_SECONDS", 75.0),
            max_retries=app.config.get("ASSISTANT_MAX_RETRIES", 0),
        )
    elif assistant_provider == "ollama":
        llm_provider = OllamaLLMAdapter(
            base_url=app.config.get("OLLAMA_BASE_URL", "http://localhost:11434"),
            model=app.config.get("OLLAMA_MODEL", "qwen3:8b"),
        )
    else:
        raise ValueError(
            "RESIDENTIAL_ASSISTANT_PROVIDER must be 'groq' or 'ollama'."
        )

    # Instantiate business services
    health_svc = HealthService(data_provider, model_provider)
    forecast_svc = ForecastService(data_provider, model_provider)
    dashboard_svc = DashboardService(data_provider, model_provider)
    peak_svc = PeakDemandService(data_provider)
    anomaly_svc = AnomalyService(data_provider)
    customer_svc = CustomerService(data_provider)
    insight_svc = InsightService(data_provider)
    customer_bill_prediction_svc = CustomerBillPredictionService(
        dataset_path=app.config["CUSTOMER_GOLD_DATASET_PATH"],
        metadata_path=app.config["CUSTOMER_MODEL_METADATA_PATH"],
        artifact_path=app.config["CUSTOMER_MODEL_ARTIFACT_PATH"],
        model_provider=customer_model_provider,
        tariff_inr_per_kwh=app.config["CUSTOMER_TARIFF_INR_PER_KWH"],
        forecast_model_provider=model_provider,
    )
    anomaly_prediction_svc = AnomalyPredictionService(
        dataset_path=app.config["ANOMALY_DATASET_PATH"],
        model_path=app.config["ANOMALY_MODEL_PATH"],
        project_root=app.config["PROJECT_ROOT"],
        runs_path=app.config["ANOMALY_RUNS_PATH"],
    )
    assistant_svc = AssistantService(
        data_provider,
        anomaly_service=anomaly_prediction_svc,
        route_government_queries=not app.testing,
        llm_provider=llm_provider,
        tariff_rate=app.config.get("CUSTOMER_TARIFF_INR_PER_KWH", 10.0),
        authorized_meters=app.config.get("AUTHORIZED_RESIDENTIAL_METERS"),
        temperature=app.config.get("ASSISTANT_TEMPERATURE", 0.2),
        max_tokens=app.config.get("ASSISTANT_MAX_TOKENS", 800),
        prediction_service=customer_bill_prediction_svc,
    )
    government_segmentation_svc = SegmentationService(
        output_dir=app.config["SEGMENTATION_OUTPUT_DIR"],
        reports_dir=app.config["SEGMENTATION_REPORTS_DIR"],
        max_page_size=app.config["SEGMENTATION_API_MAX_PAGE_SIZE"],
    )
    commercial_settings = CommercialSettings.from_env()
    commercial_tools = DocumentRAGCommercialTools(
        commercial_settings.rag_documents,
        settings=commercial_settings,
    )
    commercial_workflow = build_commercial_graph(
        tools=commercial_tools,
        settings=commercial_settings,
    )
    commercial_schedule_approvals = ScheduleApprovalStore(
        Path(
            os.getenv(
                "COMMERCIAL_APPROVAL_DB_PATH",
                str(
                    app.config["PROJECT_ROOT"]
                    / "data"
                    / "commercial"
                    / "rag"
                    / "schedule_approvals.sqlite3"
                ),
            )
        ).expanduser()
    )

    # Attach to app extensions
    app.extensions["data_provider"] = data_provider
    app.extensions["data_provider_status"] = (
        data_provider.availability()
        if isinstance(data_provider, UnavailableDataProvider)
        else {"status": "ready", "provider": data_provider_type}
    )
    app.extensions["model_provider"] = model_provider
    app.extensions["commercial_history_provider"] = commercial_history_provider
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
    customer_silver_history_svc = CustomerSilverHistoryService(
        app.config["CUSTOMER_SILVER_DATASET_PATH"],
        app.config["CUSTOMER_SILVER_METADATA_PATH"],
    )
    app.extensions["customer_silver_history_service"] = customer_silver_history_svc
    commercial_silver_history_svc = CommercialSilverHistoryService(
        app.config["COMMERCIAL_SILVER_DATASET_PATH"],
        app.config["COMMERCIAL_SILVER_METADATA_PATH"],
    )
    app.extensions["commercial_silver_history_service"] = commercial_silver_history_svc
    app.extensions["government_segmentation_service"] = government_segmentation_svc
    app.extensions["anomaly_prediction_service"] = anomaly_prediction_svc
    app.extensions["commercial_workflow"] = commercial_workflow
    app.extensions["commercial_rag_retriever"] = commercial_tools.retriever
    app.extensions["commercial_schedule_approvals"] = (
        commercial_schedule_approvals
    )

    retrieval_settings = AgentSettings.from_env()
    app.extensions["data_retrieval_agent"] = DataRetrievalAgent(
        settings=retrieval_settings,
        services={
            "customer_bill_prediction_service": customer_bill_prediction_svc,
            "customer_silver_history_service": customer_silver_history_svc,
            "commercial_silver_history_service": commercial_silver_history_svc,
            "commercial_history_provider": commercial_history_provider,
            "model_provider": model_provider,
            "government_segmentation_service": government_segmentation_svc,
            "anomaly_prediction_service": anomaly_prediction_svc,
            "customer_gold_path": app.config["CUSTOMER_GOLD_DATASET_PATH"],
            "customer_silver_path": app.config["CUSTOMER_SILVER_DATASET_PATH"],
            "customer_silver_metadata_path": app.config["CUSTOMER_SILVER_METADATA_PATH"],
            "commercial_silver_path": app.config["COMMERCIAL_SILVER_DATASET_PATH"],
            "commercial_silver_metadata_path": app.config["COMMERCIAL_SILVER_METADATA_PATH"],
            "customer_metadata_path": app.config["CUSTOMER_MODEL_METADATA_PATH"],
            "commercial_gold_path": app.config["COMMERCIAL_FORECAST_DATA_PATH"],
            "commercial_metadata_path": app.config["COMMERCIAL_GOLD_METADATA_PATH"],
            "government_data_path": app.config["GOVERNMENT_FORECAST_DATA_PATH"],
            "segmentation_output_dir": app.config["SEGMENTATION_OUTPUT_DIR"],
            "anomaly_dataset_path": app.config["ANOMALY_DATASET_PATH"],
            "anomaly_model_path": app.config["ANOMALY_MODEL_PATH"],
        },
        approved_sources=set(app.config.get("APPROVED_DATA_SOURCES", ())),
    )
    retrieval_identity_resolver = app.config.get("DATA_RETRIEVAL_IDENTITY_RESOLVER")
    if callable(retrieval_identity_resolver):
        app.extensions["data_retrieval_identity_resolver"] = retrieval_identity_resolver

    retrieval_settings = AgentSettings.from_env()
    app.extensions["data_retrieval_agent"] = DataRetrievalAgent(
        settings=retrieval_settings,
        services={
            "customer_bill_prediction_service": customer_bill_prediction_svc,
            "customer_silver_history_service": customer_silver_history_svc,
            "commercial_silver_history_service": commercial_silver_history_svc,
            "commercial_history_provider": commercial_history_provider,
            "model_provider": model_provider,
            "government_segmentation_service": government_segmentation_svc,
            "anomaly_prediction_service": anomaly_prediction_svc,
            "customer_gold_path": app.config["CUSTOMER_GOLD_DATASET_PATH"],
            "customer_silver_path": app.config["CUSTOMER_SILVER_DATASET_PATH"],
            "customer_silver_metadata_path": app.config["CUSTOMER_SILVER_METADATA_PATH"],
            "commercial_silver_path": app.config["COMMERCIAL_SILVER_DATASET_PATH"],
            "commercial_silver_metadata_path": app.config["COMMERCIAL_SILVER_METADATA_PATH"],
            "customer_metadata_path": app.config["CUSTOMER_MODEL_METADATA_PATH"],
            "commercial_gold_path": app.config["COMMERCIAL_FORECAST_DATA_PATH"],
            "commercial_metadata_path": app.config["COMMERCIAL_GOLD_METADATA_PATH"],
            "government_data_path": app.config["GOVERNMENT_FORECAST_DATA_PATH"],
            "segmentation_output_dir": app.config["SEGMENTATION_OUTPUT_DIR"],
            "anomaly_dataset_path": app.config["ANOMALY_DATASET_PATH"],
            "anomaly_model_path": app.config["ANOMALY_MODEL_PATH"],
        },
        approved_sources=set(app.config.get("APPROVED_DATA_SOURCES", ())),
    )
    retrieval_identity_resolver = app.config.get("DATA_RETRIEVAL_IDENTITY_RESOLVER")
    if callable(retrieval_identity_resolver):
        app.extensions["data_retrieval_identity_resolver"] = retrieval_identity_resolver

    # Register error handlers
    register_error_handlers(app)

    # Register API v1 blueprint
    app.register_blueprint(api_v1_bp, url_prefix=app.config.get("API_PREFIX", "/api/v1"))

    # Seed verified initial residential account if not present
    try:
        from app.services.auth_service import auth_service
        auth_service.seed_initial_residential_user()
    except Exception as exc:
        logging.getLogger("gridvision.auth").warning("Initial residential account seeding deferred: %s", exc)

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
                "commercial_workflow": f"{app.config.get('API_PREFIX')}/commercial/workflow",
                "commercial_schedule_approval": (
                    f"{app.config.get('API_PREFIX')}/commercial/schedules/"
                    "<proposal_id>/approval"
                ),
                "government_segmentation": f"{app.config.get('API_PREFIX')}/government/segmentation/overview",
            },
        })

    return app