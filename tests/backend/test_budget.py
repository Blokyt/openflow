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


# ─── Refonte dépense/recette (1.7.0) ─────────────────────────────────────────

def _find_entity(data, entity_id):
    for e in data["entities"]:
        if e["entity_id"] == entity_id:
            return e
    raise KeyError(entity_id)


def test_allocation_direction_default_expense(client):
    fy = _make_fy(client)
    e = client.post("/api/entities/", json={"name": "Club", "type": "internal"}).json()
    r = client.post(f"/api/budget/fiscal-years/{fy['id']}/allocations",
                    json={"entity_id": e["id"], "amount": 10000})
    assert r.status_code == 201
    assert r.json()["direction"] == "expense"


def test_allocation_income_accepted(client):
    fy = _make_fy(client)
    e = client.post("/api/entities/", json={"name": "Club", "type": "internal"}).json()
    r = client.post(f"/api/budget/fiscal-years/{fy['id']}/allocations",
                    json={"entity_id": e["id"], "amount": 5000, "direction": "income"})
    assert r.status_code == 201
    assert r.json()["direction"] == "income"


def test_allocation_expense_and_income_coexist(client):
    fy = _make_fy(client)
    e = client.post("/api/entities/", json={"name": "Club", "type": "internal"}).json()
    r1 = client.post(f"/api/budget/fiscal-years/{fy['id']}/allocations",
                     json={"entity_id": e["id"], "amount": 10000, "direction": "expense"})
    r2 = client.post(f"/api/budget/fiscal-years/{fy['id']}/allocations",
                     json={"entity_id": e["id"], "amount": 3000, "direction": "income"})
    assert r1.status_code == 201 and r2.status_code == 201


def test_allocation_duplicate_same_direction_conflict(client):
    fy = _make_fy(client)
    e = client.post("/api/entities/", json={"name": "Club", "type": "internal"}).json()
    client.post(f"/api/budget/fiscal-years/{fy['id']}/allocations",
                json={"entity_id": e["id"], "amount": 10000, "direction": "expense"})
    r = client.post(f"/api/budget/fiscal-years/{fy['id']}/allocations",
                    json={"entity_id": e["id"], "amount": 5000, "direction": "expense"})
    assert r.status_code in (400, 409)


def test_view_split_expense_income(client):
    fy = _make_fy(client)
    e = client.post("/api/entities/", json={"name": "Club", "type": "internal"}).json()
    ext = client.post("/api/entities/", json={"name": "Ext", "type": "external"}).json()
    client.post("/api/transactions/", json={"date": "2025-10-15", "label": "dep", "amount": 12000,
                                             "from_entity_id": e["id"], "to_entity_id": ext["id"]})
    client.post("/api/transactions/", json={"date": "2025-11-05", "label": "rec", "amount": 5000,
                                             "from_entity_id": ext["id"], "to_entity_id": e["id"]})
    data = client.get(f"/api/budget/view?fiscal_year_id={fy['id']}").json()
    club = _find_entity(data, e["id"])
    assert club["realized_expense"] == 12000
    assert club["realized_income"] == 5000
    assert club["realized_net"] == -7000


def test_view_internal_transfer_is_income_for_club(client):
    """Une dotation BDA -> club est une recette du club dans la vue budget."""
    fy = _make_fy(client)
    bda = client.post("/api/entities/", json={"name": "BDA", "type": "internal"}).json()
    club = client.post("/api/entities/", json={"name": "Gastro", "type": "internal", "parent_id": bda["id"]}).json()
    client.post("/api/transactions/", json={"date": "2025-10-01", "label": "dotation", "amount": 20000,
                                             "from_entity_id": bda["id"], "to_entity_id": club["id"]})
    data = client.get(f"/api/budget/view?fiscal_year_id={fy['id']}").json()
    gastro = _find_entity(data, club["id"])
    assert gastro["realized_income"] == 20000
    assert gastro["realized_expense"] == 0


def test_view_hierarchy_groups_children(client):
    fy = _make_fy(client)
    parent = client.post("/api/entities/", json={"name": "Pôles", "type": "internal"}).json()
    child = client.post("/api/entities/", json={"name": "Pôle Musique", "type": "internal", "parent_id": parent["id"]}).json()
    data = client.get(f"/api/budget/view?fiscal_year_id={fy['id']}").json()
    root = next((g for g in data["groups"] if g["entity_id"] == parent["id"]), None)
    assert root is not None
    assert child["id"] in [c["entity_id"] for c in root["children"]]
    # l'enfant n'apparaît pas comme racine
    assert all(g["entity_id"] != child["id"] for g in data["groups"])


