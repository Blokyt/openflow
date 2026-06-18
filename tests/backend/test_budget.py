"""Tests for the Budget & Exercices module (1.3.0).

Convention monétaire (C1+C2) :
  - `amount` en DB = entier de centimes, TOUJOURS POSITIF.
  - Sens porté par from_entity_id -> to_entity_id.
  - recette = from externe -> to interne ; dépense = from interne -> to externe.
  - Les endpoints JSON (/budget/view, allocations) travaillent en centimes.
  - compute_entity_balance_for_period renvoie des centimes (agnostique à l'unité).
"""
import os, sys
import sqlite3
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


def _make_fy(client, name="2025-2026", start="2025-09-01", notes=""):
    r = client.post("/api/budget/fiscal-years", json={"name": name, "start_date": start, "notes": notes})
    assert r.status_code == 201, r.text
    return r.json()


def _close_fy(client, fy_id, end_date="2026-08-31"):
    r = client.post(f"/api/budget/fiscal-years/{fy_id}/close", json={"end_date": end_date})
    assert r.status_code == 200, r.text
    return r.json()


def test_budget_tables_exist(client_and_db):
    """After migration 1.3.0, the three tables exist and legacy `budgets` is gone."""
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
    assert "budgets" not in tables


def test_compute_entity_balance_for_period_basic(client_and_db):
    client, db_path = client_and_db
    from backend.core.balance import compute_entity_balance_for_period

    src = client.post("/api/entities/", json={"name": "Src", "type": "external"}).json()
    dst = client.post("/api/entities/", json={"name": "Dst", "type": "internal"}).json()

    # Montants en centimes, positifs, sens via from/to :
    # recette = from externe (src) -> to interne (dst)
    for date, amount_cents in [("2025-05-15", 10000), ("2025-09-15", 20000), ("2025-11-15", 30000)]:
        client.post("/api/transactions/", json={
            "date": date, "label": "tx", "amount": amount_cents,
            "from_entity_id": src["id"], "to_entity_id": dst["id"],
        })

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        # opening en centimes (50000 = 500 €)
        result = compute_entity_balance_for_period(conn, dst["id"], "2025-09-01", "2025-09-30", opening=50000)
        assert result["opening"] == 50000
        # réalisé = 200 € = 20000 centimes (seule la tx du 2025-09-15 est dans la période)
        assert result["realized"] == 20000
        assert result["closing"] == 70000
    finally:
        conn.close()


def test_compute_entity_balance_for_period_expense(client_and_db):
    client, db_path = client_and_db
    from backend.core.balance import compute_entity_balance_for_period

    ext = client.post("/api/entities/", json={"name": "Ext", "type": "external"}).json()
    me = client.post("/api/entities/", json={"name": "Me", "type": "internal"}).json()

    # Dépense : from interne (me) -> to externe (ext), montant 5000 centimes (50 €)
    client.post("/api/transactions/", json={
        "date": "2025-09-10", "label": "buy", "amount": 5000,
        "from_entity_id": me["id"], "to_entity_id": ext["id"],
    })

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        # opening = 100000 centimes (1000 €)
        result = compute_entity_balance_for_period(conn, me["id"], "2025-09-01", "2025-09-30", opening=100000)
        # réalisé = -5000 centimes (dépense sortante)
        assert result["realized"] == -5000
        assert result["closing"] == 95000
    finally:
        conn.close()


def test_fiscal_year_crud(client):
    r = client.get("/api/budget/fiscal-years")
    assert r.status_code == 200 and r.json() == []

    fy = _make_fy(client, notes="rentrée")
    assert fy["name"] == "2025-2026"
    assert fy["end_date"] is None

    r = client.put(f"/api/budget/fiscal-years/{fy['id']}", json={"notes": "rentrée universitaire"})
    assert r.status_code == 200
    assert r.json()["notes"] == "rentrée universitaire"

    r = client.get("/api/budget/fiscal-years")
    assert len(r.json()) == 1

    r = client.delete(f"/api/budget/fiscal-years/{fy['id']}")
    assert r.status_code == 200
    assert client.get("/api/budget/fiscal-years").json() == []


