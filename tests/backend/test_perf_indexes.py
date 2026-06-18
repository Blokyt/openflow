"""Lot F - Tests de performance : index SQL et dé-N+1 de get_budget_view.

Ces tests vérifient :
1. Que les 4 index attendus existent après la migration 1.3.0 du module transactions.
2. Que get_budget_view renvoie les mêmes totaux qu'attendu après la refactorisation
   des lookups agrégés (cohérence préservée).
"""
import os
import sys
import sqlite3

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


# ─── Tests des index SQL ──────────────────────────────────────────────────────

def test_index_on_date_exists(client_and_db):
    """idx_tx_date doit exister sur la table transactions."""
    _, db_path = client_and_db
    conn = sqlite3.connect(str(db_path))
    try:
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='transactions'"
        ).fetchall()}
    finally:
        conn.close()
    assert "idx_tx_date" in names, f"Index idx_tx_date absent. Index trouvés : {names}"


def test_index_on_from_entity_id_exists(client_and_db):
    """idx_tx_from doit exister sur la table transactions."""
    _, db_path = client_and_db
    conn = sqlite3.connect(str(db_path))
    try:
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='transactions'"
        ).fetchall()}
    finally:
        conn.close()
    assert "idx_tx_from" in names, f"Index idx_tx_from absent. Index trouvés : {names}"


def test_index_on_to_entity_id_exists(client_and_db):
    """idx_tx_to doit exister sur la table transactions."""
    _, db_path = client_and_db
    conn = sqlite3.connect(str(db_path))
    try:
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='transactions'"
        ).fetchall()}
    finally:
        conn.close()
    assert "idx_tx_to" in names, f"Index idx_tx_to absent. Index trouvés : {names}"


def test_index_on_category_id_exists(client_and_db):
    """idx_tx_category doit exister sur la table transactions."""
    _, db_path = client_and_db
    conn = sqlite3.connect(str(db_path))
    try:
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='transactions'"
        ).fetchall()}
    finally:
        conn.close()
    assert "idx_tx_category" in names, f"Index idx_tx_category absent. Index trouvés : {names}"


def test_all_four_indexes_via_pragma(client_and_db):
    """PRAGMA index_list confirme les 4 index en une seule vérification."""
    _, db_path = client_and_db
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute("PRAGMA index_list(transactions)").fetchall()
        # Les colonnes de PRAGMA index_list sont : seq, name, unique, origin, partial
        names = {r[1] for r in rows}
    finally:
        conn.close()
    expected = {"idx_tx_date", "idx_tx_from", "idx_tx_to", "idx_tx_category"}
    missing = expected - names
    assert not missing, f"Index manquants : {missing}. Présents : {names}"


# ─── Test de cohérence après dé-N+1 ──────────────────────────────────────────

