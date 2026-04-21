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


def test_fiscal_year_crud(client):
    # Empty
    r = client.get("/api/budget/fiscal-years")
    assert r.status_code == 200 and r.json() == []

    # Create
    r = client.post("/api/budget/fiscal-years", json={
        "name": "2025-2026", "start_date": "2025-09-01", "end_date": "2026-08-31",
        "is_current": True, "notes": "rentrée",
    })
    assert r.status_code == 201
    fy = r.json()
    assert fy["name"] == "2025-2026"
    assert fy["is_current"] == 1

    # Update
    r = client.put(f"/api/budget/fiscal-years/{fy['id']}", json={"notes": "rentrée universitaire"})
    assert r.status_code == 200
    assert r.json()["notes"] == "rentrée universitaire"

    # List (1 entry)
    r = client.get("/api/budget/fiscal-years")
    assert len(r.json()) == 1

    # Delete
    r = client.delete(f"/api/budget/fiscal-years/{fy['id']}")
    assert r.status_code == 200

    r = client.get("/api/budget/fiscal-years")
    assert r.json() == []


def test_fiscal_year_is_current_unique(client):
    a = client.post("/api/budget/fiscal-years", json={
        "name": "2024-2025", "start_date": "2024-09-01", "end_date": "2025-08-31",
        "is_current": True,
    }).json()
    b = client.post("/api/budget/fiscal-years", json={
        "name": "2025-2026", "start_date": "2025-09-01", "end_date": "2026-08-31",
        "is_current": True,
    }).json()

    rows = client.get("/api/budget/fiscal-years").json()
    currents = [r for r in rows if r["is_current"] == 1]
    assert len(currents) == 1
    assert currents[0]["id"] == b["id"]


def test_fiscal_year_current_endpoint(client):
    assert client.get("/api/budget/fiscal-years/current").status_code == 404
    client.post("/api/budget/fiscal-years", json={
        "name": "2025-2026", "start_date": "2025-09-01", "end_date": "2026-08-31",
        "is_current": True,
    })
    r = client.get("/api/budget/fiscal-years/current")
    assert r.status_code == 200
    assert r.json()["name"] == "2025-2026"


def test_fiscal_year_name_unique(client):
    client.post("/api/budget/fiscal-years", json={
        "name": "2025-2026", "start_date": "2025-09-01", "end_date": "2026-08-31",
    })
    r = client.post("/api/budget/fiscal-years", json={
        "name": "2025-2026", "start_date": "2025-09-01", "end_date": "2026-08-31",
    })
    assert r.status_code in (400, 409)


def test_fiscal_year_dates_validated(client):
    r = client.post("/api/budget/fiscal-years", json={
        "name": "broken", "start_date": "2026-09-01", "end_date": "2025-08-31",
    })
    assert r.status_code == 400


def test_opening_balance_upsert(client):
    fy = client.post("/api/budget/fiscal-years", json={
        "name": "2025-2026", "start_date": "2025-09-01", "end_date": "2026-08-31",
    }).json()
    e1 = client.post("/api/entities/", json={"name": "Club1", "type": "internal"}).json()
    e2 = client.post("/api/entities/", json={"name": "Club2", "type": "internal"}).json()

    # Upsert two rows
    r = client.put(f"/api/budget/fiscal-years/{fy['id']}/opening-balances", json=[
        {"entity_id": e1["id"], "amount": 1000.0, "source": "CE IDF"},
        {"entity_id": e2["id"], "amount": 500.0, "source": ""},
    ])
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    assert sum(o["amount"] for o in data) == 1500.0

    # Re-upsert with an updated value (replaces)
    r = client.put(f"/api/budget/fiscal-years/{fy['id']}/opening-balances", json=[
        {"entity_id": e1["id"], "amount": 1200.0, "source": "CE IDF au 31/08"},
    ])
    assert r.status_code == 200
    ob = client.get(f"/api/budget/fiscal-years/{fy['id']}/opening-balances").json()
    assert len(ob) == 1  # e2 removed
    assert ob[0]["amount"] == 1200.0


