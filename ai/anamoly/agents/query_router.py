"""Intent and date extraction for the anomaly assistant."""

from __future__ import annotations

import os
import re
from datetime import date, datetime, timedelta
from typing import Any

ISO_DATE_PATTERN = re.compile(r"\b\d{4}-\d{1,2}-\d{1,2}\b")
NUMERIC_DATE_PATTERN = re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{4}\b")
MONTHS = (
    "January|February|March|April|May|June|July|August|September|October|"
    "November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"
)
NAMED_DATE_PATTERNS = (
    re.compile(rf"\b\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{MONTHS})\s+\d{{4}}\b", re.I),
    re.compile(rf"\b(?:{MONTHS})\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}}\b", re.I),
    re.compile(rf"\b\d{{1,2}}(?:st|nd|rd|th)?[-\s]+(?:{MONTHS})[-\s]+\d{{4}}\b", re.I),
    re.compile(rf"\b(?:{MONTHS})[-\s]+\d{{1,2}}(?:st|nd|rd|th)?[-,\s]+\d{{4}}\b", re.I),
)
RUN_PATTERN = re.compile(
    r"\b(?:(?:saved|completed)\s+)?(?:run|analysis)(?:[ _-]?id)?[:# ]+([a-f0-9]{32})\b",
    re.IGNORECASE,
)
EVENT_PATTERN = re.compile(
    r"\b(?:event|evt)[ _-]?id[:# ]+([A-Za-z0-9_-]+)\b", re.IGNORECASE
)
# EVT_ is the canonical form. Accept the common dropped-leading-E typo VT_ as
# well so a follow-up still resolves to the saved event instead of all events.
EVENT_TOKEN_PATTERN = re.compile(r"\b(?:EVT|VT)_[A-Za-z0-9_-]+\b", re.IGNORECASE)
CUSTOMER_PATTERN = re.compile(
    r"\bcustomer[_ -]?id[:# ]+(\d+)\b", re.IGNORECASE
)
DATE_LOCALE = os.getenv("GRIDVISION_ANOMALY_DATE_LOCALE", "en-IN").lower()


def _parse_date(value: str) -> date:
    if re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", value):
        year, month, day = map(int, value.split("-"))
        return date(year, month, day)

    if re.fullmatch(r"\d{1,2}[/-]\d{1,2}[/-]\d{4}", value):
        first, second, year = map(int, re.split(r"[/-]", value))
        if first > 12:
            day_first = True
        elif second > 12:
            day_first = False
        elif DATE_LOCALE in {"en-in", "en_in", "en-gb", "en_gb", "en-au", "en_au"}:
            day_first = True
        elif DATE_LOCALE in {"en-us", "en_us", "us"}:
            day_first = False
        else:
            raise ValueError(
                f"Ambiguous numeric date for configured locale {DATE_LOCALE}: {value}"
            )
        month, day = (second, first) if day_first else (first, second)
        return date(year, month, day)

    normalized = re.sub(r"(?<=\d)(?:st|nd|rd|th)\b", "", value, flags=re.I)
    normalized = re.sub(r"[-/]", " ", normalized)
    for pattern in ("%d %B %Y", "%d %b %Y", "%B %d %Y", "%b %d %Y"):
        try:
            return datetime.strptime(normalized.replace(",", ""), pattern).date()
        except ValueError:
            continue
    raise ValueError(f"Unrecognized or invalid date: {value}")


