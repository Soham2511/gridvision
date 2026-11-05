"""LangChain tool adapters for Residential Energy Platform Features.

Exposes the 3 dedicated feature use cases as standard LangChain tools:
1. plan_house_energy -> PlanHouseEnergyUseCase
2. analyze_appliance_scenario -> AnalyzeApplianceScenarioUseCase
3. generate_energy_cost_recommendations -> ManageEnergyCostUseCase

Strictly reuses identical application use cases with zero duplication.
"""

from __future__ import annotations

import json
from typing import Any, List, Literal, Optional, Type
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from app.application.residential.analyze_appliance import AnalyzeApplianceScenarioUseCase
from app.application.residential.manage_cost import ManageEnergyCostUseCase
from app.application.residential.plan_house_energy import PlanHouseEnergyUseCase
from app.domain.residential.schemas import (
    ApplianceScenarioRequest,
    CostManagementRequest,
    ExistingApplianceSpec,
    HouseEnergyPlanningRequest,
    ProposedApplianceSpec,
)


# --- 1. Plan House Energy Tool ---

class PlanHouseEnergyInput(BaseModel):
    """Input parameters for planning house energy layout, appliance schedule, and connected load."""

    built_up_area_m2: float = Field(
        ...,
        description="Total enclosed residential built-up area in square meters (e.g. 120.0 m²)",
    )
    property_type: Literal["apartment", "independent_house", "villa", "row_house"] = Field(
        default="independent_house",
        description="Type of residential structure",
    )
    floors_count: int = Field(default=1, ge=1, le=10, description="Number of floors")
    occupancy_count: int = Field(default=4, ge=1, le=30, description="Number of regular residents")
    location_city: str = Field(default="Bangalore", description="City location")
    bedrooms_count: int = Field(default=3, ge=1, le=20, description="Number of bedrooms")
    bathrooms_count: int = Field(default=2, ge=1, le=20, description="Number of bathrooms")
    living_dining_count: int = Field(default=1, ge=1, le=10, description="Number of living/dining areas")
    daytime_occupancy: Literal["mostly_away", "home_during_day", "work_from_home"] = Field(
        default="mostly_away",
        description="Daytime occupancy profile: 'mostly_away', 'home_during_day', or 'work_from_home'",
    )
    budget_inr: float = Field(default=150000.0, description="Approximate electrical fixtures and equipment budget in ₹")
    efficiency_priority: Literal["economy", "balanced", "high_efficiency"] = Field(
        default="balanced",
        description="Preferred plan tier: 'economy', 'balanced', or 'high_efficiency'",
    )
    ac_required: bool = Field(default=False, description="Whether air conditioners are required")
    ac_count: int = Field(default=0, ge=0, le=10, description="Number of AC units")
    ac_intended_rooms: Optional[List[str]] = Field(default_factory=list, description="Intended rooms for AC (e.g. ['bedrooms', 'living_dining'])")
    ac_usage_range: Optional[Literal["up_to_4_hours", "4_to_8_hours", "more_than_8_hours", "not_sure"]] = Field(
        default="4_to_8_hours", description="Daily cooling hours"
    )
    fans_required: bool = Field(default=True, description="Whether ceiling fans are required")
    fans_count: Optional[int] = Field(default=None, ge=0, le=30, description="Number of ceiling fans")
    geyser_required: bool = Field(default=False, description="Whether water heaters/geysers are required")
    geyser_count: int = Field(default=0, ge=0, le=10, description="Number of geysers")
    geyser_usage: Optional[Literal["occasional", "regular", "frequent", "not_sure"]] = Field(
        default="regular", description="Geyser usage frequency"
    )
    refrigerator_required: bool = Field(default=True, description="Whether refrigerator is required")
    refrigerator_count: int = Field(default=1, ge=0, le=5, description="Number of refrigerators")
    washing_machine_required: bool = Field(default=False, description="Whether washing machine is required")
    washing_machine_count: int = Field(default=0, ge=0, le=3, description="Number of washing machines")
    water_pump_required: bool = Field(default=False, description="Whether water pump/borewell is required")
    induction_cooktop_required: bool = Field(default=False, description="Whether induction cooktop is required")
    microwave_required: bool = Field(default=False, description="Whether microwave oven is required")
    additional_high_load_notes: Optional[str] = Field(default=None, description="Custom high-load equipment notes")
    include_solar_pv: bool = Field(default=False, description="Whether to evaluate on-site rooftop solar PV")
    roof_area_available_m2: Optional[float] = Field(default=None, ge=0.0, description="Usable rooftop area in m²")
    solar_roof_access: Optional[Literal["private", "shared"]] = Field(default=None, description="Roof access type")
    include_ev_charger: bool = Field(default=False, description="Whether to plan EV charging provision")
    ev_category: Optional[Literal["two_wheeler", "four_wheeler", "both"]] = Field(default=None, description="EV vehicle category")
    ev_charger_rating_preference: Optional[str] = Field(default=None, description="EV charger rating preference")


