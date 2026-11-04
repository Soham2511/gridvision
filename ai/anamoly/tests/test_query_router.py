from datetime import date

from ai.anamoly.agents import query_router
from ai.anamoly.agents.query_router import route_prompt


def test_technical_and_general_anomaly_questions_do_not_require_dates():
    prompts = (
        "What is a flatline anomaly?",
        "Explain FFT and Wavelet transformation",
        "What causes a zero-block anomaly?",
    )
    for prompt in prompts:
        assert route_prompt(prompt)["intent"] in {
            "technical_explanation",
            "general_knowledge",
        }


def test_router_recognizes_dd_mm_yyyy_and_iso_historical_ranges():
    dd_mm_route = route_prompt(
        "Show anomalies from 03/04/2019 to 09/04/2019"
    )
    assert dd_mm_route["intent"] == "historical_anomaly_query"
    assert dd_mm_route["start_date"] == "2019-04-03"
    assert dd_mm_route["end_date"] == "2019-04-09"

    iso_route = route_prompt(
        "Show anomaly events between 2019-04-03 and 2019-04-09"
    )
    assert iso_route["intent"] == "historical_anomaly_query"
    assert iso_route["start_date"] == "2019-04-03"
    assert iso_route["end_date"] == "2019-04-09"

    natural_prediction = route_prompt(
        "Tell me about anamoly prediction between 1-Jan-2019 to 4-Jan-2019"
    )
    assert natural_prediction["intent"] == "historical_anomaly_query"
    assert natural_prediction["start_date"] == "2019-01-01"
    assert natural_prediction["end_date"] == "2019-01-04"


def test_router_supports_named_and_relative_dates():
    named = route_prompt("Show anomalies on 15 April 2019")
    assert named["start_date"] == "2019-04-15"

    yesterday = route_prompt(
        "What happened yesterday?", today=date(2026, 11, 4)
    )
    assert yesterday["intent"] == "historical_anomaly_query"
    assert yesterday["start_date"] == "2026-11-03"

    explicit_model = route_prompt(
        "Run the trained anomaly model for 1-Jan-2019 to 4-Jan-2019"
    )
    assert explicit_model["intent"] == "analysis_execution"
    assert explicit_model["start_date"] == "2019-01-01"
    assert explicit_model["end_date"] == "2019-01-04"


def test_router_uses_configured_us_locale_for_ambiguous_dates(monkeypatch):
    monkeypatch.setattr(query_router, "DATE_LOCALE", "en-us")

    route = route_prompt("Show anomalies on 04/03/2019")

    assert route["start_date"] == "2019-04-03"


def test_router_asks_for_clarification_when_locale_is_unknown(monkeypatch):
    monkeypatch.setattr(query_router, "DATE_LOCALE", "fr-fr")

    route = route_prompt("Show anomalies on 04/03/2019")

    assert route["intent"] == "invalid_date"


def test_router_requires_dates_only_for_historical_and_explicit_analysis():
    assert route_prompt("Show anomalies")["intent"] == "historical_anomaly_query"
    analysis = route_prompt("Please analyze this")
    assert analysis["intent"] == "analysis_execution"
    assert "start_date" not in analysis

    execution = route_prompt("Run analysis for 2019-05-01")
    assert execution["intent"] == "analysis_execution"
    assert execution["start_date"] == execution["end_date"] == "2019-05-01"

    anomaly_execution = route_prompt("Run anomaly analysis for 2019-05-03")
    assert anomaly_execution["intent"] == "analysis_execution"
    assert anomaly_execution["start_date"] == anomaly_execution["end_date"] == "2019-05-03"


def test_router_classifies_customer_event_and_rectification_queries():
    assert route_prompt("Show customer impact")["intent"] == "customer_impact_query"
    assert route_prompt("Explain event_id:evt-123")["intent"] == "event_query"
    event = route_prompt("Why was event EVT_001 classified as MULTI_AREA?")
    assert event["intent"] == "event_query"
    assert event["event_id"] == "EVT_001"
    rectification = route_prompt(
        "What corrective measures apply to event EVT_001?"
    )
    assert rectification["intent"] == "rectification_query"
    assert rectification["event_id"] == "EVT_001"
    assert route_prompt("What is the likely cause and rectification?")["intent"] == "rectification_query"


def test_router_classifies_confirmation_responses():
    assert route_prompt("yes")["intent"] == "confirmation_response"
    assert route_prompt("no thanks")["intent"] == "confirmation_declined"


def test_router_reports_invalid_dates_for_historical_requests():
    route = route_prompt("Show anomalies on 31/02/2019")
    assert route["intent"] == "invalid_date"

    technical = route_prompt("What is a flatline anomaly? Date 31/02/2019")
    assert technical["intent"] == "technical_explanation"