def extract_prompt_dates(
    prompt: str, *, today: date | None = None
) -> tuple[list[date], list[str], bool]:
    """Extract explicit or supported relative dates in prompt order."""
    matches: list[tuple[int, str]] = []
    for pattern in (ISO_DATE_PATTERN, NUMERIC_DATE_PATTERN, *NAMED_DATE_PATTERNS):
        matches.extend((match.start(), match.group(0)) for match in pattern.finditer(prompt))
    matches.sort(key=lambda item: item[0])

    parsed: list[date] = []
    raw: list[str] = []
    for _, value in matches:
        raw.append(value)
        try:
            parsed.append(_parse_date(value))
        except ValueError:
            return [], raw, True

    if parsed:
        return parsed[:2], raw[:2], False

    relative_date = today or date.today()
    lowered = prompt.lower()
    relative_patterns = (
        (r"\bday before yesterday\b", relative_date - timedelta(days=2)),
        (r"\byesterday\b", relative_date - timedelta(days=1)),
        (r"\btoday\b", relative_date),
    )
    for pattern, resolved in relative_patterns:
        if re.search(pattern, lowered):
            return [resolved], [resolved.isoformat()], False
    return [], [], False


def route_prompt(prompt: str, *, today: date | None = None) -> dict[str, Any]:
    """Classify a prompt before deciding whether dataset date validation applies."""
    text = prompt.strip()
    lowered = re.sub(r"\banamoly\b", "anomaly", text.lower())
    dates, raw_dates, invalid_date = extract_prompt_dates(text, today=today)

    run_match = RUN_PATTERN.search(text)
    event_match = EVENT_PATTERN.search(text)
    event_id = (
        event_match.group(1)
        if event_match
        else (
            EVENT_TOKEN_PATTERN.search(text).group(0)
            if EVENT_TOKEN_PATTERN.search(text)
            else None
        )
    )
    if event_id:
        event_id = str(event_id).upper()
        if event_id.startswith("VT_"):
            event_id = f"E{event_id}"
    if any(term in lowered for term in ("export", "download", "csv", "geojson")) and run_match:
        return {
            "intent": "export",
            "run_id": run_match.group(1),
            "format": "geojson" if "geojson" in lowered else "json" if "json" in lowered else "csv",
            "dataset": "events" if "event" in lowered else "anomalies",
            "dates": raw_dates,
        }

    rectification_request = any(
        term in lowered
        for term in (
            "rectification",
            "rectify",
            "rectifying",
            "rectified",
            "root cause",
            "likely cause",
            "probable cause",
            "possible cause",
            "cause of",
            "what caused",
            "causes of",
            "what can cause",
            "what could cause",
            "what could have caused",
            "could have caused",
            "may have caused",
            "may cause",
            "what may cause",
            "can be causes",
            "what could be causes",
            "cause and solution",
            "causes and solution",
            "solution",
            "solutions",
            "remedy",
            "remedies",
            "how to resolve",
            "how to address",
            "recommended fix",
            "possible cause",
            "mitigation",
            "investigate",
            "how to fix",
            "how can i fix",
            "repair",
            "fix this",
            "fix the event",
            "resolve this",
            "corrective measure",
            "response plan",
        )
    ) or (
        "how should" in lowered
        and any(term in lowered for term in ("outage", "event", "severity", "anomaly"))
    ) or (
        "what causes" in lowered
        and (event_id or dates or "this " in lowered or "high-severity" in lowered)
    )
    if event_id and not rectification_request and any(
        term in lowered
        for term in ("event", "classified", "classification", "multi_area", "multi area")
    ):
        return {
            "intent": "event_query",
            "event_id": event_id,
            "run_id": run_match.group(1) if run_match else None,
            "dates": raw_dates,
        }
    if event_id and not rectification_request and any(
        term in lowered
        for term in (
            "coordinate", "location", "latitude", "longitude", "severity",
            "scope", "event type", "anomaly type", "duration", "cluster",
            "customer", "affected", "details", "detail", "score",
        )
    ):
        return {
            "intent": "event_query",
            "event_id": event_id,
            "run_id": run_match.group(1) if run_match else None,
            "dates": raw_dates,
        }

    explicit_analysis = any(
        phrase in lowered
        for phrase in (
            "run analysis",
            "run anomaly analysis",
            "run the anomaly analysis",
            "start anomaly analysis",
            "perform anomaly analysis",
            "analyze ",
            "analyse ",
            "execute analysis",
        )
    ) or any(
        phrase in lowered
        for phrase in (
            "run trained anomaly model",
            "run the trained anomaly model",
            "run the trained model",
            "execute anomaly prediction",
            "run anomaly prediction",
            "predict anomalies",
            "perform anomaly prediction",
        )
    )
    if explicit_analysis:
        if invalid_date:
            return {"intent": "invalid_date", "dates": raw_dates}
        if not dates:
            return {"intent": "analysis_execution", "dates": []}
        return {
            "intent": "analysis_execution",
            "start_date": dates[0].isoformat(),
            "end_date": dates[1].isoformat() if len(dates) > 1 else dates[0].isoformat(),
            "dates": raw_dates,
        }

    if any(
        term in lowered
        for term in (
            "customer impact",
            "impact on customer",
            "affected customer",
            "customers affected",
            "my meter",
            "my account",
        )
    ):
        if invalid_date:
            return {"intent": "invalid_date", "dates": raw_dates}
        return {
            "intent": "customer_impact_query",
            "start_date": dates[0].isoformat() if dates else None,
            "end_date": dates[1].isoformat() if len(dates) > 1 else (
                dates[0].isoformat() if dates else None
            ),
            "customer_id": (
                int(CUSTOMER_PATTERN.search(text).group(1))
                if CUSTOMER_PATTERN.search(text)
                else None
            ),
            "run_id": run_match.group(1) if run_match else None,
            "needs_context": not dates and not CUSTOMER_PATTERN.search(text) and not run_match,
        }

    if any(
        term in lowered
        for term in (
            "rectification",
            "rectify",
            "rectifying",
            "rectified",
            "root cause",
            "likely cause",
            "probable cause",
            "possible cause",
            "cause of",
            "what caused",
            "causes of",
            "what can cause",
            "what could cause",
            "what could have caused",
            "could have caused",
            "may have caused",
            "may cause",
            "what may cause",
            "possible cause",
            "mitigation",
            "investigate",
            "how to fix",
            "how can i fix",
            "repair",
            "fix this",
            "fix the event",
            "resolve this",
            "corrective measure",
            "response plan",
        )
    ) or (
        "how should" in lowered
        and any(term in lowered for term in ("outage", "event", "severity", "anomaly"))
    ) or (
        "what causes" in lowered
        and (event_id or dates or "this " in lowered or "high-severity" in lowered)
    ):
        return {
            "intent": "rectification_query",
            "event_id": event_id,
            "run_id": run_match.group(1) if run_match else None,
            "start_date": dates[0].isoformat() if dates else None,
            "end_date": dates[1].isoformat() if len(dates) > 1 else (
                dates[0].isoformat() if dates else None
            ),
            "dates": [item.isoformat() for item in dates],
        }

    historical_request = any(
        term in lowered
        for term in (
            "show anomaly",
            "show anomalies",
            "show event",
            "show events",
            "list anomaly",
            "list event",
            "query anomaly",
            "query event",
            "find anomaly",
            "find event",
            "what anomalies",
            "what were the anomalies",
            "what happened",
            "were any ",
            "anomaly between",
            "anomalies between",
            "anomaly from",
            "anomalies from",
        )
    )
    has_anomaly_term = any(
        term in lowered
        for term in ("anomaly", "anomalies", "event", "events", "outage")
    )
    date_scoped_prediction = bool(dates) and any(
        cue in lowered for cue in ("between", "from", "on", "during", "for")
    ) and any(
        term in lowered
        for term in (
            "anomaly",
            "anomalies",
            "prediction",
            "predictions",
            "predict",
            "event",
            "events",
            "spike",
            "drop",
            "flatline",
            "zero-block",
            "zero_block",
        )
    )
    undated_prediction_period = not dates and any(
        phrase in lowered
        for phrase in (
            "anomaly prediction between",
            "anomaly predictions between",
            "anomaly prediction from",
            "anomaly predictions from",
            "anomaly prediction for",
            "anomaly predictions for",
        )
    )
    historical_request = (
        historical_request or date_scoped_prediction or undated_prediction_period
    )
    if historical_request:
        if invalid_date:
            return {"intent": "invalid_date", "dates": raw_dates}
        if not dates:
            return {"intent": "historical_anomaly_query", "dates": []}
        return {
            "intent": "historical_anomaly_query",
            "start_date": dates[0].isoformat(),
            "end_date": dates[1].isoformat() if len(dates) > 1 else dates[0].isoformat(),
            "dates": raw_dates,
        }

    external_topic = any(
        term in lowered
        for term in ("safety", "guideline", "guidance", "regulation", "standard")
    )
    if (
        any(term in lowered for term in ("regulation", "regulatory"))
        or (
            external_topic
            and any(term in lowered for term in ("current", "latest", "most recent"))
        )
    ):
        return {"intent": "current_guidance", "dates": [item.isoformat() for item in dates]}

    technical_topics = (
        "fft",
        "wavelet",
        "flatline",
        "zero_block",
        "zero-block",
        "spike anomaly",
        "voltage sag",
        "energy time series",
        "electrical",
        "electricity",
        "transformer",
        "power quality",
        "meter",
    )
    technical_verbs = (
        "explain",
        "what is",
        "what does",
        "what causes",
        "how does",
        "how do",
        "safety",
        "standard",
        "procedure",
        "guidance",
    )
    direct_technical_signals = ("safety", "standard", "procedure", "guidance")
    if (
        any(term in lowered for term in technical_topics)
        or any(term in lowered for term in direct_technical_signals)
        or (
            any(term in lowered for term in technical_verbs)
            and any(
                term in lowered
                for term in (
                    "anomaly",
                    "grid",
                    "meter",
                    "electrical",
                    "energy",
                    "voltage",
                    "transformer",
                )
            )
        )
    ):
        return {"intent": "technical_explanation", "dates": [item.isoformat() for item in dates]}

    if has_anomaly_term:
        return {"intent": "general_knowledge", "dates": [item.isoformat() for item in dates]}

    if any(word in lowered for word in ("today", "yesterday", "this week", "now")):
        return {"intent": "historical_anomaly_query", "dates": [item.isoformat() for item in dates]}

    if dates:
        return {"intent": "general_knowledge", "dates": [item.isoformat() for item in dates]}
    if re.fullmatch(
        r"(?:yes|y|yeah|yep|sure|go ahead|proceed|run it|yes please|"
        r"please proceed)[.! ]*",
        lowered,
    ):
        return {"intent": "confirmation_response", "confirmed": True, "dates": []}
    if re.fullmatch(
        r"(?:no|n|no thanks|cancel|don't|do not|not now)[.! ]*",
        lowered,
    ):
        return {"intent": "confirmation_declined", "dates": []}
    return {"intent": "general_query", "dates": []}


