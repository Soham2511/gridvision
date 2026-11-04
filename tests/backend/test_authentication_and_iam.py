"""Comprehensive Verification Suite for Centralized Authentication and Persona-Based IAM."""

from __future__ import annotations

import json
import pytest
from flask.testing import FlaskClient

from app.config import BaseConfig
from app.infrastructure.database.connection import get_session
from app.infrastructure.database.models.user import Meter, User, UserSession


@pytest.fixture(autouse=True)
def clean_test_users():
    """Fixture ensuring temporary test users are cleaned up before and after tests."""
    test_usernames = ["testresident", "newcustomer", "alicesmith", "bruteforceuser", "anotheruser"]
    with get_session() as session:
        for u in test_usernames:
            user = session.query(User).filter(User.username.ilike(u)).first()
            if user:
                session.delete(user)
        session.commit()
    yield
    with get_session() as session:
        for u in test_usernames:
            user = session.query(User).filter(User.username.ilike(u)).first()
            if user:
                session.delete(user)
        session.commit()


def test_initial_residential_user_seeded(client: FlaskClient):
    """Verify that initial residential account is provisioned with OBJECTID 2254213."""
    res = client.post(
        "/api/v1/auth/login",
        json={"identifier": "resident", "password": "GridVision@2026"},
    )
    assert res.status_code == 200
    data = res.get_json()["data"]
    assert data["user"]["username"] == "resident"
    assert data["user"]["persona"] == "RESIDENTIAL"
    assert data["user"]["role"] == "RESIDENTIAL_USER"
    assert BaseConfig.INITIAL_RESIDENTIAL_OBJECTID in data["user"]["meters"]
    assert "access_token" in data
    assert len(data["access_token"]) > 20

    # Verify HttpOnly refresh cookie is set
    cookie_header = res.headers.get("Set-Cookie", "")
    assert BaseConfig.AUTH_COOKIE_NAME in cookie_header
    assert "HttpOnly" in cookie_header


def test_login_via_email(client: FlaskClient):
    """Verify login works interchangeably with email address."""
    res = client.post(
        "/api/v1/auth/login",
        json={"identifier": "resident@gridvision.local", "password": "GridVision@2026"},
    )
    assert res.status_code == 200
    assert res.get_json()["data"]["user"]["username"] == "resident"


def test_login_case_insensitivity(client: FlaskClient):
    """Verify login username and email matching is case-insensitive."""
    res = client.post(
        "/api/v1/auth/login",
        json={"identifier": "RESIDENT@GRIDVISION.LOCAL", "password": "GridVision@2026"},
    )
    assert res.status_code == 200
    assert res.get_json()["data"]["user"]["username"] == "resident"


def test_login_invalid_password(client: FlaskClient):
    """Verify login fails with bad credentials."""
    res = client.post(
        "/api/v1/auth/login",
        json={"identifier": "resident", "password": "WrongPassword123!"},
    )
    assert res.status_code == 401
    err = res.get_json()["error"]
    assert err["code"] == "AUTHENTICATION_FAILED"


def test_account_lockout_after_five_failed_attempts(client: FlaskClient):
    """Verify account lockout kicks in after 5 consecutive failed login attempts."""
    # Register temporary user
    reg = client.post(
        "/api/v1/auth/register",
        json={
            "username": "bruteforceuser",
            "email": "brute@example.com",
            "password": "Password123!",
            "confirm_password": "Password123!",
        },
    )
    assert reg.status_code == 201

    # 5 consecutive failed attempts
    for i in range(5):
        fail_res = client.post(
            "/api/v1/auth/login",
            json={"identifier": "bruteforceuser", "password": "wrong-password"},
        )
        assert fail_res.status_code == 401

    # 6th attempt should be blocked with lockout message
    locked_res = client.post(
        "/api/v1/auth/login",
        json={"identifier": "bruteforceuser", "password": "Password123!"},
    )
    assert locked_res.status_code == 401
    assert "temporarily locked" in locked_res.get_json()["error"]["message"]


def test_user_registration_validation(client: FlaskClient):
    """Verify strict validation rules during registration."""
    # Missing fields
    res = client.post("/api/v1/auth/register", json={})
    assert res.status_code == 400

    # Short password
    res = client.post(
        "/api/v1/auth/register",
        json={
            "username": "testresident",
            "email": "test@example.com",
            "password": "pass",
            "confirm_password": "pass",
        },
    )
    assert res.status_code == 400
    assert "at least 8 characters" in res.get_json()["error"]["message"]

    # Password mismatch
    res = client.post(
        "/api/v1/auth/register",
        json={
            "username": "testresident",
            "email": "test@example.com",
            "password": "Password123!",
            "confirm_password": "DifferentPassword123!",
        },
    )
    assert res.status_code == 400
    assert "do not match" in res.get_json()["error"]["message"]

    # Invalid email
    res = client.post(
        "/api/v1/auth/register",
        json={
            "username": "testresident",
            "email": "not-an-email",
            "password": "Password123!",
            "confirm_password": "Password123!",
        },
    )
    assert res.status_code == 400
    assert "valid email" in res.get_json()["error"]["message"]

    # Duplicate username (case-insensitive check against 'resident')
    res = client.post(
        "/api/v1/auth/register",
        json={
            "username": "Resident",
            "email": "newunique@example.com",
            "password": "Password123!",
            "confirm_password": "Password123!",
        },
    )
    assert res.status_code == 400
    assert "already registered" in res.get_json()["error"]["message"]


