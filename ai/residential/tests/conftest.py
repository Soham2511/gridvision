"""Pytest fixtures for residential assistant and complaint tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from flask import Flask
from flask.testing import FlaskClient

BACKEND_PATH = Path(__file__).resolve().parents[3] / "backend"
if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app import create_app
from app.config import TestingConfig


@pytest.fixture
def app() -> Flask:
    """Create an application instance configured for testing."""
    return create_app(config_class=TestingConfig)


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    """Create a test client for the application."""
    return app.test_client()