def test_only_one_open_mandate(client):
    """Cannot create a new fiscal year while one is still open."""
    _make_fy(client, "2024-2025", "2024-09-01")
    r = client.post("/api/budget/fiscal-years", json={
        "name": "2025-2026", "start_date": "2025-09-01",
    })
    assert r.status_code == 400
    assert "ouvert" in r.json()["detail"].lower()


def test_fiscal_year_current_endpoint(client):
    assert client.get("/api/budget/fiscal-years/current").status_code == 404
    _make_fy(client)
    r = client.get("/api/budget/fiscal-years/current")
    assert r.status_code == 200
    assert r.json()["name"] == "2025-2026"
    assert r.json()["end_date"] is None


def test_fiscal_year_name_unique(client):
    _make_fy(client, "2025-2026", "2025-09-01")
    # First try: blocked by open mandate (400)
    r = client.post("/api/budget/fiscal-years", json={
        "name": "2025-2026", "start_date": "2025-09-01",
    })
    assert r.status_code in (400, 409)


def test_close_fiscal_year(client):
    fy = _make_fy(client)
    assert fy["end_date"] is None

    r = client.post(f"/api/budget/fiscal-years/{fy['id']}/close", json={"end_date": "2026-08-31"})
    assert r.status_code == 200
    closed = r.json()
    assert closed["end_date"] == "2026-08-31"

    r = client.get("/api/budget/fiscal-years/current")
    assert r.status_code == 404


def test_close_fiscal_year_defaults_to_today(client):
    fy = _make_fy(client)
    r = client.post(f"/api/budget/fiscal-years/{fy['id']}/close", json={})
    assert r.status_code == 200
    assert r.json()["end_date"] is not None


def test_close_already_closed_returns_400(client):
    fy = _make_fy(client)
    _close_fy(client, fy["id"])
    r = client.post(f"/api/budget/fiscal-years/{fy['id']}/close", json={})
    assert r.status_code == 400
    assert "déjà" in r.json()["detail"].lower()


def test_close_date_must_be_after_start(client):
    fy = _make_fy(client, start="2025-09-01")
    r = client.post(f"/api/budget/fiscal-years/{fy['id']}/close", json={"end_date": "2025-08-01"})
    assert r.status_code == 400


def test_allocation_crud(client):
    fy = _make_fy(client)
    e = client.post("/api/entities/", json={"name": "Club", "type": "internal"}).json()
    c = client.post("/api/categories/", json={"name": "Food"}).json()

    # Allocations en centimes : 2000 € = 200000 centimes
    r = client.post(f"/api/budget/fiscal-years/{fy['id']}/allocations", json={
        "entity_id": e["id"], "amount": 200000, "notes": "enveloppe globale",
    })
    assert r.status_code == 201
    global_alloc = r.json()
    assert global_alloc["category_id"] is None

    # 1500 € = 150000 centimes
    r = client.post(f"/api/budget/fiscal-years/{fy['id']}/allocations", json={
        "entity_id": e["id"], "category_id": c["id"], "amount": 150000,
    })
    assert r.status_code == 201

    rows = client.get(f"/api/budget/fiscal-years/{fy['id']}/allocations").json()
    assert len(rows) == 2

    # Mise à jour : 2500 € = 250000 centimes
    r = client.put(f"/api/budget/allocations/{global_alloc['id']}", json={"amount": 250000})
    assert r.status_code == 200
    assert r.json()["amount"] == 250000

    r = client.delete(f"/api/budget/allocations/{global_alloc['id']}")
    assert r.status_code == 200
    rows = client.get(f"/api/budget/fiscal-years/{fy['id']}/allocations").json()
    assert len(rows) == 1


def test_allocation_unique_triplet(client):
    fy = _make_fy(client)
    e = client.post("/api/entities/", json={"name": "Club", "type": "internal"}).json()
    c = client.post("/api/categories/", json={"name": "Food"}).json()

    # 100 € = 10000 centimes
    client.post(f"/api/budget/fiscal-years/{fy['id']}/allocations", json={
        "entity_id": e["id"], "category_id": c["id"], "amount": 10000,
    })
    # 200 € = 20000 centimes, même triplet -> conflit
    r = client.post(f"/api/budget/fiscal-years/{fy['id']}/allocations", json={
        "entity_id": e["id"], "category_id": c["id"], "amount": 20000,
    })
    assert r.status_code in (400, 409)