def test_successful_registration_and_isolation(client: FlaskClient):
    """Verify new user registration provisions residential account with authorized smart meter."""
    reg_res = client.post(
        "/api/v1/auth/register",
        json={
            "username": "newcustomer",
            "email": "newcustomer@example.com",
            "password": "SecurePassword999!",
            "confirm_password": "SecurePassword999!",
        },
    )
    assert reg_res.status_code == 201
    data = reg_res.get_json()["data"]
    assert data["user"]["username"] == "newcustomer"
    assert data["user"]["persona"] == "RESIDENTIAL"
    assert data["user"]["role"] == "RESIDENTIAL_USER"
    assert BaseConfig.INITIAL_RESIDENTIAL_OBJECTID in data["user"]["meters"]
    token = data["access_token"]

    # Check /me endpoint
    me_res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_res.status_code == 200
    assert me_res.get_json()["data"]["username"] == "newcustomer"
    assert BaseConfig.INITIAL_RESIDENTIAL_OBJECTID in me_res.get_json()["data"]["meters"]

    # New user accessing residential dashboard with provisioned meter
    dash_res = client.get("/api/v1/dashboard/household", headers={"Authorization": f"Bearer {token}"})
    assert dash_res.status_code == 200
    dash_data = dash_res.get_json()["data"]
    assert "consumptionCurve" in dash_data


def test_token_refresh_and_rotation(client: FlaskClient):
    """Verify session rotation via refresh token."""
    # Login to get initial session
    login_res = client.post(
        "/api/v1/auth/login",
        json={"identifier": "resident", "password": "GridVision@2026"},
    )
    raw_refresh = login_res.get_json()["data"]["refresh_token"]

    # First refresh: should rotate session and return new tokens
    ref_res = client.post("/api/v1/auth/refresh", json={"refresh_token": raw_refresh})
    assert ref_res.status_code == 200
    new_data = ref_res.get_json()["data"]
    new_access = new_data["access_token"]
    new_refresh = new_data["refresh_token"]
    assert new_refresh != raw_refresh

    # Test new access token against /me
    me_res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {new_access}"})
    assert me_res.status_code == 200
    assert me_res.get_json()["data"]["username"] == "resident"

    # Reuse of revoked old refresh token must be rejected (401)
    reuse_res = client.post("/api/v1/auth/refresh", json={"refresh_token": raw_refresh})
    assert reuse_res.status_code == 401


def test_logout_revocation(client: FlaskClient):
    """Verify logout revokes the refresh session and clears cookie."""
    login_res = client.post(
        "/api/v1/auth/login",
        json={"identifier": "resident", "password": "GridVision@2026"},
    )
    raw_refresh = login_res.get_json()["data"]["refresh_token"]

    logout_res = client.post("/api/v1/auth/logout", json={"refresh_token": raw_refresh})
    assert logout_res.status_code == 200

    # Refresh after logout must fail
    ref_res = client.post("/api/v1/auth/refresh", json={"refresh_token": raw_refresh})
    assert ref_res.status_code == 401


def test_invalid_bearer_token_rejection(client: FlaskClient):
    """Verify invalid or forged JWT tokens fail closed."""
    res = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer forged.invalid.token"})
    assert res.status_code == 401



def test_assistant_chat_for_unmetered_user(client: FlaskClient):
    """Verify assistant handles chat gracefully, and users without meters get guided response."""
    from app.services.assistant.auth import UserPrincipal
    from unittest.mock import patch

    # 1. Test user with authorized meter (normal registration scopes properly)
    reg = client.post(
        "/api/v1/auth/register",
        json={
            "username": "anotheruser",
            "email": "another@example.com",
            "password": "Password123!",
            "confirm_password": "Password123!",
        },
    )
    token = reg.get_json()["data"]["access_token"]

    res = client.post(
        "/api/v1/assistant/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"prompt": "hello", "persona": "household", "entity_id": "2235404", "history": []},
    )
    assert res.status_code == 200
    data = res.get_json()["data"]
    assert "answer" in data
    assert data["status"] in ("success", "not_found")

    # 2. Test user strictly without any provisioned meter
    unmetered_principal = UserPrincipal(
        user_id="999",
        role="RESIDENTIAL_USER",
        persona="RESIDENTIAL",
        authorized_meters=(),
    )
    from app.services.assistant.auth import HouseholdAuthService
    with patch.object(HouseholdAuthService, "resolve_principal", return_value=unmetered_principal):
        res2 = client.post(
            "/api/v1/assistant/chat",
            headers={"Authorization": f"Bearer {token}"},
            json={"prompt": "hello", "persona": "household", "entity_id": "2235404", "history": []},
        )
        assert res2.status_code == 200
        data2 = res2.get_json()["data"]
        assert "no smart meter provisioned" in data2["answer"].lower()
        assert data2["status"] == "success"
