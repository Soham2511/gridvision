"""Configurable Complaint Category Catalogue and Form Schema Definitions.

Supports configurable categories for RESIDENTIAL with full extensibility for future COMMERCIAL customer segments.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class FormFieldType(str, Enum):
    TEXT = "text"
    TEXTAREA = "textarea"
    SELECT = "select"
    MULTI_SELECT = "multi_select"
    BOOLEAN = "boolean"
    NUMBER = "number"
    DATETIME = "datetime"
    DATE = "date"


class FormFieldOption(BaseModel):
    value: str
    label: str
    description: Optional[str] = None


class CategoryFormField(BaseModel):
    """Field definition for dynamic schema-driven complaint registration form."""
    field_id: str
    label: str
    field_type: FormFieldType
    required: bool = False
    default_value: Optional[Any] = None
    placeholder: Optional[str] = None
    helper_text: Optional[str] = None
    tooltip: Optional[str] = None
    options: List[FormFieldOption] = Field(default_factory=list)
    min_value: Optional[float] = None
    max_value: Optional[float] = None


class ComplaintCategory(BaseModel):
    """Configurable complaint category metadata and dynamic form definition."""
    category_id: str
    label: str
    customer_segment: str = "RESIDENTIAL"
    description: str
    icon_name: str
    badge: Optional[str] = None
    safety_critical: bool = False
    fields: List[CategoryFormField] = Field(default_factory=list)
    guidance_notes: Optional[str] = None


# Initial 8 Residential Categories Catalogue
RESIDENTIAL_COMPLAINT_CATEGORIES: Dict[str, ComplaintCategory] = {
    "power_supply_interruption": ComplaintCategory(
        category_id="power_supply_interruption",
        label="Power Supply Interruption",
        customer_segment="RESIDENTIAL",
        description="Complete outage, intermittent supply, or frequent unexpected power cuts.",
        icon_name="PowerOff",
        badge="Supply Quality",
        safety_critical=False,
        guidance_notes="Helps identify feeder outages, localized transformer trips, or service wire issues.",
        fields=[
            CategoryFormField(
                field_id="interruption_type",
                label="Interruption Type",
                field_type=FormFieldType.SELECT,
                required=True,
                default_value="complete_outage",
                options=[
                    FormFieldOption(value="complete_outage", label="Complete Power Outage", description="No power in the premises at all"),
                    FormFieldOption(value="intermittent", label="Intermittent Supply", description="Power turns on and off repeatedly"),
                    FormFieldOption(value="frequent_tripping", label="Frequent Circuit Tripping", description="Main breaker trips repeatedly under normal load"),
                ],
            ),
            CategoryFormField(
                field_id="incident_start",
                label="When did the interruption start?",
                field_type=FormFieldType.DATETIME,
                required=True,
                helper_text="Approximate date and time the power supply was lost.",
            ),
            CategoryFormField(
                field_id="power_currently_available",
                label="Is power still unavailable right now?",
                field_type=FormFieldType.BOOLEAN,
                required=True,
                default_value=True,
            ),
            CategoryFormField(
                field_id="scope_affected",
                label="Extent of affected area",
                field_type=FormFieldType.SELECT,
                required=True,
                default_value="entire_house",
                options=[
                    FormFieldOption(value="entire_house", label="Entire Household"),
                    FormFieldOption(value="partial_house", label="Partial (some rooms only)"),
                    FormFieldOption(value="single_room", label="Single Room or Circuit"),
                ],
            ),
            CategoryFormField(
                field_id="is_recurring",
                label="Is this a recurring issue?",
                field_type=FormFieldType.BOOLEAN,
                required=False,
                default_value=False,
            ),
            CategoryFormField(
                field_id="approximate_duration_hours",
                label="Approximate duration (hours)",
                field_type=FormFieldType.NUMBER,
                required=False,
                min_value=0.1,
                max_value=720.0,
                helper_text="Estimated total hours affected if already restored or known.",
            ),
        ],
    ),

    "voltage_fluctuation": ComplaintCategory(
        category_id="voltage_fluctuation",
        label="Voltage Fluctuation & Power Quality",
        customer_segment="RESIDENTIAL",
        description="Low or high voltage, flickering lights, or appliances unexpectedly shutting down.",
        icon_name="Activity",
        badge="Power Quality",
        safety_critical=False,
        guidance_notes="GridVision checks historical transformer voltage and local feeder indicators where available.",
        fields=[
            CategoryFormField(
                field_id="voltage_issue_type",
                label="Observed Issue Type",
                field_type=FormFieldType.SELECT,
                required=True,
                default_value="frequent_fluctuations",
                options=[
                    FormFieldOption(value="low_voltage", label="Unusually Low Voltage (dim lights, AC fails to start)"),
                    FormFieldOption(value="high_voltage", label="Unusually High Voltage (fans running abnormally fast)"),
                    FormFieldOption(value="frequent_fluctuations", label="Frequent Voltage Surges / Dips"),
                    FormFieldOption(value="lights_flickering", label="Continuous or Intermittent Lights Flickering"),
                    FormFieldOption(value="appliance_tripping", label="Sensitive Appliances Switching Off"),
                ],
            ),
            CategoryFormField(
                field_id="observation_time",
                label="When was this observed?",
                field_type=FormFieldType.DATETIME,
                required=True,
                helper_text="When did you first notice the voltage instability?",
            ),
            CategoryFormField(
                field_id="pattern",
                label="Frequency Pattern",
                field_type=FormFieldType.SELECT,
                required=True,
                default_value="intermittent",
                options=[
                    FormFieldOption(value="continuous", label="Continuous / Constant"),
                    FormFieldOption(value="intermittent", label="Intermittent (comes and goes)"),
                    FormFieldOption(value="during_peak_hours", label="During Evening Peak Hours Only"),
                ],
            ),
            CategoryFormField(
                field_id="affected_appliances_rooms",
                label="Affected Rooms or Appliances",
                field_type=FormFieldType.TEXT,
                required=False,
                placeholder="e.g., Living room lights, Refrigerator, AC compressor",
                helper_text="Mention any specific appliances that struggled to operate.",
            ),
            CategoryFormField(
                field_id="is_currently_occurring",
                label="Is it still happening right now?",
                field_type=FormFieldType.BOOLEAN,
                required=True,
                default_value=True,
            ),
        ],
    ),

    "meter_issue": ComplaintCategory(
        category_id="meter_issue",
        label="Meter & Meter Reading Issues",
        customer_segment="RESIDENTIAL",
        description="Meter display blank, suspected reading discrepancy, or communication faults.",
        icon_name="Gauge",
        badge="Hardware",
        safety_critical=False,
        guidance_notes="Your registered Smart Meter ID will be verified against operational telemetry records.",
        fields=[
            CategoryFormField(
                field_id="meter_issue_type",
                label="Meter Issue Type",
                field_type=FormFieldType.SELECT,
                required=True,
                default_value="suspected_incorrect_reading",
                options=[
                    FormFieldOption(value="display_blank_error", label="Meter LCD Display Blank / Error Code"),
                    FormFieldOption(value="suspected_incorrect_reading", label="Suspected Inaccurate Reading / Fast Meter"),
                    FormFieldOption(value="communication_failure", label="No Automated Reading / Communication Drop"),
                    FormFieldOption(value="physical_damage", label="Physical Damage / Broken Seal / Burnt Terminal"),
                    FormFieldOption(value="red_light_tamper", label="Tamper Indicator or Red Warning LED Active"),
                ],
            ),
            CategoryFormField(
                field_id="observed_start_date",
                label="When did you notice the meter issue?",
                field_type=FormFieldType.DATE,
                required=True,
            ),
            CategoryFormField(
                field_id="display_operational",
                label="Is the meter digital display currently readable?",
                field_type=FormFieldType.BOOLEAN,
                required=True,
                default_value=True,
            ),
            CategoryFormField(
                field_id="discrepancy_details",
                label="Observed Discrepancy (kWh reading if visible)",
                field_type=FormFieldType.TEXT,
                required=False,
                placeholder="e.g., Current meter shows 1420 kWh, but bill stated 1890 kWh",
            ),
        ],
    ),

    "billing_consumption": ComplaintCategory(
        category_id="billing_consumption",
        label="Billing & Consumption Issues",
        customer_segment="RESIDENTIAL",
        description="Unexpected bill spike, tariff calculation dispute, or consumption mismatch.",
        icon_name="Receipt",
        badge="Billing",
        safety_critical=False,
        guidance_notes="AI validator retrieves authenticated consumption history to compare period-over-period patterns.",
        fields=[
            CategoryFormField(
                field_id="billing_issue_type",
                label="Billing Issue Type",
                field_type=FormFieldType.SELECT,
                required=True,
                default_value="unexpected_high_bill",
                options=[
                    FormFieldOption(value="unexpected_high_bill", label="Unexpected Bill Increase / Unusually High Bill"),
                    FormFieldOption(value="consumption_spike", label="Unexplained Consumption Spike (kWh)"),
                    FormFieldOption(value="meter_bill_mismatch", label="Discrepancy Between Meter Reading and Bill"),
                    FormFieldOption(value="duplicate_unexplained_charge", label="Duplicate or Unexplained Tariff Surcharge"),
                    FormFieldOption(value="billing_cycle_dispute", label="Incorrect Billing Period / Delayed Bill"),
                ],
            ),
            CategoryFormField(
                field_id="billing_period",
                label="Disputed Billing Month / Period",
                field_type=FormFieldType.TEXT,
                required=True,
                placeholder="e.g., January 2026 or 2026-01",
                helper_text="Target billing cycle month under dispute.",
            ),
            CategoryFormField(
                field_id="actual_bill_amount_inr",
                label="Billed Amount (₹)",
                field_type=FormFieldType.NUMBER,
                required=False,
                min_value=0.0,
                helper_text="Total invoice amount received.",
            ),
            CategoryFormField(
                field_id="expected_amount_inr",
                label="Expected / Typical Amount (₹)",
                field_type=FormFieldType.NUMBER,
                required=False,
                min_value=0.0,
                helper_text="Typical average bill for a comparable month.",
            ),
            CategoryFormField(
                field_id="previous_bills_affected",
                label="Did previous bills have a similar issue?",
                field_type=FormFieldType.BOOLEAN,
                required=False,
                default_value=False,
            ),
        ],
    ),

    "electrical_safety": ComplaintCategory(
        category_id="electrical_safety",
        label="Electrical Safety Concerns",
        customer_segment="RESIDENTIAL",
        description="Sparking, burning smell, exposed wires, electric shock, or dangerous overheating.",
        icon_name="ShieldAlert",
        badge="Urgent Safety",
        safety_critical=True,
        guidance_notes=(
            "URGENT: For immediate danger, keep clear of electrical hazards and call emergency services. "
            "Safety complaints are given priority escalation and are never dismissed based solely on meter readings."
        ),
        fields=[
            CategoryFormField(
                field_id="safety_issue_type",
                label="Nature of Safety Concern",
                field_type=FormFieldType.SELECT,
                required=True,
                default_value="sparking_visible",
                options=[
                    FormFieldOption(value="sparking_visible", label="Visible Sparking / Arcing at Panel or Socket"),
                    FormFieldOption(value="burning_smell", label="Strong Electrical Burning / Melting Plastic Odor"),
                    FormFieldOption(value="exposed_wiring", label="Exposed Live Wire / Damaged Insulation"),
                    FormFieldOption(value="electric_shock_leakage", label="Electric Shock or Tingling from Appliance/Taps"),
                    FormFieldOption(value="frequent_overheating", label="Distribution Board / Switchboard Running Dangerously Hot"),
                ],
            ),
            CategoryFormField(
                field_id="hazard_location",
                label="Location of Hazard on Premises",
                field_type=FormFieldType.TEXT,
                required=True,
                placeholder="e.g., Main Distribution Board in hallway, Kitchen Geyser socket",
            ),
            CategoryFormField(
                field_id="is_condition_ongoing",
                label="Is the dangerous condition ongoing right now?",
                field_type=FormFieldType.BOOLEAN,
                required=True,
                default_value=True,
            ),
            CategoryFormField(
                field_id="visible_damage_present",
                label="Is there visible blackening, melting, or smoke?",
                field_type=FormFieldType.BOOLEAN,
                required=True,
                default_value=False,
            ),
            CategoryFormField(
                field_id="person_or_equipment_affected",
                label="Has any person or major equipment been affected?",
                field_type=FormFieldType.BOOLEAN,
                required=True,
                default_value=False,
            ),
        ],
    ),

    "solar_distributed_energy": ComplaintCategory(
        category_id="solar_distributed_energy",
        label="Solar & Distributed Energy Issues",
        customer_segment="RESIDENTIAL",
        description="Rooftop solar generation drops, inverter fault codes, or net-metering issues.",
        icon_name="Sun",
        badge="Solar PV",
        safety_critical=False,
        guidance_notes="For properties with connected solar PV, battery systems, or net-metering agreements.",
        fields=[
            CategoryFormField(
                field_id="solar_issue_type",
                label="Solar Issue Type",
                field_type=FormFieldType.SELECT,
                required=True,
                default_value="low_generation",
                options=[
                    FormFieldOption(value="low_generation", label="Generation Significantly Below Expected Yield"),
                    FormFieldOption(value="inverter_error_fault", label="Solar Inverter Tripped / Red Error Code"),
                    FormFieldOption(value="monitoring_offline", label="Solar Generation Monitoring App Offline"),
                    FormFieldOption(value="battery_discharge_issue", label="Home Battery Failing to Charge or Discharge"),
                    FormFieldOption(value="net_metering_discrepancy", label="Solar Export Credit Missing on Monthly Bill"),
                ],
            ),
            CategoryFormField(
                field_id="is_system_operational",
                label="Is the inverter currently powering on?",
                field_type=FormFieldType.BOOLEAN,
                required=True,
                default_value=True,
            ),
            CategoryFormField(
                field_id="approximate_start_time",
                label="When was the drop in yield first observed?",
                field_type=FormFieldType.DATE,
                required=True,
            ),
            CategoryFormField(
                field_id="inverter_error_code",
                label="Inverter Display Error Code (if visible)",
                field_type=FormFieldType.TEXT,
                required=False,
                placeholder="e.g., Error E031, Grid Voltage Out of Range",
            ),
        ],
    ),

    "ev_charging": ComplaintCategory(
        category_id="ev_charging",
        label="EV Charging Infrastructure Issues",
        customer_segment="RESIDENTIAL",
        description="Home EV charger not initiating charge, intermittent interruption, or circuit tripping.",
        icon_name="Zap",
        badge="EV",
        safety_critical=False,
        guidance_notes="Evaluates home EV charger connection circuits, MCB ratings, and DISCOM supply adequacy.",
        fields=[
            CategoryFormField(
                field_id="ev_issue_type",
                label="Charger Issue Type",
                field_type=FormFieldType.SELECT,
                required=True,
                default_value="charger_not_powering_on",
                options=[
                    FormFieldOption(value="charger_not_powering_on", label="Charger Not Powering On"),
                    FormFieldOption(value="charging_stops_unexpectedly", label="Charging Stops Unexpectedly Mid-Cycle"),
                    FormFieldOption(value="breaker_tripping_on_plug_in", label="Dedicated Circuit Breaker Trips Upon Connection"),
                    FormFieldOption(value="slow_charging_speed", label="Abnormally Slow Charging Rate"),
                ],
            ),
            CategoryFormField(
                field_id="charger_type",
                label="Charger Rating",
                field_type=FormFieldType.SELECT,
                required=True,
                default_value="16a_level_1",
                options=[
                    FormFieldOption(value="16a_level_1", label="3.3 kW Single-Phase AC (16A standard)"),
                    FormFieldOption(value="32a_level_2", label="7.4 kW Single-Phase AC Fast (32A)"),
                    FormFieldOption(value="three_phase_11kw", label="11 kW Three-Phase AC Level-2"),
                    FormFieldOption(value="not_sure", label="Not sure / Standard 15A Socket"),
                ],
            ),
            CategoryFormField(
                field_id="charging_starts",
                label="Does the vehicle detect connection when plugged in?",
                field_type=FormFieldType.BOOLEAN,
                required=True,
                default_value=False,
            ),
            CategoryFormField(
                field_id="approximate_start_time",
                label="When did the charger issue start?",
                field_type=FormFieldType.DATETIME,
                required=True,
            ),
        ],
    ),

    "other_issues": ComplaintCategory(
        category_id="other_issues",
        label="Other Electrical & Utility Issues",
        customer_segment="RESIDENTIAL",
        description="General electrical issues or utility service matters not covered above.",
        icon_name="HelpCircle",
        badge="General",
        safety_critical=False,
        guidance_notes="Submit any general inquiry or service dispute not represented in standard categories.",
        fields=[
            CategoryFormField(
                field_id="specific_topic",
                label="Primary Subject Area",
                field_type=FormFieldType.SELECT,
                required=True,
                default_value="general_supply",
                options=[
                    FormFieldOption(value="general_supply", label="General Power Supply"),
                    FormFieldOption(value="contractor_wiring", label="External Contractor Wiring"),
                    FormFieldOption(value="meter_relocation", label="Meter Relocation or Shifting Request"),
                    FormFieldOption(value="sanctioned_load_change", label="Sanctioned Load Enhancement / Reduction"),
                    FormFieldOption(value="other_inquiry", label="Other General Dispute or Inquiry"),
                ],
            ),
            CategoryFormField(
                field_id="is_ongoing",
                label="Is the issue currently active?",
                field_type=FormFieldType.BOOLEAN,
                required=True,
                default_value=True,
            ),
        ],
    ),
}


def get_categories_for_segment(segment: str = "RESIDENTIAL") -> List[ComplaintCategory]:
    """Return all active categories for a customer segment."""
    clean_seg = (segment or "RESIDENTIAL").upper().strip()
    return [c for c in RESIDENTIAL_COMPLAINT_CATEGORIES.values() if c.customer_segment == clean_seg]


def get_category_by_id(category_id: str) -> Optional[ComplaintCategory]:
    """Retrieve category definition by ID."""
    clean_id = (category_id or "").strip().lower()
    return RESIDENTIAL_COMPLAINT_CATEGORIES.get(clean_id)

