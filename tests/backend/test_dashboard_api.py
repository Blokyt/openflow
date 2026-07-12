import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import pytest

def test_get_available_widgets(client):
    response = client.get("/api/dashboard/widgets")
    assert response.status_code == 200
    widgets = response.json()
    assert isinstance(widgets, list)
    ids = [w["id"] for w in widgets]
    assert "current_balance" in ids

def test_get_layout(client):
    response = client.get("/api/dashboard/layout")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_save_layout(client):
    layout = [
        {"widget_id": "current_balance", "module_id": "dashboard", "position_x": 0, "position_y": 0, "size": "quarter", "visible": True},
    ]
    response = client.put("/api/dashboard/layout", json=layout)
    assert response.status_code == 200
    saved = client.get("/api/dashboard/layout").json()
    assert len(saved) >= 1

def test_get_summary(client):
    response = client.get("/api/dashboard/summary")
    assert response.status_code == 200
    data = response.json()
    assert "balance" in data
    assert "total_income" in data
    assert "total_expenses" in data


def test_summary_filters_by_period(client):
    # Default injected pair is internal -> external, so both count as global expenses.
    assert client.post("/api/transactions/", json={"date": "2025-03-15", "label": "in-period", "amount": 5000}).status_code == 201
    assert client.post("/api/transactions/", json={"date": "2020-01-01", "label": "out-period", "amount": 3000}).status_code == 201

    full = client.get("/api/dashboard/summary").json()
    assert full["total_expenses"] == 8000
    assert full["transaction_count"] == 2

    scoped = client.get("/api/dashboard/summary", params={"date_from": "2025-01-01", "date_to": "2025-12-31"}).json()
    assert scoped["total_expenses"] == 5000
    assert scoped["transaction_count"] == 1
    # "Solde actuel" stays the real current balance, independent of the period.
    assert scoped["balance"] == full["balance"]


def test_recent_filters_by_period(client):
    client.post("/api/transactions/", json={"date": "2025-06-01", "label": "recent-in", "amount": 4000})
    client.post("/api/transactions/", json={"date": "2019-06-01", "label": "recent-out", "amount": 2000})
    recent = client.get("/api/dashboard/recent", params={"date_from": "2025-01-01", "date_to": "2025-12-31"}).json()
    labels = [t["label"] for t in recent]
    assert "recent-in" in labels
    assert "recent-out" not in labels


# ─── Périmètre sous-entités (include_children) ───────────────────────────────

def _setup_tree(client):
    """BDA (racine interne) > Gastro (enfant interne) ; Fournisseur externe.

    Transactions :
      - ext -> BDA      200000 (recette du groupe)
      - Gastro -> ext    30000 (dépense du groupe, catégorisée)
      - BDA -> Gastro    50000 (virement interne au groupe : neutre en périmètre)
    """
    bda = client.post("/api/entities/", json={"name": "BDA", "type": "internal"}).json()
    gastro = client.post("/api/entities/", json={
        "name": "Gastro", "type": "internal", "parent_id": bda["id"]
    }).json()
    ext = client.post("/api/entities/", json={"name": "Fournisseur", "type": "external"}).json()
    cat = client.post("/api/categories/", json={"name": "Courses", "color": "#123456"}).json()

    client.post("/api/transactions/", json={
        "date": "2025-06-01", "label": "Don", "amount": 200000,
        "from_entity_id": ext["id"], "to_entity_id": bda["id"],
    })
    client.post("/api/transactions/", json={
        "date": "2025-06-15", "label": "Achat", "amount": 30000, "category_id": cat["id"],
        "from_entity_id": gastro["id"], "to_entity_id": ext["id"],
    })
    client.post("/api/transactions/", json={
        "date": "2025-06-10", "label": "Dotation", "amount": 50000, "category_id": cat["id"],
        "from_entity_id": bda["id"], "to_entity_id": gastro["id"],
    })
    return bda, gastro, ext


def test_summary_include_children_consolidates_subtree(client):
    bda, gastro, ext = _setup_tree(client)
    consolidated = client.get(f"/api/entities/{bda['id']}/consolidated").json()

    dash = client.get("/api/dashboard/summary", params={
        "entity_id": bda["id"], "include_children": "true",
    }).json()
    # Solde consolidé (propre + descendants), pas le solde propre.
    assert dash["balance"] == consolidated["consolidated_balance"]
    # Recettes/dépenses = flux traversant la frontière du sous-arbre uniquement :
    # le virement interne BDA -> Gastro ne compte ni en recette ni en dépense.
    assert dash["total_income"] == 200000
    assert dash["total_expenses"] == 30000
    # Le virement interne touche le sous-arbre : il reste compté comme mouvement.
    assert dash["transaction_count"] == 3


def test_summary_without_include_children_stays_own_scope(client):
    bda, gastro, ext = _setup_tree(client)
    own = client.get(f"/api/entities/{bda['id']}/balance").json()
    dash = client.get("/api/dashboard/summary", params={"entity_id": bda["id"]}).json()
    assert dash["balance"] == own["balance"]