class PlanHouseEnergyTool(BaseTool):
    """Plans an energy-efficient residential electrical and energy setup based on property characteristics."""

    name: str = "plan_house_energy"
    description: str = (
        "Create a residential electrical/equipment plan from the home's area, rooms, occupancy, "
        "location, preferences, and budget. Use for planning or sizing a new/renovated home, "
        "not for analyzing an existing appliance replacement. Returns connected load, diversified "
        "demand, a room-wise schedule, modeled monthly cost, and alternative efficiency tiers. "
        "Use verified premises-profile and appliance-inventory tools first when the request "
        "depends on the customer's registered property details."
    )
    args_schema: Type[BaseModel] = PlanHouseEnergyInput

    authorized_meter_id: str
    use_case: PlanHouseEnergyUseCase = Field(default_factory=PlanHouseEnergyUseCase)

    def _run(self, **kwargs: Any) -> str:
        request = HouseEnergyPlanningRequest(**kwargs)
        response = self.use_case.execute(meter_id=self.authorized_meter_id, request=request)
        return json.dumps(response.model_dump(), indent=2)

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        return self._run(*args, **kwargs)


class PlanHouseAreaM2Tool(PlanHouseEnergyTool):
    """Alias for plan_house_energy for robust LLM tool call dispatch."""

    name: str = "plan_house_area_m2"
    description: str = (
        "Alias for plan_house_energy. Use only for a new-home or renovation plan that needs a "
        "room-wise equipment schedule and connected-load estimate from the home's area and "
        "occupancy. For replacement savings on one appliance, use analyze_appliance_scenario."
    )


# --- 2. Analyze Appliance Scenario Tool ---

class AnalyzeApplianceScenarioInput(BaseModel):
    """Input parameters for analyzing appliance purchase, replacement, or upgrade."""

    intention: Literal["purchase_new", "replace_existing", "upgrade_existing", "sell_remove"] = Field(
        default="replace_existing",
        description="Intention: 'replace_existing', 'purchase_new', 'upgrade_existing', or 'sell_remove'",
    )
    appliance_category: str = Field(
        default="Air Conditioner",
        description="Appliance category (e.g. 'Air Conditioner', 'Ceiling Fan', 'Refrigerator', 'Water Heater')",
    )
    existing_rated_power_w: float = Field(
        default=1650.0,
        description="Rated power of current appliance in Watts (e.g. 1650W for 1.5T AC, 75W for fan)",
    )
    existing_efficiency_label: str = Field(
        default="Non-Inverter / 1-2 Star BEE",
        description="Star rating or technology label of current appliance",
    )
    daily_usage_hours: float = Field(
        default=8.0,
        description="Average daily usage in hours (e.g. 8.0 hours/day)",
    )
    proposed_rated_power_w: float = Field(
        default=1250.0,
        description="Rated power of proposed appliance in Watts (e.g. 1250W for 5-star AC, 28W for BLDC fan)",
    )
    proposed_efficiency_label: str = Field(
        default="5-Star BEE Dual-Inverter",
        description="Star rating or technology label of proposed appliance",
    )
    proposed_purchase_price_inr: float = Field(
        default=39000.0,
        description="Purchase price of proposed unit in ₹",
    )
    expected_resale_value_inr: Optional[float] = Field(
        default=None,
        description="Resale or scrap proceeds for old unit in ₹ (if replacing)",
    )


