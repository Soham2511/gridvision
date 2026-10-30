"""Peak demand analysis and automated demand response (ADR) simulation service."""

from __future__ import annotations

from typing import Any

from app.providers.data_provider import BaseDataProvider


class PeakDemandService:
    """Calculates peak stress, capacity margins, and ADR curtailment simulations."""

    def __init__(self, data_provider: BaseDataProvider) -> None:
        self.data_provider = data_provider

    def get_peak_analysis(self) -> dict[str, Any]:
        return self.data_provider.get_peak_demand_analysis()

    def simulate_curtailment(
        self,
        curtailment_mw: float,
        duration_hours: float = 2.0,
    ) -> dict[str, Any]:
        peak_data = self.data_provider.get_peak_demand_analysis()
        orig_peak = peak_data["expectedPeakMw"]
        cap_limit = peak_data["peakCapacityLimitMw"]

        new_peak = round(max(0.0, orig_peak - curtailment_mw), 2)
        new_margin = round(((cap_limit - new_peak) / cap_limit) * 100, 2)

        risk_level = "low" if new_margin >= 12.0 else ("moderate" if new_margin >= 8.0 else "elevated")

        return {
            "curtailmentMw": curtailment_mw,
            "durationHours": duration_hours,
            "originalPeakMw": orig_peak,
            "newPeakMw": new_peak,
            "peakCapacityLimitMw": cap_limit,
            "originalReserveMarginPct": peak_data["reserveMarginPct"],
            "newReserveMarginPct": new_margin,
            "riskLevel": risk_level,
            "dispatchConfirmed": True,
            "dispatchTimestamp": "Just now",
            "message": f"Successfully simulated dispatch of {curtailment_mw} MW curtailment for {duration_hours}h.",
        }
