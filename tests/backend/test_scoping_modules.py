"""Scoping des lectures : dashboard, budget, reports, reimbursements, categories.

Carry-over Task 9 : GET /api/transactions/balance (solde légal global) réservé
à l'admin.
"""
import sqlite3

NOW = "2026-01-01T00:00:00+00:00"


def _seed(db_path):
    """BDA -> (Gastronomine, CCMP), toutes internes, aucune transaction."""
    conn = sqlite3.connect(str(db_path))
    ids = {}

    def entity(name, parent=None):
        cur = conn.execute(
            "INSERT INTO entities (name, type, parent_id, is_default, color, position, created_at, updated_at) "
            "VALUES (?, 'internal', ?, 0, '#000', 0, ?, ?)", (name, parent, NOW, NOW))
        ids[name] = cur.lastrowid
        return cur.lastrowid

    bda = entity("BDA")
    entity("Gastronomine", bda)
    entity("CCMP", bda)
    conn.commit(); conn.close()
    return ids


def _seed_with_flows(db_path):
    """Comme _seed, plus une entité externe et une transaction par club interne
    (nécessaire pour les rapports/remboursements, qui ont besoin de flux réels)."""
    conn = sqlite3.connect(str(db_path))
    ids = {}

    def entity(name, typ="internal", parent=None):
        cur = conn.execute(
            "INSERT INTO entities (name, type, parent_id, is_default, color, position, created_at, updated_at) "
            "VALUES (?, ?, ?, 0, '#000', 0, ?, ?)", (name, typ, parent, NOW, NOW))
        ids[name] = cur.lastrowid
        return cur.lastrowid

    bda = entity("BDA")
    entity("Gastronomine", parent=bda)
    entity("CCMP", parent=bda)
    ext = entity("Fournisseur", typ="external")

    def tx(label, frm, to, amount=1000):
        cur = conn.execute(
            "INSERT INTO transactions (date, label, description, amount, category_id, contact_id, "
            "created_by, created_at, updated_at, from_entity_id, to_entity_id) "
            "VALUES ('2026-01-15', ?, '', ?, NULL, NULL, '', ?, ?, ?, ?)",
            (label, amount, NOW, NOW, frm, to))
        ids[f"tx_{label}"] = cur.lastrowid
        return cur.lastrowid

    tx("gastro", ext, ids["Gastronomine"])
    tx("ccmp", ext, ids["CCMP"])

    def reimb(person, tx_key, amount=500):
        cur = conn.execute(
            "INSERT INTO reimbursements (transaction_id, person_name, amount, status, notes, created_at, updated_at) "
            "VALUES (?, ?, ?, 'pending', '', ?, ?)",
            (ids[f"tx_{tx_key}"], person, amount, NOW, NOW))
        ids[f"reimb_{person}"] = cur.lastrowid

    reimb("Alice", "gastro")
    reimb("Bob", "ccmp")

    conn.commit(); conn.close()
    return ids


# ─── dashboard ───────────────────────────────────────────────────────────────

def test_dashboard_requires_entity_for_non_admin(client_and_db, login_as):
    _, db_path = client_and_db
    ids = _seed(db_path)
    tres = login_as("d1@t.fr", roles=[(ids["Gastronomine"], "treasurer")])
    # Sans entity_id : refusé pour un non-admin.
    r = tres.get("/api/dashboard/summary")
    assert r.status_code in (400, 403)
    # Dans le périmètre : OK.
    assert tres.get(f"/api/dashboard/summary?entity_id={ids['Gastronomine']}").status_code == 200
    # Hors périmètre : 403.
    assert tres.get(f"/api/dashboard/summary?entity_id={ids['CCMP']}").status_code == 403


def test_dashboard_timeseries_scoped(client_and_db, login_as):
    _, db_path = client_and_db
    ids = _seed(db_path)
    tres = login_as("d2@t.fr", roles=[(ids["Gastronomine"], "treasurer")])
    assert tres.get("/api/dashboard/timeseries").status_code in (400, 403)
    assert tres.get(f"/api/dashboard/timeseries?entity_id={ids['Gastronomine']}").status_code == 200
    assert tres.get(f"/api/dashboard/timeseries?entity_id={ids['CCMP']}").status_code == 403


