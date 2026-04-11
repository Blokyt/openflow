import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from fastapi.testclient import TestClient
from backend.main import create_app
import pytest

@pytest.fixture
def client():
    app = create_app(config_path="config.yaml", db_path="data/openflow.db")
    return TestClient(app)

def test_list_categories(client):
    response = client.get("/api/categories/")
    assert response.status_code == 200

def test_create_category(client):
    response = client.post("/api/categories/", json={"name": "Communication", "color": "#3B82F6"})
    assert response.status_code == 201
    assert response.json()["name"] == "Communication"

def test_create_subcategory(client):
    parent = client.post("/api/categories/", json={"name": "Parent"}).json()
    child = client.post("/api/categories/", json={"name": "Child", "parent_id": parent["id"]}).json()
    assert child["parent_id"] == parent["id"]

def test_update_category(client):
    cat = client.post("/api/categories/", json={"name": "Old"}).json()
    response = client.put(f"/api/categories/{cat['id']}", json={"name": "New"})
    assert response.status_code == 200
    assert response.json()["name"] == "New"

def test_delete_category(client):
    cat = client.post("/api/categories/", json={"name": "Del"}).json()
    response = client.delete(f"/api/categories/{cat['id']}")
    assert response.status_code == 200
    assert client.get(f"/api/categories/{cat['id']}").status_code == 404

def test_get_tree(client):
    response = client.get("/api/categories/tree")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
