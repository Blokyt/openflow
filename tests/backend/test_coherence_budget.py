"""Cross-module coherence: budget view ↔ balance calculation ↔ transactions."""
import os, sys
import sqlite3
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


def test_budget_view_matches_entity_balance_for_period(client_and_db):
    """opening + realized_total from /view == compute_entity_balance_for_period closing."""
    client, db_path = client_and_db
    from backend.core.balance import compute_entity_balance_for_period

    fy = client.post("/api/budget/fiscal-years", json={
        "name": "2025-2026", "start_date": "2025-09-01", "end_date": "2026-08-31",
        "is_current": True,
    }).json()
    e = client.post("/api/entities/", json={"name": "Club", "type": "internal"}).json()
    ext = client.post("/api/entities/", json={"name": "Ext", "type": "external"}).json()

    client.put(f"/api/budget/fiscal-years/{fy['id']}/opening-balances", json=[
        {"entity_id": e["id"], "amount": 2000.0},
    ])
    client.post("/api/transactions/", json={
        "date": "2025-10-01", "label": "x", "amount": -150.0,
        "from_entity_id": e["id"], "to_entity_id": ext["id"],
    })
    client.post("/api/transactions/", json={
        "date": "2026-02-01", "label": "y", "amount": 75.0,
        "from_entity_id": ext["id"], "to_entity_id": e["id"],
    })

    view = client.get(f"/api/budget/view?fiscal_year_id={fy['id']}").json()
    club = next(x for x in view["entities"] if x["entity_id"] == e["id"])

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        direct = compute_entity_balance_for_period(conn, e["id"], "2025-09-01", "2026-08-31", opening=2000.0)
    finally:
        conn.close()

    assert round(club["opening_balance"] + club["realized_total"], 2) == round(direct["closing"], 2)


def test_view_ignores_transactions_outside_period(client):
    fy = client.post("/api/budget/fiscal-years", json={
        "name": "2025-2026", "start_date": "2025-09-01", "end_date": "2026-08-31",
    }).json()
    e = client.post("/api/entities/", json={"name": "Club", "type": "internal"}).json()
    ext = client.post("/api/entities/", json={"name": "Ext", "type": "external"}).json()

    # Before period
    client.post("/api/transactions/", json={
        "date": "2025-06-15", "label": "pre", "amount": 1000.0,
        "from_entity_id": ext["id"], "to_entity_id": e["id"],
    })
    # After period
    client.post("/api/transactions/", json={
        "date": "2026-10-15", "label": "post", "amount": 1000.0,
        "from_entity_id": ext["id"], "to_entity_id": e["id"],
    })

    view = client.get(f"/api/budget/view?fiscal_year_id={fy['id']}").json()
    club = next(x for x in view["entities"] if x["entity_id"] == e["id"])
    assert club["realized_total"] == 0.0