def test_dashboard_top_categories_scoped(client_and_db, login_as):
    _, db_path = client_and_db
    ids = _seed(db_path)
    tres = login_as("d3@t.fr", roles=[(ids["Gastronomine"], "treasurer")])
    assert tres.get("/api/dashboard/top-categories").status_code in (400, 403)
    assert tres.get(f"/api/dashboard/top-categories?entity_id={ids['Gastronomine']}").status_code == 200
    assert tres.get(f"/api/dashboard/top-categories?entity_id={ids['CCMP']}").status_code == 403


def test_dashboard_recent_scoped(client_and_db, login_as):
    _, db_path = client_and_db
    ids = _seed(db_path)
    tres = login_as("d4@t.fr", roles=[(ids["Gastronomine"], "treasurer")])
    assert tres.get("/api/dashboard/recent").status_code in (400, 403)
    assert tres.get(f"/api/dashboard/recent?entity_id={ids['Gastronomine']}").status_code == 200
    assert tres.get(f"/api/dashboard/recent?entity_id={ids['CCMP']}").status_code == 403


def test_dashboard_widgets_and_layout_open_to_all(client_and_db, login_as):
    """Pas de notion d'entity_id (config UI globale, pas de données financières) :
    reste accessible à tout connecté, sans restriction de périmètre."""
    _, db_path = client_and_db
    ids = _seed(db_path)
    viewer = login_as("d5@t.fr", roles=[(ids["Gastronomine"], "viewer")])
    assert viewer.get("/api/dashboard/widgets").status_code == 200
    assert viewer.get("/api/dashboard/layout").status_code == 200


def test_dashboard_admin_unchanged(client_and_db):
    client, db_path = client_and_db
    ids = _seed(db_path)
    assert client.get("/api/dashboard/summary").status_code == 200
    assert client.get(f"/api/dashboard/summary?entity_id={ids['CCMP']}").status_code == 200


# ─── budget ──────────────────────────────────────────────────────────────────

def test_budget_view_scoped(client_and_db, login_as):
    client, db_path = client_and_db
    ids = _seed(db_path)
    fy = client.post("/api/budget/fiscal-years",
                     json={"name": "2026", "start_date": "2026-01-01"}).json()
    tres = login_as("b1@t.fr", roles=[(ids["Gastronomine"], "treasurer")])
    r = tres.get(f"/api/budget/view?fiscal_year_id={fy['id']}")
    assert r.status_code == 200
    entity_ids = {e["entity_id"] for e in r.json()["entities"]}
    assert ids["Gastronomine"] in entity_ids
    assert ids["CCMP"] not in entity_ids and ids["BDA"] not in entity_ids


def test_fiscal_years_readable_by_all(client_and_db, login_as):
    _, db_path = client_and_db
    ids = _seed(db_path)
    viewer = login_as("f1@t.fr", roles=[(ids["Gastronomine"], "viewer")])
    assert viewer.get("/api/budget/fiscal-years").status_code == 200


def _walk_entity_ids(nodes):
    """Parcourt récursivement un arbre `groups` et yield chaque entity_id (tous niveaux)."""
    for n in nodes:
        yield n["entity_id"]
        yield from _walk_entity_ids(n["children"])


def test_budget_view_groups_and_totals_scoped(client_and_db, login_as):
    """CRITICAL : `groups` (arbre) et `totals` (agrégat) doivent être élagués au
    périmètre, pas seulement `entities` (liste plate)."""
    client, db_path = client_and_db
    ids = _seed(db_path)
    fy = client.post("/api/budget/fiscal-years",
                     json={"name": "2026g", "start_date": "2026-01-01"}).json()
    # Allocation hors périmètre (BDA, racine) et dans le périmètre (Gastronomine).
    assert client.post(f"/api/budget/fiscal-years/{fy['id']}/allocations",
                       json={"entity_id": ids["BDA"], "direction": "expense",
                             "amount": 10000}).status_code == 201
    assert client.post(f"/api/budget/fiscal-years/{fy['id']}/allocations",
                       json={"entity_id": ids["Gastronomine"], "direction": "expense",
                             "amount": 3000}).status_code == 201

    tres = login_as("bv1@t.fr", roles=[(ids["Gastronomine"], "treasurer")])
    r = tres.get(f"/api/budget/view?fiscal_year_id={fy['id']}")
    assert r.status_code == 200
    data = r.json()

    seen = set(_walk_entity_ids(data["groups"]))
    assert ids["BDA"] not in seen
    assert ids["CCMP"] not in seen
    assert ids["Gastronomine"] in seen
    # Le total ne doit refléter QUE le sous-arbre du rôle (3000), pas le
    # total global (13000, incluant BDA hors périmètre).
    assert data["totals"]["allocated_expense"] == 3000

    # Admin : chemin strictement inchangé (BDA racine, total global).
    admin_data = client.get(f"/api/budget/view?fiscal_year_id={fy['id']}").json()
    admin_seen = set(_walk_entity_ids(admin_data["groups"]))
    assert ids["BDA"] in admin_seen and ids["CCMP"] in admin_seen
    assert admin_data["totals"]["allocated_expense"] == 13000


