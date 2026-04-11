import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from fastapi.testclient import TestClient
from backend.main import create_app
import pytest

@pytest.fixture
def client():
    app = create_app(config_path="config.yaml", db_path="data/openflow.db")
    return TestClient(app)

def test_list_divisions(client):
    response = client.get("/api/divisions/")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_create_division(client):
    response = client.post("/api/divisions/", json={"name": "Marketing", "color": "#3B82F6"})
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Marketing"
    assert data["color"] == "#3B82F6"
    assert "id" in data

def test_get_division(client):
    created = client.post("/api/divisions/", json={"name": "Finance"}).json()
    response = client.get(f"/api/divisions/{created['id']}")
    assert response.status_code == 200
    assert response.json()["name"] == "Finance"

def test_get_division_not_found(client):
    response = client.get("/api/divisions/999999")
    assert response.status_code == 404

def test_update_division(client):
    div = client.post("/api/divisions/", json={"name": "OldName"}).json()
    response = client.put(f"/api/divisions/{div['id']}", json={"name": "NewName"})
    assert response.status_code == 200
    assert response.json()["name"] == "NewName"

def test_delete_division(client):
    div = client.post("/api/divisions/", json={"name": "ToDelete"}).json()
    response = client.delete(f"/api/divisions/{div['id']}")
    assert response.status_code == 200
    assert response.json()["deleted"] == div["id"]
    assert client.get(f"/api/divisions/{div['id']}").status_code == 404

def test_get_division_summary(client):
    div = client.post("/api/divisions/", json={"name": "SummaryTest"}).json()
    response = client.get(f"/api/divisions/{div['id']}/summary")
    assert response.status_code == 200
    data = response.json()
    assert "income" in data
    assert "expenses" in data
    assert "balance" in data
    assert data["division_id"] == div["id"]
    # No transactions linked yet, so all should be 0
    assert data["income"] == 0
    assert data["expenses"] == 0
    assert data["balance"] == 0

def test_get_summary_not_found(client):
    response = client.get("/api/divisions/999999/summary")
    assert response.status_code == 404
