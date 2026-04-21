"""Tests for the Budget & Exercices module (1.2.0)."""
import os, sys
import sqlite3
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


def test_budget_tables_exist(client_and_db):
    """After migration 1.2.0, the three new tables exist and legacy `budgets` is gone."""
    _, db_path = client_and_db
    conn = sqlite3.connect(str(db_path))
    try:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
    finally:
        conn.close()
    assert "fiscal_years" in tables
    assert "fiscal_year_opening_balances" in tables
    assert "budget_allocations" in tables
    assert "budgets" not in tables  # legacy dropped


def test_compute_entity_balance_for_period_basic(client_and_db):
    """Balance for an entity over a period = opening + net signed flow in [start, end]."""
    client, db_path = client_and_db
    from backend.core.balance import compute_entity_balance_for_period

    src = client.post("/api/entities/", json={"name": "Src", "type": "external"}).json()
    dst = client.post("/api/entities/", json={"name": "Dst", "type": "internal"}).json()

    # 3 tx: one before period, one inside, one after
    for date, amount in [("2025-05-15", 100.0), ("2025-09-15", 200.0), ("2025-11-15", 300.0)]:
        client.post("/api/transactions/", json={
            "date": date, "label": "tx", "amount": amount,
            "from_entity_id": src["id"], "to_entity_id": dst["id"],
        })

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        # Period = all of September
        result = compute_entity_balance_for_period(conn, dst["id"], "2025-09-01", "2025-09-30", opening=500.0)
        assert result["opening"] == 500.0
        assert result["realized"] == 200.0  # only the September tx
        assert result["closing"] == 700.0
    finally:
        conn.close()


def test_compute_entity_balance_for_period_expense(client_and_db):
    """Expense (from=entity, amount<0) counts negatively in realized."""
    client, db_path = client_and_db
    from backend.core.balance import compute_entity_balance_for_period

    ext = client.post("/api/entities/", json={"name": "Ext", "type": "external"}).json()
    me = client.post("/api/entities/", json={"name": "Me", "type": "internal"}).json()

    client.post("/api/transactions/", json={
        "date": "2025-09-10", "label": "buy", "amount": -50.0,
        "from_entity_id": me["id"], "to_entity_id": ext["id"],
    })

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        result = compute_entity_balance_for_period(conn, me["id"], "2025-09-01", "2025-09-30", opening=1000.0)
        assert result["realized"] == -50.0
        assert result["closing"] == 950.0
    finally:
        conn.close()
