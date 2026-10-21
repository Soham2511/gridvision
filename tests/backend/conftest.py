"""Pytest fixtures and configuration."""

from __future__ import annotations

import pytest
from flask import Flask
from flask.testing import FlaskClient

from app import create_app
from app.config import TestingConfig


@pytest.fixture
def app() -> Flask:
    """Create an application instance configured for testing."""
    app = create_app(config_class=TestingConfig)
    return app


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    """Flask test client fixture."""
    return app.test_client()
