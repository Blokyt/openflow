import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from fastapi.testclient import TestClient
from backend.main import create_app
import pytest

@pytest.fixture
def client():
    app = create_app(config_path="config.yaml", db_path="data/openflow.db")
    return TestClient(app)

def test_list_contacts_empty(client):
    response = client.get("/api/tiers/")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_create_contact(client):
    contact = {"name": "Alice Dupont", "type": "client", "email": "alice@example.com"}
    response = client.post("/api/tiers/", json=contact)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Alice Dupont"
    assert data["type"] == "client"
    assert data["email"] == "alice@example.com"
    assert "id" in data

def test_get_contact(client):
    contact = client.post("/api/tiers/", json={"name": "Bob Martin", "type": "supplier"}).json()
    response = client.get(f"/api/tiers/{contact['id']}")
    assert response.status_code == 200
    assert response.json()["name"] == "Bob Martin"

def test_get_contact_not_found(client):
    response = client.get("/api/tiers/999999")
    assert response.status_code == 404

def test_update_contact(client):
    contact = client.post("/api/tiers/", json={"name": "Old Name", "type": "member"}).json()
    response = client.put(f"/api/tiers/{contact['id']}", json={"name": "New Name", "phone": "0600000000"})
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "New Name"
    assert data["phone"] == "0600000000"
    assert data["type"] == "member"

def test_delete_contact(client):
    contact = client.post("/api/tiers/", json={"name": "To Delete", "type": "other"}).json()
    response = client.delete(f"/api/tiers/{contact['id']}")
    assert response.status_code == 200
    assert response.json()["deleted"] == contact["id"]
    assert client.get(f"/api/tiers/{contact['id']}").status_code == 404

def test_filter_by_type(client):
    client.post("/api/tiers/", json={"name": "Client One", "type": "client"})
    client.post("/api/tiers/", json={"name": "Supplier One", "type": "supplier"})
    response = client.get("/api/tiers/?type=client")
    assert response.status_code == 200
    results = response.json()
    assert all(c["type"] == "client" for c in results)

def test_filter_by_search(client):
    client.post("/api/tiers/", json={"name": "Recherche Unique XYZ", "type": "client"})
    response = client.get("/api/tiers/?search=Unique XYZ")
    assert response.status_code == 200
    results = response.json()
    assert any("Unique XYZ" in c["name"] for c in results)

def test_default_type_is_other(client):
    contact = client.post("/api/tiers/", json={"name": "No Type"}).json()
    assert contact["type"] == "other"
