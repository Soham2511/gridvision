"""Unit tests for deterministic alerts engine."""

from __future__ import annotations

from dashboard.components.alerts_panel import compute_system_alerts


def test_alerts_unready_api() -> None:
    """Unready API generates critical alert."""
    alerts = compute_system_alerts(api_readiness={"status": "not_ready", "models_loaded": []})
    assert any(a.severity == "critical" and "API Artifact Readiness" in a.title for a in alerts)


def test_alerts_negative_energy_flag() -> None:
    """Negative energy prediction generates critical alert."""
    pred_res = {
        "prediction_status": "invalid_negative_energy",
        "prediction": -12.5,
        "entity_id": "MT_001",
        "forecast_timestamp": "2014-12-30T00:00:00",
    }
    alerts = compute_system_alerts(recent_prediction_result=pred_res)
    assert any(a.severity == "critical" and "Negative Energy" in a.title for a in alerts)


def test_alerts_low_coverage() -> None:
    """Daily coverage below 0.9 generates warning alert."""
    alerts = compute_system_alerts(coverage_ratio=0.75)
    assert any(a.severity == "warning" and "Low Daily Interval Coverage" in a.title for a in alerts)


def test_alerts_clean_state() -> None:
    """Healthy system with valid outputs produces zero alerts."""
    pred_res = {
        "prediction_status": "valid",
        "prediction": 45.2,
        "entity_id": "MT_001",
    }
    alerts = compute_system_alerts(
        api_readiness={"status": "ready", "models_loaded": ["commercial", "government", "residential"], "models_expected": ["commercial", "government", "residential"]},
        recent_prediction_result=pred_res,
        coverage_ratio=0.98,
        forecast_error_abs=10.0,
    )
    assert len(alerts) == 0
