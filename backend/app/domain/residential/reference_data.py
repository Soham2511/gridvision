"""Verified reference datasets and official engineering benchmarks for Residential Energy.

Sources:
- Bureau of Energy Efficiency (BEE) Standards & Labeling Programme (India).
- National Building Code (NBC 2016) Part 8 / Energy Conservation Building Code (ECBC-R).
- Central Electricity Authority (CEA) CO2 Baseline Database for Indian Power Sector (0.82 kg CO2/kWh).
- Ministry of New and Renewable Energy (MNRE) Rooftop Solar Guidelines.

Includes ReferenceDataBridge providing seamless interoperability between legacy static
benchmark dictionaries and the dynamic ReferenceResolver service.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Central Electricity Authority (CEA) Indian grid emission intensity factor (kg CO2 / kWh)
CEA_GRID_EMISSION_FACTOR_KG_PER_KWH = 0.82

# National Building Code / ECBC-R Lighting Power Density (LPD) norms in Watts per m²
LIGHTING_POWER_DENSITY_NORMS_W_PER_M2: Dict[str, float] = {
    "living_room": 5.0,
    "master_bedroom": 4.5,
    "bedroom": 4.0,
    "kitchen": 6.5,
    "bathroom": 4.0,
    "balcony": 2.5,
    "dining_room": 5.0,
    "study": 6.0,
    "staircase_corridor": 3.0,
    "default": 4.5,
}

# Standard Ceiling Fan density (1 fan per 12-14 m² room area)
ROOM_FAN_ALLOCATION_AREA_M2 = 14.0

# BEE Standards & Technology Benchmarks for Household Appliances
APPLIANCE_BENCHMARKS: Dict[str, Dict[str, Any]] = {
    "air_conditioner_1.5t": {
        "description": "1.5 Ton Room Air Conditioner",
        "standard_non_inverter": {
            "label": "1-2 Star / Non-Inverter Legacy",
            "rated_power_w": 1650.0,
            "average_power_draw_w": 1450.0,
            "typical_iseer": 3.1,
            "annual_energy_kwh_1600h": 1450.0 * 1600 / 1000,
            "unit_price_inr": 28000.0,
        },
        "3_star_inverter": {
            "label": "3-Star BEE Inverter",
            "rated_power_w": 1400.0,
            "average_power_draw_w": 950.0,
            "typical_iseer": 3.85,
            "annual_energy_kwh_1600h": 950.0 * 1600 / 1000,
            "unit_price_inr": 34000.0,
        },
        "5_star_inverter": {
            "label": "5-Star BEE Dual-Inverter",
            "rated_power_w": 1250.0,
            "average_power_draw_w": 680.0,
            "typical_iseer": 5.2,
            "annual_energy_kwh_1600h": 680.0 * 1600 / 1000,
            "unit_price_inr": 42000.0,
        },
    },
    "air_conditioner_1.0t": {
        "description": "1.0 Ton Room Air Conditioner",
        "standard_non_inverter": {
            "label": "1-2 Star Non-Inverter",
            "rated_power_w": 1200.0,
            "average_power_draw_w": 1050.0,
            "unit_price_inr": 24000.0,
        },
        "5_star_inverter": {
            "label": "5-Star Inverter",
            "rated_power_w": 950.0,
            "average_power_draw_w": 480.0,
            "unit_price_inr": 36000.0,
        },
    },
    "ceiling_fan": {
        "description": "1200 mm Sweep Ceiling Fan",
        "conventional_induction": {
            "label": "Conventional Induction Motor",
            "rated_power_w": 75.0,
            "average_power_draw_w": 70.0,
            "unit_price_inr": 1600.0,
        },
        "bldc_energy_efficient": {
            "label": "5-Star BEE BLDC Motor (Brushless DC)",
            "rated_power_w": 28.0,
            "average_power_draw_w": 28.0,
            "unit_price_inr": 3100.0,
        },
    },
    "refrigerator_250l": {
        "description": "250L Frost-Free Double Door Refrigerator",
        "conventional_non_inverter": {
            "label": "Legacy 2-Star Conventional",
            "rated_power_w": 180.0,
            "annual_energy_kwh": 310.0,
            "average_power_draw_w": 35.4,
            "unit_price_inr": 19000.0,
        },
        "5_star_inverter": {
            "label": "5-Star Smart Inverter Compressor",
            "rated_power_w": 110.0,
            "annual_energy_kwh": 185.0,
            "average_power_draw_w": 21.1,
            "unit_price_inr": 26000.0,
        },
    },
    "water_heater_geyser_15l": {
        "description": "15L Storage Water Heater",
        "standard_conventional": {
            "label": "Legacy 2-Star Storage Geyser",
            "rated_power_w": 2000.0,
            "standing_loss_kwh_24h": 0.85,
            "unit_price_inr": 6000.0,
        },
        "5_star_insulated": {
            "label": "5-Star High-Density PUF Insulated",
            "rated_power_w": 2000.0,
            "standing_loss_kwh_24h": 0.45,
            "unit_price_inr": 9500.0,
        },
    },
    "lighting": {
        "cfl_tube_fixture": {
            "label": "CFL / Fluorescent T8 Tube",
            "rated_power_w": 36.0,
            "luminous_efficacy_lm_w": 60.0,
            "unit_price_inr": 150.0,
        },
        "led_high_efficiency": {
            "label": "BEE 5-Star LED Batten / Downlight",
            "rated_power_w": 18.0,
            "luminous_efficacy_lm_w": 120.0,
            "unit_price_inr": 350.0,
        },
    },
}

# Rooftop Solar PV Benchmark Parameters (MNRE norms for Indian climatic zones)
SOLAR_PV_NORMS = {
    "rooftop_area_required_m2_per_kwp": 10.0,
    "annual_generation_kwh_per_kwp": 1450.0,  # ~4.0 kWh/kWp/day
    "monthly_generation_kwh_per_kwp": 120.0,
    "system_cost_inr_per_kwp": 52000.0,      # Market rate with net-metering & mounting
    "mnre_subsidy_percentage": 0.30,         # PM Surya Ghar scheme subsidy ~30-40% up to 3 kWp
    "system_lifespan_years": 25,
    "annual_degradation_pct": 0.7,
}

# Standard Indian Residential Diversity Factors (IS 732 / CEA electrical design guide)
RESIDENTIAL_DIVERSITY_FACTORS = {
    "lighting_and_fans": 0.70,   # Not all lights and fans are on at full capacity simultaneously
    "small_appliances": 0.50,    # TVs, computers, chargers
    "heavy_appliances": 0.60,    # ACs, geysers, motors, microwave
    "overall_connected_load_to_maximum_demand": 0.65,
}


# --- Bridge Helper & Adapter for ReferenceResolver ---

class ReferenceDataBridge:
    """Adapter bridging legacy static reference data dictionaries and dynamic ReferenceResolver."""

    def __init__(self, resolver: Any = None) -> None:
        self.resolver = resolver

    def get_emission_factor(
        self, jurisdiction: str = "IN", effective_date: Optional[date] = None
    ) -> float:
        """Resolve CEA grid emission factor via resolver if present, else return static benchmark."""
        if self.resolver is not None:
            try:
                resolved = self.resolver.resolve(
                    identifier="cea_grid_emission_factor",
                    category="grid_emission",
                    jurisdiction=jurisdiction,
                    effective_date=effective_date,
                )
                val = getattr(resolved, "value", getattr(resolved, "normalized_value", None))
                if val is not None:
                    return float(val)
            except Exception as e:
                logger.debug("Bridge emission factor resolution failed: %s; using static benchmark", e)
        return CEA_GRID_EMISSION_FACTOR_KG_PER_KWH

    def get_appliance_benchmark(
        self,
        appliance_key: str,
        tier: Optional[str] = None,
        jurisdiction: str = "IN",
        effective_date: Optional[date] = None,
    ) -> Any:
        """Resolve appliance benchmark via resolver if present, else fallback to static dictionary."""
        if self.resolver is not None:
            # Try specific candidate identifiers
            candidates_to_try = []
            if tier:
                candidates_to_try.append(f"{appliance_key}_{tier}")
            candidates_to_try.append(appliance_key)

            for cand in candidates_to_try:
                try:
                    resolved = self.resolver.resolve(
                        identifier=cand,
                        category="appliance",
                        jurisdiction=jurisdiction,
                        effective_date=effective_date,
                    )
                    val = getattr(resolved, "value", getattr(resolved, "normalized_value", None))
                    if val is not None:
                        return val
                except Exception:
                    continue

        # Fallback to static dictionary
        if appliance_key in APPLIANCE_BENCHMARKS:
            bench = APPLIANCE_BENCHMARKS[appliance_key]
            if tier and tier in bench:
                return bench[tier]
            return bench
        return None

    def get_lighting_power_density(self, room_type: str) -> float:
        """Return lighting power density in W/m² for the given room."""
        return LIGHTING_POWER_DENSITY_NORMS_W_PER_M2.get(
            room_type,
            LIGHTING_POWER_DENSITY_NORMS_W_PER_M2.get("default", 4.5),
        )

    def get_fan_allocation_area(self) -> float:
        """Return floor area per fan allocation norm."""
        return ROOM_FAN_ALLOCATION_AREA_M2

    def get_solar_norm(self, key: str) -> Any:
        """Return rooftop solar PV planning norm."""
        return SOLAR_PV_NORMS.get(key)

    def get_diversity_factor(self, key: str) -> float:
        """Return electrical diversity factor."""
        return RESIDENTIAL_DIVERSITY_FACTORS.get(key, 0.65)


def get_reference_emission_factor(resolver: Any = None, jurisdiction: str = "IN") -> float:
    """Helper function to resolve emission factor with optional ReferenceResolver."""
    return ReferenceDataBridge(resolver).get_emission_factor(jurisdiction=jurisdiction)


def get_reference_appliance_benchmark(
    appliance_key: str, tier: Optional[str] = None, resolver: Any = None
) -> Any:
    """Helper function to resolve appliance benchmark with optional ReferenceResolver."""
    return ReferenceDataBridge(resolver).get_appliance_benchmark(appliance_key, tier=tier)
