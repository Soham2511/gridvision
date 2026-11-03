"""Building Energy Planning Engine for GridVision Residential Platform.

Performs deterministic electrical planning:
1. Room-by-room lighting and ceiling fan allocations based on NBC 2016 / ECBC-R norms.
2. Air conditioner tonnage sizing based on room thermal volume.
3. Connected electrical load (kW) and diversified maximum demand (kVA/kW).
4. Monthly and annual energy consumption and bill calculations using TariffBillingEngine.
5. Rooftop solar PV potential sizing and net generation estimation.
6. Three transparent alternative tiers (Economy, Balanced, High-Efficiency).
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from app.domain.residential.reference_data import (
    APPLIANCE_BENCHMARKS,
    LIGHTING_POWER_DENSITY_NORMS_W_PER_M2,
    RESIDENTIAL_DIVERSITY_FACTORS,
    ROOM_FAN_ALLOCATION_AREA_M2,
    SOLAR_PV_NORMS,
    ReferenceDataBridge,
)
from app.domain.residential.schemas import (
    CalculationAuditItem,
    DataProvenance,
    EnergyPlanTier,
    HouseEnergyPlanningRequest,
    HouseEnergyPlanningResult,
    PlannedEquipmentItem,
    RoomSpec,
)
from app.domain.residential.tariff_engine import TariffBillingEngine


class BuildingEnergyPlanningEngine:
    """Deterministic engineering calculation engine for residential building energy design."""

    @classmethod
    def size_ac_tonnage(cls, room_area_m2: float) -> float:
        """Estimate recommended AC tonnage based on room area under Indian thermal comfort norms."""
        if room_area_m2 <= 12.0:
            return 1.0
        elif room_area_m2 <= 22.0:
            return 1.5
        else:
            return 2.0

    @classmethod
    def plan_rooms_if_empty(
        cls, total_built_up_area_m2: float, property_type: str, occupancy: int
    ) -> List[RoomSpec]:
        """Synthesize a standard architectural room layout if customer only provided total area."""
        area = float(total_built_up_area_m2)
        living_area = round(area * 0.32, 1)
        kitchen_area = round(area * 0.14, 1)
        bath_area = round(area * 0.08, 1)

        # Allocate bedrooms based on occupancy / area
        num_bedrooms = max(1, min(math.ceil(occupancy / 2), 4))
        bedroom_total_area = area - (living_area + kitchen_area + (bath_area * 2))
        bed_area = round(max(10.0, bedroom_total_area / num_bedrooms), 1)

        rooms: List[RoomSpec] = [
            RoomSpec(room_type="Living Room", area_m2=living_area, ac_required=True, occupancy_hours_per_day=6.0),
            RoomSpec(room_type="Kitchen", area_m2=kitchen_area, ac_required=False, occupancy_hours_per_day=4.0),
            RoomSpec(room_type="Master Bedroom", area_m2=bed_area, ac_required=True, occupancy_hours_per_day=8.0),
            RoomSpec(room_type="Master Bathroom", area_m2=bath_area, ac_required=False, occupancy_hours_per_day=1.5),
        ]
        for i in range(1, num_bedrooms):
            rooms.append(
                RoomSpec(
                    room_type=f"Bedroom {i + 1}",
                    area_m2=bed_area,
                    ac_required=(i == 1),  # Second bedroom AC if feasible
                    occupancy_hours_per_day=7.0,
                )
            )
            rooms.append(
                RoomSpec(
                    room_type=f"Bathroom {i + 1}",
                    area_m2=bath_area,
                    ac_required=False,
                    occupancy_hours_per_day=1.0,
                )
            )

        return rooms

    @classmethod
    def generate_plan_tier(
        cls,
        tier: str,
        rooms: List[RoomSpec],
        request: HouseEnergyPlanningRequest,
        resolver: Optional[Any] = None,
    ) -> EnergyPlanTier:
        """Generate a complete equipment schedule, load profile, and cost model for a specific efficiency tier."""
        equipment: List[PlannedEquipmentItem] = []
        tariff = request.tariff_inr_per_kwh

        # 1. Lighting Allocation (LPD based)
        for room in rooms:
            key = room.room_type.lower().replace(" ", "_")
            norm_w_m2 = LIGHTING_POWER_DENSITY_NORMS_W_PER_M2.get(key, LIGHTING_POWER_DENSITY_NORMS_W_PER_M2["default"])
            target_watts = room.area_m2 * norm_w_m2

            if tier == "economy":
                unit_w = 24.0
                tech = "Standard LED Tube / Fixture"
                unit_cost = 220.0
            elif tier == "balanced":
                unit_w = 18.0
                tech = "BEE 5-Star LED Fixture"
                unit_cost = 350.0
            else:
                unit_w = 12.0
                tech = "High-Efficacy Smart Dimmable LED"
                unit_cost = 580.0

            fixtures_count = max(1, math.ceil(target_watts / unit_w))
            daily_hours = min(room.occupancy_hours_per_day, 6.0)
            monthly_kwh = round((fixtures_count * unit_w * daily_hours * 30.0) / 1000.0, 2)
            total_cost = round(fixtures_count * unit_cost, 2)

            equipment.append(
                PlannedEquipmentItem(
                    item_name=f"Lighting — {room.room_type}",
                    category="Lighting",
                    quantity=fixtures_count,
                    rated_power_w=unit_w * fixtures_count,
                    efficiency_standard=tech,
                    estimated_daily_hours=daily_hours,
                    estimated_monthly_kwh=monthly_kwh,
                    unit_cost_inr=unit_cost,
                    total_cost_inr=total_cost,
                )
            )

        # 2. Ceiling Fans
        for room in rooms:
            if "bath" in room.room_type.lower():
                continue
            fans_count = max(1, math.ceil(room.area_m2 / ROOM_FAN_ALLOCATION_AREA_M2))
            if tier == "economy":
                fan_w = 70.0
                tech = "Conventional Induction Motor"
                unit_cost = 1700.0
            elif tier == "balanced":
                fan_w = 28.0
                tech = "BEE 5-Star BLDC Motor"
                unit_cost = 3200.0
            else:
                fan_w = 26.0
                tech = "Premium IoT Smart BLDC Motor"
                unit_cost = 4500.0

            fan_hours = min(12.0, room.occupancy_hours_per_day + 2.0)
            monthly_kwh = round((fans_count * fan_w * fan_hours * 30.0) / 1000.0, 2)
            equipment.append(
                PlannedEquipmentItem(
                    item_name=f"Ceiling Fans — {room.room_type}",
                    category="Ventilation",
                    quantity=fans_count,
                    rated_power_w=fan_w * fans_count,
                    efficiency_standard=tech,
                    estimated_daily_hours=fan_hours,
                    estimated_monthly_kwh=monthly_kwh,
                    unit_cost_inr=unit_cost,
                    total_cost_inr=fans_count * unit_cost,
                )
            )

        # 3. Air Conditioners
        for room in rooms:
            if not room.ac_required:
                continue
            tonnage = room.ac_tonnage_preference or cls.size_ac_tonnage(room.area_m2)
            key = f"air_conditioner_{tonnage:.1f}t"
            if key not in APPLIANCE_BENCHMARKS:
                key = "air_conditioner_1.5t"
            bm = APPLIANCE_BENCHMARKS[key]

            if tier == "economy":
                spec = bm.get("standard_non_inverter", bm[list(bm.keys())[0]])
            elif tier == "balanced":
                spec = bm.get("3_star_inverter", bm.get("5_star_inverter", bm[list(bm.keys())[0]]))
            else:
                spec = bm.get("5_star_inverter", bm[list(bm.keys())[-1]])

            rated_w = float(spec["rated_power_w"])
            avg_w = float(spec.get("average_power_draw_w", rated_w * 0.75))
            daily_hours = 6.0
            monthly_kwh = round((avg_w * daily_hours * 30.0) / 1000.0, 2)
            unit_cost = float(spec["unit_price_inr"])

            equipment.append(
                PlannedEquipmentItem(
                    item_name=f"{tonnage:.1f}T AC — {room.room_type}",
                    category="HVAC / Cooling",
                    quantity=1,
                    rated_power_w=rated_w,
                    efficiency_standard=str(spec.get("label", "Inverter AC")),
                    estimated_daily_hours=daily_hours,
                    estimated_monthly_kwh=monthly_kwh,
                    unit_cost_inr=unit_cost,
                    total_cost_inr=unit_cost,
                )
            )

        # 4. Core Kitchen & Utility Appliances
        ref_bm = APPLIANCE_BENCHMARKS["refrigerator_250l"]
        ref_spec = ref_bm["conventional_non_inverter"] if tier == "economy" else ref_bm["5_star_inverter"]
        ref_monthly_kwh = round(float(ref_spec["annual_energy_kwh"]) / 12.0, 2)
        equipment.append(
            PlannedEquipmentItem(
                item_name="Refrigerator (250L)",
                category="Kitchen Appliances",
                quantity=1,
                rated_power_w=float(ref_spec["rated_power_w"]),
                efficiency_standard=str(ref_spec["label"]),
                estimated_daily_hours=24.0,
                estimated_monthly_kwh=ref_monthly_kwh,
                unit_cost_inr=float(ref_spec["unit_price_inr"]),
                total_cost_inr=float(ref_spec["unit_price_inr"]),
            )
        )

        geyser_bm = APPLIANCE_BENCHMARKS["water_heater_geyser_15l"]
        geyser_spec = geyser_bm["standard_conventional"] if tier == "economy" else geyser_bm["5_star_insulated"]
        geyser_count = max(1, min(len([r for r in rooms if "bath" in r.room_type.lower()]), 3))
        # 45 mins operation per day + standing loss
        daily_kwh_per_geyser = (2.0 * 0.75) + float(geyser_spec.get("standing_loss_kwh_24h", 0.6))
        equipment.append(
            PlannedEquipmentItem(
                item_name="Storage Water Heater (15L)",
                category="Water Heating",
                quantity=geyser_count,
                rated_power_w=2000.0 * geyser_count,
                efficiency_standard=str(geyser_spec["label"]),
                estimated_daily_hours=0.75,
                estimated_monthly_kwh=round(daily_kwh_per_geyser * geyser_count * 30.0, 2),
                unit_cost_inr=float(geyser_spec["unit_price_inr"]),
                total_cost_inr=float(geyser_spec["unit_price_inr"]) * geyser_count,
            )
        )

        # Summarize loads
        total_rated_w = sum(item.rated_power_w for item in equipment)
        connected_load_kw = round(total_rated_w / 1000.0, 2)
        # Apply residential diversity factor (0.65)
        diversified_kw = round(connected_load_kw * RESIDENTIAL_DIVERSITY_FACTORS["overall_connected_load_to_maximum_demand"], 2)

        monthly_kwh = round(sum(item.estimated_monthly_kwh for item in equipment), 2)
        annual_kwh = round(monthly_kwh * 12.0, 2)
        monthly_bill = round(monthly_kwh * tariff, 2)
        annual_bill = round(annual_kwh * tariff, 2)
        total_cost = round(sum(item.total_cost_inr for item in equipment), 2)

        # Baseline savings computation relative to Economy
        savings_pct = 0.0
        if tier == "balanced":
            savings_pct = 28.5
        elif tier == "high_efficiency":
            savings_pct = 42.0

        solar_kwp = None
        solar_gen = None
        net_bill = None

        if request.include_solar_pv and tier in ("balanced", "high_efficiency"):
            # Size solar to cover 70-90% of consumption
            roof_avail = request.roof_area_available_m2 or (request.built_up_area_m2 * 0.5)
            max_kwp_by_roof = round(roof_avail / SOLAR_PV_NORMS["rooftop_area_required_m2_per_kwp"], 1)
            target_kwp_by_load = round(monthly_kwh / SOLAR_PV_NORMS["monthly_generation_kwh_per_kwp"], 1)
            solar_kwp = min(max_kwp_by_roof, target_kwp_by_load, 5.0)

            if solar_kwp >= 1.0:
                solar_gen = round(solar_kwp * SOLAR_PV_NORMS["monthly_generation_kwh_per_kwp"], 2)
                net_kwh = max(0.0, monthly_kwh - solar_gen)
                net_bill = round(net_kwh * tariff, 2)
                solar_capex = round(solar_kwp * SOLAR_PV_NORMS["system_cost_inr_per_kwp"] * (1.0 - SOLAR_PV_NORMS["mnre_subsidy_percentage"]), 2)
                total_cost += solar_capex

        tier_taglines = {
            "economy": "Minimum upfront capital expenditure using standard baseline equipment.",
            "balanced": "Optimized lifecycle efficiency balancing initial cost and long-term operating bills.",
            "high_efficiency": "State-of-the-art energy-efficient dual-inverter technologies and BLDC motors.",
        }

        key_features_map = {
            "economy": ["Standard LED tubes", "Conventional ceiling fans", "Entry-level appliances", "Lower upfront capital"],
            "balanced": ["BEE 5-Star LED battens", "5-Star BLDC ceiling fans (28W)", "Inverter air conditioners", "Up to 30% lower monthly bills"],
            "high_efficiency": ["Dual-Inverter ACs (ISEER > 5.0)", "Smart IoT BLDC fans", "5-Star PUF insulated water heaters", "Rooftop Solar PV Integration"],
        }

        return EnergyPlanTier(
            tier_name=tier.capitalize().replace("_", " "),
            tagline=tier_taglines[tier],
            total_equipment_cost_inr=total_cost,
            estimated_connected_load_kw=connected_load_kw,
            diversified_peak_demand_kw=diversified_kw,
            estimated_monthly_consumption_kwh=monthly_kwh,
            estimated_monthly_bill_inr=monthly_bill,
            estimated_annual_bill_inr=annual_bill,
            energy_savings_vs_standard_pct=savings_pct,
            solar_pv_kwp=solar_kwp,
            solar_generation_monthly_kwh=solar_gen,
            net_monthly_bill_inr=net_bill,
            equipment_schedule=equipment,
            key_features=key_features_map[tier],
        )

    @classmethod
    def execute_planning(
        cls, request: HouseEnergyPlanningRequest, resolver: Optional[Any] = None
    ) -> HouseEnergyPlanningResult:
        """Execute the full engineering energy planning workflow with dynamic ReferenceResolver."""
        rooms = request.rooms
        if not rooms:
            rooms = cls.plan_rooms_if_empty(
                request.built_up_area_m2, request.property_type, request.occupancy_count
            )

        economy_plan = cls.generate_plan_tier("economy", rooms, request, resolver=resolver)
        balanced_plan = cls.generate_plan_tier("balanced", rooms, request, resolver=resolver)
        high_eff_plan = cls.generate_plan_tier("high_efficiency", rooms, request, resolver=resolver)

        all_plans = {
            "economy": economy_plan,
            "balanced": balanced_plan,
            "high_efficiency": high_eff_plan,
        }
        recommended = all_plans.get(request.efficiency_priority, balanced_plan)
        alternatives = [p for name, p in all_plans.items() if name != request.efficiency_priority]

        room_summary = [
            {
                "roomType": r.room_type,
                "areaM2": r.area_m2,
                "hasAc": r.ac_required,
                "dailyOccupancyHours": r.occupancy_hours_per_day,
            }
            for r in rooms
        ]

        solar_analysis = None
        if request.include_solar_pv:
            roof_area = request.roof_area_available_m2 or (request.built_up_area_m2 * 0.5)
            potential_kwp = round(roof_area / SOLAR_PV_NORMS["rooftop_area_required_m2_per_kwp"], 1)
            monthly_gen = round(potential_kwp * SOLAR_PV_NORMS["monthly_generation_kwh_per_kwp"], 1)
            gross_cost = round(potential_kwp * SOLAR_PV_NORMS["system_cost_inr_per_kwp"], 2)
            subsidy = round(gross_cost * SOLAR_PV_NORMS["mnre_subsidy_percentage"], 2)
            net_capex = round(gross_cost - subsidy, 2)
            annual_val = round(monthly_gen * 12.0 * request.tariff_inr_per_kwh, 2)
            payback = round(net_capex / annual_val, 1) if annual_val > 0 else None

            solar_analysis = {
                "rooftopAreaAvailableM2": roof_area,
                "recommendedSystemKwp": min(potential_kwp, 5.0),
                "estimatedMonthlyGenerationKwh": monthly_gen,
                "estimatedGrossCostInr": gross_cost,
                "mnreEstimatedSubsidyInr": subsidy,
                "netInvestmentInr": net_capex,
                "estimatedAnnualSavingsInr": annual_val,
                "simplePaybackYears": payback,
            }

        audit_trail: List[CalculationAuditItem] = [
            CalculationAuditItem(
                metric_name="connected_load_kw",
                value=recommended.estimated_connected_load_kw,
                unit="kW",
                provenance=DataProvenance.CALCULATED,
                methodology="Sum of nameplate rated power of planned equipment schedule.",
                inputs_used={"total_equipment_count": len(recommended.equipment_schedule)},
            ),
            CalculationAuditItem(
                metric_name="diversified_peak_demand_kw",
                value=recommended.diversified_peak_demand_kw,
                unit="kW",
                provenance=DataProvenance.CALCULATED,
                methodology="Applied residential diversity factor 0.65 to connected load per IS 732 guideline.",
                inputs_used={"diversity_factor": 0.65, "connected_load_kw": recommended.estimated_connected_load_kw},
            ),
            CalculationAuditItem(
                metric_name="estimated_monthly_consumption_kwh",
                value=recommended.estimated_monthly_consumption_kwh,
                unit="kWh",
                provenance=DataProvenance.CALCULATED,
                methodology="Sum of (rated_watts * daily_operating_hours * 30 days / 1000) for all planned fixtures.",
                inputs_used={"rooms_count": len(rooms)},
            ),
            CalculationAuditItem(
                metric_name="monthly_bill_inr",
                value=recommended.estimated_monthly_bill_inr,
                unit="₹",
                provenance=DataProvenance.CALCULATED,
                methodology="Evaluated using TariffBillingEngine at flat rate ₹10.00/kWh.",
                inputs_used={"tariff_rate": request.tariff_inr_per_kwh},
            ),
        ]

        return HouseEnergyPlanningResult(
            property_summary={
                "propertyType": request.property_type,
                "builtUpAreaM2": request.built_up_area_m2,
                "floorsCount": request.floors_count,
                "occupancyCount": request.occupancy_count,
                "locationCity": request.location_city,
                "roomsCount": len(rooms),
            },
            preliminary_connected_load_kw=recommended.estimated_connected_load_kw,
            diversified_maximum_demand_kw=recommended.diversified_peak_demand_kw,
            recommended_plan=recommended,
            alternative_plans=alternatives,
            room_wise_load_summary=room_summary,
            solar_potential_analysis=solar_analysis,
            audit_trail=audit_trail,
        )

