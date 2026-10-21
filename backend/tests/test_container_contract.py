"""Test WSGI Application Factory and Container Contracts."""

import pytest
from app import create_app
from app.config import ProductionConfig


def test_wsgi_app_factory():
    """Ensure WSGI server can instantiate application cleanly via app:create_app()."""
    app = create_app()
    assert app is not None
    client = app.test_client()
    resp = client.get("/")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["service"] == "GridVision REST API"


def test_production_config_with_secret(monkeypatch):
    """Ensure ProductionConfig instantiates when SECRET_KEY is provided."""
    monkeypatch.setattr(ProductionConfig, "SECRET_KEY", "prod-test-key-12345")
    cfg = ProductionConfig()
    assert cfg.DEBUG is False
    assert cfg.SECRET_KEY == "prod-test-key-12345"


def test_reverse_proxy_headers_and_prefix():
    """Verify API prefix matches routing configuration."""
    app = create_app()
    client = app.test_client()
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.get_json()["data"]["status"] == "alive"