def test_view_realized_and_categories(client):
    fy = _make_fy(client)
    e = client.post("/api/entities/", json={"name": "Club", "type": "internal"}).json()
    ext = client.post("/api/entities/", json={"name": "Ext", "type": "external"}).json()
    cat = client.post("/api/categories/", json={"name": "Food"}).json()

    # Allocations en centimes : 500 € = 50000 ; 300 € = 30000
    client.post(f"/api/budget/fiscal-years/{fy['id']}/allocations", json={
        "entity_id": e["id"], "amount": 50000,
    })
    client.post(f"/api/budget/fiscal-years/{fy['id']}/allocations", json={
        "entity_id": e["id"], "category_id": cat["id"], "amount": 30000,
    })

    # Dépense : from interne (e) -> to externe (ext) = 120 € = 12000 centimes
    client.post("/api/transactions/", json={
        "date": "2025-10-15", "label": "buy food", "amount": 12000,
        "from_entity_id": e["id"], "to_entity_id": ext["id"],
        "category_id": cat["id"],
    })
    # Recette : from externe (ext) -> to interne (e) = 50 € = 5000 centimes
    client.post("/api/transactions/", json={
        "date": "2025-11-05", "label": "cash in", "amount": 5000,
        "from_entity_id": ext["id"], "to_entity_id": e["id"],
    })
    # Tx hors période : dépense de 200 € = 20000 centimes (date 2024-08-15 < start 2025-09-01)
    client.post("/api/transactions/", json={
        "date": "2024-08-15", "label": "old", "amount": 20000,
        "from_entity_id": e["id"], "to_entity_id": ext["id"],
    })

    r = client.get(f"/api/budget/view?fiscal_year_id={fy['id']}")
    assert r.status_code == 200
    data = r.json()
    assert data["fiscal_year"]["id"] == fy["id"]
    assert data["previous_fiscal_year_id"] is None
    club = next(x for x in data["entities"] if x["entity_id"] == e["id"])

    # opening = solde de e au 2025-08-31 (en centimes).
    # Seule la tx old (2024-08-15) est antérieure : from=e -> sortie = -20000.
    assert club["opening_balance"] == -20000

    # allocated_total en centimes : 50000 (allocation globale)
    assert club["allocated_total"] == 50000

    # réalisé total en centimes : -12000 (dépense) + 5000 (recette) = -7000
    assert round(club["realized_total"], 2) == -7000

    food = next(c for c in club["categories"] if c["category_id"] == cat["id"])
    # allocation food = 30000 centimes
    assert food["allocated"] == 30000
    # réalisé food = -12000 centimes (seule la dépense est catégorisée)
    assert round(food["realized"], 2) == -12000


def test_view_with_previous_year(client):
    """With a prior fiscal year, realized_n_minus_1 is populated."""
    fy_prev = _make_fy(client, "2024-2025", "2024-09-01")
    e = client.post("/api/entities/", json={"name": "Club", "type": "internal"}).json()
    ext = client.post("/api/entities/", json={"name": "Ext", "type": "external"}).json()

    # Dépense N-1 : créée pendant que fy_prev est ouvert (sinon le verrou bloque).
    # 100 € = 10000 centimes (from interne -> to externe)
    client.post("/api/transactions/", json={
        "date": "2024-10-15", "label": "prev year buy", "amount": 10000,
        "from_entity_id": e["id"], "to_entity_id": ext["id"],
    })

    _close_fy(client, fy_prev["id"], "2025-08-31")
    fy = _make_fy(client, "2025-2026", "2025-09-01")

    # Dépense N : 140 € = 14000 centimes (from interne -> to externe)
    client.post("/api/transactions/", json={
        "date": "2025-10-15", "label": "this year buy", "amount": 14000,
        "from_entity_id": e["id"], "to_entity_id": ext["id"],
    })

    data = client.get(f"/api/budget/view?fiscal_year_id={fy['id']}").json()
    assert data["previous_fiscal_year_id"] == fy_prev["id"]
    club = next(x for x in data["entities"] if x["entity_id"] == e["id"])
    # réalisé N = -14000 (dépense sortante)
    assert round(club["realized_total"], 2) == -14000
    # réalisé N-1 = -10000 (dépense sortante l'année précédente)
    assert round(club["realized_n_minus_1"], 2) == -10000


