import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import pytest


@pytest.fixture
def entity_pair(client):
    src = client.post("/api/entities/", json={"name": "Src", "type": "external"}).json()
    dst = client.post("/api/entities/", json={"name": "Dst", "type": "internal"}).json()
    return src["id"], dst["id"]


def test_list_transactions_empty(client):
    response = client.get("/api/transactions/")
    assert response.status_code == 200

def test_create_transaction(client, entity_pair):
    src, dst = entity_pair
    # 45,50 € = 4550 centimes ; sens dépense : from externe -> to interne
    tx = {"date": "2026-01-15", "label": "Achat", "amount": 4550, "from_entity_id": src, "to_entity_id": dst}
    response = client.post("/api/transactions/", json=tx)
    assert response.status_code == 201
    assert response.json()["label"] == "Achat"
    assert "id" in response.json()


def test_create_transaction_invalid_date_rejected(client, entity_pair):
    """Une date non ISO est refusée (422) : sinon regroupement/filtres corrompus."""
    src, dst = entity_pair
    for bad in ("31/12/2026", "pas une date"):
        r = client.post("/api/transactions/", json={
            "date": bad, "label": "x", "amount": 100, "from_entity_id": src, "to_entity_id": dst})
        assert r.status_code == 422, (bad, r.status_code)


def test_get_transaction(client, entity_pair):
    src, dst = entity_pair
    # 100,00 € = 10000 centimes
    tx = client.post("/api/transactions/", json={"date": "2026-01-15", "label": "Test", "amount": 10000, "from_entity_id": src, "to_entity_id": dst}).json()
    response = client.get(f"/api/transactions/{tx['id']}")
    assert response.status_code == 200

def test_update_transaction(client, entity_pair):
    src, dst = entity_pair
    # 50,00 € = 5000 centimes
    tx = client.post("/api/transactions/", json={"date": "2026-01-15", "label": "Old", "amount": 5000, "from_entity_id": src, "to_entity_id": dst}).json()
    response = client.put(f"/api/transactions/{tx['id']}", json={"label": "New"})
    assert response.status_code == 200
    assert response.json()["label"] == "New"

def test_delete_transaction(client, entity_pair):
    src, dst = entity_pair
    # 10,00 € = 1000 centimes
    tx = client.post("/api/transactions/", json={"date": "2026-01-15", "label": "Del", "amount": 1000, "from_entity_id": src, "to_entity_id": dst}).json()
    response = client.delete(f"/api/transactions/{tx['id']}")
    assert response.status_code == 200
    assert client.get(f"/api/transactions/{tx['id']}").status_code == 404

def test_get_balance(client):
    response = client.get("/api/transactions/balance")
    assert response.status_code == 200
    assert "balance" in response.json()


def test_list_transactions_reimb_status_filter(client_and_db):
    client, _ = client_and_db
    src = client.post("/api/entities/", json={"name": "Src", "type": "external"}).json()
    dst = client.post("/api/entities/", json={"name": "Dst", "type": "internal"}).json()
    src_id, dst_id = src["id"], dst["id"]

    # Create 3 transactions (montants en centimes, tous positifs)
    tx_pending = client.post("/api/transactions/", json={
        "date": "2026-01-01", "label": "Pending", "amount": 1000,
        "from_entity_id": src_id, "to_entity_id": dst_id,
    }).json()
    tx_reimbursed = client.post("/api/transactions/", json={
        "date": "2026-01-02", "label": "Reimbursed", "amount": 2000,
        "from_entity_id": src_id, "to_entity_id": dst_id,
    }).json()
    tx_none = client.post("/api/transactions/", json={
        "date": "2026-01-03", "label": "NoReimb", "amount": 3000,
        "from_entity_id": src_id, "to_entity_id": dst_id,
    }).json()

    # Attach reimbursements (montants en centimes)
    client.post("/api/reimbursements/", json={
        "transaction_id": tx_pending["id"], "person_name": "Alice",
        "amount": 1000, "status": "pending",
    })
    client.post("/api/reimbursements/", json={
        "transaction_id": tx_reimbursed["id"], "person_name": "Bob",
        "amount": 2000, "status": "reimbursed",
    })

    # Filter: pending → only tx_pending
    r = client.get("/api/transactions/?reimb_status=pending")
    assert r.status_code == 200
    ids = [t["id"] for t in r.json()["items"]]
    assert tx_pending["id"] in ids
    assert tx_reimbursed["id"] not in ids
    assert tx_none["id"] not in ids

    # Filter: reimbursed → only tx_reimbursed
    r = client.get("/api/transactions/?reimb_status=reimbursed")
    assert r.status_code == 200
    ids = [t["id"] for t in r.json()["items"]]
    assert tx_reimbursed["id"] in ids
    assert tx_pending["id"] not in ids
    assert tx_none["id"] not in ids

    # Filter: none → only tx_none
    r = client.get("/api/transactions/?reimb_status=none")
    assert r.status_code == 200
    ids = [t["id"] for t in r.json()["items"]]
    assert tx_none["id"] in ids
    assert tx_pending["id"] not in ids
    assert tx_reimbursed["id"] not in ids

    # Invalid value → 400
    r = client.get("/api/transactions/?reimb_status=invalid")
    assert r.status_code == 400


