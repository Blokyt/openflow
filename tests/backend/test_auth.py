"""Tests for auth endpoints: login, logout, me, password change, entity access."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_user(client, username="authuser", password="TestPass123!xx", role="lecteur"):
    resp = client.post("/api/multi_users/", json={
        "username": username,
        "password": password,
        "role": role,
        "display_name": "Auth Test User",
    })
    assert resp.status_code == 201, resp.text
    return resp.json()


def make_entity(client, name="TestEntity"):
    resp = client.post("/api/entities/", json={"name": name, "type": "internal"})
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# POST /api/multi_users/login
# ---------------------------------------------------------------------------

def test_login_success(client):
    make_user(client, username="login_ok_user", password="CorrectPass1!xx")
    resp = client.post("/api/multi_users/login", json={
        "username": "login_ok_user",
        "password": "CorrectPass1!xx",
    })
    assert resp.status_code == 200
    # Cookie should be set
    assert "session_id" in resp.cookies


def test_login_wrong_password(client):
    make_user(client, username="login_wrong_pwd_user", password="RightPass1!xxx")
    resp = client.post("/api/multi_users/login", json={
        "username": "login_wrong_pwd_user",
        "password": "wrongpass",
    })
    assert resp.status_code == 401


def test_login_nonexistent_user(client):
    resp = client.post("/api/multi_users/login", json={
        "username": "ghost_user_xyz",
        "password": "whatever",
    })
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/multi_users/logout
# ---------------------------------------------------------------------------

def test_logout(client):
    make_user(client, username="logout_test_user", password="LogoutPass1!xx")
    # Login
    login_resp = client.post("/api/multi_users/login", json={
        "username": "logout_test_user",
        "password": "LogoutPass1!xx",
    })
    assert login_resp.status_code == 200
    assert "session_id" in client.cookies

    # Logout
    logout_resp = client.post("/api/multi_users/logout")
    assert logout_resp.status_code == 200

    # Cookie should be cleared — /me should now return 401
    # We need to clear the client cookies to simulate cleared cookie
    client.cookies.clear()
    me_resp = client.get("/api/multi_users/me")
    assert me_resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/multi_users/me
# ---------------------------------------------------------------------------

def test_me_with_session(client):
    make_user(client, username="me_session_user", password="MePass1!secureX")
    client.post("/api/multi_users/login", json={
        "username": "me_session_user",
        "password": "MePass1!secureX",
    })
    resp = client.get("/api/multi_users/me")
    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == "me_session_user"
    assert "id" in data
    assert "display_name" in data
    assert "entities" in data


def test_me_without_session(client):
    resp = client.get("/api/multi_users/me")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PUT /api/multi_users/me/password
# ---------------------------------------------------------------------------

def test_change_password(client):
    make_user(client, username="change_pwd_user", password="OldPassword1!xx")
    client.post("/api/multi_users/login", json={
        "username": "change_pwd_user",
        "password": "OldPassword1!xx",
    })

    # Change password
    resp = client.put("/api/multi_users/me/password", json={
        "old_password": "OldPassword1!xx",
        "new_password": "NewPassword123!",
    })
    assert resp.status_code == 200

    # Login with new password
    client.cookies.clear()
    login_resp = client.post("/api/multi_users/login", json={
        "username": "change_pwd_user",
        "password": "NewPassword123!",
    })
    assert login_resp.status_code == 200


def test_change_password_wrong_old(client):
    make_user(client, username="wrong_old_pwd_user", password="CorrectOld1!xxx")
    client.post("/api/multi_users/login", json={
        "username": "wrong_old_pwd_user",
        "password": "CorrectOld1!xxx",
    })

    resp = client.put("/api/multi_users/me/password", json={
        "old_password": "wrongold",
        "new_password": "DoesntMatter1!x",
    })
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Entity access endpoints
# ---------------------------------------------------------------------------

def test_assign_entity_access(authed_client):
    user = make_user(authed_client, username="assign_entity_user")
    entity = make_entity(authed_client, name="AssignEntity")

    resp = authed_client.post(f"/api/multi_users/{user['id']}/entities", json={
        "entity_id": entity["id"],
        "role": "lecteur",
    })
    assert resp.status_code == 201

    list_resp = authed_client.get(f"/api/multi_users/{user['id']}/entities")
    assert list_resp.status_code == 200
    entities = list_resp.json()
    entity_ids = [e["entity_id"] for e in entities]
    assert entity["id"] in entity_ids


def test_remove_entity_access(authed_client):
    user = make_user(authed_client, username="remove_entity_user")
    entity = make_entity(authed_client, name="RemoveEntity")

    # Assign
    authed_client.post(f"/api/multi_users/{user['id']}/entities", json={
        "entity_id": entity["id"],
        "role": "lecteur",
    })

    # Remove
    del_resp = authed_client.delete(f"/api/multi_users/{user['id']}/entities/{entity['id']}")
    assert del_resp.status_code == 200

    # List should be empty
    list_resp = authed_client.get(f"/api/multi_users/{user['id']}/entities")
    assert list_resp.json() == []


def test_assign_duplicate_entity_returns_400(authed_client):
    user = make_user(authed_client, username="dup_entity_user")
    entity = make_entity(authed_client, name="DupEntity")

    authed_client.post(f"/api/multi_users/{user['id']}/entities", json={
        "entity_id": entity["id"],
        "role": "lecteur",
    })
    resp = authed_client.post(f"/api/multi_users/{user['id']}/entities", json={
        "entity_id": entity["id"],
        "role": "tresorier",
    })
    assert resp.status_code == 400


def test_assign_invalid_entity_role_returns_400(authed_client):
    user = make_user(authed_client, username="invalid_role_entity_user")
    entity = make_entity(authed_client, name="InvalidRoleEntity")

    resp = authed_client.post(f"/api/multi_users/{user['id']}/entities", json={
        "entity_id": entity["id"],
        "role": "admin",
    })
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# GET /api/multi_users/me — includes entities
# ---------------------------------------------------------------------------

def test_me_includes_entities(authed_client):
    user = make_user(authed_client, username="me_entities_user", password="MeEntPass1!xxx")
    entity = make_entity(authed_client, name="MeIncludeEntity")

    # Assign entity
    authed_client.post(f"/api/multi_users/{user['id']}/entities", json={
        "entity_id": entity["id"],
        "role": "tresorier",
    })

    # Login as the new user (replacing the admin session)
    authed_client.post("/api/multi_users/login", json={
        "username": "me_entities_user",
        "password": "MeEntPass1!xxx",
    })

    # /me should include entities
    resp = authed_client.get("/api/multi_users/me")
    assert resp.status_code == 200
    data = resp.json()
    assert "entities" in data
    assert len(data["entities"]) >= 1
    entity_ids = [e["entity_id"] for e in data["entities"]]
    assert entity["id"] in entity_ids
