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
