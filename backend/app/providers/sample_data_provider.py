"""Sample data provider providing deterministic datasets for development and testing."""

from __future__ import annotations

import copy
import math
from datetime import datetime
from typing import Any

from app.providers.data_provider import BaseDataProvider


class SampleDataProvider(BaseDataProvider):
    """Deterministic, production-free data provider grounded in reference schema."""

    def __init__(self) -> None:
        self._commercial_buildings: list[dict[str, Any]] = [
            {
                "buildingId": "Panther_office_1",
                "siteId": "Panther",
                "primarySpaceUsage": "Commercial Office",
                "sqm": 14250,
                "yearBuilt": 2012,
                "recentDemandKwh": 342.8,
                "predictedDemandKwh": 351.2,
                "absErrorKwh": 8.4,
                "pctError": 2.45,
                "lastTimestamp": "2017-12-31 23:00",
            },
            {
                "buildingId": "Panther_parking_1",
                "siteId": "Panther",
                "primarySpaceUsage": "Parking Facility",
                "sqm": 8500,
                "yearBuilt": 2015,
                "recentDemandKwh": 88.5,
                "predictedDemandKwh": 82.0,
                "absErrorKwh": 6.5,
                "pctError": 7.34,
                "lastTimestamp": "2017-12-31 23:00",
            },
            {
                "buildingId": "Eagle_education_2",
                "siteId": "Eagle",
                "primarySpaceUsage": "University Campus",
                "sqm": 22400,
                "yearBuilt": 2008,
                "recentDemandKwh": 580.4,
                "predictedDemandKwh": 594.1,
                "absErrorKwh": 13.7,
                "pctError": 2.36,
                "lastTimestamp": "2017-12-31 23:00",
            },
            {
                "buildingId": "Fox_retail_1",
                "siteId": "Fox",
                "primarySpaceUsage": "Retail Mall",
                "sqm": 31000,
                "yearBuilt": 2016,
                "recentDemandKwh": 840.2,
                "predictedDemandKwh": 822.0,
                "absErrorKwh": 18.2,
                "pctError": 2.16,
                "lastTimestamp": "2017-12-31 23:00",
            },
            {
                "buildingId": "Bull_assembly_3",
                "siteId": "Bull",
                "primarySpaceUsage": "Manufacturing Assembly",
                "sqm": 18900,
                "yearBuilt": 2005,
                "recentDemandKwh": 675.0,
                "predictedDemandKwh": 660.5,
                "absErrorKwh": 14.5,
                "pctError": 2.14,
                "lastTimestamp": "2017-12-31 23:00",
            },
        ]

        self._residential_meters: list[dict[str, Any]] = [
            {
                "householdId": "METER-1000",
                "dailyKwh": 14.8,
                "actualCycleKwhSoFar": 284.5,
                "targetRemainingKwh": 145.2,
                "predictedRemainingKwh": 140.0,
                "estimatedMonthEndKwh": 424.5,
                "estimatedMonthEndBillInr": 4245.0,
                "coverageRatio": 0.985,
                "elapsedDays": 19,
                "lastDate": "2014-05-19",
            },
            {
                "householdId": "METER-1001",
                "dailyKwh": 22.4,
                "actualCycleKwhSoFar": 412.0,
                "targetRemainingKwh": 198.5,
                "predictedRemainingKwh": 205.0,
                "estimatedMonthEndKwh": 617.0,
                "estimatedMonthEndBillInr": 6170.0,
                "coverageRatio": 0.992,
                "elapsedDays": 19,
                "lastDate": "2014-05-19",
            },
            {
                "householdId": "METER-1002",
                "dailyKwh": 9.2,
                "actualCycleKwhSoFar": 178.6,
                "targetRemainingKwh": 92.4,
                "predictedRemainingKwh": 88.0,
                "estimatedMonthEndKwh": 266.6,
                "estimatedMonthEndBillInr": 2666.0,
                "coverageRatio": 0.978,
                "elapsedDays": 19,
                "lastDate": "2014-05-19",
            },
            {
                "householdId": "METER-1003",
                "dailyKwh": 31.5,
                "actualCycleKwhSoFar": 598.0,
                "targetRemainingKwh": 280.0,
                "predictedRemainingKwh": 272.5,
                "estimatedMonthEndKwh": 870.5,
                "estimatedMonthEndBillInr": 8705.0,
                "coverageRatio": 0.965,
                "elapsedDays": 19,
                "lastDate": "2014-05-19",
            },
        ]

        self._regional_sites: list[dict[str, Any]] = [
            {
                "siteId": "Bear",
                "buildingCount": 92,
                "totalDemandKwh": 48250.0,
                "predictedDemandKwh": 49100.0,
                "peakHourKwh": 4250.0,
                "shareOfTotalPct": 14.8,
                "season": "Summer",
            },
            {
                "siteId": "Bull",
                "buildingCount": 124,
                "totalDemandKwh": 62400.0,
                "predictedDemandKwh": 61800.0,
                "peakHourKwh": 5890.0,
                "shareOfTotalPct": 19.1,
                "season": "Summer",
            },
            {
                "siteId": "Eagle",
                "buildingCount": 85,
                "totalDemandKwh": 41200.0,
                "predictedDemandKwh": 42000.0,
                "peakHourKwh": 3840.0,
                "shareOfTotalPct": 12.6,
                "season": "Summer",
            },
            {
                "siteId": "Fox",
                "buildingCount": 110,
                "totalDemandKwh": 55800.0,
                "predictedDemandKwh": 54900.0,
                "peakHourKwh": 5120.0,
                "shareOfTotalPct": 17.1,
                "season": "Summer",
            },
            {
                "siteId": "Panther",
                "buildingCount": 145,
                "totalDemandKwh": 78900.0,
                "predictedDemandKwh": 80200.0,
                "peakHourKwh": 7450.0,
                "shareOfTotalPct": 24.2,
                "season": "Summer",
            },
            {
                "siteId": "Peacock",
                "buildingCount": 68,
                "totalDemandKwh": 39500.0,
                "predictedDemandKwh": 38900.0,
                "peakHourKwh": 3410.0,
                "shareOfTotalPct": 12.2,
                "season": "Summer",
            },
        ]

        self._regional_rankings: list[dict[str, Any]] = [
            {"siteId": "Panther", "demandKwh": 78900.0, "buildingCount": 145, "percentageOfSystem": 24.2},
            {"siteId": "Bull", "demandKwh": 62400.0, "buildingCount": 124, "percentageOfSystem": 19.1},
            {"siteId": "Fox", "demandKwh": 55800.0, "buildingCount": 110, "percentageOfSystem": 17.1},
            {"siteId": "Bear", "demandKwh": 48250.0, "buildingCount": 92, "percentageOfSystem": 14.8},
            {"siteId": "Eagle", "demandKwh": 41200.0, "buildingCount": 85, "percentageOfSystem": 12.6},
            {"siteId": "Peacock", "demandKwh": 39500.0, "buildingCount": 68, "percentageOfSystem": 12.2},
        ]

        self._anomalies: list[dict[str, Any]] = [
            {
                "id": "ANOM-2026-001",
                "entityId": "SUB-NORTH-104",
                "entityName": "North Substation 104",
                "entityType": "Substation",
                "detectedAt": "2026-10-19T14:30:00Z",
                "anomalyType": "Unusual Spike",
                "severity": "critical",
                "deviationPercent": 48.5,
                "baselineDemandKw": 1820.0,
                "observedDemandKw": 2702.7,
                "status": "investigating",
                "rootCauseDiagnosis": "Unscheduled industrial chiller restart coincident with peak grid window.",
                "recommendedAction": "Dispatch automated curtailment signal and notify regional plant operator.",
            },
            {
                "id": "ANOM-2026-002",
                "entityId": "BLDG-PANTHER-01",
                "entityName": "Panther Commercial Complex",
                "entityType": "Commercial Facility",
                "detectedAt": "2026-10-19T12:00:00Z",
                "anomalyType": "Baseload Drift",
                "severity": "warning",
                "deviationPercent": 24.2,
                "baselineDemandKw": 340.0,
                "observedDemandKw": 422.3,
                "status": "confirmed",
                "rootCauseDiagnosis": "HVAC damper stuck at 100% outside air during high thermal load.",
                "recommendedAction": "Schedule building management system actuator recalibration.",
            },
            {
                "id": "ANOM-2026-003",
                "entityId": "METER-RES-4091",
                "entityName": "Green Valley Feeder 7",
                "entityType": "Residential Feeder",
                "detectedAt": "2026-10-19T09:15:00Z",
                "anomalyType": "Sensor Drop",
                "severity": "info",
                "deviationPercent": -92.0,
                "baselineDemandKw": 112.0,
                "observedDemandKw": 8.9,
                "status": "investigating",
                "rootCauseDiagnosis": "Cellular backhaul telemetry packet drop on concentrator unit.",
                "recommendedAction": "Trigger remote modem reboot cycle; verify zero-energy threshold.",
            },
            {
                "id": "ANOM-2026-004",
                "entityId": "PLANT-BULL-IND",
                "entityName": "Bull Industrial Assembly Zone",
                "entityType": "Industrial Plant",
                "detectedAt": "2026-10-18T22:45:00Z",
                "anomalyType": "Phase Imbalance",
                "severity": "warning",
                "deviationPercent": 18.7,
                "baselineDemandKw": 680.0,
                "observedDemandKw": 807.2,
                "status": "resolved",
                "rootCauseDiagnosis": "Single-phase compressor auxiliary heater overloaded branch circuit.",
                "recommendedAction": "Branch load redistributed across L2 and L3 phases.",
            },
        ]

        self._customer_segments: list[dict[str, Any]] = [
            {
                "id": "seg-large-ind",
                "name": "Large Industrial",
                "sharePercentage": 42.5,
                "demandMwh": 4820.0,
                "entityCount": 38,
                "growthPct": 3.8,
                "color": "#0284C7",
                "description": "Continuous process manufacturing, steel assembly, and chemical synthesis.",
                "avgDailyKwh": 126800.0,
                "peakWindow": "14:00 – 17:30",
            },
            {
                "id": "seg-commercial",
                "name": "Commercial Office & Retail",
                "sharePercentage": 28.3,
                "demandMwh": 3210.0,
                "entityCount": 420,
                "growthPct": -1.2,
                "color": "#00A389",
                "description": "Mid-to-high rise office facilities, shopping malls, and corporate campuses.",
                "avgDailyKwh": 7640.0,
                "peakWindow": "11:00 – 16:00",
            },
            {
                "id": "seg-residential",
                "name": "High-Density Residential",
                "sharePercentage": 19.8,
                "demandMwh": 2245.0,
                "entityCount": 18450,
                "growthPct": 5.4,
                "color": "#38BDF8",
                "description": "Smart-metered suburban and urban apartment clusters with evening peaks.",
                "avgDailyKwh": 18.5,
                "peakWindow": "18:30 – 21:30",
            },
            {
                "id": "seg-municipal",
                "name": "Municipal & Public Infrastructure",
                "sharePercentage": 9.4,
                "demandMwh": 1065.0,
                "entityCount": 142,
                "growthPct": 0.8,
                "color": "#F59E0B",
                "description": "Water treatment, street lighting networks, and healthcare centers.",
                "avgDailyKwh": 7500.0,
                "peakWindow": "02:00 – 05:00",
            },
        ]

        self._diurnal_curves: list[dict[str, Any]] = [
            {"hour": 0, "hourLabel": "00:00", "commercialLoad": 180, "residentialLoad": 240, "governmentLoad": 160},
            {"hour": 2, "hourLabel": "02:00", "commercialLoad": 160, "residentialLoad": 190, "governmentLoad": 140},
            {"hour": 4, "hourLabel": "04:00", "commercialLoad": 175, "residentialLoad": 170, "governmentLoad": 150},
            {"hour": 6, "hourLabel": "06:00", "commercialLoad": 310, "residentialLoad": 320, "governmentLoad": 280},
            {"hour": 8, "hourLabel": "08:00", "commercialLoad": 620, "residentialLoad": 410, "governmentLoad": 450},
            {"hour": 10, "hourLabel": "10:00", "commercialLoad": 840, "residentialLoad": 330, "governmentLoad": 510},
            {"hour": 12, "hourLabel": "12:00", "commercialLoad": 910, "residentialLoad": 340, "governmentLoad": 580},
            {"hour": 14, "hourLabel": "14:00", "commercialLoad": 890, "residentialLoad": 360, "governmentLoad": 620},
            {"hour": 16, "hourLabel": "16:00", "commercialLoad": 820, "residentialLoad": 420, "governmentLoad": 640},
            {"hour": 18, "hourLabel": "18:00", "commercialLoad": 580, "residentialLoad": 780, "governmentLoad": 530},
            {"hour": 20, "hourLabel": "20:00", "commercialLoad": 380, "residentialLoad": 840, "governmentLoad": 410},
            {"hour": 22, "hourLabel": "22:00", "commercialLoad": 240, "residentialLoad": 510, "governmentLoad": 270},
        ]

        self._business_insights: list[dict[str, Any]] = [
            {
                "id": "INS-001",
                "category": "peak_shaving",
                "title": "Shift 18.5 MW Commercial Chiller Pre-Cooling",
                "description": "Commercial offices show synchronized 14:00-16:00 thermal spikes. Pre-cooling thermal storage between 06:00-09:00 can shave 18.5 MW coincident peak.",
                "impactMetric": "18.5 MW Peak Shaved",
                "potentialValue": "₹1.42 Cr / month",
                "actionableRecommendation": "Deploy ADR signals to Panther, Bull, and Fox HVAC systems at 13:45 daily.",
                "urgency": "high",
                "sector": "commercial",
            },
            {
                "id": "INS-002",
                "category": "grid_stress",
                "title": "North Substation 104 Reserve Deficit Warning",
                "description": "Coincident peak load is forecasted at 492.6 MW against a 520 MW firm threshold, dropping reserve margins to 5.2%.",
                "impactMetric": "5.2% Margin (Critical)",
                "potentialValue": "Risk Mitigation",
                "actionableRecommendation": "Dispatch 15 MW contractual demand response 30 minutes ahead of peak window.",
                "urgency": "high",
                "sector": "government",
            },
            {
                "id": "INS-003",
                "category": "efficiency",
                "title": "Residential Feeder Baseload Drift Detected",
                "description": "Green Valley Feeder baseload increased by 14% month-over-month, likely indicating water pump timer misalignment.",
                "impactMetric": "34 MWh / month waste",
                "potentialValue": "₹3.4L / month",
                "actionableRecommendation": "Alert municipal pump operators and push automated app notifications to end-users.",
                "urgency": "medium",
                "sector": "residential",
            },
            {
                "id": "INS-004",
                "category": "renewable",
                "title": "Solar Curtailment Avoidance through BESS Charging",
                "description": "Midday solar generation in the Peacock sector exceeds local feeder demand by 6.2 MW between 11:30 and 13:30.",
                "impactMetric": "6.2 MW Clean Energy",
                "potentialValue": "₹68,000 / day",
                "actionableRecommendation": "Route surplus power into grid-tied battery storage to discharge during evening residential peak.",
                "urgency": "medium",
                "sector": "all",
            },
        ]

        self._peak_analysis: dict[str, Any] = {
            "expectedPeakMw": 492.6,
            "expectedPeakTime": "2026-10-23T18:30:00+05:30",
            "currentLoadMw": 384.2,
            "peakCapacityLimitMw": 520.0,
            "reserveMarginPct": 5.27,
            "riskLevel": "elevated",
            "historicalCyclePeakMw": 478.4,
            "mitigationStrategy": "Dispatch 15 MW automated curtailment across Commercial Class A contracts.",
            "hourlyDistribution": [
                {"hour": 0, "hourLabel": "00:00", "avgDemandMw": 240.5, "peakFrequencyPct": 0.0},
                {"hour": 2, "hourLabel": "02:00", "avgDemandMw": 215.2, "peakFrequencyPct": 0.0},
                {"hour": 4, "hourLabel": "04:00", "avgDemandMw": 230.8, "peakFrequencyPct": 0.0},
                {"hour": 6, "hourLabel": "06:00", "avgDemandMw": 310.4, "peakFrequencyPct": 2.1},
                {"hour": 8, "hourLabel": "08:00", "avgDemandMw": 395.0, "peakFrequencyPct": 4.5},
                {"hour": 10, "hourLabel": "10:00", "avgDemandMw": 435.6, "peakFrequencyPct": 12.8},
                {"hour": 12, "hourLabel": "12:00", "avgDemandMw": 452.1, "peakFrequencyPct": 18.2},
                {"hour": 14, "hourLabel": "14:00", "avgDemandMw": 468.9, "peakFrequencyPct": 24.6},
                {"hour": 16, "hourLabel": "16:00", "avgDemandMw": 474.2, "peakFrequencyPct": 29.8},
                {"hour": 18, "hourLabel": "18:00", "avgDemandMw": 492.6, "peakFrequencyPct": 42.1},
                {"hour": 20, "hourLabel": "20:00", "avgDemandMw": 448.0, "peakFrequencyPct": 15.3},
                {"hour": 22, "hourLabel": "22:00", "avgDemandMw": 315.4, "peakFrequencyPct": 1.2},
            ],
            "dailyPeakTimeline": [
                {"date": "18 Oct", "dayLabel": "Sat", "peakMw": 462.4, "thresholdMw": 460.0},
                {"date": "19 Oct", "dayLabel": "Sun", "peakMw": 455.1, "thresholdMw": 460.0},
                {"date": "20 Oct", "dayLabel": "Mon", "peakMw": 478.2, "thresholdMw": 460.0},
                {"date": "21 Oct", "dayLabel": "Tue", "peakMw": 484.0, "thresholdMw": 460.0},
                {"date": "22 Oct", "dayLabel": "Wed", "peakMw": 488.5, "thresholdMw": 460.0},
                {"date": "23 Oct", "dayLabel": "Thu (Today)", "peakMw": 492.6, "thresholdMw": 460.0},
                {"date": "24 Oct", "dayLabel": "Fri", "peakMw": 481.0, "thresholdMw": 460.0},
            ],
        }

        self._household_overview: dict[str, Any] = {
            "householdId": "METER-1000",
            "userName": "Ramesh Sharma",
            "currentDailyUsageKwh": 14.8,
            "dailyAvgKwh": 15.2,
            "dailyAvgChangePct": -2.6,
            "prev7DaysAvgKwh": 15.6,
            "monthlyAvgKwh": 456.0,
            "monthlyAvgChangePct": 4.1,
            "prevMonthKwh": 438.0,
            "predictedMonthEndKwh": 462.5,
            "consumptionCurve": [
                {"time": "00:00", "actualConsumption": 0.45, "predictedConsumption": None, "actualNote": "Night baseload"},
                {"time": "02:00", "actualConsumption": 0.38, "predictedConsumption": None},
                {"time": "04:00", "actualConsumption": 0.42, "predictedConsumption": None},
                {"time": "06:00", "actualConsumption": 0.95, "predictedConsumption": None, "actualNote": "Geyser active"},
                {"time": "08:00", "actualConsumption": 1.45, "predictedConsumption": None},
                {"time": "10:00", "actualConsumption": 0.85, "predictedConsumption": None},
                {"time": "12:00", "actualConsumption": 0.72, "predictedConsumption": None},
                {"time": "14:00", "actualConsumption": 1.10, "predictedConsumption": None, "actualNote": "Air conditioning"},
                {"time": "16:00", "actualConsumption": 0.90, "predictedConsumption": 0.90},
                {"time": "18:00", "actualConsumption": None, "predictedConsumption": 1.85, "predictedNote": "Evening peak"},
                {"time": "20:00", "actualConsumption": None, "predictedConsumption": 2.10, "predictedNote": "Cooking + HVAC"},
                {"time": "22:00", "actualConsumption": None, "predictedConsumption": 1.20},
            ],
        }

    # --- Concrete Implementations ---
    def get_commercial_buildings(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._commercial_buildings)

    def get_commercial_building(self, building_id: str) -> dict[str, Any] | None:
        for b in self._commercial_buildings:
            if b["buildingId"] == building_id:
                return copy.deepcopy(b)
        return None

    def get_residential_meters(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._residential_meters)

    def get_residential_meter(self, household_id: str) -> dict[str, Any] | None:
        for m in self._residential_meters:
            if m["householdId"] == household_id:
                return copy.deepcopy(m)
        return None

    def get_regional_sites(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._regional_sites)

    def get_regional_site(self, site_id: str) -> dict[str, Any] | None:
        for s in self._regional_sites:
            if s["siteId"].lower() == site_id.lower():
                return copy.deepcopy(s)
        return None

    def get_regional_rankings(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._regional_rankings)

    def get_commercial_dashboard(
        self,
        tab: str = "building",
        time_range: str = "1D",
        building_id: str = "Panther_office_1",
    ) -> dict[str, Any]:
        is_regional = tab == "regional"
        scale = 4.25 if is_regional else 1.0

        avg_demand = 320.0 * scale
        avg_demand_delta_pct = 6.5 if is_regional else -12.0
        prev_period_avg_demand = 1333.0 if is_regional else 365.0
        peak_demand = 820.0 * scale
        peak_timestamp = "19 Oct 2026, 02:30 PM"
        predicted_peak = 910.0 * scale
        predicted_peak_timestamp = "19 Oct 2026, 05:00 PM"
        predicted_total = 6850.0 * scale
        predicted_total_horizon = "for 19 Oct 2026 (today)"
        demarcation_time = "16:30"

        curve: list[dict[str, Any]] = []

        if time_range == "1D":
            raw_1d = [
                {"time": "00:00", "actual": 160, "pred": None},
                {"time": "01:00", "actual": 190, "pred": None},
                {"time": "02:00", "actual": 150, "pred": None},
                {"time": "03:00", "actual": 165, "pred": None},
                {"time": "04:00", "actual": 145, "pred": None},
                {"time": "05:00", "actual": 220, "pred": None},
                {"time": "06:00", "actual": 390, "pred": None},
                {"time": "07:00", "actual": 450, "pred": None},
                {"time": "08:00", "actual": 430, "pred": None},
                {"time": "09:00", "actual": 470, "pred": None},
                {"time": "10:00", "actual": 520, "pred": None},
                {"time": "11:00", "actual": 570, "pred": None},
                {"time": "12:00", "actual": 620, "pred": None},
                {"time": "13:00", "actual": 590, "pred": None},
                {"time": "14:00", "actual": 560, "pred": None},
                {"time": "14:30", "actual": 820, "pred": None},
                {"time": "15:00", "actual": 630, "pred": None},
                {"time": "16:00", "actual": 710, "pred": None},
                {"time": "16:30", "actual": 730, "pred": 730},
                {"time": "17:00", "actual": None, "pred": 910},
                {"time": "18:00", "actual": None, "pred": 850},
                {"time": "19:00", "actual": None, "pred": 780},
                {"time": "20:00", "actual": None, "pred": 720},
                {"time": "21:00", "actual": None, "pred": 670},
                {"time": "22:00", "actual": None, "pred": 610},
                {"time": "23:00", "actual": None, "pred": 540},
                {"time": "24:00", "actual": None, "pred": 480},
            ]
            curve = [
                {
                    "time": p["time"],
                    "actualDemand": round(p["actual"] * scale) if p["actual"] is not None else None,
                    "predictedDemand": round(p["pred"] * scale) if p["pred"] is not None else None,
                    "fullDate": f"19 Oct 2026, {p['time']}",
                }
                for p in raw_1d
            ]
        elif time_range == "7D":
            avg_demand = 1480.0 if is_regional else 345.0
            avg_demand_delta_pct = 4.2
            prev_period_avg_demand = 1420.0 if is_regional else 331.0
            peak_demand = 3620.0 if is_regional else 840.0
            peak_timestamp = "16 Oct 2026, 02:45 PM"
            predicted_peak = 3780.0 if is_regional else 885.0
            predicted_peak_timestamp = "22 Oct 2026, 03:00 PM"
            predicted_total = 204000.0 if is_regional else 48200.0
            predicted_total_horizon = "next 7 days forecast"
            demarcation_time = "19 Oct"

            days = ["13 Oct", "14 Oct", "15 Oct", "16 Oct", "17 Oct", "18 Oct", "19 Oct", "20 Oct", "21 Oct", "22 Oct", "23 Oct", "24 Oct"]
            for idx, day in enumerate(days):
                is_actual = idx <= 6
                is_overlap = idx == 6
                base = (300 + math.sin(idx * 0.8) * 120 + (450 if idx == 3 else 0)) * scale
                pred_base = (320 + math.sin(idx * 0.8) * 140 + (480 if idx == 9 else 0)) * scale
                curve.append({
                    "time": day,
                    "actualDemand": round(base) if is_actual else None,
                    "predictedDemand": round(base if is_overlap else pred_base) if idx >= 6 else None,
                    "fullDate": f"{day} 2026",
                })
        else:
            # Monthly/Multi-month default fallback curve
            sampled_days = ["20 Sep", "24 Sep", "28 Sep", "02 Oct", "06 Oct", "10 Oct", "14 Oct", "19 Oct", "24 Oct", "28 Oct", "02 Nov", "06 Nov", "10 Nov"]
            for idx, day in enumerate(sampled_days):
                is_actual = idx <= 7
                is_overlap = idx == 7
                base = (310 + math.sin(idx * 0.5) * 150 + (500 if idx == 3 else 0)) * scale
                pred_base = (330 + math.sin(idx * 0.5) * 160 + (520 if idx == 9 else 0)) * scale
                curve.append({
                    "time": day,
                    "actualDemand": round(base) if is_actual else None,
                    "predictedDemand": round(base if is_overlap else pred_base) if idx >= 7 else None,
                    "fullDate": f"{day} 2026",
                })

        actual_callout = {
            "time": "12:00",
            "value": round(620.0 * scale),
            "timestamp": "19 Oct 2026, 12:00 PM",
            "label": "Regional Demand" if is_regional else "Actual Demand",
        } if time_range == "1D" else None

        predicted_callout = {
            "time": "17:00",
            "value": round(910.0 * scale),
            "timestamp": "19 Oct 2026, 05:00 PM",
            "label": "Predicted Demand",
        } if time_range == "1D" else None

        return {
            "tab": tab,
            "buildingId": building_id,
            "regionId": "Panther_Region_North",
            "timeRange": time_range,
            "avgDemand": round(avg_demand),
            "avgDemandDeltaPct": round(avg_demand_delta_pct, 1),
            "prevPeriodAvgDemand": round(prev_period_avg_demand),
            "peakDemand": round(peak_demand),
            "peakTimestamp": peak_timestamp,
            "predictedPeak": round(predicted_peak),
            "predictedPeakTimestamp": predicted_peak_timestamp,
            "predictedTotal": round(predicted_total),
            "predictedTotalHorizon": predicted_total_horizon,
            "unit": "kW",
            "totalUnit": "kWh",
            "actualCallout": actual_callout,
            "predictedCallout": predicted_callout,
            "demarcationTime": demarcation_time,
            "curve": curve,
        }

    def get_household_overview(self, household_id: str | None = None) -> dict[str, Any]:
        data = copy.deepcopy(self._household_overview)
        if household_id:
            data["householdId"] = household_id
        return data

    def get_government_regions(self) -> list[dict[str, Any]]:
        return [
            {
                "id": "north",
                "name": "North Region",
                "currentDemand": 3120,
                "predictedDemand": 3400,
                "deltaPct": -8,
                "isIncreaseNegative": True,
                "pinColor": "#2563EB",
                "sparkline": [2700, 2850, 2980, 3120],
                "unit": "MW",
            },
            {
                "id": "south",
                "name": "South Region",
                "currentDemand": 2950,
                "predictedDemand": 3100,
                "deltaPct": 12,
                "isIncreaseNegative": True,
                "pinColor": "#2563EB",
                "sparkline": [2600, 2750, 2890, 2950],
                "unit": "MW",
            },
            {
                "id": "east",
                "name": "East Region",
                "currentDemand": 2160,
                "predictedDemand": 2300,
                "deltaPct": -5,
                "isIncreaseNegative": True,
                "pinColor": "#10B981",
                "sparkline": [2300, 2240, 2190, 2160],
                "unit": "MW",
            },
            {
                "id": "west",
                "name": "West Region",
                "currentDemand": 1980,
                "predictedDemand": 2100,
                "deltaPct": 10,
                "isIncreaseNegative": True,
                "pinColor": "#2563EB",
                "sparkline": [1750, 1820, 1910, 1980],
                "unit": "MW",
            },
            {
                "id": "central",
                "name": "Central Region",
                "currentDemand": 1750,
                "predictedDemand": 1880,
                "deltaPct": -7,
                "isIncreaseNegative": True,
                "pinColor": "#10B981",
                "sparkline": [1890, 1840, 1790, 1750],
                "unit": "MW",
            },
            {
                "id": "northeast",
                "name": "North-East Region",
                "currentDemand": 680,
                "predictedDemand": 750,
                "deltaPct": 15,
                "isIncreaseNegative": True,
                "pinColor": "#7C3AED",
                "sparkline": [580, 610, 640, 680],
                "unit": "MW",
            },
        ]

    def get_government_dashboard(
        self,
        view_type: str = "overall",
        region_id: str | None = None,
        time_range: str = "1D",
    ) -> dict[str, Any]:
        regions_list: dict[str, dict[str, Any]] = {
            "north": {"name": "North Region", "baseAvg": 3120, "basePeak": 4980, "basePred": 5400, "baseTotal": 75200, "delta": -8.0, "prevAvg": 3390, "factor": 1.0},
            "south": {"name": "South Region", "baseAvg": 2950, "basePeak": 4720, "basePred": 5120, "baseTotal": 71100, "delta": 12.0, "prevAvg": 2634, "factor": 0.945},
            "east": {"name": "East Region", "baseAvg": 2160, "basePeak": 3450, "basePred": 3750, "baseTotal": 52000, "delta": -5.0, "prevAvg": 2274, "factor": 0.692},
            "west": {"name": "West Region", "baseAvg": 1980, "basePeak": 3160, "basePred": 3440, "baseTotal": 47700, "delta": 10.0, "prevAvg": 1800, "factor": 0.635},
            "central": {"name": "Central Region", "baseAvg": 1750, "basePeak": 2790, "basePred": 3040, "baseTotal": 42200, "delta": -7.0, "prevAvg": 1882, "factor": 0.561},
            "northeast": {"name": "North-East Region", "baseAvg": 680, "basePeak": 1080, "basePred": 1180, "baseTotal": 16400, "delta": 15.0, "prevAvg": 591, "factor": 0.218},
        }

        selected_region = regions_list.get(region_id or "north") if (view_type == "region" and region_id) else None
        is_region = view_type == "region" and selected_region is not None

        scale = (selected_region["baseAvg"] / 5420.0) if is_region and selected_region else 1.0

        avg_demand = selected_region["baseAvg"] if is_region and selected_region else 5420
        avg_demand_delta_pct = selected_region["delta"] if is_region and selected_region else -12.0
        prev_period_avg_demand = selected_region["prevAvg"] if is_region and selected_region else 6180
        peak_demand = selected_region["basePeak"] if is_region and selected_region else 8930
        peak_timestamp = "19 Oct 2026, 02:30 PM"
        predicted_peak = selected_region["basePred"] if is_region and selected_region else 9200
        predicted_peak_timestamp = "19 Oct 2026, 05:00 PM"
        predicted_total = selected_region["baseTotal"] if is_region and selected_region else 128500
        predicted_total_horizon = "for 19 Oct 2026 (today)"
        demarcation_time = "16:30"

        y_domain = [0, 6000] if is_region else [0, 12000]
        y_ticks = [0, 1000, 2000, 3000, 4000, 5000, 6000] if is_region else [0, 2000, 4000, 6000, 8000, 10000, 12000]

        raw_1d = [
            {"time": "00:00", "actual": 1600, "pred": None},
            {"time": "02:00", "actual": 1500, "pred": None},
            {"time": "04:00", "actual": 1600, "pred": None},
            {"time": "06:00", "actual": 3600, "pred": None},
            {"time": "08:00", "actual": 4700, "pred": None},
            {"time": "10:00", "actual": 5100, "pred": None},
            {"time": "12:00", "actual": 6420, "pred": None},
            {"time": "14:00", "actual": 5800, "pred": None},
            {"time": "14:30", "actual": 8930, "pred": None},
            {"time": "16:00", "actual": 7000, "pred": None},
            {"time": "16:30", "actual": 7200, "pred": 7200},
            {"time": "17:00", "actual": None, "pred": 9200},
            {"time": "18:00", "actual": None, "pred": 8600},
            {"time": "20:00", "actual": None, "pred": 7400},
            {"time": "22:00", "actual": None, "pred": 6200},
            {"time": "24:00", "actual": None, "pred": 5000},
        ]

        curve = [
            {
                "time": p["time"],
                "actualDemand": round(p["actual"] * scale) if p["actual"] is not None else None,
                "predictedDemand": round(p["pred"] * scale) if p["pred"] is not None else None,
                "fullDate": f"19 Oct 2026, {p['time']}",
            }
            for p in raw_1d
        ]

        return {
            "viewType": view_type,
            "regionId": region_id,
            "regionName": selected_region["name"] if is_region and selected_region else "System-Wide",
            "timeRange": time_range,
            "avgDemand": round(avg_demand),
            "avgDemandDeltaPct": round(avg_demand_delta_pct, 1),
            "prevPeriodAvgDemand": round(prev_period_avg_demand),
            "peakDemand": round(peak_demand),
            "peakTimestamp": peak_timestamp,
            "predictedPeak": round(predicted_peak),
            "predictedPeakTimestamp": predicted_peak_timestamp,
            "predictedTotal": round(predicted_total),
            "predictedTotalHorizon": predicted_total_horizon,
            "unit": "MW",
            "totalUnit": "MWh",
            "actualCallout": {
                "time": "12:00",
                "value": round(6420 * scale),
                "timestamp": "19 Oct 2026, 12:00 PM",
                "label": "Actual Demand",
            },
            "predictedCallout": {
                "time": "17:00",
                "value": round(9200 * scale),
                "timestamp": "19 Oct 2026, 05:00 PM",
                "label": "Predicted Demand",
            },
            "demarcationTime": demarcation_time,
            "yDomain": y_domain,
            "yTicks": y_ticks,
            "curve": curve,
        }

    def get_historical_insights(
        self,
        persona: str = "household",
        time_range: str = "30D",
        entity_id: str | None = None,
    ) -> dict[str, Any]:
        # 30-day base template
        base_points = [
            {"date": f"{day:02d} Oct", "fullDate": f"{day:02d} Oct 2026", "peakDemand": round(3.5 + (day % 4) * 0.4, 1), "avgDemand": round(2.0 + (day % 3) * 0.3, 1), "totalConsumption": round(24.0 + (day % 5) * 2.2, 1), "peakTime": "07:00 PM"}
            for day in range(1, 31)
        ]

        if persona == "commercial":
            base_points = [
                {
                    **p,
                    "peakDemand": round(p["peakDemand"] * 65.5 + 40, 1),
                    "avgDemand": round(p["avgDemand"] * 62.0 + 35, 1),
                    "totalConsumption": round(p["totalConsumption"] * 64.0 + 500, 1),
                }
                for p in base_points
            ]
        elif persona == "government":
            base_points = [
                {
                    **p,
                    "peakDemand": round(p["peakDemand"] * 28.5 + 320, 1),
                    "avgDemand": round(p["avgDemand"] * 25.0 + 310, 1),
                    "totalConsumption": round(p["totalConsumption"] * 26.0 + 5000, 1),
                }
                for p in base_points
            ]

        days_returned = 30 if time_range == "30D" else (90 if time_range == "90D" else (365 if time_range == "1Y" else 730))
        total_sum = sum(p["totalConsumption"] for p in base_points)
        avg_daily = round(total_sum / len(base_points), 1)
        peak_pt = max(base_points, key=lambda p: p["peakDemand"])

        return {
            "persona": persona,
            "entityId": entity_id,
            "timeRange": time_range,
            "daysReturned": days_returned,
            "startDate": "20 Sep 2026",
            "endDate": "19 Oct 2026",
            "avgDailyConsumption": avg_daily,
            "avgMonthlyConsumption": round(avg_daily * 30, 1),
            "peakConsumption": peak_pt["peakDemand"],
            "peakTimestamp": f"{peak_pt['fullDate']}, {peak_pt['peakTime']}",
            "unit": "MW" if persona == "government" else "kWh",
            "historyCurve": base_points,
        }

    def get_peak_demand_analysis(self) -> dict[str, Any]:
        return copy.deepcopy(self._peak_analysis)

    def get_anomaly_events(
        self,
        severity: str | None = None,
        status: str | None = None,
        search: str | None = None,
    ) -> list[dict[str, Any]]:
        results = copy.deepcopy(self._anomalies)
        if severity and severity.lower() != "all":
            results = [a for a in results if a["severity"].lower() == severity.lower()]
        if status and status.lower() != "all":
            results = [a for a in results if a["status"].lower() == status.lower()]
        if search:
            query = search.lower()
            results = [
                a
                for a in results
                if query in a["entityId"].lower()
                or query in a["entityName"].lower()
                or query in a["anomalyType"].lower()
            ]
        return results

    def update_anomaly_status(self, event_id: str, status: str) -> dict[str, Any] | None:
        for a in self._anomalies:
            if a["id"].lower() == event_id.lower():
                a["status"] = status
                return copy.deepcopy(a)
        return None

    def get_customer_segments(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._customer_segments)

    def get_customer_segmentation_matrix(self) -> dict[str, Any]:
        return {
            "totalCustomers": 12480,
            "industrySegments": [
                {"id": "hospitals", "name": "Hospitals", "sharePct": 24, "count": 2995, "color": "#0284C7"},
                {"id": "hostels", "name": "Hostels", "sharePct": 18, "count": 2246, "color": "#00A389"},
                {"id": "offices", "name": "Offices", "sharePct": 16, "count": 1997, "color": "#38BDF8"},
                {"id": "retail", "name": "Retail", "sharePct": 14, "count": 1747, "color": "#22C55E"},
                {"id": "manufacturing", "name": "Manufacturing", "sharePct": 12, "count": 1497, "color": "#F59E0B"},
                {"id": "education", "name": "Education", "sharePct": 9, "count": 1123, "color": "#F97316"},
                {"id": "other", "name": "Other", "sharePct": 7, "count": 875, "color": "#A855F7"},
            ],
            "timeOfDayConsumption": [
                {"periodKey": "day", "periodName": "Day", "timeRange": "(6 AM – 12 PM)", "periodLabel": "Day (6 AM – 12 PM)", "consumptionMwh": 2450, "color": "#00A389"},
                {"periodKey": "evening", "periodName": "Evening", "timeRange": "(12 PM – 6 PM)", "periodLabel": "Evening (12 PM – 6 PM)", "consumptionMwh": 3120, "color": "#0284C7"},
                {"periodKey": "night", "periodName": "Night", "timeRange": "(6 PM – 12 AM)", "periodLabel": "Night (6 PM – 12 AM)", "consumptionMwh": 1980, "color": "#818CF8"},
                {"periodKey": "late_night", "periodName": "Late Night", "timeRange": "(12 AM – 6 AM)", "periodLabel": "Late Night (12 AM – 6 AM)", "consumptionMwh": 920, "color": "#C4B5FD"},
            ],
            "regionalMonthlyDemand": [
                {"regionId": "north", "regionName": "North", "avgDemandMw": 4200, "demandLabel": "4,200 MW", "color": "#00A389"},
                {"regionId": "south", "regionName": "South", "avgDemandMw": 3650, "demandLabel": "3,650 MW", "color": "#00A389"},
                {"regionId": "east", "regionName": "East", "avgDemandMw": 2980, "demandLabel": "2,980 MW", "color": "#00A389"},
                {"regionId": "west", "regionName": "West", "avgDemandMw": 2450, "demandLabel": "2,450 MW", "color": "#00A389"},
                {"regionId": "central", "regionName": "Central", "avgDemandMw": 3120, "demandLabel": "3,120 MW", "color": "#00A389"},
                {"regionId": "northeast", "regionName": "North-East", "avgDemandMw": 1980, "demandLabel": "1,980 MW", "color": "#00A389"},
            ],
        }

    def get_diurnal_curves(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._diurnal_curves)

    def get_business_insights(
        self,
        category: str | None = None,
        sector: str | None = None,
    ) -> list[dict[str, Any]]:
        results = copy.deepcopy(self._business_insights)
        if category and category.lower() != "all":
            results = [ins for ins in results if ins["category"].lower() == category.lower()]
        if sector and sector.lower() != "all":
            results = [ins for ins in results if ins["sector"] in (sector.lower(), "all")]
        return results

    def get_platform_health_summary(self) -> dict[str, Any]:
        return {
            "totalBuildings": 124,
            "totalRegions": 8,
            "dataTimeInterval": "1 hour",
            "totalDataAccumulated": "2 years",
            "dataAccumulatedSubtext": "Jan 2024 – Oct 2026",
            "lastUpdated": datetime.now().strftime("%d %b %Y, %I:%M %p"),
            "models": [
                {
                    "id": "m-res-01",
                    "modelName": "Residential Forecasting",
                    "personaUsed": "Residential",
                    "version": "v1.2.0",
                    "status": "Active",
                    "lastInference": "19 Oct 2026, 10:05 AM",
                    "mse": 0.012,
                    "rmse": 0.109,
                    "r2": 0.92,
                },
                {
                    "id": "m-comm-01",
                    "modelName": "Commercial Forecasting",
                    "personaUsed": "Commercial",
                    "version": "v1.1.3",
                    "status": "Active",
                    "lastInference": "19 Oct 2026, 09:55 AM",
                    "mse": 0.018,
                    "rmse": 0.134,
                    "r2": 0.89,
                },
                {
                    "id": "m-gov-01",
                    "modelName": "Government Forecasting",
                    "personaUsed": "Government & Utilities",
                    "version": "v1.0.5",
                    "status": "Active",
                    "lastInference": "19 Oct 2026, 09:40 AM",
                    "mse": 0.021,
                    "rmse": 0.145,
                    "r2": 0.87,
                },
                {
                    "id": "m-anom-01",
                    "modelName": "Anomaly Detection",
                    "personaUsed": "All Personas",
                    "version": "v0.9.1",
                    "status": "Monitoring",
                    "lastInference": "19 Oct 2026, 09:50 AM",
                    "mse": 0.035,
                    "rmse": 0.187,
                    "r2": 0.81,
                },
                {
                    "id": "m-cust-01",
                    "modelName": "Customer Segmentation",
                    "personaUsed": "All Personas",
                    "version": "v0.8.0",
                    "status": "Active",
                    "lastInference": "19 Oct 2026, 09:20 AM",
                    "mse": 0.028,
                    "rmse": 0.168,
                    "r2": 0.84,
                },
            ],
        }
