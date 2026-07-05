"""Verrouillage progressif du login + journal des connexions."""
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from tests.backend.conftest import ADMIN_EMAIL


def _seed_events(db_path, email, *, failures, ip="testclient", age_seconds=0, then_success=False):
    """Insère des événements de connexion directement en base.

    then_success=True ajoute un succès APRÈS les échecs (remise à zéro du compteur).
    """
    conn = sqlite3.connect(str(db_path))
    try:
        when = (datetime.now(timezone.utc) - timedelta(seconds=age_seconds)).isoformat()
        for _ in range(failures):
            conn.execute(
                "INSERT INTO login_events (email, ip, success, created_at, user_agent) "
                "VALUES (?, ?, 0, ?, '')", (email, ip, when))
        if then_success:
            conn.execute(
                "INSERT INTO login_events (email, ip, success, created_at, user_agent) "
                "VALUES (?, ?, 1, ?, '')", (email, ip, when))
        conn.commit()
    finally:
        conn.close()


def _anon(client):
    client.cookies.clear()
    return client


def test_lockout_after_five_failures(client_and_db):
    client, db_path = client_and_db
    _seed_events(db_path, ADMIN_EMAIL, failures=5)
    r = _anon(client).post("/api/users/login",
                           json={"email": ADMIN_EMAIL, "password": "admin-test-password"})
    assert r.status_code == 429
    assert "Trop de tentatives" in r.json()["detail"]
    assert "Retry-After" in r.headers


def test_no_lockout_below_threshold(client_and_db):
    client, db_path = client_and_db
    _seed_events(db_path, ADMIN_EMAIL, failures=4)
    r = _anon(client).post("/api/users/login",
                           json={"email": ADMIN_EMAIL, "password": "admin-test-password"})
    assert r.status_code == 200


def test_lockout_expires_after_delay(client_and_db):
    """5 échecs vieux de plus de 30 s : le délai est purgé, on peut se reconnecter."""
    client, db_path = client_and_db
    _seed_events(db_path, ADMIN_EMAIL, failures=5, age_seconds=3600)
    r = _anon(client).post("/api/users/login",
                           json={"email": ADMIN_EMAIL, "password": "admin-test-password"})
    assert r.status_code == 200


def test_success_resets_counter(client_and_db):
    client, db_path = client_and_db
    _seed_events(db_path, ADMIN_EMAIL, failures=8, then_success=True)
    r = _anon(client).post("/api/users/login",
                           json={"email": ADMIN_EMAIL, "password": "admin-test-password"})
    assert r.status_code == 200


def test_unknown_email_is_locked_too(client_and_db):
    client, db_path = client_and_db
    _seed_events(db_path, "inconnu@nulle-part.fr", failures=5)
    r = _anon(client).post("/api/users/login",
                           json={"email": "inconnu@nulle-part.fr", "password": "x"})
    assert r.status_code == 429


def test_ip_lockout_across_accounts(client_and_db):
    """15 échecs depuis la même IP (emails variés) verrouillent l'IP entière."""
    client, db_path = client_and_db
    for i in range(15):
        _seed_events(db_path, f"compte{i}@test.fr", failures=1, ip="testclient")
    r = _anon(client).post("/api/users/login",
                           json={"email": ADMIN_EMAIL, "password": "admin-test-password"})
    assert r.status_code == 429


def test_progressive_delays():
    """Formule : 30 s au seuil, doublement par échec supplémentaire, plafond 30 min."""
    from backend.modules.users.lockout import _remaining, EMAIL_THRESHOLD
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    last = now.isoformat()
    assert _remaining(4, EMAIL_THRESHOLD, last, now) == 0
    assert _remaining(5, EMAIL_THRESHOLD, last, now) == 30
    assert _remaining(6, EMAIL_THRESHOLD, last, now) == 60
    assert _remaining(7, EMAIL_THRESHOLD, last, now) == 120
    assert _remaining(50, EMAIL_THRESHOLD, last, now) == 30 * 60


def test_failed_login_is_journaled(client_and_db):
    client, db_path = client_and_db
    _anon(client).post("/api/users/login",
                       json={"email": ADMIN_EMAIL, "password": "mauvais"})
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT email, success FROM login_events ORDER BY id DESC LIMIT 1").fetchone()
    finally:
        conn.close()
    assert row == (ADMIN_EMAIL, 0)


def test_successful_login_is_journaled(client_and_db):
    client, db_path = client_and_db
    _anon(client).post("/api/users/login",
                       json={"email": ADMIN_EMAIL, "password": "admin-test-password"})
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT email, success FROM login_events ORDER BY id DESC LIMIT 1").fetchone()
    finally:
        conn.close()
    assert row == (ADMIN_EMAIL, 1)


def test_login_events_admin_only(client_and_db, login_as):
    client, db_path = client_and_db
    _seed_events(db_path, "quelquun@test.fr", failures=2)
    r = client.get("/api/users/login-events")
    assert r.status_code == 200
    events = r.json()
    assert len(events) >= 2
    assert {"id", "email", "ip", "success", "created_at", "user_agent"} <= set(events[0])

    viewer = login_as("lecteur.journal@test.fr", roles=[])
    assert viewer.get("/api/users/login-events").status_code == 403


def test_login_events_anonymous_401(client_and_db):
    client, _ = client_and_db
    assert _anon(client).get("/api/users/login-events").status_code == 401


def test_login_events_limit(client_and_db):
    client, db_path = client_and_db
    _seed_events(db_path, "beaucoup@test.fr", failures=10)
    r = client.get("/api/users/login-events?limit=3")
    assert r.status_code == 200
    assert len(r.json()) == 3
