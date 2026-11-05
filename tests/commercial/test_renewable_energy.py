"""Tests for Tavily-backed solar estimates and assistant integration."""

from __future__ import annotations

import json

from ai.commercial.tools.renewable_energy import RenewableEnergyTools


class _Response:
    status = 200

    def __init__(self, payload: dict) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *args: object) -> None:
        del args

    def read(self, size: int) -> bytes:
        return self._body[:size]


class _Opener:
    def __init__(self, response: _Response) -> None:
        self.response = response
        self.request_body = b""

    def open(self, request, timeout: float) -> _Response:
        assert timeout == 12.0
        self.request_body = request.data
        return self.response


def test_solar_estimate_uses_inputs_and_tavily_sources(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    key_file = tmp_path / "api.key"
    key_file.write_text("test-key", encoding="utf-8")
    tool = RenewableEnergyTools(key_file)
    opener = _Opener(
        _Response(
            {
                "results": [
                    {
                        "url": "https://example.com/solar",
                        "title": "Solar reference",
                        "content": "Local rooftop solar information.",
                    }
                ]
            }
        )
    )
    tool._opener = opener

    result = tool.get_renewable_scenarios(
        None,
        "Estimate a 5 kW rooftop system in Bengaluru, monthly usage "
        "600 kWh, tariff ₹8 per kWh",
    )

    estimate = result.data["estimate"]
    assert result.status == "available"
    assert estimate["capacity_kw"] == 5
    assert estimate["annual_generation_kwh"] == 6570
    assert estimate["estimated_install_cost_inr"] == 275000
    assert estimate["estimated_annual_savings_inr"] == 52560
    assert estimate["simple_payback_years"] == 5.2
    assert result.evidence_refs[0].locator == "https://example.com/solar"
    assert any("Local rooftop solar information" in item for item in result.findings)
    assert json.loads(opener.request_body)["api_key"] == "test-key"
    assert json.loads(opener.request_body)["include_answer"] is False


def test_explicit_web_search_returns_tavily_answer_and_citations(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    key_file = tmp_path / "api.key"
    key_file.write_text("test-key", encoding="utf-8")
    tool = RenewableEnergyTools(key_file)
    opener = _Opener(
        _Response(
            {
                "answer": "A concise answer from web sources.",
                "results": [
                    {
                        "url": "https://example.com/guide",
                        "title": "Energy guide",
                        "content": "Supporting source excerpt.",
                    }
                ],
            }
        )
    )
    tool._opener = opener

    observation = tool.search_web("How can industrial motors save energy?")

    assert observation.status == "available"
    assert observation.findings == ("A concise answer from web sources.",)
    assert observation.evidence_refs[0].locator == "https://example.com/guide"
    assert observation.data["results"][0]["title"] == "Energy guide"
    assert json.loads(opener.request_body)["include_answer"] is True


def test_solar_request_without_site_inputs_does_not_invent_a_system_size(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    tool = RenewableEnergyTools(tmp_path / "missing.key")

    result = tool.get_renewable_scenarios(None, "Estimate rooftop solar")

    assert result.status == "unavailable"
    assert result.error is not None
    assert result.error.code == "SOLAR_INPUT_REQUIRED"


def test_solar_estimate_sizes_from_roof_area_and_annual_usage() -> None:
    estimate = RenewableEnergyTools._estimate(
        "Estimate a system for 120 sqm roof, annual usage 12,000 kWh"
    )

    assert estimate["capacity_kw"] == 24
    assert estimate["annual_consumption_kwh"] == 12000
    assert estimate["estimated_annual_savings_inr"] is None
    assert estimate["tariff_inr_per_kwh"] is None


def test_wind_estimate_requires_user_supplied_capacity_and_capacity_factor(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    tool = RenewableEnergyTools(tmp_path / "missing.key")

    result = tool.get_renewable_scenarios(
        None,
        "Estimate a 100 kW wind turbine at 30% capacity factor, "
        "annual usage 300,000 kWh, tariff ₹8/kWh, project cost ₹10,000,000",
    )

    assert result.status == "available"
    estimate = result.data["estimate"]
    assert estimate["technology"] == "wind"
    assert estimate["annual_generation_kwh"] == 262800
    assert estimate["estimated_annual_savings_inr"] == 2102400
    assert estimate["simple_payback_years"] == 4.8
    assert result.error is not None
    assert result.error.code == "TAVILY_API_KEY_MISSING"


def test_battery_estimate_uses_explicit_efficiency_and_tariff_spread(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    tool = RenewableEnergyTools(tmp_path / "missing.key")

    result = tool.get_renewable_scenarios(
        None,
        "Battery capacity 100 kWh, battery power 50 kW, round-trip efficiency "
        "90%, 1 cycle/day, peak tariff ₹15/kWh, off-peak tariff ₹8/kWh, "
        "project cost ₹1,000,000",
    )

    assert result.status == "available"
    estimate = result.data["estimate"]
    assert estimate["technology"] == "battery"
    assert estimate["estimated_annual_arbitrage_savings_inr"] == 111528
    assert estimate["simple_payback_years"] == 9.0
    assert any("one hour" in assumption for assumption in result.assumptions)
