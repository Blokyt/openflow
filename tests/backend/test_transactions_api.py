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
    tx = {"date": "2026-01-15", "label": "Achat", "amount": -45.50, "from_entity_id": src, "to_entity_id": dst}
    response = client.post("/api/transactions/", json=tx)
    assert response.status_code == 201
    assert response.json()["label"] == "Achat"
    assert "id" in response.json()

def test_get_transaction(client, entity_pair):
    src, dst = entity_pair
    tx = client.post("/api/transactions/", json={"date": "2026-01-15", "label": "Test", "amount": 100.0, "from_entity_id": src, "to_entity_id": dst}).json()
    response = client.get(f"/api/transactions/{tx['id']}")
    assert response.status_code == 200

def test_update_transaction(client, entity_pair):
    src, dst = entity_pair
    tx = client.post("/api/transactions/", json={"date": "2026-01-15", "label": "Old", "amount": 50.0, "from_entity_id": src, "to_entity_id": dst}).json()
    response = client.put(f"/api/transactions/{tx['id']}", json={"label": "New"})
    assert response.status_code == 200
    assert response.json()["label"] == "New"

def test_delete_transaction(client, entity_pair):
    src, dst = entity_pair
    tx = client.post("/api/transactions/", json={"date": "2026-01-15", "label": "Del", "amount": -10.0, "from_entity_id": src, "to_entity_id": dst}).json()
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

    # Create 3 transactions
    tx_pending = client.post("/api/transactions/", json={
        "date": "2026-01-01", "label": "Pending", "amount": -10.0,
        "from_entity_id": src_id, "to_entity_id": dst_id,
    }).json()
    tx_reimbursed = client.post("/api/transactions/", json={
        "date": "2026-01-02", "label": "Reimbursed", "amount": -20.0,
        "from_entity_id": src_id, "to_entity_id": dst_id,
    }).json()
    tx_none = client.post("/api/transactions/", json={
        "date": "2026-01-03", "label": "NoReimb", "amount": -30.0,
        "from_entity_id": src_id, "to_entity_id": dst_id,
    }).json()

    # Attach reimbursements
    client.post("/api/reimbursements/", json={
        "transaction_id": tx_pending["id"], "person_name": "Alice",
        "amount": 10.0, "status": "pending",
    })
    client.post("/api/reimbursements/", json={
        "transaction_id": tx_reimbursed["id"], "person_name": "Bob",
        "amount": 20.0, "status": "reimbursed",
    })

    # Filter: pending → only tx_pending
    r = client.get("/api/transactions/?reimb_status=pending")
    assert r.status_code == 200
    ids = [t["id"] for t in r.json()]
    assert tx_pending["id"] in ids
    assert tx_reimbursed["id"] not in ids
    assert tx_none["id"] not in ids

    # Filter: reimbursed → only tx_reimbursed
    r = client.get("/api/transactions/?reimb_status=reimbursed")
    assert r.status_code == 200
    ids = [t["id"] for t in r.json()]
    assert tx_reimbursed["id"] in ids
    assert tx_pending["id"] not in ids
    assert tx_none["id"] not in ids

    # Filter: none → only tx_none
    r = client.get("/api/transactions/?reimb_status=none")
    assert r.status_code == 200
    ids = [t["id"] for t in r.json()]
    assert tx_none["id"] in ids
    assert tx_pending["id"] not in ids
    assert tx_reimbursed["id"] not in ids

    # Invalid value → 400
    r = client.get("/api/transactions/?reimb_status=invalid")
    assert r.status_code == 400


def test_list_transactions_amount_filter(client_and_db):
    """amount_min / amount_max filter on ABS(amount)."""
    client, _ = client_and_db
    src = client.post("/api/entities/", json={"name": "Src", "type": "external"}).json()
    dst = client.post("/api/entities/", json={"name": "Dst", "type": "internal"}).json()
    src_id, dst_id = src["id"], dst["id"]

    # Create transactions with various amounts
    tx_small = client.post("/api/transactions/", json={
        "date": "2026-01-01", "label": "Small", "amount": -30.0,
        "from_entity_id": src_id, "to_entity_id": dst_id,
    }).json()
    tx_medium = client.post("/api/transactions/", json={
        "date": "2026-01-02", "label": "Medium", "amount": 75.0,
        "from_entity_id": src_id, "to_entity_id": dst_id,
    }).json()
    tx_large = client.post("/api/transactions/", json={
        "date": "2026-01-03", "label": "Large", "amount": -200.0,
        "from_entity_id": src_id, "to_entity_id": dst_id,
    }).json()

    # amount_min=100 → only tx_large (abs(-200) >= 100)
    r = client.get("/api/transactions/?amount_min=100")
    assert r.status_code == 200
    ids = [t["id"] for t in r.json()]
    assert tx_large["id"] in ids
    assert tx_medium["id"] not in ids
    assert tx_small["id"] not in ids

    # amount_max=50 → only tx_small (abs(-30) <= 50)
    r = client.get("/api/transactions/?amount_max=50")
    assert r.status_code == 200
    ids = [t["id"] for t in r.json()]
    assert tx_small["id"] in ids
    assert tx_medium["id"] not in ids
    assert tx_large["id"] not in ids

    # amount_min=50 & amount_max=100 → only tx_medium (abs(75) in [50, 100])
    r = client.get("/api/transactions/?amount_min=50&amount_max=100")
    assert r.status_code == 200
    ids = [t["id"] for t in r.json()]
    assert tx_medium["id"] in ids
    assert tx_small["id"] not in ids
    assert tx_large["id"] not in ids

    # amount_min > amount_max → 400
    r = client.get("/api/transactions/?amount_min=200&amount_max=50")
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

    r = client.post("/api/transactions/", json={
        "date": "2026-01-15", "label": "Achat avancé", "amount": -50.0,
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
    assert rembo["amount"] == 50.0  # abs(-50)


def test_create_transaction_with_payer_returns_contact_id_in_list(client_and_db, contact_and_entities):
    """GET /transactions/ returns reimb_contact_id for pre-selection on edit."""
    client, db_path = client_and_db
    contact_id, src_id, dst_id = contact_and_entities

    r = client.post("/api/transactions/", json={
        "date": "2026-01-15", "label": "Avance test", "amount": -30.0,
        "from_entity_id": src_id, "to_entity_id": dst_id,
        "payer_contact_id": contact_id,
    })
    assert r.status_code == 201
    tx_id = r.json()["id"]

    txs = client.get("/api/transactions/").json()
    tx = next(t for t in txs if t["id"] == tx_id)
    assert tx["reimb_contact_id"] == contact_id


def test_update_transaction_set_payer(client_and_db, contact_and_entities):
    """PUT with payer_contact_id on a tx that had none creates the rembo."""
    client, db_path = client_and_db
    contact_id, src_id, dst_id = contact_and_entities

    tx = client.post("/api/transactions/", json={
        "date": "2026-01-15", "label": "No payer", "amount": -20.0,
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

    tx = client.post("/api/transactions/", json={
        "date": "2026-01-15", "label": "Has payer", "amount": -40.0,
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

    tx = client.post("/api/transactions/", json={
        "date": "2026-01-15", "label": "Change payer", "amount": -60.0,
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

    tx = client.post("/api/transactions/", json={
        "date": "2026-01-15", "label": "Stable payer", "amount": -15.0,
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