def test_top_categories_include_children_ignores_internal_transfers(client):
    bda, gastro, ext = _setup_tree(client)
    cats = client.get("/api/dashboard/top-categories", params={
        "entity_id": bda["id"], "include_children": "true",
    }).json()
    # Seule la dépense Gastro -> ext (30000) doit apparaître ; la dotation
    # interne BDA -> Gastro (50000, même catégorie) est neutre pour le groupe.
    totals = {c["name"]: c["total"] for c in cats}
    assert totals.get("Courses") == 30000


def test_recent_include_children_covers_subtree(client):
    bda, gastro, ext = _setup_tree(client)
    recent = client.get("/api/dashboard/recent", params={
        "entity_id": bda["id"], "include_children": "true",
    }).json()
    labels = {t["label"] for t in recent}
    assert {"Don", "Achat", "Dotation"} <= labels


def test_timeseries_bounded_to_period(client):
    """Le graphe d'évolution doit pouvoir être borné à un exercice passé."""
    bda, gastro, ext = _setup_tree(client)
    # Activité hors période, plus récente (ne doit pas apparaître dans la fenêtre).
    client.post("/api/transactions/", json={
        "date": "2026-02-01", "label": "Hors période", "amount": 10000,
        "from_entity_id": ext["id"], "to_entity_id": bda["id"],
    })
    series = client.get("/api/dashboard/timeseries", params={
        "entity_id": bda["id"], "include_children": "true",
        "date_from": "2025-05-01", "date_to": "2025-12-31",
    }).json()
    months = [p["month"] for p in series]
    assert months[0] >= "2025-05"
    assert months[-1] <= "2025-12"
    # Solde de fin de période = solde consolidé arrêté au 2025-12 :
    # 200000 - 30000 = 170000 (les références de solde ne sont pas posées ici).
    assert series[-1]["balance"] == 170000
    # Croissance cohérente : juin porte tout le flux de la période.
    by_month = {p["month"]: p["balance"] for p in series}
    assert by_month["2025-06"] == 170000
    assert by_month["2025-05"] == 0


# ─── reference_date / reference_amount sur /summary ──────────────────────────

def test_summary_exposes_reference_date_and_amount(client):
    """/summary expose la date/le montant de référence du solde affiché
    (compute_entity_balance les calcule déjà, ils manquaient à la réponse)."""
    bda = client.post("/api/entities/", json={"name": "BDA", "type": "internal"}).json()
    r = client.put(f"/api/entities/{bda['id']}/balance-ref",
                   json={"reference_date": "2025-09-01", "reference_amount": 50000})
    assert r.status_code == 200, r.text

    dash = client.get("/api/dashboard/summary", params={"entity_id": bda["id"]}).json()
    assert dash["reference_date"] == "2025-09-01"
    assert dash["reference_amount"] == 50000


def test_summary_reference_present_without_entity(client):
    """Sans entity_id (vue globale), les clés reference_date/reference_amount
    sont toujours présentes dans la réponse (None si indisponibles)."""
    data = client.get("/api/dashboard/summary").json()
    assert "reference_date" in data
    assert "reference_amount" in data


def test_summary_reference_matches_consolidated_with_include_children(client):
    """Avec include_children, la référence exposée est celle du solde consolidé."""
    bda, gastro, ext = _setup_tree(client)
    r = client.put(f"/api/entities/{bda['id']}/balance-ref",
                   json={"reference_date": "2025-05-01", "reference_amount": 100000})
    assert r.status_code == 200, r.text

    dash = client.get("/api/dashboard/summary", params={
        "entity_id": bda["id"], "include_children": "true",
    }).json()
    assert dash["reference_date"] == "2025-05-01"
    assert dash["reference_amount"] == 100000


# ─── category_id sur /top-categories ──────────────────────────────────────────

def test_top_categories_exposes_category_id(client):
    """/top-categories expose category_id (clé React stable), en plus de name/color/total."""
    bda, gastro, ext = _setup_tree(client)
    cats = client.get("/api/dashboard/top-categories", params={
        "entity_id": bda["id"], "include_children": "true",
    }).json()
    assert cats, "au moins une catégorie attendue"
    for c in cats:
        assert "category_id" in c
    courses = next(c for c in cats if c["name"] == "Courses")
    assert courses["category_id"] is not None


def test_top_categories_uncategorized_has_null_category_id(client):
    """Une dépense sans catégorie doit exposer category_id = None (pas absent)."""
    ext = client.post("/api/entities/", json={"name": "ExtNC", "type": "external"}).json()
    bda = client.post("/api/entities/", json={"name": "BDANC", "type": "internal"}).json()
    client.post("/api/transactions/", json={
        "date": "2025-06-01", "label": "sans-categorie", "amount": 1500,
        "from_entity_id": bda["id"], "to_entity_id": ext["id"],
    })
    cats = client.get("/api/dashboard/top-categories", params={"entity_id": bda["id"]}).json()
    assert any(c["category_id"] is None for c in cats)