def test_view_group_aggregates_children(client):
    fy = _make_fy(client)
    parent = client.post("/api/entities/", json={"name": "Pôles", "type": "internal"}).json()
    child = client.post("/api/entities/", json={"name": "Comédie", "type": "internal", "parent_id": parent["id"]}).json()
    ext = client.post("/api/entities/", json={"name": "Ext", "type": "external"}).json()
    client.post("/api/transactions/", json={"date": "2025-10-01", "label": "achat", "amount": 10000,
                                             "from_entity_id": child["id"], "to_entity_id": ext["id"]})
    data = client.get(f"/api/budget/view?fiscal_year_id={fy['id']}").json()
    root = next(g for g in data["groups"] if g["entity_id"] == parent["id"])
    assert root["realized_expense"] == 10000   # le parent agrège la dépense de l'enfant


def test_view_category_split(client):
    fy = _make_fy(client)
    e = client.post("/api/entities/", json={"name": "Club", "type": "internal"}).json()
    ext = client.post("/api/entities/", json={"name": "Ext", "type": "external"}).json()
    cat = client.post("/api/categories/", json={"name": "Concerts"}).json()
    client.post(f"/api/budget/fiscal-years/{fy['id']}/allocations",
                json={"entity_id": e["id"], "category_id": cat["id"], "amount": 50000, "direction": "expense"})
    client.post(f"/api/budget/fiscal-years/{fy['id']}/allocations",
                json={"entity_id": e["id"], "category_id": cat["id"], "amount": 20000, "direction": "income"})
    client.post("/api/transactions/", json={"date": "2025-10-15", "label": "salle", "amount": 15000,
                                             "from_entity_id": e["id"], "to_entity_id": ext["id"], "category_id": cat["id"]})
    client.post("/api/transactions/", json={"date": "2025-11-10", "label": "billets", "amount": 8000,
                                             "from_entity_id": ext["id"], "to_entity_id": e["id"], "category_id": cat["id"]})
    data = client.get(f"/api/budget/view?fiscal_year_id={fy['id']}").json()
    club = _find_entity(data, e["id"])
    concerts = next(c for c in club["categories"] if c["category_id"] == cat["id"])
    assert concerts["allocated_expense"] == 50000
    assert concerts["allocated_income"] == 20000
    assert concerts["realized_expense"] == 15000
    assert concerts["realized_income"] == 8000
    assert club["allocated_expense"] == 50000
    assert club["allocated_income"] == 20000


def test_view_n1_split(client):
    fy_prev = _make_fy(client, "2024-2025", "2024-09-01")
    e = client.post("/api/entities/", json={"name": "Club", "type": "internal"}).json()
    ext = client.post("/api/entities/", json={"name": "Ext", "type": "external"}).json()
    client.post("/api/transactions/", json={"date": "2024-10-15", "label": "dep", "amount": 10000,
                                             "from_entity_id": e["id"], "to_entity_id": ext["id"]})
    client.post("/api/transactions/", json={"date": "2024-11-01", "label": "rec", "amount": 4000,
                                             "from_entity_id": ext["id"], "to_entity_id": e["id"]})
    _close_fy(client, fy_prev["id"], "2025-08-31")
    fy = _make_fy(client, "2025-2026", "2025-09-01")
    data = client.get(f"/api/budget/view?fiscal_year_id={fy['id']}").json()
    club = _find_entity(data, e["id"])
    assert club["realized_expense_n1"] == 10000
    assert club["realized_income_n1"] == 4000


# ─── Hiérarchie de catégories dépliable ──────────────────────────────────────

def test_view_category_tree_nested(client):
    """Les catégories sont renvoyées en arbre (parent -> sous-catégories) avec agrégation."""
    fy = _make_fy(client)
    club = client.post("/api/entities/", json={"name": "Club", "type": "internal"}).json()
    ext = client.post("/api/entities/", json={"name": "Ext", "type": "external"}).json()
    parent = client.post("/api/categories/", json={"name": "Spectacles"}).json()
    child = client.post("/api/categories/", json={"name": "Concerts", "parent_id": parent["id"]}).json()

    client.post(f"/api/budget/fiscal-years/{fy['id']}/allocations",
                json={"entity_id": club["id"], "category_id": child["id"], "amount": 50000, "direction": "expense"})
    client.post("/api/transactions/", json={"date": "2025-10-15", "label": "salle", "amount": 15000,
                                             "from_entity_id": club["id"], "to_entity_id": ext["id"], "category_id": child["id"]})

    data = client.get(f"/api/budget/view?fiscal_year_id={fy['id']}").json()
    club_node = next(g for g in data["groups"] if g["entity_id"] == club["id"])
    roots = club_node["categories"]

    # La racine d'affichage est la catégorie parente, qui agrège son enfant.
    spect = next(c for c in roots if c["category_id"] == parent["id"])
    assert spect["is_leaf"] is False
    assert spect["parent_id"] is None
    assert spect["allocated_expense"] == 50000
    assert spect["realized_expense"] == 15000
    assert child["id"] in [k["category_id"] for k in spect["children"]]
    # La sous-catégorie n'apparaît pas comme racine.
    assert all(c["category_id"] != child["id"] for c in roots)

    concerts = next(k for k in spect["children"] if k["category_id"] == child["id"])
    assert concerts["is_leaf"] is True
    assert concerts["parent_id"] == parent["id"]
    assert concerts["allocated_expense"] == 50000
    assert concerts["realized_expense"] == 15000

    # Pas de double comptage : le total entité reste le réel des transactions.
    assert club_node["realized_expense"] == 15000