def test_budget_view_zero_roles_empty(client_and_db, login_as):
    client, db_path = client_and_db
    ids = _seed(db_path)
    fy = client.post("/api/budget/fiscal-years",
                     json={"name": "2026z", "start_date": "2026-01-01"}).json()
    nouser = login_as("bv2@t.fr", roles=[])
    r = nouser.get(f"/api/budget/view?fiscal_year_id={fy['id']}")
    assert r.status_code == 200
    data = r.json()
    assert data["entities"] == []
    assert data["groups"] == []
    assert data["totals"]["allocated_expense"] == 0
    assert data["totals"]["realized_expense"] == 0
    assert data["totals"]["realized_net"] == 0
    assert data["totals"]["remaining"] == 0


def test_budget_view_categories_scoped(client_and_db, login_as):
    client, db_path = client_and_db
    ids = _seed(db_path)
    fy = client.post("/api/budget/fiscal-years",
                     json={"name": "2026c", "start_date": "2026-01-01"}).json()
    tres = login_as("bc1@t.fr", roles=[(ids["Gastronomine"], "treasurer")])
    base = f"/api/budget/view/categories?fiscal_year_id={fy['id']}"
    r = tres.get(base)
    assert r.status_code == 400
    assert r.json()["detail"] == "Une entité est requise pour ce rôle"
    assert tres.get(f"{base}&entity_id={ids['CCMP']}").status_code == 403
    assert tres.get(f"{base}&entity_id={ids['Gastronomine']}").status_code == 200
    # Admin : inchangé, y compris sans entity_id (vue globale).
    assert client.get(base).status_code == 200


def test_budget_allocations_and_opening_balances_scoped(client_and_db, login_as):
    client, db_path = client_and_db
    ids = _seed(db_path)
    fy = client.post("/api/budget/fiscal-years",
                     json={"name": "2026a", "start_date": "2026-01-01"}).json()
    client.post(f"/api/budget/fiscal-years/{fy['id']}/allocations",
                json={"entity_id": ids["Gastronomine"], "direction": "expense", "amount": 1000})
    client.post(f"/api/budget/fiscal-years/{fy['id']}/allocations",
                json={"entity_id": ids["CCMP"], "direction": "expense", "amount": 2000})
    client.put(f"/api/budget/fiscal-years/{fy['id']}/opening-balances/{ids['Gastronomine']}",
               json={"amount": 500})
    client.put(f"/api/budget/fiscal-years/{fy['id']}/opening-balances/{ids['CCMP']}",
               json={"amount": 700})

    tres = login_as("ba1@t.fr", roles=[(ids["Gastronomine"], "treasurer")])

    allocs = tres.get(f"/api/budget/fiscal-years/{fy['id']}/allocations").json()
    entity_ids = {a["entity_id"] for a in allocs}
    assert ids["Gastronomine"] in entity_ids
    assert ids["CCMP"] not in entity_ids

    obs = tres.get(f"/api/budget/fiscal-years/{fy['id']}/opening-balances").json()
    ob_ids = {o["entity_id"] for o in obs}
    assert ids["Gastronomine"] in ob_ids
    assert ids["CCMP"] not in ob_ids

    # Admin : inchangé (les deux entités remontent).
    admin_allocs = client.get(f"/api/budget/fiscal-years/{fy['id']}/allocations").json()
    assert {a["entity_id"] for a in admin_allocs} == {ids["Gastronomine"], ids["CCMP"]}
    admin_obs = client.get(f"/api/budget/fiscal-years/{fy['id']}/opening-balances").json()
    assert {o["entity_id"] for o in admin_obs} == {ids["Gastronomine"], ids["CCMP"]}


