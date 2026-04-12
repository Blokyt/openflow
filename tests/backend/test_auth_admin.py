"""Tests for admin-only guards on user management."""
import pytest


def test_list_users_no_auth_when_no_users(client):
    """When no users exist, listing is open (bootstrap)."""
    resp = client.get("/api/multi_users/")
    assert resp.status_code == 200


def test_create_first_user_no_auth(client):
    """First user creation is open (bootstrap)."""
    resp = client.post("/api/multi_users/", json={
        "username": "admin", "password": "pass123", "role": "admin"
    })
    assert resp.status_code == 201


def test_list_users_requires_admin_after_first(client):
    """After first user exists, listing requires admin."""
    client.post("/api/multi_users/", json={
        "username": "admin", "password": "pass123", "role": "admin"
    })
    # Not logged in — should be rejected
    resp = client.get("/api/multi_users/")
    assert resp.status_code in (401, 403)


def test_admin_can_list_users(authed_client):
    """Logged-in admin can list users."""
    resp = authed_client.get("/api/multi_users/")
    assert resp.status_code == 200


def test_admin_can_create_user(authed_client):
    """Admin can create additional users."""
    resp = authed_client.post("/api/multi_users/", json={
        "username": "newuser", "password": "pass123", "role": "reader"
    })
    assert resp.status_code == 201


def test_admin_can_delete_user(authed_client):
    """Admin can delete a user."""
    user = authed_client.post("/api/multi_users/", json={
        "username": "todelete", "password": "pass123"
    }).json()
    resp = authed_client.delete(f"/api/multi_users/{user['id']}")
    assert resp.status_code == 200


def test_cleanup_sessions(authed_client):
    """Admin can clean up sessions."""
    resp = authed_client.post("/api/multi_users/cleanup-sessions")
    assert resp.status_code == 200
    assert "remaining_sessions" in resp.json()
