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


class PlannedEquipmentItem(BaseModel):
    """Individual recommended equipment specification in the energy plan."""
    item_name: str
    category: str
    quantity: int
    rated_power_w: float
    efficiency_standard: str  # e.g., "5-Star BEE Inverter", "BLDC Motor", "LED CRI>80"
    estimated_daily_hours: float
    estimated_monthly_kwh: float
    unit_cost_inr: Optional[float] = None
    total_cost_inr: Optional[float] = None
    cost_status: Literal["verified", "unavailable", "customer_estimate"] = "verified"
    room_assignment: Optional[str] = None
    is_provision_only: bool = False
    notes: Optional[str] = None
    provenance: DataProvenance = DataProvenance.CALCULATED


class RoomScheduleItem(BaseModel):
    """Room-wise electrical and equipment allocation."""
    room_name: str
    room_type: str = "general"  # bedroom, living_dining, kitchen, bathroom, utility, general
    equipment: List[PlannedEquipmentItem] = Field(default_factory=list)
    total_connected_load_w: float = 0.0
    ac_provision: bool = False
    notes: Optional[str] = None


class BudgetSummary(BaseModel):
    """Structured budget comparison and equipment breakdown."""
    lighting_fans_cost_inr: Optional[float] = None
    cooling_cost_inr: Optional[float] = None
    water_heating_cost_inr: Optional[float] = None
    other_equipment_cost_inr: Optional[float] = None
    total_equipment_cost_inr: float = 0.0
    estimated_equipment_cost_inr: Optional[float] = None
    allocated_budget_inr: float = 0.0
    budget_exceeded: bool = False
    budget_variance_inr: float = 0.0
    budget_status: Literal["within_budget", "exceeds_budget", "incomplete"] = "within_budget"
    cost_coverage: Literal["complete", "partial", "unavailable"] = "complete"
    unpriced_items: List[str] = Field(default_factory=list)
    wiring_installation_note: str = (
        "Equipment budget covers purchase cost of fixtures and appliances. "
        "Conduit piping, internal wiring runs, distribution boards, MCBs, "
        "and contractor installation labor are quoted separately by an electrical contractor."
    )


class PracticalRecommendationItem(BaseModel):
    """Targeted, source-backed energy optimization recommendation for the resident."""
    title: str
    category: str  # cooling, ventilation, water_heating, solar, ev, wiring_infrastructure
    rationale: str
    source: str
    expected_benefit: str
    is_quantitative: bool = False
    estimated_monthly_savings_inr: Optional[float] = None
    estimated_monthly_kwh_saved: Optional[float] = None


class SolarReadinessAnalysis(BaseModel):
    """Rooftop Solar PV feasibility or readiness assessment."""
    status: Literal["feasibility_estimated", "feasible", "preliminary_readiness", "not_requested"] = "not_requested"
    roof_area_available_m2: Optional[float] = None
    roof_access: Optional[Literal["private", "shared"]] = None
    recommended_system_kwp: Optional[float] = None
    feasible_capacity_kw: Optional[float] = None
    estimated_monthly_generation_kwh: Optional[float] = None
    estimated_gross_cost_inr: Optional[float] = None
    mnre_estimated_subsidy_inr: Optional[float] = None
    net_investment_inr: Optional[float] = None
    estimated_annual_savings_inr: Optional[float] = None
    simple_payback_years: Optional[float] = None
    feasibility_notes: List[str] = Field(default_factory=list)
    next_steps: List[str] = Field(default_factory=list)
    missing_inputs: List[str] = Field(default_factory=list)


class EvReadinessAnalysis(BaseModel):
    """Electric vehicle charging infrastructure readiness assessment."""
    status: Literal["readiness_planned", "not_requested"] = "not_requested"
    ev_category: Optional[Literal["two_wheeler", "four_wheeler", "both"]] = None
    recommended_charger_type: str = "Dedicated 16A / 3.3 kW AC Level-1"
    recommended_charger_rating_kw: Optional[float] = None
    recommended_circuit_rating: str = "16A Single-Phase (3.3 kW)"
    recommended_supply_phase: Optional[str] = None
    dedicated_circuit_required: bool = True
    safety_guidelines: List[str] = Field(default_factory=list)
    wiring_notes: str = "Protected dedicated radial sub-circuit per IS 17017 standards."
    discom_verification_needed: List[str] = Field(default_factory=list)