def test_budget_view_totals_coherence_multi_entities(client):
    """get_budget_view renvoie les mêmes totaux qu'attendu avec plusieurs entités/catégories.

    Ce test vérifie que la refactorisation des lookups agrégés n'a pas cassé
    les calculs de réalisé (dé-N+1 ou memoïsation).
    """
    # Crée un exercice ouvert
    fy = client.post("/api/budget/fiscal-years", json={
        "name": "2025-2026", "start_date": "2025-09-01",
    }).json()
    assert fy.get("id"), f"Exercice non créé : {fy}"

    # Deux entités internes
    e1 = client.post("/api/entities/", json={"name": "ClubA", "type": "internal"}).json()
    e2 = client.post("/api/entities/", json={"name": "ClubB", "type": "internal"}).json()
    # Entité externe (tierce)
    ext = client.post("/api/entities/", json={"name": "Fournisseur", "type": "external"}).json()

    # Trois catégories
    c1 = client.post("/api/categories/", json={"name": "Nourriture"}).json()
    c2 = client.post("/api/categories/", json={"name": "Transport"}).json()
    c3 = client.post("/api/categories/", json={"name": "Matériel"}).json()

    # Allocations (en centimes)
    client.post(f"/api/budget/fiscal-years/{fy['id']}/allocations", json={
        "entity_id": e1["id"], "category_id": c1["id"], "amount": 50000,  # 500 €
    })
    client.post(f"/api/budget/fiscal-years/{fy['id']}/allocations", json={
        "entity_id": e1["id"], "category_id": c2["id"], "amount": 20000,  # 200 €
    })
    client.post(f"/api/budget/fiscal-years/{fy['id']}/allocations", json={
        "entity_id": e2["id"], "category_id": c3["id"], "amount": 30000,  # 300 €
    })

    # Transactions pour e1 (en centimes)
    # Dépense c1 : from e1 -> to ext = -12000
    client.post("/api/transactions/", json={
        "date": "2025-10-15", "label": "repas ClubA", "amount": 12000,
        "from_entity_id": e1["id"], "to_entity_id": ext["id"],
        "category_id": c1["id"],
    })
    # Dépense c2 : from e1 -> to ext = -5000
    client.post("/api/transactions/", json={
        "date": "2025-11-01", "label": "train ClubA", "amount": 5000,
        "from_entity_id": e1["id"], "to_entity_id": ext["id"],
        "category_id": c2["id"],
    })
    # Recette sans catégorie : from ext -> to e1 = +8000
    client.post("/api/transactions/", json={
        "date": "2025-12-01", "label": "subvention ClubA", "amount": 8000,
        "from_entity_id": ext["id"], "to_entity_id": e1["id"],
    })

    # Transactions pour e2 (en centimes)
    # Dépense c3 : from e2 -> to ext = -10000
    client.post("/api/transactions/", json={
        "date": "2025-10-20", "label": "achat ClubB", "amount": 10000,
        "from_entity_id": e2["id"], "to_entity_id": ext["id"],
        "category_id": c3["id"],
    })
    # Recette c3 : from ext -> to e2 = +3000
    client.post("/api/transactions/", json={
        "date": "2025-11-20", "label": "remb ClubB", "amount": 3000,
        "from_entity_id": ext["id"], "to_entity_id": e2["id"],
        "category_id": c3["id"],
    })

    # Transaction hors période (avant start_date) - doit être ignorée dans realized
    client.post("/api/transactions/", json={
        "date": "2025-08-01", "label": "avant", "amount": 99000,
        "from_entity_id": e1["id"], "to_entity_id": ext["id"],
    })

    r = client.get(f"/api/budget/view?fiscal_year_id={fy['id']}")
    assert r.status_code == 200, r.text
    data = r.json()

    club_a = next((x for x in data["entities"] if x["entity_id"] == e1["id"]), None)
    club_b = next((x for x in data["entities"] if x["entity_id"] == e2["id"]), None)
    assert club_a is not None, "ClubA absent de la vue budget"
    assert club_b is not None, "ClubB absent de la vue budget"

    # ClubA : réalisé = -12000 (c1) - 5000 (c2) + 8000 (sans cat) = -9000
    assert round(club_a["realized_total"], 2) == -9000, (
        f"ClubA realized_total attendu -9000, reçu {club_a['realized_total']}"
    )

    # ClubB : réalisé = -10000 (c3 dépense) + 3000 (c3 recette) = -7000
    assert round(club_b["realized_total"], 2) == -7000, (
        f"ClubB realized_total attendu -7000, reçu {club_b['realized_total']}"
    )

    # Catégories de ClubA
    cat_c1 = next((c for c in club_a["categories"] if c["category_id"] == c1["id"]), None)
    cat_c2 = next((c for c in club_a["categories"] if c["category_id"] == c2["id"]), None)
    assert cat_c1 is not None, "Catégorie c1 absente pour ClubA"
    assert cat_c2 is not None, "Catégorie c2 absente pour ClubA"
    assert round(cat_c1["realized"], 2) == -12000, (
        f"ClubA cat c1 realized attendu -12000, reçu {cat_c1['realized']}"
    )
    assert round(cat_c2["realized"], 2) == -5000, (
        f"ClubA cat c2 realized attendu -5000, reçu {cat_c2['realized']}"
    )

    # Catégorie de ClubB
    cat_c3 = next((c for c in club_b["categories"] if c["category_id"] == c3["id"]), None)
    assert cat_c3 is not None, "Catégorie c3 absente pour ClubB"
    assert round(cat_c3["realized"], 2) == -7000, (
        f"ClubB cat c3 realized attendu -7000, reçu {cat_c3['realized']}"
    )

    # Totaux globaux
    # total_allocated = c1(50000) + c2(20000) [ClubA sans global -> sum détail] + c3(30000) [ClubB]
    # allocated_effective pour ClubA = 70000 (pas d'alloc globale, donc sum des catégories)
    # allocated_effective pour ClubB = 30000
    assert round(data["totals"]["allocated"], 2) == 100000, (
        f"Totaux allocated attendu 100000, reçu {data['totals']['allocated']}"
    )
    # total_realized = -9000 + -7000 = -16000
    assert round(data["totals"]["realized"], 2) == -16000, (
        f"Totaux realized attendu -16000, reçu {data['totals']['realized']}"
    )


