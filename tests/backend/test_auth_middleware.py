"""Tests for auth middleware."""
import pytest


def _create_and_login(client, username="admin", password="admin123"):
    """Create a user and login, return the client (cookies are set)."""
    client.post("/api/multi_users/", json={
        "username": username, "password": password, "role": "admin"
    })
    resp = client.post("/api/multi_users/login", json={
        "username": username, "password": password
    })
    assert resp.status_code == 200
    return client


def test_api_without_users_is_open(client):
    """When no users exist, API should be accessible without auth."""
    resp = client.get("/api/transactions/")
    assert resp.status_code == 200


def test_api_with_users_requires_auth(client):
    """After creating a user, API requires auth."""
    # Create a user (this makes the DB non-empty)
    client.post("/api/multi_users/", json={
        "username": "admin", "password": "pass123", "role": "admin"
    })
    # Now try to access without login
    resp = client.get("/api/transactions/")
    assert resp.status_code == 401


def test_api_with_session_works(client):
    """With valid session cookie, API is accessible."""
    _create_and_login(client)
    resp = client.get("/api/transactions/")
    assert resp.status_code == 200


def test_login_is_always_public(client):
    """Login endpoint is accessible even when auth is required."""
    client.post("/api/multi_users/", json={
        "username": "admin", "password": "pass123", "role": "admin"
    })
    # Login should work without existing session
    resp = client.post("/api/multi_users/login", json={
        "username": "admin", "password": "pass123"
    })
    assert resp.status_code == 200


def test_invalid_session_returns_401(client):
    """Invalid session cookie returns 401."""
    client.post("/api/multi_users/", json={
        "username": "admin", "password": "pass123", "role": "admin"
    })
    client.cookies.set("session_id", "fake-session-id")
    resp = client.get("/api/transactions/")
    assert resp.status_code == 401