class AnalyzeApplianceScenarioTool(BaseTool):
    """Analyzes appliance purchase, replacement, or upgrade scenarios for electricity savings and payback."""

    name: str = "analyze_appliance_scenario"
    description: str = (
        "Compare one existing appliance with a proposed purchase, replacement, upgrade, or removal. "
        "Use when asked about an AC/fan/refrigerator upgrade or its savings/payback. Provide the "
        "old and proposed wattage/efficiency, daily hours, and proposed price from user input or "
        "verified inventory/benchmark tools; do not invent missing specifications or prices. "
        "Returns annual kWh and bill savings, net investment, payback, break-even, and 7-year "
        "total cost of ownership. For a whole-home prioritized savings package, use "
        "generate_energy_cost_recommendations instead."
    )
    args_schema: Type[BaseModel] = AnalyzeApplianceScenarioInput

    authorized_meter_id: str
    use_case: AnalyzeApplianceScenarioUseCase = Field(default_factory=AnalyzeApplianceScenarioUseCase)

    def _run(self, **kwargs: Any) -> str:
        existing = ExistingApplianceSpec(
            category=kwargs.get("appliance_category", "Air Conditioner"),
            rated_power_w=float(kwargs.get("existing_rated_power_w", 1650.0)),
            efficiency_label=str(kwargs.get("existing_efficiency_label", "Non-Inverter / 1-2 Star BEE")),
            daily_usage_hours=float(kwargs.get("daily_usage_hours", 8.0)),
            expected_resale_value_inr=kwargs.get("expected_resale_value_inr"),
        )
        proposed = ProposedApplianceSpec(
            category=kwargs.get("appliance_category", "Air Conditioner"),
            rated_power_w=float(kwargs.get("proposed_rated_power_w", 1250.0)),
            efficiency_label=str(kwargs.get("proposed_efficiency_label", "5-Star BEE Dual-Inverter")),
            purchase_price_inr=float(kwargs.get("proposed_purchase_price_inr", 39000.0)),
            daily_usage_hours=float(kwargs.get("daily_usage_hours", 8.0)),
        )
        request = ApplianceScenarioRequest(
            intention=kwargs.get("intention", "replace_existing"),
            existing_appliance=existing,
            proposed_appliance=proposed,
        )
        response = self.use_case.execute(meter_id=self.authorized_meter_id, request=request)
        return json.dumps(response.model_dump(), indent=2)

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        return self._run(*args, **kwargs)


# --- 3. Manage Energy Cost Tool ---

class ManageEnergyCostInput(BaseModel):
    """Input parameters for personalized energy cost management."""

    available_investment_budget_inr: float = Field(
        default=40000.0,
        description="Available investment capital in ₹. Enter 0 for zero-cost / behavioral strategies only.",
    )
    target_monthly_savings_inr: Optional[float] = Field(
        default=None,
        description="Optional target monthly bill reduction in ₹",
    )
    primary_objective: Literal["maximize_savings", "fastest_payback", "low_upfront_cost", "environmental_impact"] = Field(
        default="maximize_savings",
        description="Optimization objective: 'maximize_savings', 'fastest_payback', 'low_upfront_cost', or 'environmental_impact'",
    )
    willingness_to_shift_schedules: bool = Field(
        default=True,
        description="Whether customer is willing to adjust thermostat (24°C) and shift high-draw appliances off-peak",
    )
    willingness_to_replace_appliances: bool = Field(
        default=True,
        description="Whether customer is open to upgrading inefficient fans or equipment",
    )
    solar_interest: bool = Field(
        default=True,
        description="Whether customer is interested in rooftop solar PV",
    )


class ManageEnergyCostTool(BaseTool):
    """Generates personalized energy cost reduction recommendations grounded in smart meter telemetry."""

    name: str = "generate_energy_cost_recommendations"
    description: str = (
        "Build a household-wide, prioritized electricity cost-reduction package using the "
        "authorized meter's usage, investment budget, target savings, and stated preferences. "
        "Use when the customer asks how to lower bills, requests a savings plan/package, or asks "
        "for personalized efficiency actions. Returns modeled monthly/annual savings, upfront "
        "investment, strategies, and payback. For one appliance's replacement economics, use "
        "analyze_appliance_scenario instead; recommendations are estimates, not guaranteed savings."
    )
    args_schema: Type[BaseModel] = ManageEnergyCostInput

    authorized_meter_id: str
    use_case: ManageEnergyCostUseCase = Field(default_factory=ManageEnergyCostUseCase)

    def _run(self, **kwargs: Any) -> str:
        request = CostManagementRequest(**kwargs)
        response = self.use_case.execute(meter_id=self.authorized_meter_id, request=request)
        return json.dumps(response.model_dump(), indent=2)

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        return self._run(*args, **kwargs)
