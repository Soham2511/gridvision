"""Standardized Pydantic v2 domain schemas for Residential Energy Intelligence Platform.

Covers:
1. Questionnaires and dynamic field specifications.
2. Feature 1: New House Energy Planning schemas.
3. Feature 2: Appliance Purchase, Sale, and Upgrade Analysis schemas.
4. Feature 3: Personalized Energy Cost Management schemas.
5. Explicit Data Provenance and Calculation Audit trails.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# --- Data Provenance & Audit Trail ---

class DataProvenance(str, Enum):
    """Authoritative source tracking for all residential data points."""
    EXISTING_DATASET = "existing_dataset"               # From customer_silver / customer_gold parquet
    CUSTOMER_PROVIDED = "customer_provided"             # Entered by the customer in questionnaires/chat
    OFFICIAL_REFERENCE = "official_reference"           # BEE, CEA, BIS, National Building Code standards
    MANUFACTURER_SPEC = "manufacturer_specification"    # Verified manufacturer nameplate specs
    VERIFIED_MARKET_QUOTE = "verified_market_quote"     # Confirmed vendor / market quotation
    CALCULATED = "calculated"                           # Produced by deterministic domain engine
    FORECAST = "forecast"                               # Produced by predictive ML or extrapolation model


class CalculationAuditItem(BaseModel):
    """Traceable audit item explaining derivation, formula, and source inputs."""
    metric_name: str
    value: Union[float, int, str, bool]
    unit: Optional[str] = None
    provenance: DataProvenance
    methodology: str
    inputs_used: Dict[str, Any] = Field(default_factory=dict)
    notes: Optional[str] = None


# --- Phase B: Reusable Questionnaire Framework ---

class QuestionInputType(str, Enum):
    TEXT = "text"
    NUMBER = "number"
    CURRENCY = "currency"
    DROPDOWN = "dropdown"
    MULTI_SELECT = "multi_select"
    BOOLEAN = "boolean"
    RADIO = "radio"


class QuestionOption(BaseModel):
    """Allowed option for dropdowns, radios, and multi-select fields."""
    value: str
    label: str
    description: Optional[str] = None


class QuestionCondition(BaseModel):
    """Conditional visibility rule: show this question only if another field matches condition."""
    depends_on_field: str
    operator: Literal["equals", "not_equals", "in", "greater_than"] = "equals"
    expected_value: Any


class QuestionField(BaseModel):
    """Specification of a single questionnaire field."""
    field_id: str
    label: str
    description: Optional[str] = None
    tooltip: Optional[str] = None
    input_type: QuestionInputType
    required: bool = True
    unit: Optional[str] = None
    placeholder: Optional[str] = None
    default_value: Optional[Any] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    options: Optional[List[QuestionOption]] = None
    conditional_visibility: Optional[QuestionCondition] = None
    category: str = "general"
    prefill_from_context_key: Optional[str] = None


class QuestionnaireSchema(BaseModel):
    """Complete questionnaire specification for a feature."""
    feature_id: str
    title: str
    subtitle: str
    description: str
    field_groups: List[str]
    fields: List[QuestionField]


# --- Feature 1: New House Energy Planning Schemas ---

class RoomSpec(BaseModel):
    """Specification of a single room in the house."""
    room_type: str = Field(..., description="e.g. Living Room, Master Bedroom, Kitchen, Bathroom, Balcony, Study")
    area_m2: float = Field(..., ge=1.0, le=500.0, description="Approximate room area in square meters")
    ac_required: bool = False
    ac_tonnage_preference: Optional[float] = Field(default=None, description="Preferred AC tonnage, e.g. 1.0, 1.5, 2.0")
    occupancy_hours_per_day: float = Field(default=8.0, ge=0.0, le=24.0)


class HouseEnergyPlanningRequest(BaseModel):
    """Input payload for New House Energy Planning."""
    property_type: Literal["apartment", "independent_house", "villa", "row_house"] = "independent_house"
    built_up_area_m2: float = Field(..., ge=15.0, le=2000.0, description="Total built-up area in m²")
    floors_count: int = Field(default=1, ge=1, le=10)
    occupancy_count: int = Field(default=4, ge=1, le=30)
    location_city: str = Field(default="Bangalore", description="City location for climate and solar insolation norms")
    rooms: List[RoomSpec] = Field(default_factory=list, description="Room-wise specifications")
    budget_inr: float = Field(default=150000.0, ge=10000.0, description="Customer upfront equipment/electrical budget in ₹")
    efficiency_priority: Literal["economy", "balanced", "high_efficiency"] = "balanced"
    include_solar_pv: bool = False
    roof_area_available_m2: Optional[float] = Field(default=None, ge=0.0)
    include_battery_storage: bool = False
    include_ev_charger: bool = False
    tariff_inr_per_kwh: float = Field(default=10.0, ge=1.0)


class PlannedEquipmentItem(BaseModel):
    """Individual recommended equipment specification in the energy plan."""
    item_name: str
    category: str
    quantity: int
    rated_power_w: float
    efficiency_standard: str  # e.g., "5-Star BEE Inverter", "BLDC Motor", "LED CRI>80"
    estimated_daily_hours: float
    estimated_monthly_kwh: float
    unit_cost_inr: float
    total_cost_inr: float
    provenance: DataProvenance = DataProvenance.CALCULATED


class EnergyPlanTier(BaseModel):
    """A distinct alternative plan (e.g. Economy, Balanced, High-Efficiency)."""
    tier_name: str
    tagline: str
    total_equipment_cost_inr: float
    estimated_connected_load_kw: float
    diversified_peak_demand_kw: float
    estimated_monthly_consumption_kwh: float
    estimated_monthly_bill_inr: float
    estimated_annual_bill_inr: float
    energy_savings_vs_standard_pct: float
    solar_pv_kwp: Optional[float] = None
    solar_generation_monthly_kwh: Optional[float] = None
    net_monthly_bill_inr: Optional[float] = None
    equipment_schedule: List[PlannedEquipmentItem]
    key_features: List[str]


class HouseEnergyPlanningResult(BaseModel):
    """Output results for New House Energy Planning."""
    property_summary: Dict[str, Any]
    preliminary_connected_load_kw: float
    diversified_maximum_demand_kw: float
    recommended_plan: EnergyPlanTier
    alternative_plans: List[EnergyPlanTier]
    room_wise_load_summary: List[Dict[str, Any]]
    solar_potential_analysis: Optional[Dict[str, Any]] = None
    audit_trail: List[CalculationAuditItem]
    technical_disclaimer: str = (
        "Preliminary engineering estimate for planning purposes. "
        "Final wiring, cable sizing, and circuit protection must comply with National Electrical Code (NEC) / IS 732 "
        "and be certified by a licensed electrical contractor."
    )


# --- Feature 2: Appliance Purchase, Sale, and Upgrade Analysis Schemas ---

class ExistingApplianceSpec(BaseModel):
    """Details of the customer's current appliance being analyzed."""
    category: str = Field(..., description="e.g., Air Conditioner, Refrigerator, Geyser, Washing Machine, Ceiling Fan")
    brand_model: Optional[str] = None
    rated_power_w: float = Field(..., ge=5.0, le=10000.0, description="Rated power in Watts")
    efficiency_label: str = Field(default="Non-Inverter / 1-2 Star BEE", description="Star rating or technology")
    age_years: float = Field(default=5.0, ge=0.0, le=30.0)
    current_condition: Literal["working_well", "requires_frequent_repair", "degraded_performance"] = "working_well"
    daily_usage_hours: float = Field(..., ge=0.1, le=24.0)
    expected_resale_value_inr: Optional[float] = Field(default=None, ge=0.0)


