import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import pytest


# --- Account CRUD ---

def test_list_accounts_empty(client):
    response = client.get("/api/multi_accounts/")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_create_account(client):
    payload = {"name": "Compte courant", "type": "checking", "initial_balance": 1000.0}
    response = client.post("/api/multi_accounts/", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Compte courant"
    assert data["type"] == "checking"
    assert data["initial_balance"] == 1000.0
    assert "id" in data


def test_create_account_savings(client):
    payload = {"name": "Livret A", "type": "savings", "initial_balance": 500.0, "color": "#22C55E"}
    response = client.post("/api/multi_accounts/", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["type"] == "savings"
    assert data["color"] == "#22C55E"


def test_create_account_cash(client):
    payload = {"name": "Caisse", "type": "cash", "initial_balance": 200.0}
    response = client.post("/api/multi_accounts/", json=payload)
    assert response.status_code == 201
    assert response.json()["type"] == "cash"


def test_create_account_invalid_type(client):
    response = client.post("/api/multi_accounts/", json={"name": "Bad", "type": "unknown"})
    assert response.status_code == 400


def test_get_account(client):
    acc = client.post("/api/multi_accounts/", json={"name": "Test", "type": "checking"}).json()
    response = client.get(f"/api/multi_accounts/{acc['id']}")
    assert response.status_code == 200
    assert response.json()["id"] == acc["id"]


def test_get_account_not_found(client):
    response = client.get("/api/multi_accounts/999999")
    assert response.status_code == 404


def test_update_account(client):
    acc = client.post("/api/multi_accounts/", json={"name": "Old Name", "type": "checking"}).json()
    response = client.put(f"/api/multi_accounts/{acc['id']}", json={"name": "New Name", "color": "#EF4444"})
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "New Name"
    assert data["color"] == "#EF4444"


def test_update_account_not_found(client):
    response = client.put("/api/multi_accounts/999999", json={"name": "Ghost"})
    assert response.status_code == 404


def test_delete_account(client):
    acc = client.post("/api/multi_accounts/", json={"name": "To Delete", "type": "cash"}).json()
    response = client.delete(f"/api/multi_accounts/{acc['id']}")
    assert response.status_code == 200
    assert response.json()["deleted"] == acc["id"]
    assert client.get(f"/api/multi_accounts/{acc['id']}").status_code == 404


def test_delete_account_not_found(client):
    response = client.delete("/api/multi_accounts/999999")
    assert response.status_code == 404


# --- Transfers ---

def test_create_transfer(client):
    acc1 = client.post("/api/multi_accounts/", json={"name": "Source", "type": "checking", "initial_balance": 2000.0}).json()
    acc2 = client.post("/api/multi_accounts/", json={"name": "Dest", "type": "savings"}).json()

    payload = {
        "from_account_id": acc1["id"],
        "to_account_id": acc2["id"],
        "amount": 300.0,
        "date": "2026-03-01",
        "label": "Epargne mensuelle",
    }
    response = client.post("/api/multi_accounts/transfers", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["from_account_id"] == acc1["id"]
    assert data["to_account_id"] == acc2["id"]
    assert data["amount"] == 300.0
    assert data["label"] == "Epargne mensuelle"
    assert data["from_transaction_id"] is not None
    assert data["to_transaction_id"] is not None


def test_create_transfer_same_account(client):
    acc = client.post("/api/multi_accounts/", json={"name": "Solo", "type": "checking"}).json()
    response = client.post("/api/multi_accounts/transfers", json={
        "from_account_id": acc["id"],
        "to_account_id": acc["id"],
        "amount": 100.0,
        "date": "2026-03-01",
    })
    assert response.status_code == 400


def test_create_transfer_negative_amount(client):
    acc1 = client.post("/api/multi_accounts/", json={"name": "A", "type": "checking"}).json()
    acc2 = client.post("/api/multi_accounts/", json={"name": "B", "type": "checking"}).json()
    response = client.post("/api/multi_accounts/transfers", json={
        "from_account_id": acc1["id"],
        "to_account_id": acc2["id"],
        "amount": -50.0,
        "date": "2026-03-01",
    })
    assert response.status_code == 400


def test_create_transfer_account_not_found(client):
    acc = client.post("/api/multi_accounts/", json={"name": "Real", "type": "checking"}).json()
    response = client.post("/api/multi_accounts/transfers", json={
        "from_account_id": acc["id"],
        "to_account_id": 999999,
        "amount": 50.0,
        "date": "2026-03-01",
    })
    assert response.status_code == 404


def test_list_transfers(client):
    response = client.get("/api/multi_accounts/transfers")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


# --- Balances ---

def test_balances_initial(client):
    acc = client.post("/api/multi_accounts/", json={"name": "Balance Test", "type": "checking", "initial_balance": 1500.0}).json()
    response = client.get("/api/multi_accounts/balances")
    assert response.status_code == 200
    balances = response.json()
    target = next((b for b in balances if b["id"] == acc["id"]), None)
    assert target is not None
    assert target["balance"] == 1500.0
    assert target["incoming"] == 0.0
    assert target["outgoing"] == 0.0


def test_balances_after_transfer(client):
    acc1 = client.post("/api/multi_accounts/", json={"name": "From Bal", "type": "checking", "initial_balance": 1000.0}).json()
    acc2 = client.post("/api/multi_accounts/", json={"name": "To Bal", "type": "savings", "initial_balance": 0.0}).json()

    client.post("/api/multi_accounts/transfers", json={
        "from_account_id": acc1["id"],
        "to_account_id": acc2["id"],
        "amount": 400.0,
        "date": "2026-04-01",
        "label": "Test virement",
    })

    response = client.get("/api/multi_accounts/balances")
    assert response.status_code == 200
    balances = response.json()

    b1 = next(b for b in balances if b["id"] == acc1["id"])
    b2 = next(b for b in balances if b["id"] == acc2["id"])

    # From account: 1000 initial - 400 outgoing = 600
    assert b1["balance"] == 600.0
    assert b1["outgoing"] == 400.0

    # To account: 0 initial + 400 incoming = 400
    assert b2["balance"] == 400.0
    assert b2["incoming"] == 400.0
