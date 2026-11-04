"""API v1 Blueprint aggregating all domain routes."""

from __future__ import annotations

from flask import Blueprint

from app.api.v1.health import bp as health_bp
from app.api.v1.overview import bp as overview_bp
from app.api.v1.entities import bp as entities_bp
from app.api.v1.forecast import bp as forecast_bp
from app.api.v1.dashboard import bp as dashboard_bp
from app.api.v1.historical import bp as historical_bp
from app.api.v1.peak import bp as peak_bp
from app.api.v1.anomalies import bp as anomalies_bp
from app.api.v1.customers import bp as customers_bp
from app.api.v1.insights import bp as insights_bp
from app.api.v1.assistant import bp as assistant_bp
from app.api.v1.models import bp as models_bp
from app.api.v1.segmentation import bp as segmentation_bp
from app.api.v1.ai_layer import bp as ai_layer_bp
from data_retrieval_agent.api import bp as data_retrieval_agent_bp
from report_generator.api.routes import bp as report_generator_bp
from app.api.v1.commercial_workflow import bp as commercial_workflow_bp

api_v1_bp = Blueprint("api_v1", __name__)

api_v1_bp.register_blueprint(health_bp)
api_v1_bp.register_blueprint(overview_bp)
api_v1_bp.register_blueprint(entities_bp)
api_v1_bp.register_blueprint(forecast_bp)
api_v1_bp.register_blueprint(dashboard_bp)
api_v1_bp.register_blueprint(historical_bp)
api_v1_bp.register_blueprint(peak_bp)
api_v1_bp.register_blueprint(anomalies_bp)
api_v1_bp.register_blueprint(customers_bp)
api_v1_bp.register_blueprint(insights_bp)
api_v1_bp.register_blueprint(assistant_bp)
api_v1_bp.register_blueprint(models_bp)
api_v1_bp.register_blueprint(segmentation_bp)
api_v1_bp.register_blueprint(ai_layer_bp)
api_v1_bp.register_blueprint(data_retrieval_agent_bp, url_prefix="/data-retrieval-agent")
api_v1_bp.register_blueprint(report_generator_bp, url_prefix="/report-generator")
api_v1_bp.register_blueprint(commercial_workflow_bp)
