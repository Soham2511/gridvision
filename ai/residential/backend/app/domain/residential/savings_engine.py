"""Energy Savings and Scenario Calculation Engine for GridVision Residential Platform.

Determines the incremental and compound energy and financial impacts of efficiency
interventions relative to an empirical household consumption baseline.
"""

from __future__ import annotations
from typing import Any, Dict, List


class EnergySavingsEngine:
    """Deterministic calculation engine for energy savings and scenario evaluation."""

    @classmethod
    def calculate_scenario_delta(
        cls,
        baseline_kwh: float,
        proposed_kwh: float,
        tariff_rate_inr_per_kwh: float = 10.0,
    ) -> Dict[str, float]:
        """Compute absolute and percentage delta between baseline and proposed scenario."""
        base = max(0.0, float(baseline_kwh))
        prop = max(0.0, float(proposed_kwh))
        delta_kwh = round(base - prop, 2)
        pct = round((delta_kwh / base) * 100.0, 1) if base > 0 else 0.0
        savings_inr = round(delta_kwh * float(tariff_rate_inr_per_kwh), 2)

        return {
            "baseline_kwh": base,
            "proposed_kwh": prop,
            "energy_saved_kwh": delta_kwh,
            "percentage_reduction_pct": pct,
            "financial_savings_inr": savings_inr,
        }

    @classmethod
    def evaluate_behavioral_ac_setback(
        cls,
        current_ac_temp_c: float,
        recommended_temp_c: float = 24.0,
        ac_monthly_consumption_kwh: float = 180.0,
        tariff_rate_inr_per_kwh: float = 10.0,
    ) -> Dict[str, Any]:
        """BEE Guideline: Every 1°C increase in AC setpoint saves ~6% electricity."""
        delta_deg = max(0.0, float(recommended_temp_c) - float(current_ac_temp_c))
        pct_savings = min(30.0, delta_deg * 6.0)
        saved_kwh = round(ac_monthly_consumption_kwh * (pct_savings / 100.0), 2)
        saved_inr = round(saved_kwh * tariff_rate_inr_per_kwh, 2)

        return {
            "intervention": f"Adjust AC thermostat from {current_ac_temp_c}°C to {recommended_temp_c}°C",
            "delta_temperature_c": delta_deg,
            "energy_reduction_pct": pct_savings,
            "monthly_savings_kwh": saved_kwh,
            "monthly_savings_inr": saved_inr,
            "annual_savings_inr": round(saved_inr * 12.0, 2),
            "upfront_cost_inr": 0.0,
        }