def test_list_transactions_amount_filter(client_and_db):
    """amount_min / amount_max filter sur les montants en centimes."""
    client, _ = client_and_db
    src = client.post("/api/entities/", json={"name": "Src", "type": "external"}).json()
    dst = client.post("/api/entities/", json={"name": "Dst", "type": "internal"}).json()
    src_id, dst_id = src["id"], dst["id"]

    # Montants en centimes : 30 € = 3000, 75 € = 7500, 200 € = 20000
    tx_small = client.post("/api/transactions/", json={
        "date": "2026-01-01", "label": "Small", "amount": 3000,
        "from_entity_id": src_id, "to_entity_id": dst_id,
    }).json()
    tx_medium = client.post("/api/transactions/", json={
        "date": "2026-01-02", "label": "Medium", "amount": 7500,
        "from_entity_id": src_id, "to_entity_id": dst_id,
    }).json()
    tx_large = client.post("/api/transactions/", json={
        "date": "2026-01-03", "label": "Large", "amount": 20000,
        "from_entity_id": src_id, "to_entity_id": dst_id,
    }).json()

    # amount_min=10000 → only tx_large (20000 >= 10000)
    r = client.get("/api/transactions/?amount_min=10000")
    assert r.status_code == 200
    ids = [t["id"] for t in r.json()["items"]]
    assert tx_large["id"] in ids
    assert tx_medium["id"] not in ids
    assert tx_small["id"] not in ids

    # amount_max=5000 → only tx_small (3000 <= 5000)
    r = client.get("/api/transactions/?amount_max=5000")
    assert r.status_code == 200
    ids = [t["id"] for t in r.json()["items"]]
    assert tx_small["id"] in ids
    assert tx_medium["id"] not in ids
    assert tx_large["id"] not in ids

    # amount_min=5000 & amount_max=10000 → only tx_medium (7500 in [5000, 10000])
    r = client.get("/api/transactions/?amount_min=5000&amount_max=10000")
    assert r.status_code == 200
    ids = [t["id"] for t in r.json()["items"]]
    assert tx_medium["id"] in ids
    assert tx_small["id"] not in ids
    assert tx_large["id"] not in ids

    # amount_min > amount_max → 400
    r = client.get("/api/transactions/?amount_min=20000&amount_max=5000")
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Payer (advance payer) tests
# ---------------------------------------------------------------------------

@pytest.fixture
def contact_and_entities(client):
    """Returns (contact_id, src_entity_id, dst_entity_id)."""
    src = client.post("/api/entities/", json={"name": "SrcPayer", "type": "external"}).json()
    dst = client.post("/api/entities/", json={"name": "DstPayer", "type": "internal"}).json()
    contact = client.post("/api/tiers/", json={"name": "Alice", "type": "membre"}).json()
    return contact["id"], src["id"], dst["id"]


def test_create_transaction_with_payer(client_and_db, contact_and_entities):
    """POST tx with payer_contact_id creates a reimbursement row."""
    client, db_path = client_and_db
    contact_id, src_id, dst_id = contact_and_entities

    # 50,00 € = 5000 centimes
    r = client.post("/api/transactions/", json={
        "date": "2026-01-15", "label": "Achat avancé", "amount": 5000,
        "from_entity_id": src_id, "to_entity_id": dst_id,
        "payer_contact_id": contact_id,
    })
    assert r.status_code == 201
    tx_id = r.json()["id"]

    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rembo = conn.execute(
        "SELECT * FROM reimbursements WHERE transaction_id = ?", (tx_id,)
    ).fetchone()
    conn.close()

    assert rembo is not None
    assert rembo["contact_id"] == contact_id
    assert rembo["status"] == "pending"
    # Le remboursement est stocké en centimes (même convention que la transaction)
    assert rembo["amount"] == 5000