def test_view_no_fiscal_year(client):
    r = client.get("/api/budget/view?fiscal_year_id=999")
    assert r.status_code == 404


def test_view_allocated_total_uses_detail_when_no_global(client):
    fy = _make_fy(client)
    e = client.post("/api/entities/", json={"name": "Club", "type": "internal"}).json()
    c1 = client.post("/api/categories/", json={"name": "A"}).json()
    c2 = client.post("/api/categories/", json={"name": "B"}).json()

    # 300 € = 30000 + 200 € = 20000 centimes (aucune allocation globale)
    client.post(f"/api/budget/fiscal-years/{fy['id']}/allocations", json={
        "entity_id": e["id"], "category_id": c1["id"], "amount": 30000,
    })
    client.post(f"/api/budget/fiscal-years/{fy['id']}/allocations", json={
        "entity_id": e["id"], "category_id": c2["id"], "amount": 20000,
    })

    data = client.get(f"/api/budget/view?fiscal_year_id={fy['id']}").json()
    club = next(x for x in data["entities"] if x["entity_id"] == e["id"])
    # allocated_total = somme des détails = 50000 centimes
    assert club["allocated_total"] == 50000
    assert data["totals"]["allocated"] == 50000


def test_view_remaining_handles_recettes(client):
    fy = _make_fy(client)
    e = client.post("/api/entities/", json={"name": "Club", "type": "internal"}).json()
    ext = client.post("/api/entities/", json={"name": "Ext", "type": "external"}).json()

    # Allocation 1000 € = 100000 centimes
    client.post(f"/api/budget/fiscal-years/{fy['id']}/allocations", json={
        "entity_id": e["id"], "amount": 100000,
    })
    # Recette 300 € = 30000 centimes (from externe -> to interne)
    client.post("/api/transactions/", json={
        "date": "2025-10-10", "label": "recette", "amount": 30000,
        "from_entity_id": ext["id"], "to_entity_id": e["id"],
    })

    data = client.get(f"/api/budget/view?fiscal_year_id={fy['id']}").json()
    # remaining = allocated + realized = 100000 + 30000 = 130000 centimes
    assert round(data["totals"]["remaining"], 2) == 130000


def test_view_category_endpoint(client):
    """GET /view/categories returns parent-level category rows."""
    fy = _make_fy(client)
    e = client.post("/api/entities/", json={"name": "Club", "type": "internal"}).json()
    ext = client.post("/api/entities/", json={"name": "Ext", "type": "external"}).json()
    parent = client.post("/api/categories/", json={"name": "Dépenses"}).json()
    child = client.post("/api/categories/", json={"name": "Nourriture", "parent_id": parent["id"]}).json()

    # Allocation 500 € = 50000 centimes
    client.post(f"/api/budget/fiscal-years/{fy['id']}/allocations", json={
        "entity_id": e["id"], "category_id": child["id"], "amount": 50000,
    })
    # Dépense 150 € = 15000 centimes (from interne -> to externe)
    client.post("/api/transactions/", json={
        "date": "2025-10-10", "label": "repas", "amount": 15000,
        "from_entity_id": e["id"], "to_entity_id": ext["id"],
        "category_id": child["id"],
    })

    r = client.get(f"/api/budget/view/categories?fiscal_year_id={fy['id']}")
    assert r.status_code == 200
    data = r.json()
    assert "categories" in data
    dep = next((c for c in data["categories"] if c["category_id"] == parent["id"]), None)
    assert dep is not None
    # allocated = 50000 centimes
    assert dep["allocated"] == 50000
    # réalisé = -15000 centimes (dépense sortante)
    assert round(dep["realized"], 2) == -15000


def test_entity_delete_cascades_budget(client):
    fy = _make_fy(client)
    e = client.post("/api/entities/", json={"name": "Doomed", "type": "internal"}).json()
    # 50 € = 5000 centimes
    client.post(f"/api/budget/fiscal-years/{fy['id']}/allocations", json={
        "entity_id": e["id"], "amount": 5000,
    })

    assert len(client.get(f"/api/budget/fiscal-years/{fy['id']}/allocations").json()) == 1

    r = client.delete(f"/api/entities/{e['id']}")
    assert r.status_code == 200

    assert len(client.get(f"/api/budget/fiscal-years/{fy['id']}/allocations").json()) == 0