def test_opening_balance_rejects_external_entity(client):
    fy = client.post("/api/budget/fiscal-years", json={
        "name": "2025-2026", "start_date": "2025-09-01", "end_date": "2026-08-31",
    }).json()
    ext = client.post("/api/entities/", json={"name": "Bank", "type": "external"}).json()

    r = client.put(f"/api/budget/fiscal-years/{fy['id']}/opening-balances", json=[
        {"entity_id": ext["id"], "amount": 1000.0},
    ])
    assert r.status_code == 400


def test_suggested_opening(client):
    # Internal entity with some history
    ext = client.post("/api/entities/", json={"name": "Ext", "type": "external"}).json()
    me = client.post("/api/entities/", json={"name": "Me", "type": "internal"}).json()
    # Adjust its reference so we have a known baseline
    client.put(f"/api/entities/{me['id']}/balance-ref", json={
        "reference_date": "2025-01-01", "reference_amount": 1000.0,
    })
    # One tx before the fiscal year start
    client.post("/api/transactions/", json={
        "date": "2025-06-15", "label": "paid", "amount": 200.0,
        "from_entity_id": ext["id"], "to_entity_id": me["id"],
    })

    fy = client.post("/api/budget/fiscal-years", json={
        "name": "2025-2026", "start_date": "2025-09-01", "end_date": "2026-08-31",
    }).json()

    r = client.get(f"/api/budget/fiscal-years/{fy['id']}/suggested-opening")
    assert r.status_code == 200
    data = r.json()
    me_row = next(x for x in data if x["entity_id"] == me["id"])
    assert me_row["suggested_amount"] == 1200.0  # 1000 ref + 200 flow


def test_allocation_crud(client):
    fy = client.post("/api/budget/fiscal-years", json={
        "name": "2025-2026", "start_date": "2025-09-01", "end_date": "2026-08-31",
    }).json()
    e = client.post("/api/entities/", json={"name": "Club", "type": "internal"}).json()
    c = client.post("/api/categories/", json={"name": "Food"}).json()

    # Create global (no category)
    r = client.post(f"/api/budget/fiscal-years/{fy['id']}/allocations", json={
        "entity_id": e["id"], "amount": 2000.0, "notes": "enveloppe globale",
    })
    assert r.status_code == 201
    global_alloc = r.json()
    assert global_alloc["category_id"] is None

    # Create categorized
    r = client.post(f"/api/budget/fiscal-years/{fy['id']}/allocations", json={
        "entity_id": e["id"], "category_id": c["id"], "amount": 1500.0,
    })
    assert r.status_code == 201

    # List
    rows = client.get(f"/api/budget/fiscal-years/{fy['id']}/allocations").json()
    assert len(rows) == 2

    # Update
    r = client.put(f"/api/budget/allocations/{global_alloc['id']}", json={"amount": 2500.0})
    assert r.status_code == 200
    assert r.json()["amount"] == 2500.0

    # Delete
    r = client.delete(f"/api/budget/allocations/{global_alloc['id']}")
    assert r.status_code == 200
    rows = client.get(f"/api/budget/fiscal-years/{fy['id']}/allocations").json()
    assert len(rows) == 1


def test_allocation_unique_triplet(client):
    fy = client.post("/api/budget/fiscal-years", json={
        "name": "2025-2026", "start_date": "2025-09-01", "end_date": "2026-08-31",
    }).json()
    e = client.post("/api/entities/", json={"name": "Club", "type": "internal"}).json()
    c = client.post("/api/categories/", json={"name": "Food"}).json()

    client.post(f"/api/budget/fiscal-years/{fy['id']}/allocations", json={
        "entity_id": e["id"], "category_id": c["id"], "amount": 100.0,
    })
    r = client.post(f"/api/budget/fiscal-years/{fy['id']}/allocations", json={
        "entity_id": e["id"], "category_id": c["id"], "amount": 200.0,
    })
    assert r.status_code in (400, 409)


