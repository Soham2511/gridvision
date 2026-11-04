"""Pure domain Tariff and Billing Calculation Engine for GridVision Residential Platform.

Handles:
1. Energy charge calculations (flat tier or slab-based).
2. Fixed charges and statutory electricity duty.
3. Multi-year tariff escalation scenarios for lifecycle costing.
4. Nominal and discounted present value cash-flow projections.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional


class TariffBillingEngine:
    """Deterministic mathematical calculation engine for electricity tariffs and bills."""

    DEFAULT_TARIFF_RATE = 10.0
    DEFAULT_FIXED_CHARGE_INR = 120.0
    DEFAULT_ELECTRICITY_DUTY_PCT = 5.0  # Common state electricity duty rate

    @classmethod
    def calculate_monthly_bill(
        cls,
        consumption_kwh: float,
        tariff_rate_inr_per_kwh: float = DEFAULT_TARIFF_RATE,
        fixed_charge_inr: float = 0.0,
        electricity_duty_pct: float = 0.0,
    ) -> Dict[str, float]:
        """Compute monthly residential bill components deterministically."""
        clean_kwh = max(0.0, float(consumption_kwh))
        clean_rate = max(0.1, float(tariff_rate_inr_per_kwh))

        energy_charge = round(clean_kwh * clean_rate, 2)
        duty_amount = round(energy_charge * (electricity_duty_pct / 100.0), 2)
        total_bill = round(energy_charge + fixed_charge_inr + duty_amount, 2)

        return {
            "consumption_kwh": clean_kwh,
            "tariff_rate_inr_per_kwh": clean_rate,
            "energy_charge_inr": energy_charge,
            "fixed_charge_inr": round(fixed_charge_inr, 2),
            "electricity_duty_inr": duty_amount,
            "total_bill_inr": total_bill,
        }

    @classmethod
    def calculate_annual_bill(
        cls,
        annual_consumption_kwh: float,
        tariff_rate_inr_per_kwh: float = DEFAULT_TARIFF_RATE,
        fixed_charge_monthly_inr: float = 0.0,
    ) -> float:
        """Compute total annual electricity cost in INR."""
        clean_kwh = max(0.0, float(annual_consumption_kwh))
        energy_cost = clean_kwh * float(tariff_rate_inr_per_kwh)
        fixed_annual = float(fixed_charge_monthly_inr) * 12.0
        return round(energy_cost + fixed_annual, 2)

    @classmethod
    def project_escalated_operating_costs(
        cls,
        annual_kwh: float,
        base_tariff_rate: float,
        annual_escalation_pct: float,
        years: int,
        discount_rate_pct: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """Project annual operating electricity expenses across N years under tariff inflation."""
        projections: List[Dict[str, Any]] = []
        current_rate = float(base_tariff_rate)
        disc_rate = float(discount_rate_pct) / 100.0
        esc_rate = float(annual_escalation_pct) / 100.0

        for y in range(1, years + 1):
            nominal_cost = round(annual_kwh * current_rate, 2)
            discount_factor = 1.0 / ((1.0 + disc_rate) ** y) if disc_rate > 0 else 1.0
            discounted_cost = round(nominal_cost * discount_factor, 2)

            projections.append({
                "year": y,
                "projected_tariff_rate": round(current_rate, 3),
                "nominal_cost_inr": nominal_cost,
                "discounted_cost_inr": discounted_cost,
            })
            current_rate = current_rate * (1.0 + esc_rate)

        return projections

