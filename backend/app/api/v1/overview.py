"""Executive overview dashboard route."""

from __future__ import annotations

from flask import Blueprint, current_app
from app.utils.responses import success_response

bp = Blueprint("overview", __name__)


@bp.route("/overview", methods=["GET"])
def get_overview():
    """Returns aggregated executive summary metrics for OverviewPage."""
    data_provider = current_app.extensions["data_provider"]
    peak_service = current_app.extensions["peak_service"]
    anomaly_service = current_app.extensions["anomaly_service"]

    peak_data = peak_service.get_peak_analysis()
    anomalies = anomaly_service.get_anomalies()
    unresolved_anomalies = [a for a in anomalies if a["status"] != "resolved"]

    kpis = [
        {
            "id": "ov-current-demand",
            "title": "Active Grid Load",
            "value": "384.2",
            "unit": "MW",
            "changePercent": 3.4,
            "changePeriod": "vs prior hour",
            "trend": "up",
            "isPositiveGood": False,
            "subtext": "Coincident draw across 17 regional grid zones",
            "badge": "Live",
            "badgeVariant": "cyan",
            "category": "consumption",
        },
        {
            "id": "ov-forecast-total",
            "title": "7-Day Projected Total",
            "value": "64.8",
            "unit": "GWh",
            "changePercent": -1.8,
            "changePeriod": "vs prior 7-day cycle",
            "trend": "down",
            "isPositiveGood": True,
            "subtext": "Autoregressive LightGBM multi-horizon aggregate",
            "badge": "Forecast",
            "badgeVariant": "teal",
            "category": "forecast",
        },
        {
            "id": "ov-peak-projected",
            "title": "Projected Peak Window",
            "value": str(peak_data["expectedPeakMw"]),
            "unit": "MW",
            "changePercent": 5.2,
            "changePeriod": "above baseline reserve",
            "trend": "up",
            "isPositiveGood": False,
            "subtext": f"Anticipated: {peak_data['expectedPeakTime']}",
            "badge": "Elevated Risk",
            "badgeVariant": "amber",
            "category": "peak",
        },
        {
            "id": "ov-anomalies",
            "title": "Active Grid Anomalies",
            "value": str(len(unresolved_anomalies)),
            "unit": "unresolved",
            "changePercent": 1,
            "changePeriod": "critical severity",
            "trend": "up",
            "isPositiveGood": False,
            "subtext": "SUB-NORTH-104 requires engineering inspection",
            "badge": f"{len(anomalies)} Total",
            "badgeVariant": "danger",
            "category": "anomaly",
        },
    ]

    return success_response({
        "kpis": kpis,
        "peakAnalysis": peak_data,
        "activeAnomaliesCount": len(unresolved_anomalies),
    })
