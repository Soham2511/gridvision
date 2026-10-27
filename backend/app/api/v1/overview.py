"""Executive overview dashboard route."""

from __future__ import annotations

from flask import Blueprint, current_app
from app.utils.responses import success_response

bp = Blueprint("overview", __name__)


@bp.route("/overview", methods=["GET"])
def get_overview():
    """Returns aggregated executive summary metrics for OverviewPage."""
    data_provider = current_app.extensions["data_provider"]
    anomaly_service = current_app.extensions["anomaly_service"]
    peak_service = current_app.extensions["peak_service"]

    peak_data = peak_service.get_peak_analysis()
    anomalies = anomaly_service.get_anomalies()
    unresolved_anomalies = [a for a in anomalies if a["status"] != "resolved"]
    commercial_dashboard = data_provider.get_commercial_dashboard(
        tab="building", time_range="7D"
    )
    most_urgent_anomaly = next(iter(unresolved_anomalies), None)

    kpis = [
        {
            "id": "ov-current-demand",
            "title": "Active Grid Load",
            "value": str(peak_data["currentLoadMw"]),
            "unit": "MW",
            "trend": "neutral",
            "isPositiveGood": False,
            "subtext": f"System capacity limit: {peak_data['peakCapacityLimitMw']} MW",
            "badge": "Backend",
            "badgeVariant": "cyan",
            "category": "consumption",
        },
        {
            "id": "ov-forecast-total",
            "title": "7-Day Projected Total",
            "value": str(commercial_dashboard["predictedTotal"]),
            "unit": commercial_dashboard["totalUnit"],
            "changePercent": commercial_dashboard["avgDemandDeltaPct"],
            "changePeriod": "vs previous period",
            "trend": (
                "up"
                if commercial_dashboard["avgDemandDeltaPct"] > 0
                else "down"
                if commercial_dashboard["avgDemandDeltaPct"] < 0
                else "neutral"
            ),
            "isPositiveGood": True,
            "subtext": commercial_dashboard["predictedTotalHorizon"],
            "badge": "Forecast",
            "badgeVariant": "teal",
            "category": "forecast",
        },
        {
            "id": "ov-peak-projected",
            "title": "Projected Peak Window",
            "value": str(peak_data["expectedPeakMw"]),
            "unit": "MW",
            "trend": "neutral",
            "isPositiveGood": False,
            "subtext": f"Expected: {peak_data['expectedPeakTime']}",
            "badge": "Elevated Risk",
            "badgeVariant": "amber",
            "category": "peak",
        },
        {
            "id": "ov-anomalies",
            "title": "Active Grid Anomalies",
            "value": str(len(unresolved_anomalies)),
            "unit": "unresolved",
            "changePeriod": "unresolved",
            "trend": "neutral",
            "isPositiveGood": False,
            "subtext": (
                f"Highest priority: {most_urgent_anomaly['entityName']}"
                if most_urgent_anomaly
                else "No unresolved anomalies"
            ),
            "badge": f"{len(anomalies)} total",
            "badgeVariant": "danger",
            "category": "anomaly",
        },
    ]

    return success_response({
        "kpis": kpis,
        "peakAnalysis": peak_data,
        "activeAnomaliesCount": len(unresolved_anomalies),
    })
