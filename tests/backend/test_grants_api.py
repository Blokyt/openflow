import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from fastapi.testclient import TestClient
from backend.main import create_app
import pytest

@pytest.fixture
def client():
    app = create_app(config_path="config.yaml", db_path="data/openflow.db")
    return TestClient(app)

def test_list_grants_empty(client):
    response = client.get("/api/grants/")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_create_grant(client):
    payload = {
        "name": "Subvention Mairie",
        "amount_granted": 5000.0,
        "date_granted": "2026-01-15",
    }
    response = client.post("/api/grants/", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Subvention Mairie"
    assert data["amount_granted"] == 5000.0
    assert data["amount_received"] == 0
    assert data["status"] == "pending"
    assert "id" in data

def test_create_grant_full(client):
    payload = {
        "name": "Subvention Region",
        "amount_granted": 12000.0,
        "amount_received": 6000.0,
        "date_granted": "2026-02-01",
        "date_received": "2026-03-01",
        "purpose": "Formation",
        "status": "partial",
        "notes": "Premiere tranche recue",
    }
    response = client.post("/api/grants/", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["amount_received"] == 6000.0
    assert data["status"] == "partial"
    assert data["notes"] == "Premiere tranche recue"

def test_get_grant(client):
    created = client.post("/api/grants/", json={
        "name": "Grant GET Test",
        "amount_granted": 1000.0,
        "date_granted": "2026-01-01",
    }).json()
    response = client.get(f"/api/grants/{created['id']}")
    assert response.status_code == 200
    assert response.json()["name"] == "Grant GET Test"

def test_get_grant_not_found(client):
    response = client.get("/api/grants/999999")
    assert response.status_code == 404

def test_filter_by_status(client):
    client.post("/api/grants/", json={"name": "Pending Grant", "amount_granted": 100.0, "date_granted": "2026-01-01", "status": "pending"})
    client.post("/api/grants/", json={"name": "Received Grant", "amount_granted": 200.0, "date_granted": "2026-01-01", "status": "received"})
    response = client.get("/api/grants/?status=pending")
    assert response.status_code == 200
    results = response.json()
    assert all(r["status"] == "pending" for r in results)
    assert any(r["name"] == "Pending Grant" for r in results)

def test_filter_by_status_received(client):
    client.post("/api/grants/", json={"name": "Done Grant", "amount_granted": 500.0, "date_granted": "2026-01-01", "status": "received"})
    response = client.get("/api/grants/?status=received")
    assert response.status_code == 200
    results = response.json()
    assert all(r["status"] == "received" for r in results)

def test_update_grant(client):
    created = client.post("/api/grants/", json={
        "name": "Update Test",
        "amount_granted": 3000.0,
        "date_granted": "2026-01-01",
    }).json()
    response = client.put(f"/api/grants/{created['id']}", json={
        "status": "partial",
        "amount_received": 1500.0,
        "date_received": "2026-04-01",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "partial"
    assert data["amount_received"] == 1500.0
    assert data["date_received"] == "2026-04-01"

def test_update_grant_not_found(client):
    response = client.put("/api/grants/999999", json={"status": "received"})
    assert response.status_code == 404

def test_delete_grant(client):
    created = client.post("/api/grants/", json={
        "name": "To Delete",
        "amount_granted": 100.0,
        "date_granted": "2026-01-01",
    }).json()
    response = client.delete(f"/api/grants/{created['id']}")
    assert response.status_code == 200
    assert response.json()["deleted"] == created["id"]
    assert client.get(f"/api/grants/{created['id']}").status_code == 404

def test_delete_grant_not_found(client):
    response = client.delete("/api/grants/999999")
    assert response.status_code == 404

def test_summary_endpoint(client):
    # Create grants with various statuses
    client.post("/api/grants/", json={"name": "G1", "amount_granted": 1000.0, "amount_received": 0.0, "date_granted": "2026-01-01", "status": "pending"})
    client.post("/api/grants/", json={"name": "G2", "amount_granted": 2000.0, "amount_received": 1000.0, "date_granted": "2026-01-01", "status": "partial"})
    client.post("/api/grants/", json={"name": "G3", "amount_granted": 500.0, "amount_received": 500.0, "date_granted": "2026-01-01", "status": "received"})

    response = client.get("/api/grants/summary")
    assert response.status_code == 200
    data = response.json()
    assert "total_granted" in data
    assert "total_received" in data
    assert "total_pending" in data
    assert data["total_granted"] >= 3500.0
    assert data["total_received"] >= 1500.0
    assert data["total_pending"] >= 2000.0

def test_summary_not_matched_by_id_route(client):
    # Ensure /summary is not treated as /{id}
    response = client.get("/api/grants/summary")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert "total_granted" in data