def test_create_transaction_with_payer_returns_contact_id_in_list(client_and_db, contact_and_entities):
    """GET /transactions/ returns reimb_contact_id for pre-selection on edit."""
    client, db_path = client_and_db
    contact_id, src_id, dst_id = contact_and_entities

    # 30,00 € = 3000 centimes
    r = client.post("/api/transactions/", json={
        "date": "2026-01-15", "label": "Avance test", "amount": 3000,
        "from_entity_id": src_id, "to_entity_id": dst_id,
        "payer_contact_id": contact_id,
    })
    assert r.status_code == 201
    tx_id = r.json()["id"]

    txs = client.get("/api/transactions/").json()["items"]
    tx = next(t for t in txs if t["id"] == tx_id)
    assert tx["reimb_contact_id"] == contact_id


def test_update_transaction_set_payer(client_and_db, contact_and_entities):
    """PUT with payer_contact_id on a tx that had none creates the rembo."""
    client, db_path = client_and_db
    contact_id, src_id, dst_id = contact_and_entities

    # 20,00 € = 2000 centimes
    tx = client.post("/api/transactions/", json={
        "date": "2026-01-15", "label": "No payer", "amount": 2000,
        "from_entity_id": src_id, "to_entity_id": dst_id,
    }).json()

    r = client.put(f"/api/transactions/{tx['id']}", json={"payer_contact_id": contact_id})
    assert r.status_code == 200

    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rembo = conn.execute(
        "SELECT * FROM reimbursements WHERE transaction_id = ?", (tx["id"],)
    ).fetchone()
    conn.close()

    assert rembo is not None
    assert rembo["contact_id"] == contact_id
    assert rembo["status"] == "pending"


def test_update_transaction_remove_payer(client_and_db, contact_and_entities):
    """PUT with payer_contact_id=null removes existing rembo."""
    client, db_path = client_and_db
    contact_id, src_id, dst_id = contact_and_entities

    # 40,00 € = 4000 centimes
    tx = client.post("/api/transactions/", json={
        "date": "2026-01-15", "label": "Has payer", "amount": 4000,
        "from_entity_id": src_id, "to_entity_id": dst_id,
        "payer_contact_id": contact_id,
    }).json()

    r = client.put(f"/api/transactions/{tx['id']}", json={"payer_contact_id": None})
    assert r.status_code == 200

    import sqlite3
    conn = sqlite3.connect(db_path)
    rembo = conn.execute(
        "SELECT * FROM reimbursements WHERE transaction_id = ?", (tx["id"],)
    ).fetchone()
    conn.close()

    assert rembo is None


def test_update_transaction_change_payer(client_and_db, contact_and_entities):
    """PUT with different payer_contact_id replaces the existing rembo."""
    client, db_path = client_and_db
    contact_a_id, src_id, dst_id = contact_and_entities
    contact_b = client.post("/api/tiers/", json={"name": "Bob", "type": "membre"}).json()
    contact_b_id = contact_b["id"]

    # 60,00 € = 6000 centimes
    tx = client.post("/api/transactions/", json={
        "date": "2026-01-15", "label": "Change payer", "amount": 6000,
        "from_entity_id": src_id, "to_entity_id": dst_id,
        "payer_contact_id": contact_a_id,
    }).json()

    r = client.put(f"/api/transactions/{tx['id']}", json={"payer_contact_id": contact_b_id})
    assert r.status_code == 200

    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rembos = conn.execute(
        "SELECT * FROM reimbursements WHERE transaction_id = ?", (tx["id"],)
    ).fetchall()
    conn.close()

    assert len(rembos) == 1
    assert rembos[0]["contact_id"] == contact_b_id


def test_update_transaction_no_payer_key_leaves_rembo_untouched(client_and_db, contact_and_entities):
    """PUT without payer_contact_id key does not touch existing rembo."""
    client, db_path = client_and_db
    contact_id, src_id, dst_id = contact_and_entities

    # 15,00 € = 1500 centimes
    tx = client.post("/api/transactions/", json={
        "date": "2026-01-15", "label": "Stable payer", "amount": 1500,
        "from_entity_id": src_id, "to_entity_id": dst_id,
        "payer_contact_id": contact_id,
    }).json()

    # Update only the label — payer_contact_id key is absent
    r = client.put(f"/api/transactions/{tx['id']}", json={"label": "Stable payer updated"})
    assert r.status_code == 200

    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rembo = conn.execute(
        "SELECT * FROM reimbursements WHERE transaction_id = ?", (tx["id"],)
    ).fetchone()
    conn.close()

    assert rembo is not None
    assert rembo["contact_id"] == contact_id


