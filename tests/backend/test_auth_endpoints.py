"""Tests des endpoints d'authentification du module users."""
import sqlite3
from datetime import datetime, timezone

from backend.core.auth import SESSION_COOKIE, hash_password

NOW = datetime.now(timezone.utc).isoformat()


def _seed_user(db_path, email="tresorier@club.fr", password="mot-de-passe-solide",
               is_admin=0, is_active=1):
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute(
            "INSERT INTO users (email, display_name, password_hash, is_admin, is_active, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (email, "Trésorier Test", hash_password(password), is_admin, is_active, NOW),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def test_login_success_sets_cookie(client_and_db):
    client, db_path = client_and_db
    _seed_user(db_path)
    r = client.post("/api/users/login",
                    json={"email": "tresorier@club.fr", "password": "mot-de-passe-solide"})
    assert r.status_code == 200
    assert r.json()["email"] == "tresorier@club.fr"
    assert "password_hash" not in r.json()
    assert SESSION_COOKIE in r.cookies


def test_login_wrong_password(client_and_db):
    client, db_path = client_and_db
    _seed_user(db_path)
    r = client.post("/api/users/login",
                    json={"email": "tresorier@club.fr", "password": "mauvais-mot-de-passe"})
    assert r.status_code == 401


def test_login_unknown_email(client_and_db):
    client, _ = client_and_db
    r = client.post("/api/users/login",
                    json={"email": "inconnu@club.fr", "password": "peu-importe-longueur"})
    assert r.status_code == 401


def test_login_inactive_user(client_and_db):
    client, db_path = client_and_db
    _seed_user(db_path, is_active=0)
    r = client.post("/api/users/login",
                    json={"email": "tresorier@club.fr", "password": "mot-de-passe-solide"})
    assert r.status_code == 401


def test_login_invalid_payload(client_and_db):
    client, _ = client_and_db
    r = client.post("/api/users/login", json={"email": "seul"})
    assert r.status_code == 422


def test_me_roundtrip_and_logout(client_and_db):
    client, db_path = client_and_db
    _seed_user(db_path)
    client.post("/api/users/login",
                json={"email": "tresorier@club.fr", "password": "mot-de-passe-solide"})
    r = client.get("/api/users/me")
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "tresorier@club.fr"
    assert body["is_admin"] == 0
    assert body["roles"] == []
    assert body["allowed_entity_ids"] == []
    r = client.post("/api/users/logout")
    assert r.status_code == 200
    assert client.get("/api/users/me").status_code == 401


def test_me_without_session(client):
    assert client.get("/api/users/me").status_code == 401


def test_login_rate_limited(client_and_db):
    client, db_path = client_and_db
    _seed_user(db_path)
    for _ in range(5):
        client.post("/api/users/login",
                    json={"email": "tresorier@club.fr", "password": "mauvais-mot-de-passe"})
    r = client.post("/api/users/login",
                    json={"email": "tresorier@club.fr", "password": "mauvais-mot-de-passe"})
    assert r.status_code == 429