def test_budget_view_n_minus_1_coherence(client):
    """realized_n_minus_1 est correct après dé-N+1 avec exercice précédent."""
    # Exercice N-1
    fy_prev = client.post("/api/budget/fiscal-years", json={
        "name": "2024-2025", "start_date": "2024-09-01",
    }).json()

    e = client.post("/api/entities/", json={"name": "Club", "type": "internal"}).json()
    ext = client.post("/api/entities/", json={"name": "Ext", "type": "external"}).json()
    cat = client.post("/api/categories/", json={"name": "Repas"}).json()

    # Tx en N-1
    client.post("/api/transactions/", json={
        "date": "2024-10-15", "label": "n-1 cat", "amount": 8000,
        "from_entity_id": e["id"], "to_entity_id": ext["id"],
        "category_id": cat["id"],
    })

    # Clôture N-1 et création N
    client.post(f"/api/budget/fiscal-years/{fy_prev['id']}/close", json={"end_date": "2025-08-31"})
    fy = client.post("/api/budget/fiscal-years", json={
        "name": "2025-2026", "start_date": "2025-09-01",
    }).json()

    # Allocation sur N avec catégorie
    client.post(f"/api/budget/fiscal-years/{fy['id']}/allocations", json={
        "entity_id": e["id"], "category_id": cat["id"], "amount": 15000,
    })

    # Tx en N
    client.post("/api/transactions/", json={
        "date": "2025-10-15", "label": "n cat", "amount": 6000,
        "from_entity_id": e["id"], "to_entity_id": ext["id"],
        "category_id": cat["id"],
    })

    r = client.get(f"/api/budget/view?fiscal_year_id={fy['id']}")
    assert r.status_code == 200, r.text
    data = r.json()

    club = next((x for x in data["entities"] if x["entity_id"] == e["id"]), None)
    assert club is not None

    # realized_n_minus_1 global = -8000 (tx du N-1)
    assert round(club["realized_n_minus_1"], 2) == -8000, (
        f"realized_n_minus_1 global attendu -8000, reçu {club['realized_n_minus_1']}"
    )

    # Catégorie : realized N = -6000, realized_n1 = -8000
    cat_row = next((c for c in club["categories"] if c["category_id"] == cat["id"]), None)
    assert cat_row is not None
    assert round(cat_row["realized"], 2) == -6000, (
        f"Cat realized attendu -6000, reçu {cat_row['realized']}"
    )
    assert round(cat_row["realized_n_minus_1"], 2) == -8000, (
        f"Cat realized_n_minus_1 attendu -8000, reçu {cat_row['realized_n_minus_1']}"
    )
