"""Tavily-backed solar research and transparent rooftop solar estimates."""

from __future__ import annotations

import json
import math
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from ai.commercial.schemas.communication import (
    AgentError,
    EvidenceRef,
    ToolObservation,
)

MAX_RESPONSE_BYTES = 500_000
MAX_RESULTS = 3
PANEL_CAPACITY_KW_PER_SQM = 0.2
DEFAULT_PEAK_SUN_HOURS = 4.5
DEFAULT_PERFORMANCE_RATIO = 0.8
DEFAULT_INSTALL_COST_INR_PER_KW = 55_000
NUMBER_PATTERN = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
CAPACITY_PATTERN = re.compile(
    rf"(?P<value>{NUMBER_PATTERN})\s*(?P<unit>kwp|kw|mw)\b",
    re.IGNORECASE,
)
AREA_PATTERN = re.compile(
    rf"(?P<value>{NUMBER_PATTERN})\s*(?P<unit>sqm|sq\.?\s*m(?:etre|eter)?s?|"
    r"m(?:etre|eter)s?\s*(?:2|²)|sq\.?\s*ft|square\s*feet)\b",
    re.IGNORECASE,
)
USAGE_PATTERN = re.compile(
    rf"(?P<value>{NUMBER_PATTERN})\s*kwh"
    r"(?:\s*(?:/|per)\s*(?P<period>month|year)|\s+(?P<word_period>monthly|annual(?:ly)?))?\b",
    re.IGNORECASE,
)
LOCATION_PATTERN = re.compile(
    r"\b(?:in|near|around)\s+([A-Za-z][A-Za-z .'-]{1,48}?)"
    r"(?=,|[.;?!]|$|\s+(?:for|with|on|and|using|at)\b)",
    re.IGNORECASE,
)
TARIFF_PATTERN = re.compile(
    rf"(?:tariff|rate)\D{{0,12}}({NUMBER_PATTERN})\s*"
    r"(?:₹|rs\.?|inr)?\s*(?:/|per\s*)\s*kwh",
    re.IGNORECASE,
)
CAPACITY_FACTOR_PATTERN = re.compile(
    r"(?:capacity\s+factor\D{0,12}(\d{1,2}(?:\.\d+)?)\s*%|"
    r"(\d{1,2}(?:\.\d+)?)\s*%\D{0,12}capacity\s+factor)",
    re.IGNORECASE,
)
BATTERY_ENERGY_PATTERN = re.compile(
    rf"(?:battery|storage)\s+(?:energy\s+)?capacity\D{{0,12}}"
    rf"({NUMBER_PATTERN})\s*kwh\b",
    re.IGNORECASE,
)
BATTERY_POWER_PATTERN = re.compile(
    rf"(?:battery|storage)\s+(?:charge|discharge|power)\s*"
    rf"(?:power)?\D{{0,12}}({NUMBER_PATTERN})\s*kw\b",
    re.IGNORECASE,
)
EFFICIENCY_PATTERN = re.compile(
    r"round[- ]?trip efficiency\D{0,12}(\d{1,3}(?:\.\d+)?)\s*%",
    re.IGNORECASE,
)
CYCLE_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*cycles?\s*(?:per|/)\s*day",
    re.IGNORECASE,
)
PEAK_TARIFF_PATTERN = re.compile(
    rf"peak\s+tariff\D{{0,12}}({NUMBER_PATTERN})\s*"
    r"(?:₹|rs\.?|inr)?\s*(?:/|per\s*)\s*kwh",
    re.IGNORECASE,
)
OFFPEAK_TARIFF_PATTERN = re.compile(
    rf"off[- ]?peak\s+tariff\D{{0,12}}({NUMBER_PATTERN})\s*"
    r"(?:₹|rs\.?|inr)?\s*(?:/|per\s*)\s*kwh",
    re.IGNORECASE,
)
CAPEX_PATTERN = re.compile(
    rf"(?:capex|capital cost|project cost|installation cost)\D{{0,20}}"
    rf"(?:₹|rs\.?|inr)?\s*({NUMBER_PATTERN})",
    re.IGNORECASE,
)