# ─── categories ──────────────────────────────────────────────────────────────

def test_categories_tree_scoped(client_and_db, login_as):
    _, db_path = client_and_db
    ids = _seed(db_path)
    tres = login_as("c1@t.fr", roles=[(ids["Gastronomine"], "treasurer")])
    assert tres.get("/api/categories/").status_code == 200
    assert tres.get(f"/api/categories/tree?entity_id={ids['Gastronomine']}&include_children=true").status_code == 200
    assert tres.get(f"/api/categories/tree?entity_id={ids['CCMP']}").status_code == 403
    assert tres.get("/api/categories/tree").status_code == 403


# ─── reimbursements ──────────────────────────────────────────────────────────

def test_reimbursements_scoped(client_and_db, login_as):
    _, db_path = client_and_db
    ids = _seed(db_path)
    tres = login_as("r1@t.fr", roles=[(ids["Gastronomine"], "treasurer")])
    r = tres.get("/api/reimbursements/")
    assert r.status_code == 200
    # Le seed ne crée aucun remboursement : liste vide, mais l'endpoint répond.
    assert r.json() == []


def test_reimbursements_list_filtered_to_scope(client_and_db, login_as):
    _, db_path = client_and_db
    ids = _seed_with_flows(db_path)
    tres = login_as("r2@t.fr", roles=[(ids["Gastronomine"], "treasurer")])
    r = tres.get("/api/reimbursements/")
    assert r.status_code == 200
    names = {item["person_name"] for item in r.json()}
    assert "Alice" in names
    assert "Bob" not in names


def test_reimbursements_detail_scoped(client_and_db, login_as):
    _, db_path = client_and_db
    ids = _seed_with_flows(db_path)
    tres = login_as("r3@t.fr", roles=[(ids["Gastronomine"], "treasurer")])
    assert tres.get(f"/api/reimbursements/{ids['reimb_Alice']}").status_code == 200
    assert tres.get(f"/api/reimbursements/{ids['reimb_Bob']}").status_code == 403


def test_reimbursements_summary_scoped(client_and_db, login_as):
    client, db_path = client_and_db
    ids = _seed_with_flows(db_path)
    tres = login_as("rsum1@t.fr", roles=[(ids["Gastronomine"], "treasurer")])
    r = tres.get("/api/reimbursements/summary")
    assert r.status_code == 200
    names = {item["person_name"] for item in r.json()}
    assert "Alice" in names
    assert "Bob" not in names

    # Admin : inchangé, les deux remontent.
    admin_names = {item["person_name"] for item in client.get("/api/reimbursements/summary").json()}
    assert admin_names == {"Alice", "Bob"}


# ─── reports ─────────────────────────────────────────────────────────────────

def test_reports_compte_resultat_scoped(client_and_db, login_as):
    _, db_path = client_and_db
    ids = _seed_with_flows(db_path)
    tres = login_as("rp1@t.fr", roles=[(ids["Gastronomine"], "treasurer")])
    base = "/api/reports/compte-resultat?start_date=2026-01-01&end_date=2026-12-31"
    assert tres.get(base).status_code in (400, 403)
    assert tres.get(f"{base}&entity_id={ids['Gastronomine']}").status_code == 200
    assert tres.get(f"{base}&entity_id={ids['CCMP']}").status_code == 403


def test_reports_compte_resultat_pdf_scoped(client_and_db, login_as):
    _, db_path = client_and_db
    ids = _seed_with_flows(db_path)
    tres = login_as("rp2@t.fr", roles=[(ids["Gastronomine"], "treasurer")])
    base = "/api/reports/compte-resultat/pdf?start_date=2026-01-01&end_date=2026-12-31"
    assert tres.get(base).status_code in (400, 403)
    assert tres.get(f"{base}&entity_id={ids['Gastronomine']}").status_code == 200
    assert tres.get(f"{base}&entity_id={ids['CCMP']}").status_code == 403


