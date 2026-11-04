"""Deterministic, corpus-aware query planning for Commercial PDF retrieval."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

QUERY_TOPICS: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    (
        "electricity_costs",
        (
            "electricity bill",
            "energy charge",
            "tariff",
            "demand charge",
            "power factor",
            "fixed charge",
            "bill components",
            "cost of electricity",
        ),
        (
            "industrial electricity bill energy charges kWh tariff maximum "
            "demand charges fixed charges power factor taxes contract"
        ),
    ),
    (
        "load_profiles_and_peak_shaving",
        (
            "load profile",
            "peak demand",
            "peak shaving",
            "load shifting",
            "shift load",
            "demand peak",
            "baseload",
        ),
        (
            "load profile peak demand kW interval demand baseload idle load "
            "load shifting flexible activity tariff destination window "
            "stagger equipment starts reschedule"
        ),
    ),
    (
        "compressed_air",
        ("compressed air", "air compressor", "air leak", "compressed-air"),
        (
            "compressed air system leakage leaks pressure end uses filters "
            "dryers repair minimum required pressure process requirements"
        ),
    ),
    (
        "motors_and_pumps",
        ("motor", "motors", "pump", "pumps", "variable speed"),
        (
            "motors pumps process demand throttling bypass variable speed "
            "alignment bearings seals lubrication minimum flow"
        ),
    ),
    (
        "cooling_and_hvac",
        ("cooling", "hvac", "air conditioning", "heat exchanger", "condenser"),
        (
            "cooling HVAC heat exchanger filters condenser ambient temperature "
            "setpoint product quality humidity worker safety"
        ),
    ),
    (
        "furnaces_and_process_heating",
        ("furnace", "furnaces", "process heating", "waste heat", "heating recipe"),
        (
            "furnaces process heating idle time insulation seals batch scheduling "
            "waste heat recipes ramp rates soak times quality controls"
        ),
    ),
    (
        "lighting",
        ("lighting", "lights", "occupancy sensor"),
        (
            "lighting zone-based controls occupancy sensors scheduling "
            "illumination emergency lighting safety"
        ),
    ),
    (
        "solar_pv",
        ("solar", "solar pv", "photovoltaic", "rooftop PV"),
        (
            "solar rooftop PV photovoltaic usable roof area shading structural "
            "suitability orientation tilt solar resource interval load profile"
        ),
    ),
    (
        "battery_storage",
        ("battery", "batteries", "storage", "state of charge"),
        (
            "battery energy capacity kWh power capability kW state of charge "
            "round-trip efficiency degradation warranty inverter peak shaving "
            "backup self-consumption"
        ),
    ),
    (
        "energy_calculations",
        (
            "simple payback",
            "load factor",
            "self-consumption ratio",
            "energy charge calculation",
            "calculation framework",
            "average demand",
        ),
        (
            "illustrative calculation energy charge interval kWh tariff average "
            "demand load factor self-consumption ratio simple payback round-trip "
            "efficiency example"
        ),
    ),
    (
        "optimization_constraints",
        (
            "optimization",
            "optimize",
            "optimise",
            "scheduling",
            "schedule loads",
            "production constraints",
            "machine constraints",
        ),
        (
            "energy cost optimizer minimize total cost production engineering "
            "constraints machine availability operating hours process sequence "
            "precedence production deadlines maintenance battery state of charge "
            "inverter limits safety quality feasible"
        ),
    ),
    (
        "equipment_register",
        (
            "equipment",
            "equipment register",
            "machine register",
            "machine id",
            "rated power",
            "operating window",
        ),
        (
            "factory profile equipment register machine ID asset nameplate rated "
            "power operating window production equipment process dependencies"
        ),
    ),
    (
        "automotive_parts_operations",
        (
            "automotive parts",
            "cnc machining",
            "metal stamping",
            "stamping press",
            "injection molding",
            "die casting",
            "parts assembly",
            "paint line",
        ),
        (
            "automotive parts manufacturing illustrative process CNC machining "
            "metal stamping press injection molding die casting parts assembly "
            "paint line maintenance windows production jobs machine safety"
        ),
    ),
    (
        "analysis_workflow",
        (
            "analysis workflow",
            "analysis steps",
            "how should gridvision",
            "rag workflow",
            "retrieval workflow",
        ),
        (
            "ingest factory documents interval meter data tariff baseline "
            "forecast operating constraints deterministic calculations "
            "optimizer report evidence human approval"
        ),
    ),
    (
        "evidence_and_safety",
        (
            "evidence",
            "provenance",
            "conflicting documents",
            "safety",
            "confidence",
            "source references",
        ),
        (
            "evidence provenance document revision page section conflicts "
            "site-approved documents safety procedures source references "
            "general educational demonstration"
        ),
    ),
)

FACTORY_SPECIFIC_QUERY = re.compile(
    r"\b(?:"
    r"our (?:specific )?(?:machine|machines|equipment|bill|tariff|meter|"
    r"production|maintenance|factory data|energy use|energy consumption)|"
    r"this (?:specific )?(?:machine|equipment|factory|facility|site)|"
    r"actual (?:factory|facility|machine|meter|production|energy|load)|"
    r"current (?:factory|facility|machine|meter|production|energy|load)|"
    r"machine (?:id|status|schedule|record)|maintenance (?:schedule|record)|"
    r"work order|meter reading|load profile|production target|"
    r"how many machines|"
    r"(?:energy|electricity|power) consumption (?:at|for|of) "
    r"(?:our|this|the) (?:factory|facility|site)|"
    r"our (?:factory|facility|site) (?:uses|consumes|consumption|load)"
    r")\b",
    re.IGNORECASE,
)
MACHINE_STATUS_QUERY = re.compile(
    r"\b(?:how many|count|number of)\s+(?:the\s+)?machines?\b|"
    r"\b(?:machines?|equipment)\s+(?:are\s+)?"
    r"(?:working|running|operational|active|online)\b",
    re.IGNORECASE,
)
QUERY_STOP_WORDS = {
    "a",
    "about",
    "an",
    "and",
    "check",
    "do",
    "factory",
    "for",
    "give",
    "help",
    "i",
    "in",
    "information",
    "me",
    "operations",
    "please",
    "tell",
    "the",
    "to",
    "what",
    "where",
    "which",
    "who",
    "with",
    "you",
}


@dataclass(frozen=True)
class RetrievalQuery:
    """Validated route from a natural-language request to a corpus search."""

    status: Literal["ready", "needs_clarification", "factory_specific"]
    search_text: str
    topics: tuple[str, ...] = ()
    anchor_phrases: tuple[str, ...] = ()
    reason: str | None = None


def build_retrieval_query(question: str) -> RetrievalQuery:
    """Create a focused search query using topics documented in the handbook."""
    normalized = " ".join(question.split())
    lowered = normalized.casefold()
    factory_specific = bool(FACTORY_SPECIFIC_QUERY.search(normalized))
    if MACHINE_STATUS_QUERY.search(normalized):
        return RetrievalQuery(
            status="factory_specific",
            search_text=(
                f"{normalized} machine machines equipment status running "
                "working operational active online stopped idle offline"
            ),
            topics=("equipment_register",),
            reason=(
                "Factory-specific questions require evidence from an actual, "
                "non-demonstration operations record."
            ),
        )
    matched = [
        (name, aliases, terms)
        for name, aliases, terms in QUERY_TOPICS
        if any(alias in lowered for alias in aliases)
    ]
    if not matched:
        informative_terms = [
            token
            for token in re.findall(r"[a-z0-9][a-z0-9._/-]*", lowered)
            if token not in QUERY_STOP_WORDS
        ]
        if len(informative_terms) >= 2 or factory_specific:
            return RetrievalQuery(
                status="factory_specific" if factory_specific else "ready",
                search_text=normalized,
                reason=(
                    "Factory-specific questions require evidence from an "
                    "actual, non-demonstration operations record."
                    if factory_specific
                    else None
                ),
            )
        return RetrievalQuery(
            status="needs_clarification",
            search_text="",
            reason=(
                "Specify a handbook topic such as electricity tariffs, peak "
                "demand, compressed air, motors and pumps, cooling/HVAC, "
                "furnaces, lighting, solar, batteries, optimization, or "
                "evidence and safety."
            ),
        )

    search_text = " ".join(
        [normalized, *(terms for _, _, terms in matched)]
    )
    anchor_phrases = tuple(
        dict.fromkeys(
            alias
            for _, aliases, _ in matched
            for alias in aliases
            if alias in lowered
        )
    )
    return RetrievalQuery(
        status="factory_specific" if factory_specific else "ready",
        search_text=search_text,
        topics=tuple(name for name, _, _ in matched),
        anchor_phrases=anchor_phrases,
        reason=(
            "Factory-specific questions require evidence from an actual, "
            "non-demonstration operations record."
            if factory_specific
            else None
        ),
    )
