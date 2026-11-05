"""Appliance Lifecycle Cost and Scenario Analysis Engine for GridVision Residential Platform.

Performs deterministic lifecycle economic and energy calculations:
1. Annual energy consumption based on rated power, operating hours, and duty factor.
2. Net upfront replacement investment (purchase + installation - resale).
3. Multi-year cash flows under tariff inflation.
4. Simple Payback Period and Break-Even year.
5. Total Cost of Ownership (TCO) / Net Present Value (NPV).
6. CO2 emissions reduction using CEA grid emission benchmarks.
7. Sensitivity analysis across usage hours and tariff escalation rates.

Integrated with ReferenceResolver (Milestone 4 / R5) for verified BEE appliance benchmarks
and CEA grid emission factors, while maintaining 100% backwards compatibility and
strictly preserving all mathematical calculation formulas.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List, Optional, Union

from app.domain.residential.reference_data import CEA_GRID_EMISSION_FACTOR_KG_PER_KWH
from app.domain.residential.schemas import (
    ApplianceScenarioRequest,
    ApplianceScenarioResult,
    CalculationAuditItem,
    DataProvenance,
    ExistingApplianceSpec,
    ProposedApplianceSpec,
    YearCashflow,
)

logger = logging.getLogger(__name__)


def _run_analysis(
    cls: type,
    request: ApplianceScenarioRequest,
    resolver: Any = None,
) -> ApplianceScenarioResult:
    """Core calculation logic executing lifecycle comparison between existing and proposed appliance."""
    # 1. Resolve Grid Emission Factor
    emission_factor = CEA_GRID_EMISSION_FACTOR_KG_PER_KWH
    emission_provenance = DataProvenance.CALCULATED
    emission_metadata: Dict[str, Any] = {}

    if resolver is not None:
        try:
            from app.services.reference.resolver import ReferenceResolutionContext

            ctx = ReferenceResolutionContext(
                category="grid_emission",
                identifier="cea_grid_emission_factor",
                jurisdiction="IN",
                effective_date=date.today(),
            )
            resolved_emission = resolver.resolve(ctx)
            val = getattr(
                resolved_emission, "value", getattr(resolved_emission, "normalized_value", None)
            )
            if val is not None:
                emission_factor = float(val)
            emission_provenance = DataProvenance.OFFICIAL_REFERENCE
            emission_metadata = getattr(resolved_emission, "provenance", {}) or {}
        except Exception as e:
            logger.debug("Resolver emission factor resolution fallback: %s", e)
            emission_factor = CEA_GRID_EMISSION_FACTOR_KG_PER_KWH

    # 2. Resolve or fallback Existing Appliance Spec
    if request.existing_appliance is not None:
        existing = request.existing_appliance
    elif resolver is not None:
        try:
            from app.services.reference.resolver import ReferenceResolutionContext

            res_exist = resolver.resolve(
                ReferenceResolutionContext(
                    category="appliance",
                    identifier="room_ac_1.5t_non_inverter_baseline",
                    jurisdiction="IN",
                    effective_date=date.today(),
                )
            )
            specs = getattr(res_exist, "specifications", {}) or {}
            if not specs and hasattr(res_exist, "provenance"):
                specs = res_exist.provenance.get("technical_specifications", {})
            existing = ExistingApplianceSpec(
                category="Air Conditioner",
                rated_power_w=float(specs.get("rated_power_w", 1650.0)),
                daily_usage_hours=8.0,
                efficiency_label="Non-Inverter / 1-2 Star BEE",
                age_years=6.0,
            )
        except Exception:
            existing = ExistingApplianceSpec(
                category="Air Conditioner",
                rated_power_w=1650.0,
                daily_usage_hours=8.0,
                efficiency_label="Non-Inverter / 1-2 Star BEE",
                age_years=6.0,
            )
    else:
        existing = ExistingApplianceSpec(
            category="Air Conditioner",
            rated_power_w=1650.0,
            daily_usage_hours=8.0,
            efficiency_label="Non-Inverter / 1-2 Star BEE",
            age_years=6.0,
        )

    # 3. Resolve or fallback Proposed Appliance Spec
    if request.proposed_appliance is not None:
        proposed = request.proposed_appliance
    elif resolver is not None:
        try:
            from app.services.reference.resolver import ReferenceResolutionContext

            res_prop = resolver.resolve(
                ReferenceResolutionContext(
                    category="appliance",
                    identifier="room_ac_1.5t_5star_iseer",
                    jurisdiction="IN",
                    effective_date=date.today(),
                )
            )
            specs = getattr(res_prop, "specifications", {}) or {}
            if not specs and hasattr(res_prop, "provenance"):
                specs = res_prop.provenance.get("technical_specifications", {})
            proposed = ProposedApplianceSpec(
                category=existing.category,
                rated_power_w=float(specs.get("rated_power_w", 1250.0)),
                daily_usage_hours=existing.daily_usage_hours,
                efficiency_label="5-Star BEE Dual-Inverter",
                purchase_price_inr=38000.0,
                installation_cost_inr=1500.0,
            )
        except Exception:
            proposed = ProposedApplianceSpec(
                category=existing.category,
                rated_power_w=1250.0,
                daily_usage_hours=existing.daily_usage_hours,
                efficiency_label="5-Star BEE Dual-Inverter",
                purchase_price_inr=38000.0,
                installation_cost_inr=1500.0,
            )
    else:
        proposed = ProposedApplianceSpec(
            category=existing.category,
            rated_power_w=1250.0,
            daily_usage_hours=existing.daily_usage_hours,
            efficiency_label="5-Star BEE Dual-Inverter",
            purchase_price_inr=38000.0,
            installation_cost_inr=1500.0,
        )

    # 4. Energy Consumption Calculations (Strictly Preserved Formula)
    existing_annual_kwh = cls.calculate_annual_consumption_kwh(
        existing.rated_power_w, existing.daily_usage_hours, existing.category
    )
    proposed_annual_kwh = cls.calculate_annual_consumption_kwh(
        proposed.rated_power_w, proposed.daily_usage_hours, proposed.category
    )

    annual_saved_kwh = round(existing_annual_kwh - proposed_annual_kwh, 2)
    base_tariff = float(request.tariff_inr_per_kwh)
    annual_saved_inr = round(annual_saved_kwh * base_tariff, 2)

    # 5. Net Upfront Investment Calculation
    resale = float(existing.expected_resale_value_inr or 0.0)
    net_upfront = round(
        float(proposed.purchase_price_inr) + float(proposed.installation_cost_inr) - resale, 2
    )

    # 6. Simple Payback Period Calculation
    simple_payback = None
    if annual_saved_inr > 0:
        simple_payback = round(net_upfront / annual_saved_inr, 2)

    # 7. Multi-Year Cash Flows with Escalation and Discounting
    cashflows: List[YearCashflow] = []
    cumulative_savings = -net_upfront
    break_even_year: Optional[int] = None
    esc_rate = request.annual_tariff_escalation_pct / 100.0
    disc_rate = request.discount_rate_pct / 100.0

    npv_existing_operating = 0.0
    npv_proposed_operating = 0.0

    for year in range(1, request.analysis_period_years + 1):
        curr_rate = base_tariff * ((1.0 + esc_rate) ** (year - 1))
        op_cost_exist = round(existing_annual_kwh * curr_rate, 2)
        op_cost_prop = round(proposed_annual_kwh * curr_rate, 2)
        savings_y = round(op_cost_exist - op_cost_prop, 2)
        cumulative_savings = round(cumulative_savings + savings_y, 2)

        disc_factor = 1.0 / ((1.0 + disc_rate) ** year)
        npv_existing_operating += op_cost_exist * disc_factor
        npv_proposed_operating += op_cost_prop * disc_factor

        if cumulative_savings >= 0 and break_even_year is None:
            break_even_year = year

        cashflows.append(
            YearCashflow(
                year=year,
                baseline_operating_cost_inr=op_cost_exist,
                proposed_operating_cost_inr=op_cost_prop,
                annual_savings_inr=savings_y,
                cumulative_net_savings_inr=cumulative_savings,
            )
        )

    # 8. Total Cost of Ownership (TCO) & Net Lifetime Savings
    tco_existing = round(npv_existing_operating, 2)
    tco_proposed = round(net_upfront + npv_proposed_operating, 2)
    net_lifetime_savings = round(tco_existing - tco_proposed, 2)
    roi_pct = round((net_lifetime_savings / net_upfront) * 100.0, 1) if net_upfront > 0 else None

    # 9. Environmental Impact
    co2_reduction_kg = round(annual_saved_kwh * emission_factor, 1)

    # 10. Verdict Formulation
    if simple_payback is not None and simple_payback <= 3.5:
        verdict = (
            f"Highly recommended upgrade. The proposed {proposed.efficiency_label} recovers its net upfront investment "
            f"in approximately {simple_payback:.1f} years, generating ₹{net_lifetime_savings:,.2f} in net lifetime savings."
        )
    elif simple_payback is not None and simple_payback <= 6.0:
        verdict = (
            f"Favorable investment. With a payback period of {simple_payback:.1f} years, this upgrade cuts annual electricity "
            f"costs by ₹{annual_saved_inr:,.2f}/year and provides continuous long-term savings."
        )
    elif annual_saved_kwh > 0:
        verdict = (
            f"Moderate financial return. Payback is {simple_payback:.1f} years due to upfront equipment costs. "
            f"Recommended if existing unit requires maintenance or if comfort and noise reduction are priorities."
        )
    else:
        verdict = "The proposed appliance does not provide significant operational energy savings over the current setup."

    # 11. Sensitivity Scenarios
    sensitivity_scenarios = [
        {
            "scenarioName": "Conservative (Low Usage: -25% hours)",
            "dailyHours": round(existing.daily_usage_hours * 0.75, 1),
            "annualSavingsInr": round(annual_saved_inr * 0.75, 2),
            "paybackYears": round(net_upfront / (annual_saved_inr * 0.75), 1) if annual_saved_inr > 0 else None,
        },
        {
            "scenarioName": "Base Case (Current Usage)",
            "dailyHours": existing.daily_usage_hours,
            "annualSavingsInr": annual_saved_inr,
            "paybackYears": simple_payback,
        },
        {
            "scenarioName": "Heavy Usage (+25% hours, Summer/Peak)",
            "dailyHours": round(min(24.0, existing.daily_usage_hours * 1.25), 1),
            "annualSavingsInr": round(annual_saved_inr * 1.25, 2),
            "paybackYears": round(net_upfront / (annual_saved_inr * 1.25), 1) if annual_saved_inr > 0 else None,
        },
    ]

    # 12. Audit Trail
    emission_notes = (
        f"Resolved via ReferenceResolver from {emission_metadata.get('document_identifier', 'CEA Database')}"
        if emission_provenance == DataProvenance.OFFICIAL_REFERENCE
        else "Standard Central Electricity Authority benchmark factor."
    )

    audit_trail: List[CalculationAuditItem] = [
        CalculationAuditItem(
            metric_name="existing_annual_kwh",
            value=existing_annual_kwh,
            unit="kWh",
            provenance=DataProvenance.CALCULATED,
            methodology=f"Rated {existing.rated_power_w}W * {existing.daily_usage_hours}h/day * 365 days * duty factor ({cls.get_duty_cycle_factor(existing.category)}).",
            inputs_used={"rated_power_w": existing.rated_power_w, "daily_hours": existing.daily_usage_hours},
        ),
        CalculationAuditItem(
            metric_name="proposed_annual_kwh",
            value=proposed_annual_kwh,
            unit="kWh",
            provenance=DataProvenance.CALCULATED,
            methodology=f"Rated {proposed.rated_power_w}W * {proposed.daily_usage_hours}h/day * 365 days * duty factor ({cls.get_duty_cycle_factor(proposed.category)}).",
            inputs_used={"rated_power_w": proposed.rated_power_w, "daily_hours": proposed.daily_usage_hours},
        ),
        CalculationAuditItem(
            metric_name="simple_payback_years",
            value=simple_payback or 0.0,
            unit="Years",
            provenance=DataProvenance.CALCULATED,
            methodology="Net upfront investment (purchase + installation - resale) / Annual operating savings in Year 1.",
            inputs_used={"net_upfront": net_upfront, "annual_savings": annual_saved_inr},
        ),
        CalculationAuditItem(
            metric_name="co2_reduction_kg_per_year",
            value=co2_reduction_kg,
            unit="kg CO2",
            provenance=emission_provenance,
            methodology=f"Annual kWh saved * CEA grid emission factor ({emission_factor} kg CO2 / kWh).",
            inputs_used={"annual_saved_kwh": annual_saved_kwh, "emission_factor": emission_factor},
            notes=emission_notes,
        ),
    ]

    return ApplianceScenarioResult(
        intention=request.intention,
        existing_annual_kwh=existing_annual_kwh,
        proposed_annual_kwh=proposed_annual_kwh,
        annual_energy_savings_kwh=annual_saved_kwh,
        annual_cost_savings_inr=annual_saved_inr,
        net_upfront_investment_inr=net_upfront,
        simple_payback_years=simple_payback,
        break_even_year=break_even_year,
        total_lifecycle_cost_existing_inr=tco_existing,
        total_lifecycle_cost_proposed_inr=tco_proposed,
        net_lifetime_savings_inr=net_lifetime_savings,
        return_on_investment_pct=roi_pct,
        co2_reduction_kg_per_year=co2_reduction_kg,
        cashflows=cashflows,
        sensitivity_scenarios=sensitivity_scenarios,
        recommendation_verdict=verdict,
        audit_trail=audit_trail,
    )


class _HybridExecuteAnalysis:
    """Descriptor enabling execute_analysis to work as both an instance method and a class method."""

    def __get__(self, obj: Any, objtype: Optional[type] = None) -> Any:
        cls = objtype if objtype is not None else type(obj)
        if obj is None:
            # Invocation via class: ApplianceLifecycleCostEngine.execute_analysis(req)
            def class_call(
                request: ApplianceScenarioRequest, resolver: Any = None
            ) -> ApplianceScenarioResult:
                return _run_analysis(cls, request, resolver=resolver)

            return class_call
        else:
            # Invocation via instance: engine.execute_analysis(req)
            def instance_call(
                request: ApplianceScenarioRequest, resolver: Any = None
            ) -> ApplianceScenarioResult:
                target_resolver = resolver if resolver is not None else obj.resolver
                return _run_analysis(cls, request, resolver=target_resolver)

            return instance_call


class ApplianceLifecycleCostEngine:
    """Deterministic engineering calculation engine for appliance lifecycle cost and replacement analysis."""

    execute_analysis = _HybridExecuteAnalysis()

    def __init__(self, resolver: Any = None) -> None:
        """Initialize ApplianceLifecycleCostEngine with an optional ReferenceResolver.

        Args:
            resolver: Optional ReferenceResolver instance bridging approved standards.
        """
        self.resolver = resolver

    @staticmethod
    def get_duty_cycle_factor(category: str) -> float:
        """Duty cycle / compressor modulation factor (air conditioners and refrigerators cycle on/off)."""
        cat = (category or "").lower()
        if "air conditioner" in cat or "ac" in cat:
            return 0.70  # Inverter compressor modulates ~70% of peak rated draw
        elif "refrigerator" in cat or "fridge" in cat:
            return 0.35  # Compressor runs ~35% of total day
        elif "water heater" in cat or "geyser" in cat:
            return 0.90  # Heating elements draw near full rated power
        elif "fan" in cat:
            return 1.0   # Fans operate continuously at set speed
        return 0.80

    @classmethod
    def calculate_annual_consumption_kwh(
        cls, rated_power_w: float, daily_hours: float, category: str
    ) -> float:
        """Calculate annual electricity consumption in kWh.

        Formula: E = (rated_power_w * duty_cycle * daily_hours * 365) / 1000
        """
        duty = cls.get_duty_cycle_factor(category)
        effective_w = float(rated_power_w) * duty
        annual_hours = float(daily_hours) * 365.0
        return round((effective_w * annual_hours) / 1000.0, 2)

    def resolve_reference(
        self,
        identifier: str,
        category: str = "appliance",
        jurisdiction: str = "IN",
        effective_date: Optional[Union[date, str]] = None,
        specifications: Optional[Dict[str, Any]] = None,
        applicability_conditions: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Explicitly resolve reference data using configured ReferenceResolver.

        Raises:
            ValueError: If no ReferenceResolver is configured.
            ReferenceResolutionError: Missing, expired, unapproved, out-of-jurisdiction, or ambiguous reference.
        """
        if self.resolver is None:
            raise ValueError("No ReferenceResolver configured on ApplianceLifecycleCostEngine")

        from app.services.reference.resolver import ReferenceResolutionContext

        eff_date = effective_date
        if isinstance(eff_date, str):
            eff_date = date.fromisoformat(eff_date)
        elif eff_date is None:
            eff_date = date.today()

        ctx = ReferenceResolutionContext(
            category=category,
            identifier=identifier,
            jurisdiction=jurisdiction,
            effective_date=eff_date,
            specifications=specifications or {},
            applicability_conditions=applicability_conditions or {},
        )
        return self.resolver.resolve(ctx)

    def resolve_emission_factor(
        self, jurisdiction: str = "IN", effective_date: Optional[Union[date, str]] = None
    ) -> float:
        """Resolve CEA grid emission factor via resolver if present, else return static benchmark."""
        if self.resolver is not None:
            resolved = self.resolve_reference(
                identifier="cea_grid_emission_factor",
                category="grid_emission",
                jurisdiction=jurisdiction,
                effective_date=effective_date,
            )
            val = getattr(resolved, "value", getattr(resolved, "normalized_value", None))
            if val is not None:
                return float(val)
        return CEA_GRID_EMISSION_FACTOR_KG_PER_KWH

    def resolve_appliance_specs(
        self,
        identifier: str,
        specifications: Optional[Dict[str, Any]] = None,
        jurisdiction: str = "IN",
        effective_date: Optional[Union[date, str]] = None,
    ) -> Any:
        """Resolve appliance technical specifications using configured ReferenceResolver."""
        return self.resolve_reference(
            identifier=identifier,
            category="appliance",
            jurisdiction=jurisdiction,
            effective_date=effective_date,
            specifications=specifications,
        )