def test_reports_bilan_scoped(client_and_db, login_as):
    client, db_path = client_and_db
    ids = _seed_with_flows(db_path)
    fy = client.post("/api/budget/fiscal-years", json={"name": "2026", "start_date": "2026-01-01"}).json()
    tres = login_as("rp3@t.fr", roles=[(ids["Gastronomine"], "treasurer")])
    # entity_id absent : refusé (le bilan sans entity_id est une vue globale).
    assert tres.get(f"/api/reports/bilan?fiscal_year_id={fy['id']}").status_code in (400, 403)
    # entity_id fourni mais fiscal_year_id absent : le bilan instantané ignore
    # entity_id (agrégat global) -> refusé pour un non-admin.
    assert tres.get(f"/api/reports/bilan?entity_id={ids['Gastronomine']}").status_code in (400, 403)
    assert tres.get(f"/api/reports/bilan?fiscal_year_id={fy['id']}&entity_id={ids['Gastronomine']}").status_code == 200
    assert tres.get(f"/api/reports/bilan?fiscal_year_id={fy['id']}&entity_id={ids['CCMP']}").status_code == 403


def test_reports_bilan_pdf_scoped(client_and_db, login_as):
    client, db_path = client_and_db
    ids = _seed_with_flows(db_path)
    fy = client.post("/api/budget/fiscal-years", json={"name": "2026b", "start_date": "2026-01-01"}).json()
    tres = login_as("rp4@t.fr", roles=[(ids["Gastronomine"], "treasurer")])
    assert tres.get(f"/api/reports/bilan/pdf?fiscal_year_id={fy['id']}").status_code in (400, 403)
    assert tres.get(f"/api/reports/bilan/pdf?fiscal_year_id={fy['id']}&entity_id={ids['Gastronomine']}").status_code == 200
    assert tres.get(f"/api/reports/bilan/pdf?fiscal_year_id={fy['id']}&entity_id={ids['CCMP']}").status_code == 403


def test_reports_accruals_scoped(client_and_db, login_as):
    client, db_path = client_and_db
    ids = _seed_with_flows(db_path)
    fy = client.post("/api/budget/fiscal-years",
                     json={"name": "2026acc", "start_date": "2026-01-01"}).json()
    client.post("/api/reports/accruals", json={
        "fiscal_year_id": fy["id"], "kind": "creance", "amount": 1000,
        "label": "Creance Gastro", "entity_id": ids["Gastronomine"],
    })
    client.post("/api/reports/accruals", json={
        "fiscal_year_id": fy["id"], "kind": "creance", "amount": 2000,
        "label": "Creance CCMP", "entity_id": ids["CCMP"],
    })
    client.post("/api/reports/accruals", json={
        "fiscal_year_id": fy["id"], "kind": "dette", "amount": 500,
        "label": "Dette globale",
    })  # entity_id absent (niveau global)

    tres = login_as("racc1@t.fr", roles=[(ids["Gastronomine"], "treasurer")])
    base = f"/api/reports/accruals?fiscal_year_id={fy['id']}"
    assert tres.get(base).status_code == 400
    assert tres.get(f"{base}&entity_id={ids['CCMP']}").status_code == 403
    r = tres.get(f"{base}&entity_id={ids['Gastronomine']}")
    assert r.status_code == 200
    labels = {a["label"] for a in r.json()}
    assert "Creance Gastro" in labels
    assert "Creance CCMP" not in labels
    # entity_id NULL exclu par défaut pour un non-admin (deny-by-default).
    assert "Dette globale" not in labels

    # Admin : inchangé, toutes les lignes remontent (y compris entity_id NULL).
    admin_labels = {a["label"] for a in client.get(base).json()}
    assert admin_labels == {"Creance Gastro", "Creance CCMP", "Dette globale"}


def test_reports_catalog_endpoints_open_to_all(client_and_db, login_as):
    """Plan comptable et mapping catégorie->compte : catalogue global (comme
    /api/categories/ et /api/tiers/), pas de donnée financière par entité."""
    _, db_path = client_and_db
    ids = _seed(db_path)
    viewer = login_as("rp5@t.fr", roles=[(ids["Gastronomine"], "viewer")])
    assert viewer.get("/api/reports/accounts").status_code == 200
    assert viewer.get("/api/reports/mapping").status_code == 200
    assert viewer.get("/api/reports/mapping/suggestions").status_code == 200


# ─── carry-over Task 9 : transactions/balance réservé admin ────────────────

def test_transactions_balance_admin_only(client_and_db, login_as):
    client, db_path = client_and_db
    ids = _seed(db_path)
    tres = login_as("tb1@t.fr", roles=[(ids["Gastronomine"], "treasurer")])
    assert tres.get("/api/transactions/balance").status_code == 403
    assert client.get("/api/transactions/balance").status_code == 200