class EnergyPlanTier(BaseModel):
    """A distinct alternative plan (e.g. Economy, Balanced, High-Efficiency)."""
    tier_name: str
    tagline: str
    total_equipment_cost_inr: float
    cost_coverage: Literal["complete", "partial", "unavailable"] = "complete"
    estimated_connected_load_kw: float
    diversified_peak_demand_kw: float
    recommended_supply_phase: str = "Single-Phase (230V)"
    supply_phase_advisory: str = "Preliminary advisory subject to DISCOM connection sanction"
    estimated_monthly_consumption_kwh: float
    estimated_monthly_bill_inr: float
    estimated_annual_bill_inr: float
    bill_calculation_status: Literal["calculated", "unavailable"] = "calculated"
    bill_calculation_notes: Optional[str] = None
    energy_savings_vs_standard_pct: float = 0.0
    monthly_savings_pct: float = 0.0
    monthly_savings_vs_economy_inr: float = 0.0
    solar_pv_kwp: Optional[float] = None
    solar_generation_monthly_kwh: Optional[float] = None
    net_monthly_bill_inr: Optional[float] = None
    equipment_schedule: List[PlannedEquipmentItem]
    equipment_list: Optional[List[PlannedEquipmentItem]] = None
    key_features: List[str]


class HouseEnergyPlanningRequest(BaseModel):
    """Input payload for New House Energy Planning.
    
    Organized into 4 sections:
    Section A - Property Profile
    Section B - Electrical & Appliance Requirements
    Section C - Energy Efficiency & Budget
    Section D - Solar & EV Readiness
    """
    # Section A — Property Profile
    property_type: Literal["apartment", "independent_house", "villa", "row_house"] = "independent_house"
    built_up_area_m2: float = Field(..., ge=15.0, le=2000.0, description="Total built-up area in m²")
    floors_count: int = Field(default=1, ge=1, le=10)
    occupancy_count: int = Field(default=4, ge=1, le=30)
    location_city: str = Field(default="Bangalore", description="City location for climate and solar insolation norms")
    bedrooms_count: int = Field(default=3, ge=1, le=20, description="Number of bedrooms")
    bathrooms_count: int = Field(default=2, ge=1, le=20, description="Number of bathrooms")
    living_dining_count: int = Field(default=1, ge=1, le=10, description="Number of living/dining areas")
    daytime_occupancy: Literal["mostly_away", "home_during_day", "work_from_home"] = Field(
        default="mostly_away", description="Daytime occupancy profile"
    )

    # Section B — Electrical & Appliance Requirements
    ac_required: bool = False
    ac_count: int = Field(default=0, ge=0, le=20)
    ac_intended_rooms: List[str] = Field(default_factory=list)
    ac_usage_range: Optional[Literal["up_to_4_hours", "4_to_8_hours", "more_than_8_hours", "not_sure"]] = "4_to_8_hours"

    fans_required: bool = True
    fans_count: Optional[int] = Field(default=None, ge=0, le=50)

    geyser_required: bool = False
    geyser_count: int = Field(default=0, ge=0, le=15)
    geyser_usage: Optional[Literal["occasional", "regular", "frequent", "not_sure"]] = "regular"

    refrigerator_required: bool = True
    refrigerator_count: int = Field(default=1, ge=0, le=10)

    washing_machine_required: bool = False
    washing_machine_count: int = Field(default=0, ge=0, le=5)

    water_pump_required: bool = False
    induction_cooktop_required: bool = False
    microwave_required: bool = False
    additional_high_load_notes: Optional[str] = None

    # Section C — Energy Efficiency and Budget
    efficiency_priority: Literal["economy", "balanced", "high_efficiency"] = "balanced"
    budget_inr: float = Field(default=150000.0, ge=10000.0, description="Approximate budget for electrical fixtures & appliances in ₹")
    tariff_inr_per_kwh: float = Field(default=10.0, ge=0.0)

    # Section D — Solar and EV Readiness
    include_solar_pv: bool = False
    roof_area_available_m2: Optional[float] = Field(default=None, ge=0.0)
    solar_roof_access: Optional[Literal["private", "shared"]] = None

    include_battery_storage: bool = False
    include_ev_charger: bool = False
    ev_category: Optional[Literal["two_wheeler", "four_wheeler", "both"]] = None
    ev_charger_rating_preference: Optional[str] = None

    # Backward compatibility: explicit room specs
    rooms: List[RoomSpec] = Field(default_factory=list, description="Optional room-wise specifications for backward compatibility")

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def _normalize_request_data(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        d = dict(data)
        if d.get("ac_intended_rooms") is None:
            d["ac_intended_rooms"] = []
        if d.get("ac_usage_range") is None:
            d["ac_usage_range"] = "4_to_8_hours"
        if d.get("geyser_usage") is None:
            d["geyser_usage"] = "regular"
        if d.get("daytime_occupancy") is None:
            d["daytime_occupancy"] = "mostly_away"
        # Unpack nested appliances payload if provided
        if "appliances" in d and isinstance(d["appliances"], dict):
            app_dict = d.pop("appliances")
            for k, v in app_dict.items():
                if k not in d or d[k] is None:
                    d[k] = v

        # If rooms list is provided (legacy payloads), extract room counts and AC requirements
        rooms = d.get("rooms")
        if rooms and isinstance(rooms, list) and len(rooms) > 0:
            bed_count = 0
            bath_count = 0
            living_count = 0
            ac_in_rooms = 0
            for r in rooms:
                rtype = str(r.get("room_type", "") if isinstance(r, dict) else getattr(r, "room_type", "")).lower()
                if "bed" in rtype:
                    bed_count += 1
                elif "bath" in rtype:
                    bath_count += 1
                elif "living" in rtype or "dining" in rtype:
                    living_count += 1

                has_ac = r.get("ac_required", False) if isinstance(r, dict) else getattr(r, "ac_required", False)
                if has_ac:
                    ac_in_rooms += 1

            if "bedrooms_count" not in d and bed_count > 0:
                d["bedrooms_count"] = bed_count
            if "bathrooms_count" not in d and bath_count > 0:
                d["bathrooms_count"] = bath_count
            if "living_dining_count" not in d and living_count > 0:
                d["living_dining_count"] = living_count
            if ac_in_rooms > 0 and not d.get("ac_required"):
                d["ac_required"] = True
                if not d.get("ac_count"):
                    d["ac_count"] = ac_in_rooms

        # EV charging synonym normalization
        if "include_ev_charging" in d and "include_ev_charger" not in d:
            d["include_ev_charger"] = bool(d.pop("include_ev_charging"))

        # Default fan count to bedrooms + living_dining if not explicitly provided
        if d.get("fans_required", True) and d.get("fans_count") is None:
            beds = int(d.get("bedrooms_count", 3))
            living = int(d.get("living_dining_count", 1))
            d["fans_count"] = beds + living

        return d


class HouseEnergyPlanningResult(BaseModel):
    """Output results for New House Energy Planning."""
    property_summary: Dict[str, Any]
    preliminary_connected_load_kw: float
    diversified_maximum_demand_kw: float
    recommended_supply_phase: str = "Single-Phase (230V)"
    recommended_plan: EnergyPlanTier
    alternative_plans: List[EnergyPlanTier]
    alternative_tiers: Optional[List[EnergyPlanTier]] = None  # Backward compatibility alias
    has_room_assignment: bool = False
    room_wise_schedule: List[RoomScheduleItem] = Field(default_factory=list)
    unassigned_appliances: List[str] = Field(default_factory=list)
    budget_summary: Optional[BudgetSummary] = None
    recommendations: List[PracticalRecommendationItem] = Field(default_factory=list)
    solar_readiness: Optional[SolarReadinessAnalysis] = None
    ev_readiness: Optional[EvReadinessAnalysis] = None
    solar_potential_analysis: Optional[Dict[str, Any]] = None  # Backward compatibility
    room_wise_load_summary: List[Dict[str, Any]] = Field(default_factory=list)  # Backward compatibility
    audit_trail: List[CalculationAuditItem]
    assumptions: List[str] = Field(default_factory=list)
    missing_or_unverified_inputs: List[str] = Field(default_factory=list)
    technical_disclaimer: str = (
        "Preliminary home energy planning blueprint for conceptual budgeting and sizing. "
        "This is not a certified electrical installation design. "
        "Final wiring routes, cable cross-sections, conduit sizing, switchgear, distribution boards, "
        "and circuit breaker protection must be designed and certified by a licensed electrical engineer / contractor "
        "in compliance with National Electrical Code (NEC) and IS 732, and verified with the local DISCOM."
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

