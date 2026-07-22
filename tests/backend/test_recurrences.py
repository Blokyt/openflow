"""Tests des transactions récurrentes : génération des échéances dues, idempotence."""
import sqlite3
from datetime import date, datetime, timedelta, timezone

from backend.modules.recurrences.api import _add_period, _due_dates


def _entities(client):
    interne = client.post("/api/entities/", json={"name": "Asso", "type": "internal"}).json()["id"]
    externe = client.post("/api/entities/", json={"name": "Banque", "type": "external"}).json()["id"]
    return interne, externe


def _count_tx(db_path):
    conn = sqlite3.connect(db_path)
    n = conn.execute("SELECT COUNT(*) FROM transactions WHERE created_by = 'récurrence'").fetchone()[0]
    conn.close()
    return n


# ─── Logique de dates ─────────────────────────────────────────────────────────

def test_add_period_monthly_clamps_end_of_month():
    assert _add_period(date(2026, 1, 31), "monthly", 1) == date(2026, 2, 28)
    assert _add_period(date(2026, 1, 15), "monthly", 2) == date(2026, 3, 15)
    assert _add_period(date(2026, 1, 1), "weekly", 1) == date(2026, 1, 8)
    assert _add_period(date(2026, 3, 1), "yearly", 1) == date(2027, 3, 1)


def test_due_dates_first_run_backfills():
    dates = _due_dates(date(2026, 1, 1), "monthly", None, None, date(2026, 3, 15))
    assert dates == [date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1)]


def test_due_dates_after_last_run():
    dates = _due_dates(date(2026, 1, 1), "monthly", date(2026, 2, 1), None, date(2026, 4, 10))
    assert dates == [date(2026, 3, 1), date(2026, 4, 1)]


def test_due_dates_respects_end():
    dates = _due_dates(date(2026, 1, 1), "monthly", None, date(2026, 2, 15), date(2026, 6, 1))
    assert dates == [date(2026, 1, 1), date(2026, 2, 1)]


# ─── API ──────────────────────────────────────────────────────────────────────

def _make_rec(client, interne, externe, start, freq="monthly", active=True):
    return client.post("/api/recurrences/", json={
        "label": "Frais bancaires", "amount_cents": 500,
        "from_entity_id": interne, "to_entity_id": externe,
        "frequency": freq, "start_date": start, "active": active,
    })


def test_create_and_list(client):
    interne, externe = _entities(client)
    r = _make_rec(client, interne, externe, "2026-01-01")
    assert r.status_code == 201
    assert len(r.json()) == 1
    assert r.json()[0]["label"] == "Frais bancaires"


def test_run_generates_and_is_idempotent(client_and_db):
    client, db_path = client_and_db
    interne, externe = _entities(client)
    start = (datetime.now(timezone.utc).date() - timedelta(days=70)).replace(day=1).isoformat()
    _make_rec(client, interne, externe, start, freq="monthly")

    r1 = client.post("/api/recurrences/run")
    assert r1.status_code == 200
    n = r1.json()["generated"]
    assert n >= 2  # au moins 2 mois écoulés
    assert _count_tx(db_path) == n

    # Relancer ne recrée rien.
    r2 = client.post("/api/recurrences/run")
    assert r2.json()["generated"] == 0
    assert _count_tx(db_path) == n


def test_inactive_recurrence_not_generated(client_and_db):
    client, db_path = client_and_db
    interne, externe = _entities(client)
    start = (datetime.now(timezone.utc).date() - timedelta(days=70)).isoformat()
    _make_rec(client, interne, externe, start, active=False)
    client.post("/api/recurrences/run")
    assert _count_tx(db_path) == 0


def test_validation_same_entity_rejected(client):
    interne, _ = _entities(client)
    r = client.post("/api/recurrences/", json={
        "label": "X", "amount_cents": 500, "from_entity_id": interne,
        "to_entity_id": interne, "frequency": "monthly", "start_date": "2026-01-01",
    })
    assert r.status_code == 400


def test_delete_recurrence_keeps_generated_transactions(client_and_db):
    client, db_path = client_and_db
    interne, externe = _entities(client)
    start = (datetime.now(timezone.utc).date() - timedelta(days=40)).isoformat()
    _make_rec(client, interne, externe, start)
    client.post("/api/recurrences/run")
    before = _count_tx(db_path)
    rec_id = client.get("/api/recurrences/").json()[0]["id"]
    client.delete(f"/api/recurrences/{rec_id}")
    assert _count_tx(db_path) == before  # transactions conservées
    assert client.get("/api/recurrences/").json() == []