# ---------------------------------------------------------------------------
# Description field
# ---------------------------------------------------------------------------

def test_create_transaction_with_description(client, entity_pair):
    """description est sauvegardé et renvoyé dans la liste."""
    src, dst = entity_pair
    # 10,00 € = 1000 centimes
    r = client.post("/api/transactions/", json={
        "date": "2026-01-15", "label": "AvecDesc", "amount": 1000,
        "from_entity_id": src, "to_entity_id": dst,
        "description": "Détail important de la dépense",
    })
    assert r.status_code == 201
    tx_id = r.json()["id"]

    txs = client.get("/api/transactions/").json()["items"]
    tx = next(t for t in txs if t["id"] == tx_id)
    assert tx.get("description") == "Détail important de la dépense"


def test_description_searchable(client, entity_pair):
    """Le champ description est inclus dans la recherche plein-texte."""
    src, dst = entity_pair
    # 5,00 € = 500 centimes
    r = client.post("/api/transactions/", json={
        "date": "2026-01-15", "label": "Libelle neutre", "amount": 500,
        "from_entity_id": src, "to_entity_id": dst,
        "description": "MotClefUnique9876",
    })
    assert r.status_code == 201
    tx_id = r.json()["id"]

    results = client.get("/api/transactions/?search=MotClefUnique9876").json()["items"]
    assert any(t["id"] == tx_id for t in results)


def test_description_empty_by_default(client, entity_pair):
    """Une transaction sans description ne renvoie pas de description non-vide."""
    src, dst = entity_pair
    # 1,00 € = 100 centimes
    r = client.post("/api/transactions/", json={
        "date": "2026-01-15", "label": "SansDesc", "amount": 100,
        "from_entity_id": src, "to_entity_id": dst,
    })
    assert r.status_code == 201
    tx_id = r.json()["id"]

    txs = client.get("/api/transactions/").json()["items"]
    tx = next(t for t in txs if t["id"] == tx_id)
    assert not tx.get("description")


def test_update_transaction_description(client, entity_pair):
    """PUT peut mettre à jour la description."""
    src, dst = entity_pair
    # 8,00 € = 800 centimes
    tx = client.post("/api/transactions/", json={
        "date": "2026-01-15", "label": "Edit desc", "amount": 800,
        "from_entity_id": src, "to_entity_id": dst,
        "description": "Ancienne description",
    }).json()

    r = client.put(f"/api/transactions/{tx['id']}", json={"description": "Nouvelle description"})
    assert r.status_code == 200

    txs = client.get("/api/transactions/").json()["items"]
    updated = next(t for t in txs if t["id"] == tx["id"])
    assert updated.get("description") == "Nouvelle description"


# ---------------------------------------------------------------------------
# contact_id sur transaction
# ---------------------------------------------------------------------------

def test_create_transaction_with_contact_id(client, entity_pair):
    """contact_id est sauvegardé et renvoyé dans la liste des transactions."""
    src, dst = entity_pair
    contact = client.post("/api/tiers/", json={"name": "Contact Test", "type": "membre"}).json()

    # 20,00 € = 2000 centimes
    r = client.post("/api/transactions/", json={
        "date": "2026-01-15", "label": "Tx avec contact", "amount": 2000,
        "from_entity_id": src, "to_entity_id": dst,
        "contact_id": contact["id"],
    })
    assert r.status_code == 201
    tx_id = r.json()["id"]

    txs = client.get("/api/transactions/").json()["items"]
    tx = next(t for t in txs if t["id"] == tx_id)
    assert tx.get("contact_id") == contact["id"]


def test_transaction_appears_in_contact_transactions(client, entity_pair):
    """Une transaction liée à un contact apparaît dans GET /tiers/{id}/transactions."""
    src, dst = entity_pair
    contact = client.post("/api/tiers/", json={"name": "Alice", "type": "membre"}).json()

    # 15,00 € = 1500 centimes
    tx = client.post("/api/transactions/", json={
        "date": "2026-01-15", "label": "Achat Alice", "amount": 1500,
        "from_entity_id": src, "to_entity_id": dst,
        "contact_id": contact["id"],
    }).json()

    r = client.get(f"/api/tiers/{contact['id']}/transactions")
    assert r.status_code == 200
    ids = [t["id"] for t in r.json()]
    assert tx["id"] in ids


