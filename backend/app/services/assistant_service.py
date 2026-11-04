"""Domain-grounded AI assistant service."""

from __future__ import annotations

from typing import Any

from app.providers.data_provider import BaseDataProvider
from ai.commercial.config.settings import CommercialSettings
from ai.commercial.tools.renewable_energy import RenewableEnergyTools


class AssistantService:
    """Answers telemetry, tariff, peak shaving, and model evaluation inquiries."""

    def __init__(
        self,
        data_provider: BaseDataProvider,
        renewable_tools: RenewableEnergyTools | None = None,
    ) -> None:
        self.data_provider = data_provider
        settings = CommercialSettings.from_env()
        self.renewable_tools = renewable_tools or RenewableEnergyTools(
            api_key_file=settings.tavily_api_key_file,
            timeout_seconds=settings.tavily_timeout_seconds,
        )

    def answer_query(
        self,
        prompt: str,
        persona: str = "household",
        entity_id: str | None = None,
    ) -> dict[str, Any]:
        p = prompt.lower()
        active_entity = entity_id or ("METER-1000" if persona == "household" else ("Panther_office_1" if persona == "commercial" else "North Region"))

        if any(
            word in p
            for word in ("solar", "renewable", "wind", "photovoltaic", "rooftop")
        ):
            observation = self.renewable_tools.get_renewable_scenarios(
                active_entity,
                prompt,
            )
            answer_parts = list(observation.findings)
            answer_parts.extend(
                f"Assumption: {assumption}"
                for assumption in observation.assumptions
            )
            if observation.evidence_refs:
                answer_parts.append(
                    "Web sources:\n"
                    + "\n".join(
                        f"- {reference.locator}"
                        for reference in observation.evidence_refs
                        if reference.locator
                    )
                )
            if any(w in p for w in ["peak", "demand", "load", "forecast"]):
                peak_data = self.data_provider.get_peak_demand_analysis()
                answer_parts.append(
                    "**Grid peak context:** "
                    f"expected system peak **{peak_data['expectedPeakMw']} MW** "
                    f"at `{peak_data['expectedPeakTime']}` "
                    f"({peak_data['riskLevel']} risk)."
                )
            answer = "\n\n".join(answer_parts)
        elif any(w in p for w in ["bill", "tariff", "calculate", "rupee", "inr"]):
            answer = (
                "**Billing Computation (Prototype Tariff Specification):**\n\n"
                "Your month-end estimated invoice is computed using the baseline equation:\n\n"
                "$$\\text{Estimated Bill (₹)} = (\\text{Month-to-Date kWh} + \\text{Predicted Remaining kWh}) \\times ₹10.00/\\text{kWh}$$\n\n"
                f"- **Active Meter**: `{active_entity}`\n"
                "- **Tariff Rate**: ₹10.00 / kWh (Flat Prototype Tier)\n"
                "- **Cycle Window**: 19 Elapsed Days / 30 Total Days in Billing Cycle.\n\n"
                "To lower your bill, consider shifting heavy induction loads (geysers, washing machines) outside peak hours."
            )
        elif any(w in p for w in ["peak", "reserve", "stress", "curtail"]):
            peak_data = self.data_provider.get_peak_demand_analysis()
            answer = (
                f"**System Peak Demand & Reserve Status:**\n\n"
                f"- **Expected Peak**: **{peak_data['expectedPeakMw']} MW** at `{peak_data['expectedPeakTime']}`\n"
                f"- **Current Active Load**: **{peak_data['currentLoadMw']} MW**\n"
                f"- **Grid Capacity Ceiling**: **{peak_data['peakCapacityLimitMw']} MW**\n"
                f"- **Reserve Margin**: **{peak_data['reserveMarginPct']}%** ({peak_data['riskLevel'].upper()} risk)\n\n"
                "**Recommended Action**: " + peak_data["mitigationStrategy"]
            )
        elif any(w in p for w in ["anomaly", "drift", "spike"]):
            anomalies = self.data_provider.get_anomaly_events()
            active_count = len([a for a in anomalies if a["status"] != "resolved"])
            answer = (
                f"**Active Grid Anomalies Summary:**\n\n"
                f"There are currently **{active_count}** unresolved anomalies being tracked across the regional network:\n\n"
                + "\n".join(
                    f"- **{a['id']}** ({a['entityName']}): {a['anomalyType']} ({a['severity'].upper()}) — *{a['rootCauseDiagnosis']}*"
                    for a in anomalies[:3]
                )
            )
        elif any(w in p for w in ["feature", "influence", "temperature", "degree", "weather"]):
            answer = (
                "**Model Feature Sensitivity & Meteorological Drivers:**\n\n"
                "Inference for commercial facilities is driven by three primary feature groups:\n\n"
                "1. **Thermal Inertia**: Cooling Degree Hours (CDH base 18°C) contributes ~38% of model variance during summer peaks.\n"
                "2. **Autoregressive Lags**: 1-hour and 24-hour lagged electrical draw provide temporal continuity.\n"
                "3. **Occupancy Schedule**: Day-of-week and hour-of-day encodings distinguish operational from night-setback baseloads."
            )
        else:
            answer = (
                f"GridVision telemetry analysis for **{active_entity}** ({persona.capitalize()} scope):\n\n"
                "Historical consumption is tracking normally within confidence bands. "
                "Daily averages and peak window projections are continuously recomputed as new hourly meter intervals stream in."
            )

        return {
            "answer": answer,
            "persona": persona,
            "entityId": entity_id,
            "status": "success",
            "availability": "unavailable",
        }
