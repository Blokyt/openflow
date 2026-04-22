"""Tests for the multi_users module API."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_user(client, **kwargs):
    payload = {
        "username": f"testuser_{id(kwargs)}",
        "password": "securepassword",
        "role": "lecteur",
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


def test_create_user_default_role_is_lecteur(client):
    user = make_user(client, username="default_role_user")
    assert user["role"] == "lecteur"


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


def test_create_user_duplicate_username_returns_400(authed_client):
    make_user(authed_client, username="duplicate_user_x")
    resp = authed_client.post("/api/multi_users/", json={
        "username": "duplicate_user_x",
        "password": "anotherpass",
    })
    assert resp.status_code == 400


def test_password_is_hashed_in_database(client_and_db):
    """Verify that bcrypt hash of the password is stored, not plaintext."""
    import sqlite3
    client, db_file = client_and_db

    password = "mysecretpassword"

    user = make_user(client, username="hash_check_user", password=password)

    conn = sqlite3.connect(str(db_file))
    row = conn.execute("SELECT password_hash FROM users WHERE id = ?", (user["id"],)).fetchone()
    conn.close()

    assert row is not None
    # bcrypt hashes start with $2b$
    assert row[0].startswith("$2b$")


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


def test_list_users_contains_created_user(authed_client):
    user = make_user(authed_client, username="listed_user")
    resp = authed_client.get("/api/multi_users/")
    ids = [u["id"] for u in resp.json()]
    assert user["id"] in ids


# ---------------------------------------------------------------------------
# GET /api/multi_users/{id} — get single
# ---------------------------------------------------------------------------

def test_get_user_returns_200(authed_client):
    user = make_user(authed_client, username="get_single_user")
    resp = authed_client.get(f"/api/multi_users/{user['id']}")
    assert resp.status_code == 200


def test_get_user_returns_correct_data(authed_client):
    user = make_user(authed_client, username="get_data_user", display_name="Display Name")
    resp = authed_client.get(f"/api/multi_users/{user['id']}")
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

def test_update_user_display_name(authed_client):
    user = make_user(authed_client, username="update_display_user")
    resp = authed_client.put(f"/api/multi_users/{user['id']}", json={"display_name": "Updated Name"})
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "Updated Name"


def test_update_user_role(authed_client):
    user = make_user(authed_client, username="update_role_user", role="lecteur")
    resp = authed_client.put(f"/api/multi_users/{user['id']}", json={"role": "tresorier"})
    assert resp.status_code == 200
    assert resp.json()["role"] == "tresorier"


def test_update_user_password_not_returned(authed_client):
    user = make_user(authed_client, username="update_pwd_user")
    resp = authed_client.put(f"/api/multi_users/{user['id']}", json={"password": "newpassword"})
    assert resp.status_code == 200
    data = resp.json()
    assert "password_hash" not in data
    assert "password" not in data


def test_update_user_password_rehashed(client_and_db):
    """After updating password, new bcrypt hash should be stored."""
    import sqlite3
    client, db_file = client_and_db

    user = make_user(client, username="rehash_user", password="oldpass")
    new_password = "newpass"

    client.put(f"/api/multi_users/{user['id']}", json={"password": new_password})

    conn = sqlite3.connect(str(db_file))
    row = conn.execute("SELECT password_hash FROM users WHERE id = ?", (user["id"],)).fetchone()
    conn.close()

    # bcrypt hashes start with $2b$
    assert row[0].startswith("$2b$")


def test_update_user_not_found_returns_404(client):
    resp = client.put("/api/multi_users/999999", json={"display_name": "Ghost"})
    assert resp.status_code == 404


def test_update_user_invalid_role_returns_400(authed_client):
    user = make_user(authed_client, username="invalid_role_update_user")
    resp = authed_client.put(f"/api/multi_users/{user['id']}", json={"role": "god"})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# DELETE /api/multi_users/{id} — delete
# ---------------------------------------------------------------------------

def test_delete_user_returns_200(authed_client):
    user = make_user(authed_client, username="delete_me_user")
    resp = authed_client.delete(f"/api/multi_users/{user['id']}")
    assert resp.status_code == 200


def test_delete_user_response_has_deleted_id(authed_client):
    user = make_user(authed_client, username="delete_id_check_user")
    resp = authed_client.delete(f"/api/multi_users/{user['id']}")
    assert resp.json()["deleted"] == user["id"]


def test_delete_user_no_longer_retrievable(authed_client):
    user = make_user(authed_client, username="delete_gone_user")
    authed_client.delete(f"/api/multi_users/{user['id']}")
    resp = authed_client.get(f"/api/multi_users/{user['id']}")
    assert resp.status_code == 404


def test_delete_user_not_found_returns_404(client):
    resp = client.delete("/api/multi_users/999999")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/multi_users/login — session purge on login
# ---------------------------------------------------------------------------

def test_login_purges_stale_sessions(client_and_db):
    """Login must delete sessions older than 24h and keep the new one."""
    import sqlite3
    from datetime import datetime, timezone, timedelta

    client, db_file = client_and_db

    # Create a user to log in with
    user = make_user(client, username="login_purge_user", password="pass1234")

    # Seed 3 old sessions directly in the DB (older than 24h)
    conn = sqlite3.connect(str(db_file))
    old_ts = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    try:
        for i in range(3):
            conn.execute(
                "INSERT INTO sessions (id, user_id, created_at) VALUES (?, ?, ?)",
                (f"stale-session-{i:04d}-0000-0000-0000-000000000000", user["id"], old_ts),
            )
        conn.commit()

        # Verify 3 stale sessions exist before login
        count_before = conn.execute(
            "SELECT COUNT(*) FROM sessions WHERE user_id = ?", (user["id"],)
        ).fetchone()[0]
        assert count_before == 3
    finally:
        conn.close()

    # Perform login
    resp = client.post("/api/multi_users/login", json={
        "username": "login_purge_user",
        "password": "pass1234",
    })
    assert resp.status_code == 200

    # After login: only the new session should remain (stale ones purged)
    conn = sqlite3.connect(str(db_file))
    try:
        sessions = conn.execute(
            "SELECT id, created_at FROM sessions WHERE user_id = ?", (user["id"],)
        ).fetchall()
    finally:
        conn.close()

    # Only 1 session (the new one) should remain
    assert len(sessions) == 1, (
        f"Expected 1 session after login, got {len(sessions)}: {sessions}"
    )
    # The surviving session must NOT be one of the stale seeds
    assert not sessions[0][0].startswith("stale-session-"), (
        "The surviving session should be the newly created one"
    )


def test_login_keeps_recent_sessions_of_other_users(client_and_db):
    """Login purge must not delete recent sessions belonging to other users."""
    import sqlite3
    import bcrypt
    from datetime import datetime, timezone, timedelta
    import uuid

    client, db_file = client_and_db

    # Create user_a via API (no users yet, so first creation is public)
    user_a = make_user(client, username="login_purge_user_a2", password="passA1234")

    # Create user_b directly in the DB (avoid auth requirement after first user exists)
    conn = sqlite3.connect(str(db_file))
    recent_ts = datetime.now(timezone.utc).isoformat()
    fresh_session_id = str(uuid.uuid4())
    try:
        hashed = bcrypt.hashpw(b"passB1234", bcrypt.gensalt()).decode()
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, role, display_name, created_at, active) "
            "VALUES (?, ?, 'lecteur', '', ?, 1)",
            ("login_purge_user_b2", hashed, recent_ts),
        )
        user_b_id = cur.lastrowid
        # Seed a RECENT session for user_b
        conn.execute(
            "INSERT INTO sessions (id, user_id, created_at) VALUES (?, ?, ?)",
            (fresh_session_id, user_b_id, recent_ts),
        )
        conn.commit()
    finally:
        conn.close()

    # user_a logs in — should NOT affect user_b's recent session
    resp = client.post("/api/multi_users/login", json={
        "username": "login_purge_user_a2",
        "password": "passA1234",
    })
    assert resp.status_code == 200

    conn = sqlite3.connect(str(db_file))
    try:
        surviving = conn.execute(
            "SELECT id FROM sessions WHERE id = ?", (fresh_session_id,)
        ).fetchone()
    finally:
        conn.close()

    assert surviving is not None, "Recent session for another user must NOT be deleted"