def classify_query(
    prompt: str,
    history: list[dict[str, Any]] | None = None,
    *,
    conversation_state: dict[str, Any] | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """Classify a turn and resolve event-detail follow-ups from thread history."""
    route = route_prompt(prompt, today=today)
    state = conversation_state or {}
    events = [item for item in state.get("events", []) if isinstance(item, dict)]
    if route.get("event_id"):
        if route["intent"] != "rectification_query":
            route = {
                **route,
                "intent": "event_query",
                "event_id": route["event_id"],
            }
        if not route.get("run_id"):
            all_matches = [
                item for item in events
                if str(item.get("event_id", item.get("id", "")))
                == str(route["event_id"])
            ]
            active_run_id = state.get("selected_run_id") or state.get("active_run_id")
            if not active_run_id:
                active_run_ids = state.get("run_ids", [])
                active_run_id = active_run_ids[0] if active_run_ids else None
            if active_run_id:
                active_matches = [
                    item for item in all_matches
                    if str(item.get("run_id", "")) == str(active_run_id)
                ]
            else:
                active_matches = []
            # Prefer an exact active-run match, then a unique match across the
            # conversation's saved runs. Reused IDs across runs stay ambiguous.
            matches = active_matches or all_matches
            if len(matches) == 1 and matches[0].get("run_id"):
                route["run_id"] = str(matches[0]["run_id"])
            elif len(matches) > 1:
                return {
                    "intent": "event_selection",
                    "requested_intent": route["intent"],
                    "candidates": matches[:20],
                }
        return route
    if route["intent"] in {
        "historical_anomaly_query", "analysis_execution",
        "customer_impact_query", "export", "invalid_date",
    }:
        return route

    lowered = prompt.lower()
    run_match = RUN_PATTERN.search(prompt)
    run_id = run_match.group(1) if run_match else None
    summary_request = any(
        word in lowered for word in (
            "summary", "summery", "summarize", "overview", "all anomalies",
            "all anomaly", "all anamoly", "all anamolies",
        )
    ) and any(
        term in lowered for term in ("this run", "current run", "saved run", "in this run", "run of detection", "run id")
    )
    all_run_detections_request = any(
        phrase in lowered
        for phrase in (
            "all detections", "all detection", "all events", "all anomalies",
            "every event", "all event",
        )
    ) and any(
        phrase in lowered
        for phrase in ("this run", "current run", "saved run", "in this run")
    )
    if summary_request or all_run_detections_request:
        active_run = run_id or state.get("active_run_id") or state.get("selected_run_id")
        active_ids = state.get("run_ids", [])
        active_run = active_run or (active_ids[0] if active_ids else None)
        return {"intent": "run_summary", "run_id": active_run}

    scope = None
    if "multi area" in lowered or "multi_area" in lowered:
        scope = "MULTI_AREA"
    elif "local area" in lowered or "local_area" in lowered:
        scope = "LOCAL_AREA"
    elif "single customer" in lowered or "single_customer" in lowered:
        scope = "SINGLE_CUSTOMER"
    if scope and any(term in lowered for term in ("anomaly", "anomal", "event", "only")):
        return {
            "intent": "event_filter_query",
            "scope": scope,
            "run_id": run_id,
            "start_date": state.get("start_date"),
            "end_date": state.get("end_date"),
        }

    if any(term in lowered for term in ("spatial map", "geospatial", "map of", "visualization", "visualisation")):
        return {
            "intent": "event_visualization",
            "run_id": run_id or (
                state.get("active_run_id")
                if any(term in lowered for term in ("this run", "current run", "saved run"))
                else None
            ),
            "start_date": state.get("start_date"),
            "end_date": state.get("end_date"),
        }

    def contextual_event_route(intent: str) -> dict[str, Any] | None:
        candidates = events
        requested_event_id = route.get("event_id")
        if requested_event_id:
            candidates = [
                item for item in candidates
                if str(item.get("event_id", item.get("id", "")))
                == str(requested_event_id)
            ]
        preferred_run_id = route.get("run_id") or state.get("selected_run_id") or state.get("active_run_id")
        if preferred_run_id:
            candidates = [
                item for item in candidates
                if str(item.get("run_id", "")) == str(preferred_run_id)
            ]
        if "local area" in lowered or "local_area" in lowered:
            candidates = [item for item in candidates if str(item.get("event_scope", "")).lower() in {"local area", "local_area"}]
        elif "single customer" in lowered or "single_customer" in lowered:
            candidates = [item for item in candidates if str(item.get("event_scope", "")).lower() in {"single customer", "single_customer"}]
        for anomaly_type in ("spike", "drop", "flatline", "zero_block"):
            if anomaly_type.replace("_", " ") in lowered or anomaly_type in lowered:
                candidates = [
                    item for item in candidates
                    if anomaly_type in [
                        str(value).lower()
                        for value in (item.get("anomaly_types") or [item.get("dominant_anomaly_type", "")])
                    ]
                ]
                break
        selected = state.get("selected_event")
        if isinstance(selected, dict) and selected in candidates:
            candidates = [selected]
        if len(candidates) == 1:
            event = candidates[0]
            return {
                **route,
                "intent": intent,
                "event_id": str(event.get("event_id", event.get("id", ""))),
                "run_id": str(event.get("run_id") or state.get("selected_run_id") or "") or None,
            }
        if len(candidates) > 1:
            return {
                "intent": "event_selection",
                "requested_intent": intent,
                "candidates": candidates[:20],
            }
        return None

    if route["intent"] == "rectification_query":
        # An explicit event identifier must not be replaced by a previously
        # selected event. Resolve it inside the active run when no run was given.
        if route.get("event_id"):
            if not route.get("run_id"):
                all_matching_events = [
                    item for item in events
                    if str(item.get("event_id", item.get("id", "")))
                    == str(route["event_id"])
                ]
                preferred_run = state.get("selected_run_id") or state.get("active_run_id")
                active_matches = [
                    item for item in all_matching_events
                    if preferred_run and str(item.get("run_id", "")) == str(preferred_run)
                ]
                matching_events = active_matches or all_matching_events
                if len(matching_events) == 1 and matching_events[0].get("run_id"):
                    route["run_id"] = str(matching_events[0]["run_id"])
                elif len(matching_events) > 1:
                    return {
                        "intent": "event_selection",
                        "requested_intent": "rectification_query",
                        "candidates": matching_events[:20],
                    }
                elif preferred_run:
                    # Keep a missing event lookup scoped to the active run; never
                    # silently fall through to a model execution or another run.
                    route["run_id"] = str(preferred_run)
            return route
        contextual = contextual_event_route("rectification_query")
        return contextual or route

    detail_follow_up = any(
        phrase in lowered
        for phrase in (
            "in detail", "more detail", "more details", "tell me more",
            "more information", "tell me about it", "about that event",
            "details please", "explain those", "explain these", "which events",
            "event details", "breakdown of events", "their coordinates",
        )
    )
    selected_event = state.get("selected_event")
    if detail_follow_up and isinstance(selected_event, dict):
        return {
            "intent": "event_query",
            "event_id": str(selected_event.get("event_id", selected_event.get("id", ""))),
            "run_id": str(selected_event.get("run_id") or state.get("selected_run_id") or "") or None,
        }
    if not detail_follow_up:
        pass
    else:
        for message in reversed(history or []):
            if message.get("role") == "assistant" and message.get("start_date") and message.get("end_date"):
                return {
                    "intent": "event_detail_followup",
                    "start_date": str(message["start_date"]),
                    "end_date": str(message["end_date"]),
                }
            if message.get("role") != "user":
                continue
            previous = route_prompt(str(message.get("content", "")), today=today)
            if (
                previous.get("intent") == "historical_anomaly_query"
                and previous.get("start_date")
                and previous.get("end_date")
            ):
                return {
                    "intent": "event_detail_followup",
                    "start_date": previous["start_date"],
                    "end_date": previous["end_date"],
                }
    attribute_request = any(
        term in lowered
        for term in (
            "coordinate", "location", "latitude", "longitude", "severity",
            "scope", "type", "duration", "cluster", "customer", "affected",
            "score", "probable cause",
        )
    )
    if attribute_request and any(term in lowered for term in ("this", "that", "it", "same", "the event")):
        contextual = contextual_event_route("event_query")
        if contextual:
            return contextual
    if attribute_request and any(term in lowered for term in ("local area", "single customer", "first event", "last event")):
        contextual = contextual_event_route("event_query")
        if contextual:
            return contextual
    return route