def test_view_realized_and_categories(client):
    fy = client.post("/api/budget/fiscal-years", json={
        "name": "2025-2026", "start_date": "2025-09-01", "end_date": "2026-08-31",
        "is_current": True,
    }).json()
    e = client.post("/api/entities/", json={"name": "Club", "type": "internal"}).json()
    ext = client.post("/api/entities/", json={"name": "Ext", "type": "external"}).json()
    cat = client.post("/api/categories/", json={"name": "Food"}).json()

    client.put(f"/api/budget/fiscal-years/{fy['id']}/opening-balances", json=[
        {"entity_id": e["id"], "amount": 1000.0},
    ])
    client.post(f"/api/budget/fiscal-years/{fy['id']}/allocations", json={
        "entity_id": e["id"], "amount": 500.0,  # global
    })
    client.post(f"/api/budget/fiscal-years/{fy['id']}/allocations", json={
        "entity_id": e["id"], "category_id": cat["id"], "amount": 300.0,
    })
    # Two tx inside the year (one categorized, one not)
    client.post("/api/transactions/", json={
        "date": "2025-10-15", "label": "buy food", "amount": -120.0,
        "from_entity_id": e["id"], "to_entity_id": ext["id"],
        "category_id": cat["id"],
    })
    client.post("/api/transactions/", json={
        "date": "2025-11-05", "label": "cash in", "amount": 50.0,
        "from_entity_id": ext["id"], "to_entity_id": e["id"],
    })
    # tx outside the year (ignored)
    client.post("/api/transactions/", json={
        "date": "2024-08-15", "label": "old", "amount": -200.0,
        "from_entity_id": e["id"], "to_entity_id": ext["id"],
    })

    r = client.get(f"/api/budget/view?fiscal_year_id={fy['id']}")
    assert r.status_code == 200
    data = r.json()
    assert data["fiscal_year"]["id"] == fy["id"]
    assert data["previous_fiscal_year_id"] is None  # no N-1
    club = next(x for x in data["entities"] if x["entity_id"] == e["id"])
    assert club["opening_balance"] == 1000.0
    assert club["allocated_total"] == 500.0
    # realized = -120 + 50 = -70
    assert round(club["realized_total"], 2) == -70.0
    # Category breakdown
    food = next(c for c in club["categories"] if c["category_id"] == cat["id"])
    assert food["allocated"] == 300.0
    assert round(food["realized"], 2) == -120.0


def test_view_with_previous_year(client):
    """With a prior fiscal year, realized_n_minus_1 is populated."""
    # N-1
    fy_prev = client.post("/api/budget/fiscal-years", json={
        "name": "2024-2025", "start_date": "2024-09-01", "end_date": "2025-08-31",
    }).json()
    fy = client.post("/api/budget/fiscal-years", json={
        "name": "2025-2026", "start_date": "2025-09-01", "end_date": "2026-08-31",
    }).json()
    e = client.post("/api/entities/", json={"name": "Club", "type": "internal"}).json()
    ext = client.post("/api/entities/", json={"name": "Ext", "type": "external"}).json()

    client.post("/api/transactions/", json={
        "date": "2024-10-15", "label": "prev year buy", "amount": -100.0,
        "from_entity_id": e["id"], "to_entity_id": ext["id"],
    })
    client.post("/api/transactions/", json={
        "date": "2025-10-15", "label": "this year buy", "amount": -140.0,
        "from_entity_id": e["id"], "to_entity_id": ext["id"],
    })

    data = client.get(f"/api/budget/view?fiscal_year_id={fy['id']}").json()
    assert data["previous_fiscal_year_id"] == fy_prev["id"]
    club = next(x for x in data["entities"] if x["entity_id"] == e["id"])
    assert round(club["realized_total"], 2) == -140.0
    assert round(club["realized_n_minus_1"], 2) == -100.0