class TavilySearchError(Exception):
    """A safe, user-facing Tavily search failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        request,
        response,
        code,
        message,
        headers,
        new_url,
    ):
        del request, response, code, message, headers, new_url
        return None


class RenewableEnergyTools:
    """Read-only solar web research and deterministic rooftop solar sizing."""

    def __init__(
        self,
        api_key_file: Path,
        *,
        timeout_seconds: float = 12.0,
    ) -> None:
        if not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 30:
            raise ValueError("Tavily timeout must be greater than 0 and at most 30 seconds.")
        self._api_key_file = api_key_file
        self._timeout_seconds = timeout_seconds
        self._opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            _NoRedirectHandler(),
        )

    def get_renewable_scenarios(
        self, factory_id: str | None, goal: str
    ) -> ToolObservation:
        """Calculate explicit solar, wind, or battery inputs and cite web research."""
        del factory_id
        try:
            lowered_goal = goal.casefold()
            if "wind" in lowered_goal or "turbine" in lowered_goal:
                estimate = self._estimate_wind(goal)
                technology = "wind"
            elif "battery" in lowered_goal or "storage" in lowered_goal:
                estimate = self._estimate_battery(goal)
                technology = "battery"
            else:
                estimate = self._estimate(goal)
                technology = "rooftop solar"
        except TavilySearchError as exc:
            return ToolObservation(
                status=(
                    "unavailable"
                    if exc.code.endswith("_INPUT_REQUIRED")
                    else "failed"
                ),
                findings=(exc.message,),
                error=AgentError(code=exc.code, message=exc.message),
            )
        location = self._location(goal)
        query_location = location or "India"
        search_query = (
            f"{technology} renewable energy technical guidance and costs in "
            f"{query_location}"
        )

        try:
            _, results = self._search(search_query)
        except TavilySearchError as exc:
            return ToolObservation(
                status="available",
                findings=(
                    self._format_estimate(estimate),
                    f"Live solar web research is unavailable ({exc.code}); "
                    "the estimate below uses the stated defaults only.",
                ),
                data={"estimate": estimate, "web_search": {"status": "unavailable"}},
                assumptions=self._assumptions(estimate),
                error=AgentError(code=exc.code, message=exc.message, retryable=True),
            )

        evidence_refs = tuple(
            EvidenceRef(
                source_id=result["url"],
                source_type="web_search",
                locator=result["url"],
                excerpt=result["content"][:1000] or result["title"],
                extraction_confidence=0.8,
            )
            for result in results
        )
        findings = [self._format_estimate(estimate)]
        if results:
            findings.append(
                "Solar web notes: "
                + " ".join(
                    f"{result['title']}: {result['content']}"
                    for result in results
                    if result["content"]
                )
            )
        else:
            findings.append(
                "Tavily returned no relevant pages; the estimate uses the stated "
                "defaults only."
            )

        return ToolObservation(
            status="available",
            findings=tuple(findings),
            data={
                "estimate": estimate,
                "web_search": {
                    "status": "available",
                    "query": search_query,
                    "results": results,
                },
            },
            evidence_refs=evidence_refs,
            assumptions=self._assumptions(estimate),
        )

    def search_web(self, query: str) -> ToolObservation:
        """Return Tavily's answer and cited sources for an explicitly approved query."""
        try:
            answer, results = self._search(query, include_answer=True)
        except TavilySearchError as exc:
            return ToolObservation(
                status="failed",
                findings=(exc.message,),
                error=AgentError(
                    code=exc.code,
                    message=exc.message,
                    retryable=True,
                ),
            )

        evidence_refs = tuple(
            EvidenceRef(
                source_id=result["url"],
                source_type="web_search",
                locator=result["url"],
                excerpt=result["content"] or result["title"],
                extraction_confidence=0.8,
            )
            for result in results
        )
        if not answer and not results:
            answer = "Tavily found no relevant web sources for this query."
        elif not answer:
            answer = (
                "Tavily did not provide a synthesized answer. Relevant source "
                "summaries are included below."
            )

        return ToolObservation(
            status="available",
            findings=(answer,),
            data={
                "query": query,
                "results": results,
            },
            evidence_refs=evidence_refs,
        )

    def _read_api_key(self) -> str:
        environment_key = os.getenv("TAVILY_API_KEY", "").strip()
        if environment_key:
            return environment_key
        try:
            api_key = self._api_key_file.read_text(encoding="utf-8").strip()
        except FileNotFoundError as exc:
            raise TavilySearchError(
                "TAVILY_API_KEY_MISSING",
                "Configure TAVILY_API_KEY or the local Tavily key file.",
            ) from exc
        except OSError as exc:
            raise TavilySearchError(
                "TAVILY_KEY_FILE_UNAVAILABLE",
                "The configured local Tavily key file could not be read.",
            ) from exc
        if not api_key:
            raise TavilySearchError(
                "TAVILY_API_KEY_EMPTY",
                "The configured local Tavily key file is empty.",
            )
        return api_key

    def _search(
        self,
        query: str,
        *,
        include_answer: bool = False,
    ) -> tuple[str | None, list[dict[str, str]]]:
        payload = json.dumps(
            {
                "api_key": self._read_api_key(),
                "query": query,
                "search_depth": "basic",
                "max_results": MAX_RESULTS,
                "include_answer": include_answer,
            },
            separators=(",", ":"),
        ).encode("utf-8")
        request = urllib.request.Request(
            "https://api.tavily.com/search",
            data=payload,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with self._opener.open(
                request,
                timeout=self._timeout_seconds,
            ) as response:
                body = response.read(MAX_RESPONSE_BYTES + 1)
                status_code = response.status
        except urllib.error.HTTPError as exc:
            raise TavilySearchError(
                "TAVILY_HTTP_ERROR",
                f"Tavily returned HTTP {exc.code}; retry the web lookup later.",
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise TavilySearchError(
                "TAVILY_UNAVAILABLE",
                "Tavily could not be reached or timed out.",
            ) from exc

        if status_code != 200:
            raise TavilySearchError(
                "TAVILY_HTTP_ERROR",
                f"Tavily returned HTTP {status_code}; retry the web lookup later.",
            )
        if len(body) > MAX_RESPONSE_BYTES:
            raise TavilySearchError(
                "TAVILY_RESPONSE_TOO_LARGE",
                "Tavily's response exceeded the configured size limit.",
            )
        try:
            response_data = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TavilySearchError(
                "TAVILY_RESPONSE_INVALID",
                "Tavily returned an invalid response.",
            ) from exc
        raw_results = response_data.get("results") if isinstance(response_data, dict) else None
        if not isinstance(raw_results, list):
            raise TavilySearchError(
                "TAVILY_RESPONSE_INVALID",
                "Tavily returned an invalid results list.",
            )

        results: list[dict[str, str]] = []
        for result in raw_results[:MAX_RESULTS]:
            if not isinstance(result, dict):
                continue
            url = result.get("url")
            if not isinstance(url, str) or not url.startswith("https://"):
                continue
            title = result.get("title")
            content = result.get("content")
            results.append(
                {
                    "url": url[:2000],
                    "title": title[:300] if isinstance(title, str) else "Solar reference",
                    "content": content[:1000] if isinstance(content, str) else "",
                }
            )
        answer = response_data.get("answer")
        return (
            answer.strip()[:4000] if isinstance(answer, str) and answer.strip() else None,
            results,
        )

    @classmethod
    def _estimate(cls, goal: str) -> dict[str, Any]:
        capacity_kw = None
        capacity_match = CAPACITY_PATTERN.search(goal)
        if capacity_match:
            capacity_kw = float(capacity_match.group("value").replace(",", ""))
            if capacity_match.group("unit").lower() == "mw":
                capacity_kw *= 1000

        area_match = AREA_PATTERN.search(goal)
        roof_area_sqm = None
        if area_match:
            roof_area_sqm = float(area_match.group("value").replace(",", ""))
            if "ft" in area_match.group("unit").lower():
                roof_area_sqm *= 0.092903

        usage_match = USAGE_PATTERN.search(goal)
        annual_consumption_kwh = None
        if usage_match:
            usage_value = float(usage_match.group("value").replace(",", ""))
            period = (
                usage_match.group("period")
                or usage_match.group("word_period")
                or ""
            ).lower()
            if not period:
                context = goal[max(0, usage_match.start() - 24):usage_match.start()].lower()
                if "annual" in context or "year" in context:
                    period = "year"
                else:
                    period = "month"
            annual_consumption_kwh = (
                usage_value
                if period.startswith("year") or period.startswith("annual")
                else usage_value * 12
            )
        if (
            capacity_kw is None
            and roof_area_sqm is None
            and annual_consumption_kwh is None
        ):
            raise TavilySearchError(
                "SOLAR_INPUT_REQUIRED",
                "Provide system capacity, usable roof area, or annual energy "
                "consumption before requesting a site-specific solar estimate.",
            )
        monthly_consumption_kwh = (
            annual_consumption_kwh / 12
            if annual_consumption_kwh is not None
            else None
        )
        if capacity_kw is None and roof_area_sqm is not None:
            capacity_kw = roof_area_sqm * PANEL_CAPACITY_KW_PER_SQM
        elif capacity_kw is None and monthly_consumption_kwh is not None:
            daily_yield_per_kw = DEFAULT_PEAK_SUN_HOURS * DEFAULT_PERFORMANCE_RATIO
            capacity_kw = (
                monthly_consumption_kwh / 30 / daily_yield_per_kw
            )
        if not math.isfinite(capacity_kw) or not 0.1 <= capacity_kw <= 100_000:
            raise TavilySearchError(
                "SOLAR_INPUT_OUT_OF_RANGE",
                "Solar system size must be between 0.1 kW and 100 MW.",
            )
        if roof_area_sqm is not None and not 1 <= roof_area_sqm <= 10_000_000:
            raise TavilySearchError(
                "SOLAR_INPUT_OUT_OF_RANGE",
                "Roof area must be between 1 and 10,000,000 square metres.",
            )
        if annual_consumption_kwh is not None and not (
            0.1 <= annual_consumption_kwh <= 12_000_000_000
        ):
            raise TavilySearchError(
                "SOLAR_INPUT_OUT_OF_RANGE",
                "Annual consumption must be between 0.1 and 12,000,000,000 kWh.",
            )

        tariff_match = TARIFF_PATTERN.search(goal)
        tariff = (
            float(tariff_match.group(1).replace(",", ""))
            if tariff_match
            else None
        )
        if tariff is not None and (
            not math.isfinite(tariff) or not 0 < tariff <= 100_000
        ):
            raise TavilySearchError(
                "SOLAR_INPUT_OUT_OF_RANGE",
                "Electricity tariff must be greater than zero and at most ₹100,000/kWh.",
            )

        annual_generation = (
            capacity_kw * DEFAULT_PEAK_SUN_HOURS * 365 * DEFAULT_PERFORMANCE_RATIO
        )
        install_cost = capacity_kw * DEFAULT_INSTALL_COST_INR_PER_KW
        annual_offset = (
            min(annual_generation, annual_consumption_kwh)
            if annual_consumption_kwh is not None
            else None
        )
        annual_savings = (
            annual_offset * tariff
            if annual_offset is not None and tariff is not None
            else None
        )
        return {
            "technology": "solar",
            "location": cls._location(goal),
            "capacity_kw": round(capacity_kw, 2),
            "roof_area_sqm": round(roof_area_sqm, 1) if roof_area_sqm else None,
            "annual_consumption_kwh": annual_consumption_kwh,
            "annual_generation_kwh": round(annual_generation),
            "estimated_install_cost_inr": round(install_cost),
            "tariff_inr_per_kwh": round(tariff, 2) if tariff is not None else None,
            "estimated_annual_savings_inr": (
                round(annual_savings) if annual_savings is not None else None
            ),
            "simple_payback_years": (
                round(install_cost / annual_savings, 1)
                if annual_savings is not None and annual_savings > 0
                else None
            ),
        }

    @classmethod
    def _estimate_wind(cls, goal: str) -> dict[str, Any]:
        capacity_match = CAPACITY_PATTERN.search(goal)
        capacity_factor_match = CAPACITY_FACTOR_PATTERN.search(goal)
        if capacity_match is None or capacity_factor_match is None:
            missing = []
            if capacity_match is None:
                missing.append("rated wind-turbine capacity (kW)")
            if capacity_factor_match is None:
                missing.append("measured or specified capacity factor (%)")
            raise TavilySearchError(
                "WIND_INPUT_REQUIRED",
                "Provide " + " and ".join(missing) + " to calculate a wind scenario.",
            )
        capacity_kw = float(capacity_match.group("value").replace(",", ""))
        unit = capacity_match.group("unit").casefold()
        if unit == "mw":
            capacity_kw *= 1000
        capacity_factor = float(
            capacity_factor_match.group(1) or capacity_factor_match.group(2)
        ) / 100
        if not 0 < capacity_kw <= 100_000 or not 0 < capacity_factor <= 1:
            raise TavilySearchError(
                "WIND_INPUT_OUT_OF_RANGE",
                "Wind capacity must be positive and at most 100 MW; "
                "capacity factor must be greater than 0% and at most 100%.",
            )
        annual_generation = capacity_kw * capacity_factor * 8760
        usage_match = USAGE_PATTERN.search(goal)
        annual_consumption = None
        if usage_match:
            usage = float(usage_match.group("value").replace(",", ""))
            period = (
                usage_match.group("period")
                or usage_match.group("word_period")
                or ""
            ).casefold()
            annual_consumption = (
                usage
                if period.startswith("year") or period.startswith("annual")
                else usage * 12
            )
        tariff_match = TARIFF_PATTERN.search(goal)
        tariff = (
            float(tariff_match.group(1).replace(",", ""))
            if tariff_match
            else None
        )
        cost_match = CAPEX_PATTERN.search(goal)
        capex = (
            float(cost_match.group(1).replace(",", ""))
            if cost_match
            else None
        )
        annual_offset = (
            min(annual_generation, annual_consumption)
            if annual_consumption is not None
            else None
        )
        annual_savings = (
            annual_offset * tariff
            if annual_offset is not None and tariff is not None
            else None
        )
        if capex is not None and (not math.isfinite(capex) or capex <= 0):
            raise TavilySearchError(
                "WIND_INPUT_OUT_OF_RANGE",
                "Project CAPEX must be a positive finite amount.",
            )
        return {
            "technology": "wind",
            "location": cls._location(goal),
            "capacity_kw": round(capacity_kw, 2),
            "capacity_factor": capacity_factor,
            "annual_generation_kwh": round(annual_generation),
            "annual_consumption_kwh": annual_consumption,
            "tariff_inr_per_kwh": tariff,
            "estimated_annual_savings_inr": (
                round(annual_savings) if annual_savings is not None else None
            ),
            "estimated_project_cost_inr": capex,
            "simple_payback_years": (
                round(capex / annual_savings, 1)
                if capex is not None
                and annual_savings is not None
                and annual_savings > 0
                else None
            ),
        }

    @classmethod
    def _estimate_battery(cls, goal: str) -> dict[str, Any]:
        energy_match = BATTERY_ENERGY_PATTERN.search(goal)
        power_match = BATTERY_POWER_PATTERN.search(goal)
        efficiency_match = EFFICIENCY_PATTERN.search(goal)
        cycles_match = CYCLE_PATTERN.search(goal)
        peak_match = PEAK_TARIFF_PATTERN.search(goal)
        offpeak_match = OFFPEAK_TARIFF_PATTERN.search(goal)
        required = {
            "battery energy capacity (kWh)": energy_match,
            "battery charge/discharge power (kW)": power_match,
            "round-trip efficiency (%)": efficiency_match,
            "cycles per day": cycles_match,
            "peak tariff (₹/kWh)": peak_match,
            "off-peak tariff (₹/kWh)": offpeak_match,
        }
        missing = [label for label, match in required.items() if match is None]
        if missing:
            raise TavilySearchError(
                "BATTERY_INPUT_REQUIRED",
                "Provide " + ", ".join(missing) + " to calculate battery "
                "arbitrage; no savings or payback is inferred.",
            )
        capacity_kwh = float(energy_match.group(1).replace(",", ""))
        power_kw = float(power_match.group(1).replace(",", ""))
        efficiency = float(efficiency_match.group(1)) / 100
        cycles_per_day = float(cycles_match.group(1))
        peak_tariff = float(peak_match.group(1).replace(",", ""))
        offpeak_tariff = float(offpeak_match.group(1).replace(",", ""))
        values = (
            capacity_kwh,
            power_kw,
            efficiency,
            cycles_per_day,
            peak_tariff,
            offpeak_tariff,
        )
        if (
            any(not math.isfinite(value) for value in values)
            or not 0 < capacity_kwh <= 1_000_000
            or not 0 < power_kw <= 1_000_000
            or not 0 < efficiency <= 1
            or not 0 < cycles_per_day <= 10
            or not 0 <= offpeak_tariff <= 100_000
            or not 0 <= peak_tariff <= 100_000
        ):
            raise TavilySearchError(
                "BATTERY_INPUT_OUT_OF_RANGE",
                "Battery capacity, power, efficiency, cycles, and tariffs "
                "must be within supported positive finite bounds.",
            )
        daily_discharge_kwh = min(capacity_kwh, power_kw) * cycles_per_day
        annual_savings = max(
            0.0,
            daily_discharge_kwh
            * 365
            * (peak_tariff - offpeak_tariff / efficiency),
        )
        cost_match = CAPEX_PATTERN.search(goal)
        capex = (
            float(cost_match.group(1).replace(",", ""))
            if cost_match
            else None
        )
        if capex is not None and (not math.isfinite(capex) or capex <= 0):
            raise TavilySearchError(
                "BATTERY_INPUT_OUT_OF_RANGE",
                "Project CAPEX must be a positive finite amount.",
            )
        return {
            "technology": "battery",
            "energy_capacity_kwh": capacity_kwh,
            "power_capacity_kw": power_kw,
            "round_trip_efficiency": efficiency,
            "cycles_per_day": cycles_per_day,
            "peak_tariff_inr_per_kwh": peak_tariff,
            "offpeak_tariff_inr_per_kwh": offpeak_tariff,
            "estimated_annual_arbitrage_savings_inr": round(annual_savings),
            "estimated_project_cost_inr": capex,
            "simple_payback_years": (
                round(capex / annual_savings, 1)
                if capex is not None and annual_savings > 0
                else None
            ),
        }

    @staticmethod
    def _location(goal: str) -> str | None:
        match = LOCATION_PATTERN.search(goal)
        if not match:
            return None
        location = match.group(1).strip(" .,-")
        return location[:50] or None

    @staticmethod
    def _assumptions(estimate: dict[str, Any]) -> tuple[str, ...]:
        if estimate["technology"] == "wind":
            assumptions = [
                "Annual generation uses the supplied rated capacity and capacity "
                "factor over 8,760 hours; site wind measurements were not independently verified."
            ]
            if estimate["estimated_annual_savings_inr"] is None:
                assumptions.append(
                    "Savings and payback require supplied annual consumption and tariff."
                )
            else:
                assumptions.append(
                    "Energy offset is capped at supplied annual consumption; "
                    "no interval load, curtailment, or export-credit profile was supplied."
                )
            if estimate["estimated_project_cost_inr"] is None:
                assumptions.append(
                    "Payback is not reported because project CAPEX was not supplied."
                )
            return tuple(assumptions)
        if estimate["technology"] == "battery":
            assumptions = [
                "Each cycle uses the full modeled energy capacity, with one hour "
                "at the supplied power rating; round-trip losses are represented "
                "by the supplied efficiency."
            ]
            if estimate["estimated_project_cost_inr"] is None:
                assumptions.append(
                    "Payback is not reported because project CAPEX was not supplied."
                )
            return tuple(assumptions)
        assumptions = [
            f"Solar yield uses {DEFAULT_PEAK_SUN_HOURS} peak-sun-hours/day and "
            f"{DEFAULT_PERFORMANCE_RATIO:.0%} system performance; location-specific "
            "weather and shading are not modeled.",
            f"Installation uses an illustrative ₹{DEFAULT_INSTALL_COST_INR_PER_KW:,}/kW "
            "before subsidies, financing, batteries, and maintenance.",
        ]
        if estimate["annual_consumption_kwh"] is None:
            assumptions.append(
                "Savings and payback are not reported because annual consumption "
                "was not supplied."
            )
        else:
            assumptions.append(
                "Estimated generation offset is capped at supplied annual "
                "consumption; no interval load or export-credit profile was supplied."
            )
        if estimate["tariff_inr_per_kwh"] is None:
            assumptions.append(
                "Savings and payback are not reported because an electricity "
                "tariff was not supplied."
            )
        return tuple(assumptions)

    @staticmethod
    def _format_estimate(estimate: dict[str, Any]) -> str:
        technology = estimate["technology"]
        if technology == "wind":
            location = f" in {estimate['location']}" if estimate["location"] else ""
            lines = [
                f"Illustrative wind estimate{location}: "
                f"{estimate['capacity_kw']:,.2f} kW at "
                f"{estimate['capacity_factor']:.1%} capacity factor; "
                f"{estimate['annual_generation_kwh']:,.0f} kWh/year."
            ]
            if estimate["estimated_annual_savings_inr"] is not None:
                lines.append(
                    "Calculated energy-charge value is "
                    f"₹{estimate['estimated_annual_savings_inr']:,.0f}/year "
                    "using supplied annual consumption and tariff."
                )
            if estimate["estimated_project_cost_inr"] is not None:
                lines.append(
                    "Supplied project CAPEX is "
                    f"₹{estimate['estimated_project_cost_inr']:,.0f}; "
                    f"simple payback: {estimate['simple_payback_years']} years."
                )
            return " ".join(lines)
        if technology == "battery":
            lines = [
                "Illustrative battery arbitrage scenario: "
                f"{estimate['energy_capacity_kwh']:,.2f} kWh / "
                f"{estimate['power_capacity_kw']:,.2f} kW, "
                f"{estimate['round_trip_efficiency']:.1%} round-trip efficiency; "
                "calculated annual arbitrage value "
                f"₹{estimate['estimated_annual_arbitrage_savings_inr']:,.0f}."
            ]
            if estimate["estimated_project_cost_inr"] is not None:
                lines.append(
                    "Supplied project CAPEX is "
                    f"₹{estimate['estimated_project_cost_inr']:,.0f}; "
                    f"simple payback: {estimate['simple_payback_years']} years."
                )
            return " ".join(lines)
        location = f" in {estimate['location']}" if estimate["location"] else ""
        lines = [
            f"Illustrative rooftop solar estimate{location}: "
            f"{estimate['capacity_kw']:,.2f} kW system; "
            f"{estimate['annual_generation_kwh']:,.0f} kWh/year generation.",
        ]
        if estimate["estimated_annual_savings_inr"] is not None:
            lines.append(
                f"Illustrative annual energy-charge value: "
                f"₹{estimate['estimated_annual_savings_inr']:,.0f} at "
                f"₹{estimate['tariff_inr_per_kwh']:,.2f}/kWh; "
                f"simple payback: {estimate['simple_payback_years']} years."
            )
        else:
            lines.append(
                "Savings and payback are not reported without both supplied "
                "annual consumption and tariff."
            )
        lines.append(
            "Illustrative installed cost: "
            f"₹{estimate['estimated_install_cost_inr']:,.0f}; uses the stated "
            "assumed cost per kW, not a quote."
        )
        if estimate["roof_area_sqm"] is not None:
            lines.append(f"Entered roof area: {estimate['roof_area_sqm']:,.1f} m².")
        return " ".join(lines)
