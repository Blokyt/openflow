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