def test_view_no_fiscal_year(client):
    r = client.get("/api/budget/view?fiscal_year_id=999")
    assert r.status_code == 404


def test_view_allocated_total_uses_detail_when_no_global(client):
    """When only category allocations exist (no global), allocated_total reflects them."""
    fy = client.post("/api/budget/fiscal-years", json={
        "name": "2025-2026", "start_date": "2025-09-01", "end_date": "2026-08-31",
    }).json()
    e = client.post("/api/entities/", json={"name": "Club", "type": "internal"}).json()
    c1 = client.post("/api/categories/", json={"name": "A"}).json()
    c2 = client.post("/api/categories/", json={"name": "B"}).json()

    # Only category-level allocations, no global
    client.post(f"/api/budget/fiscal-years/{fy['id']}/allocations", json={
        "entity_id": e["id"], "category_id": c1["id"], "amount": 300.0,
    })
    client.post(f"/api/budget/fiscal-years/{fy['id']}/allocations", json={
        "entity_id": e["id"], "category_id": c2["id"], "amount": 200.0,
    })

    data = client.get(f"/api/budget/view?fiscal_year_id={fy['id']}").json()
    club = next(x for x in data["entities"] if x["entity_id"] == e["id"])
    assert club["allocated_total"] == 500.0  # sum of details, not 0
    assert data["totals"]["allocated"] == 500.0


def test_view_remaining_handles_recettes(client):
    """totals.remaining treats realized as signed (recette increases, expense decreases)."""
    fy = client.post("/api/budget/fiscal-years", json={
        "name": "2025-2026", "start_date": "2025-09-01", "end_date": "2026-08-31",
    }).json()
    e = client.post("/api/entities/", json={"name": "Club", "type": "internal"}).json()
    ext = client.post("/api/entities/", json={"name": "Ext", "type": "external"}).json()

    # Allocated 1000, but received 300 as recette
    client.post(f"/api/budget/fiscal-years/{fy['id']}/allocations", json={
        "entity_id": e["id"], "amount": 1000.0,
    })
    client.post("/api/transactions/", json={
        "date": "2025-10-10", "label": "recette", "amount": 300.0,
        "from_entity_id": ext["id"], "to_entity_id": e["id"],
    })

    data = client.get(f"/api/budget/view?fiscal_year_id={fy['id']}").json()
    # remaining = allocated + realized = 1000 + 300 = 1300
    assert round(data["totals"]["remaining"], 2) == 1300.0


def test_entity_delete_cascades_budget(client):
    fy = client.post("/api/budget/fiscal-years", json={
        "name": "2025-2026", "start_date": "2025-09-01", "end_date": "2026-08-31",
    }).json()
    e = client.post("/api/entities/", json={"name": "Doomed", "type": "internal"}).json()
    client.put(f"/api/budget/fiscal-years/{fy['id']}/opening-balances", json=[
        {"entity_id": e["id"], "amount": 100.0},
    ])
    client.post(f"/api/budget/fiscal-years/{fy['id']}/allocations", json={
        "entity_id": e["id"], "amount": 50.0,
    })

    # Precondition
    assert len(client.get(f"/api/budget/fiscal-years/{fy['id']}/opening-balances").json()) == 1
    assert len(client.get(f"/api/budget/fiscal-years/{fy['id']}/allocations").json()) == 1

    r = client.delete(f"/api/entities/{e['id']}")
    assert r.status_code == 200

    # Cascade removed the budget rows
    assert len(client.get(f"/api/budget/fiscal-years/{fy['id']}/opening-balances").json()) == 0
    assert len(client.get(f"/api/budget/fiscal-years/{fy['id']}/allocations").json()) == 0
