"""Tests for the multi_users module API."""
import hashlib
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app


@pytest.fixture
def client():
    app = create_app(config_path="config.yaml", db_path="data/openflow.db")
    return TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_user(client, **kwargs):
    payload = {
        "username": f"testuser_{id(kwargs)}",
        "password": "securepassword",
        "role": "reader",
        "display_name": "Test User",
    }
    payload.update(kwargs)
    resp = client.post("/api/multi_users/", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# POST /api/multi_users/ — create
# ---------------------------------------------------------------------------

def test_create_user_returns_201(client):
    resp = client.post("/api/multi_users/", json={
        "username": "newuser_create_201",
        "password": "pass123",
    })
    assert resp.status_code == 201


def test_create_user_response_has_expected_fields(client):
    user = make_user(client, username="fields_check_user")
    assert "id" in user
    assert "username" in user
    assert "role" in user
    assert "display_name" in user
    assert "created_at" in user
    assert "active" in user


def test_create_user_password_not_in_response(client):
    user = make_user(client, username="no_pwd_user")
    assert "password" not in user
    assert "password_hash" not in user


def test_create_user_default_role_is_reader(client):
    user = make_user(client, username="default_role_user")
    assert user["role"] == "reader"


def test_create_user_custom_role(client):
    user = make_user(client, username="admin_user_test", role="admin")
    assert user["role"] == "admin"


def test_create_user_invalid_role_returns_400(client):
    resp = client.post("/api/multi_users/", json={
        "username": "bad_role_user",
        "password": "pass",
        "role": "superuser",
    })
    assert resp.status_code == 400


def test_create_user_duplicate_username_returns_400(client):
    make_user(client, username="duplicate_user_x")
    resp = client.post("/api/multi_users/", json={
        "username": "duplicate_user_x",
        "password": "anotherpass",
    })
    assert resp.status_code == 400


def test_password_is_hashed_in_database(client):
    """Verify that SHA-256 hash of the password is stored, not plaintext."""
    import sqlite3
    from pathlib import Path
    project_root = Path(__file__).parent.parent.parent
    db_path = project_root / "data" / "openflow.db"

    password = "mysecretpassword"
    expected_hash = hashlib.sha256(password.encode()).hexdigest()

    user = make_user(client, username="hash_check_user", password=password)

    conn = sqlite3.connect(str(db_path))
    row = conn.execute("SELECT password_hash FROM users WHERE id = ?", (user["id"],)).fetchone()
    conn.close()

    assert row is not None
    assert row[0] == expected_hash


# ---------------------------------------------------------------------------
# GET /api/multi_users/ — list
# ---------------------------------------------------------------------------

def test_list_users_returns_200(client):
    resp = client.get("/api/multi_users/")
    assert resp.status_code == 200


def test_list_users_returns_list(client):
    resp = client.get("/api/multi_users/")
    assert isinstance(resp.json(), list)


def test_list_users_no_password_hash(client):
    make_user(client, username="list_test_user")
    resp = client.get("/api/multi_users/")
    for user in resp.json():
        assert "password_hash" not in user
        assert "password" not in user


def test_list_users_contains_created_user(client):
    user = make_user(client, username="listed_user")
    resp = client.get("/api/multi_users/")
    ids = [u["id"] for u in resp.json()]
    assert user["id"] in ids


# ---------------------------------------------------------------------------
# GET /api/multi_users/{id} — get single
# ---------------------------------------------------------------------------

def test_get_user_returns_200(client):
    user = make_user(client, username="get_single_user")
    resp = client.get(f"/api/multi_users/{user['id']}")
    assert resp.status_code == 200


def test_get_user_returns_correct_data(client):
    user = make_user(client, username="get_data_user", display_name="Display Name")
    resp = client.get(f"/api/multi_users/{user['id']}")
    data = resp.json()
    assert data["username"] == "get_data_user"
    assert data["display_name"] == "Display Name"


def test_get_user_not_found_returns_404(client):
    resp = client.get("/api/multi_users/999999")
    assert resp.status_code == 404


def test_get_user_no_password_hash(client):
    user = make_user(client, username="get_no_pwd_user")
    resp = client.get(f"/api/multi_users/{user['id']}")
    data = resp.json()
    assert "password_hash" not in data
    assert "password" not in data


# ---------------------------------------------------------------------------
# PUT /api/multi_users/{id} — update
# ---------------------------------------------------------------------------

def test_update_user_display_name(client):
    user = make_user(client, username="update_display_user")
    resp = client.put(f"/api/multi_users/{user['id']}", json={"display_name": "Updated Name"})
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "Updated Name"


def test_update_user_role(client):
    user = make_user(client, username="update_role_user", role="reader")
    resp = client.put(f"/api/multi_users/{user['id']}", json={"role": "treasurer"})
    assert resp.status_code == 200
    assert resp.json()["role"] == "treasurer"


def test_update_user_password_not_returned(client):
    user = make_user(client, username="update_pwd_user")
    resp = client.put(f"/api/multi_users/{user['id']}", json={"password": "newpassword"})
    assert resp.status_code == 200
    data = resp.json()
    assert "password_hash" not in data
    assert "password" not in data


def test_update_user_password_rehashed(client):
    """After updating password, new hash should be stored."""
    import sqlite3
    from pathlib import Path
    project_root = Path(__file__).parent.parent.parent
    db_path = project_root / "data" / "openflow.db"

    user = make_user(client, username="rehash_user", password="oldpass")
    new_password = "newpass"
    expected_hash = hashlib.sha256(new_password.encode()).hexdigest()

    client.put(f"/api/multi_users/{user['id']}", json={"password": new_password})

    conn = sqlite3.connect(str(db_path))
    row = conn.execute("SELECT password_hash FROM users WHERE id = ?", (user["id"],)).fetchone()
    conn.close()

    assert row[0] == expected_hash


def test_update_user_not_found_returns_404(client):
    resp = client.put("/api/multi_users/999999", json={"display_name": "Ghost"})
    assert resp.status_code == 404


def test_update_user_invalid_role_returns_400(client):
    user = make_user(client, username="invalid_role_update_user")
    resp = client.put(f"/api/multi_users/{user['id']}", json={"role": "god"})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# DELETE /api/multi_users/{id} — delete
# ---------------------------------------------------------------------------

def test_delete_user_returns_200(client):
    user = make_user(client, username="delete_me_user")
    resp = client.delete(f"/api/multi_users/{user['id']}")
    assert resp.status_code == 200


def test_delete_user_response_has_deleted_id(client):
    user = make_user(client, username="delete_id_check_user")
    resp = client.delete(f"/api/multi_users/{user['id']}")
    assert resp.json()["deleted"] == user["id"]


def test_delete_user_no_longer_retrievable(client):
    user = make_user(client, username="delete_gone_user")
    client.delete(f"/api/multi_users/{user['id']}")
    resp = client.get(f"/api/multi_users/{user['id']}")
    assert resp.status_code == 404


def test_delete_user_not_found_returns_404(client):
    resp = client.delete("/api/multi_users/999999")
    assert resp.status_code == 404
