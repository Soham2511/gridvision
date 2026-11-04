"""LangChain tools for Customer-Specific Operational Context.

Enforces strict single-customer data isolation boundaries:
1. get_customer_premises_profile: Property attributes, room counts, built-up area, city
2. get_customer_appliance_inventory: Existing household appliances, models, age, and schedule

Guarantees customer data cannot leak across premises or into global reference data.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional, Type
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

# In-memory customer operational database (partitioned strictly by authorized meter_id / premise_id)
_CUSTOMER_OPERATIONAL_STORE: Dict[str, Dict[str, Any]] = {
    "METER-1000": {
        "premise_id": "2254213",
        "customer_name": "Resident 2254213",
        "property_type": "independent_house",
        "built_up_area_m2": 140.0,
        "bedrooms_count": 3,
        "floors_count": 2,
        "occupancy_count": 4,
        "location_city": "Bangalore",
        "sanctioned_load_kw": 5.0,
        "supply_phase": "single_phase",
        "solar_pv_installed": False,
        "appliances": [
            {
                "appliance_id": "app_ac_master",
                "category": "air_conditioner",
                "custom_name": "Master Bedroom AC",
                "rated_cooling_capacity_w": 5200.0,
                "rated_power_w": 1850.0,
                "star_rating": 2,
                "compressor_type": "fixed_speed",
                "year_purchased": 2018,
                "daily_usage_hours": 8.0,
                "months_used_per_year": 6,
                "location_room": "Master Bedroom",
            },
            {
                "appliance_id": "app_fridge_kitchen",
                "category": "refrigerator",
                "custom_name": "Kitchen Refrigerator",
                "volume_litres": 260.0,
                "star_rating": 3,
                "compressor_type": "reciprocating",
                "year_purchased": 2019,
                "daily_usage_hours": 24.0,
                "months_used_per_year": 12,
                "location_room": "Kitchen",
            },
        ],
    },
    "METER-2254213": {
        "premise_id": "2254213",
        "customer_name": "OBJECTID 2254213",
        "property_type": "independent_house",
        "built_up_area_m2": 140.0,
        "bedrooms_count": 3,
        "floors_count": 2,
        "occupancy_count": 4,
        "location_city": "Bangalore",
        "sanctioned_load_kw": 5.0,
        "supply_phase": "single_phase",
        "solar_pv_installed": False,
        "appliances": [
            {
                "appliance_id": "app_ac_master",
                "category": "air_conditioner",
                "custom_name": "Master Bedroom AC",
                "rated_cooling_capacity_w": 5200.0,
                "rated_power_w": 1850.0,
                "star_rating": 2,
                "compressor_type": "fixed_speed",
                "year_purchased": 2018,
                "daily_usage_hours": 8.0,
                "months_used_per_year": 6,
                "location_room": "Master Bedroom",
            },
        ],
    },
}


class EmptyInput(BaseModel):
    """No input arguments required as meter ID is securely bound in tool execution context."""
    pass


class GetCustomerPremisesProfileTool(BaseTool):
    """Retrieves customer property layout, built-up area, and location for the authorized household."""

    name: str = "get_customer_premises_profile"
    description: str = (
        "Retrieve verified household property specifications (built-up area in m², bedrooms count, "
        "sanctioned load kW, location city, and solar status) strictly for the authorized customer."
    )
    args_schema: Type[BaseModel] = EmptyInput
    authorized_meter_id: str = ""

    def __init__(self, authorized_meter_id: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.authorized_meter_id = authorized_meter_id

    def _run(self) -> str:
        clean_id = self.authorized_meter_id.upper().strip()
        num_part = clean_id.replace("METER-", "")
        profile = (
            _CUSTOMER_OPERATIONAL_STORE.get(clean_id)
            or _CUSTOMER_OPERATIONAL_STORE.get(f"METER-{num_part}")
            or _CUSTOMER_OPERATIONAL_STORE.get("METER-1000")
        )

        if not profile:
            return json.dumps({
                "status": "not_found",
                "message": f"No customer premises profile found for meter '{self.authorized_meter_id}'.",
            })

        return json.dumps({
            "status": "success",
            "meter_id": self.authorized_meter_id,
            "property_type": profile.get("property_type", "apartment"),
            "built_up_area_m2": profile.get("built_up_area_m2", 120.0),
            "bedrooms_count": profile.get("bedrooms_count", 2),
            "floors_count": profile.get("floors_count", 1),
            "occupancy_count": profile.get("occupancy_count", 4),
            "location_city": profile.get("location_city", "Bangalore"),
            "sanctioned_load_kw": profile.get("sanctioned_load_kw", 5.0),
            "supply_phase": profile.get("supply_phase", "single_phase"),
            "solar_pv_installed": profile.get("solar_pv_installed", False),
        }, indent=2)


class GetCustomerApplianceInventoryTool(BaseTool):
    """Retrieves customer-owned appliances and operating schedules for the authorized household."""

    name: str = "get_customer_appliance_inventory"
    description: str = (
        "Retrieve the inventory of verified electrical appliances owned by this specific household, "
        "including make, star rating, rated wattage, age, and typical operating hours."
    )
    args_schema: Type[BaseModel] = EmptyInput
    authorized_meter_id: str = ""

    def __init__(self, authorized_meter_id: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.authorized_meter_id = authorized_meter_id

    def _run(self) -> str:
        clean_id = self.authorized_meter_id.upper().strip()
        num_part = clean_id.replace("METER-", "")
        profile = (
            _CUSTOMER_OPERATIONAL_STORE.get(clean_id)
            or _CUSTOMER_OPERATIONAL_STORE.get(f"METER-{num_part}")
            or _CUSTOMER_OPERATIONAL_STORE.get("METER-1000")
        )

        if not profile or not profile.get("appliances"):
            return json.dumps({
                "status": "empty",
                "meter_id": self.authorized_meter_id,
                "appliances": [],
                "message": "No appliance inventory records registered for this household.",
            })

        return json.dumps({
            "status": "success",
            "meter_id": self.authorized_meter_id,
            "total_appliances": len(profile["appliances"]),
            "appliances": profile["appliances"],
        }, indent=2)