# ─── Pré-remplissage depuis le réel N-1 ──────────────────────────────────────

def test_seed_from_realized_creates_allocations(client):
    fy_prev = _make_fy(client, "2024-2025", "2024-09-01")
    club = client.post("/api/entities/", json={"name": "Club", "type": "internal"}).json()
    ext = client.post("/api/entities/", json={"name": "Ext", "type": "external"}).json()
    food = client.post("/api/categories/", json={"name": "Food"}).json()
    # Réel N-1 catégorisé (pendant que fy_prev est ouvert).
    client.post("/api/transactions/", json={"date": "2024-10-15", "label": "dep", "amount": 10000,
                                             "from_entity_id": club["id"], "to_entity_id": ext["id"], "category_id": food["id"]})
    client.post("/api/transactions/", json={"date": "2024-11-01", "label": "rec", "amount": 4000,
                                             "from_entity_id": ext["id"], "to_entity_id": club["id"], "category_id": food["id"]})
    # Réel N-1 SANS catégorie -> doit être ignoré (pas d'enveloppe globale).
    client.post("/api/transactions/", json={"date": "2024-12-01", "label": "divers", "amount": 9999,
                                             "from_entity_id": club["id"], "to_entity_id": ext["id"]})
    _close_fy(client, fy_prev["id"], "2025-08-31")
    fy = _make_fy(client, "2025-2026", "2025-09-01")

    r = client.post(f"/api/budget/fiscal-years/{fy['id']}/seed-from-realized")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created"] == 2
    assert body["source_fiscal_year_id"] == fy_prev["id"]

    allocs = client.get(f"/api/budget/fiscal-years/{fy['id']}/allocations").json()
    by_dir = {(a["category_id"], a["direction"]): a["amount"] for a in allocs}
    assert by_dir[(food["id"], "expense")] == 10000   # montant exact, au centime
    assert by_dir[(food["id"], "income")] == 4000
    assert all(a["category_id"] is not None for a in allocs)   # aucune enveloppe globale


def test_seed_from_realized_fills_only_empty(client):
    fy_prev = _make_fy(client, "2024-2025", "2024-09-01")
    club = client.post("/api/entities/", json={"name": "Club", "type": "internal"}).json()
    ext = client.post("/api/entities/", json={"name": "Ext", "type": "external"}).json()
    food = client.post("/api/categories/", json={"name": "Food"}).json()
    client.post("/api/transactions/", json={"date": "2024-10-15", "label": "dep", "amount": 10000,
                                             "from_entity_id": club["id"], "to_entity_id": ext["id"], "category_id": food["id"]})
    client.post("/api/transactions/", json={"date": "2024-11-01", "label": "rec", "amount": 4000,
                                             "from_entity_id": ext["id"], "to_entity_id": club["id"], "category_id": food["id"]})
    _close_fy(client, fy_prev["id"], "2025-08-31")
    fy = _make_fy(client, "2025-2026", "2025-09-01")
    # Saisie manuelle préalable de la dépense Food.
    client.post(f"/api/budget/fiscal-years/{fy['id']}/allocations",
                json={"entity_id": club["id"], "category_id": food["id"], "amount": 12345, "direction": "expense"})

    r = client.post(f"/api/budget/fiscal-years/{fy['id']}/seed-from-realized")
    assert r.status_code == 200
    assert r.json()["created"] == 1   # seule la recette manquante est créée

    allocs = client.get(f"/api/budget/fiscal-years/{fy['id']}/allocations").json()
    by_dir = {(a["category_id"], a["direction"]): a["amount"] for a in allocs}
    assert by_dir[(food["id"], "expense")] == 12345   # préservé
    assert by_dir[(food["id"], "income")] == 4000      # pré-rempli


def test_seed_from_realized_404(client):
    r = client.post("/api/budget/fiscal-years/999/seed-from-realized")
    assert r.status_code == 404


def test_seed_from_realized_no_previous_returns_400(client):
    fy = _make_fy(client, "2025-2026", "2025-09-01")
    r = client.post(f"/api/budget/fiscal-years/{fy['id']}/seed-from-realized")
    assert r.status_code == 400
    assert "précédent" in r.json()["detail"].lower()