# ---------------------------------------------------------------------------
# Contrat getContacts (limit=10000 doit renvoyer {total, items})
# ---------------------------------------------------------------------------

def test_tiers_large_limit_returns_paginated_format(client):
    """api.getContacts() utilise limit=10000 — le format paginé doit être valide."""
    r = client.get("/api/tiers/?limit=10000&offset=0")
    assert r.status_code == 200
    data = r.json()
    assert "total" in data
    assert "items" in data
    assert isinstance(data["items"], list)


def test_tiers_large_limit_returns_all_contacts(client):
    """Avec limit=10000, tous les contacts créés doivent être dans items."""
    for i in range(5):
        client.post("/api/tiers/", json={"name": f"Bulk {i}", "type": "membre"})

    r = client.get("/api/tiers/?limit=10000&offset=0")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 5
    assert len(data["items"]) == data["total"]


# ---------------------------------------------------------------------------
# Suppression : nettoyage des remboursements liés (pas d'orphelins)
# ---------------------------------------------------------------------------

def test_delete_transaction_removes_linked_reimbursements(client_and_db, contact_and_entities):
    """Supprimer une transaction supprime les remboursements qui la référencent."""
    client, db_path = client_and_db
    contact_id, src_id, dst_id = contact_and_entities

    tx = client.post("/api/transactions/", json={
        "date": "2026-01-15", "label": "Avance à supprimer", "amount": 5000,
        "from_entity_id": src_id, "to_entity_id": dst_id,
        "payer_contact_id": contact_id,
    }).json()

    import sqlite3
    conn = sqlite3.connect(db_path)
    before = conn.execute(
        "SELECT COUNT(*) FROM reimbursements WHERE transaction_id = ?", (tx["id"],)
    ).fetchone()[0]
    conn.close()
    assert before == 1

    assert client.delete(f"/api/transactions/{tx['id']}").status_code == 200

    conn = sqlite3.connect(db_path)
    after = conn.execute(
        "SELECT COUNT(*) FROM reimbursements WHERE transaction_id = ?", (tx["id"],)
    ).fetchone()[0]
    conn.close()
    assert after == 0, "Le remboursement lié aurait dû être supprimé (pas d'orphelin)."


# ---------------------------------------------------------------------------
# Pagination + tri serveur
# ---------------------------------------------------------------------------

def test_list_returns_total_and_items(client, entity_pair):
    """Le format de réponse est {total, items}."""
    src, dst = entity_pair
    for i in range(3):
        client.post("/api/transactions/", json={
            "date": f"2026-02-{10 + i:02d}", "label": f"T{i}", "amount": 1000 + i,
            "from_entity_id": src, "to_entity_id": dst,
        })
    data = client.get("/api/transactions/").json()
    assert isinstance(data, dict)
    assert data["total"] == 3
    assert len(data["items"]) == 3


def test_pagination_limit_offset(client, entity_pair):
    """limit/offset paginent sans changer le total."""
    src, dst = entity_pair
    for i in range(5):
        client.post("/api/transactions/", json={
            "date": f"2026-03-{10 + i:02d}", "label": f"P{i}", "amount": 1000,
            "from_entity_id": src, "to_entity_id": dst,
        })
    page1 = client.get("/api/transactions/?limit=2&offset=0").json()
    page2 = client.get("/api/transactions/?limit=2&offset=2").json()
    assert page1["total"] == 5
    assert len(page1["items"]) == 2
    assert len(page2["items"]) == 2
    # Pas de chevauchement entre les deux pages.
    ids1 = {t["id"] for t in page1["items"]}
    ids2 = {t["id"] for t in page2["items"]}
    assert ids1.isdisjoint(ids2)


def test_sort_by_amount_ascending(client, entity_pair):
    """sort_by=amount&sort_dir=asc trie par montant croissant côté serveur."""
    src, dst = entity_pair
    for amt in (3000, 1000, 2000):
        client.post("/api/transactions/", json={
            "date": "2026-04-01", "label": f"A{amt}", "amount": amt,
            "from_entity_id": src, "to_entity_id": dst,
        })
    items = client.get("/api/transactions/?sort_by=amount&sort_dir=asc").json()["items"]
    amounts = [t["amount"] for t in items]
    assert amounts == sorted(amounts)


def test_invalid_sort_by_returns_400(client):
    """Un sort_by hors whitelist est rejeté (anti-injection)."""
    r = client.get("/api/transactions/?sort_by=amount;DROP")
    assert r.status_code == 400