class ProposedApplianceSpec(BaseModel):
    """Details of the proposed replacement or new appliance."""
    category: str = Field(...)
    brand_model: Optional[str] = None
    rated_power_w: float = Field(..., ge=5.0, le=10000.0, description="Rated power in Watts")
    efficiency_label: str = Field(default="5-Star BEE Inverter")
    purchase_price_inr: float = Field(..., ge=500.0, le=500000.0, description="Purchase cost in ₹")
    installation_cost_inr: float = Field(default=1500.0, ge=0.0)
    expected_lifespan_years: int = Field(default=10, ge=1, le=25)
    daily_usage_hours: float = Field(..., ge=0.1, le=24.0)


class ApplianceScenarioRequest(BaseModel):
    """Input payload for Appliance Purchase, Sale, or Upgrade Analysis."""
    intention: Literal["purchase_new", "replace_existing", "upgrade_existing", "sell_remove", "compare_alternatives"] = "replace_existing"
    existing_appliance: Optional[ExistingApplianceSpec] = None
    proposed_appliance: Optional[ProposedApplianceSpec] = None
    alternative_appliances: List[ProposedApplianceSpec] = Field(default_factory=list)
    tariff_inr_per_kwh: float = Field(default=10.0, ge=1.0)
    annual_tariff_escalation_pct: float = Field(default=4.0, ge=0.0, le=15.0)
    discount_rate_pct: float = Field(default=7.0, ge=0.0, le=20.0)
    analysis_period_years: int = Field(default=7, ge=1, le=15)

    @model_validator(mode="before")
    @classmethod
    def _normalize_questionnaire_payload(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        # If existing_appliance is missing or empty, build it from flat form fields
        if not data.get("existing_appliance") and (
            "existing_rated_power_w" in data or "appliance_category" in data
        ):
            cat = str(data.get("appliance_category") or data.get("category") or "Air Conditioner")
            hours = float(data.get("daily_usage_hours") or 8.0)
            rated_w = float(data.get("existing_rated_power_w") or 1650.0)
            eff = str(data.get("existing_efficiency_label") or "Non-Inverter / 1-2 Star BEE")
            age = float(data.get("existing_age_years") or 5.0)
            resale_val = data.get("expected_resale_value_inr")
            resale = float(resale_val) if resale_val not in (None, "") else None
            data["existing_appliance"] = {
                "category": cat,
                "rated_power_w": rated_w,
                "efficiency_label": eff,
                "age_years": age,
                "daily_usage_hours": hours,
                "expected_resale_value_inr": resale,
            }

        # If proposed_appliance is missing or empty, build it from flat form fields
        if not data.get("proposed_appliance") and (
            "proposed_rated_power_w" in data or "proposed_purchase_price_inr" in data or "appliance_category" in data
        ):
            cat = str(data.get("appliance_category") or data.get("category") or "Air Conditioner")
            hours = float(data.get("daily_usage_hours") or 8.0)
            rated_w = float(data.get("proposed_rated_power_w") or 1250.0)
            eff = str(data.get("proposed_efficiency_label") or "5-Star BEE Inverter")
            price = float(data.get("proposed_purchase_price_inr") or 35000.0)
            data["proposed_appliance"] = {
                "category": cat,
                "rated_power_w": rated_w,
                "efficiency_label": eff,
                "purchase_price_inr": price,
                "daily_usage_hours": hours,
            }

        return data


class YearCashflow(BaseModel):
    """Year-by-year financial cash flow for lifecycle comparison."""
    year: int
    baseline_operating_cost_inr: float
    proposed_operating_cost_inr: float
    annual_savings_inr: float
    cumulative_net_savings_inr: float


class ApplianceScenarioResult(BaseModel):
    """Output results for Appliance Scenario Analysis."""
    intention: str
    existing_annual_kwh: float
    proposed_annual_kwh: float
    annual_energy_savings_kwh: float
    annual_cost_savings_inr: float
    net_upfront_investment_inr: float
    simple_payback_years: Optional[float] = None
    break_even_year: Optional[int] = None
    total_lifecycle_cost_existing_inr: float
    total_lifecycle_cost_proposed_inr: float
    net_lifetime_savings_inr: float
    return_on_investment_pct: Optional[float] = None
    co2_reduction_kg_per_year: float
    cashflows: List[YearCashflow]
    sensitivity_scenarios: List[Dict[str, Any]]
    recommendation_verdict: str
    audit_trail: List[CalculationAuditItem]


# --- Feature 3: Personalized Energy Cost Management Schemas ---

class CostManagementRequest(BaseModel):
    """Input payload for Personalized Energy Cost Management."""
    target_monthly_savings_inr: Optional[float] = Field(default=None, ge=100.0)
    available_investment_budget_inr: float = Field(default=50000.0, ge=0.0, description="Available capital for efficiency upgrades (₹0 for behavioral only)")
    primary_objective: Literal["maximize_savings", "fastest_payback", "low_upfront_cost", "environmental_impact"] = "maximize_savings"
    max_acceptable_payback_years: float = Field(default=4.0, ge=0.5, le=15.0)
    willingness_to_shift_schedules: bool = True
    willingness_to_replace_appliances: bool = True
    solar_interest: bool = True
    battery_interest: bool = False
    tariff_inr_per_kwh: float = Field(default=10.0, ge=1.0)


class CostSavingStrategy(BaseModel):
    """Individual tailored energy-saving recommendation."""
    strategy_id: str
    title: str
    category: Literal["zero_cost_behavioral", "low_cost_quick_win", "appliance_upgrade", "rooftop_solar"]
    description: str
    action_steps: List[str]
    supporting_evidence: str
    estimated_monthly_savings_kwh: float
    estimated_monthly_savings_inr: float
    estimated_annual_savings_inr: float
    upfront_investment_inr: float
    simple_payback_months: Optional[float] = None
    priority_rank: int
    is_eligible: bool = True
    eligibility_notes: Optional[str] = None
    provenance: DataProvenance = DataProvenance.CALCULATED


class CostManagementResult(BaseModel):
    """Output results for Personalized Energy Cost Management."""
    current_monthly_baseline_kwh: float
    current_monthly_bill_inr: float
    target_monthly_savings_inr: Optional[float] = None
    achievable_monthly_savings_inr: float
    achievable_annual_savings_inr: float
    total_investment_required_inr: float
    blended_payback_years: Optional[float] = None
    strategies: List[CostSavingStrategy]
    package_recommendations: Dict[str, Any]
    audit_trail: List[CalculationAuditItem]
    limitations: List[str] = Field(default_factory=list)

