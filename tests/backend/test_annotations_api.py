import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from fastapi.testclient import TestClient
from backend.main import create_app
import pytest


@pytest.fixture
def client():
    app = create_app(config_path="config.yaml", db_path="data/openflow.db")
    return TestClient(app)


@pytest.fixture
def transaction(client):
    """Create a transaction to attach annotations to."""
    tx = {"date": "2026-01-15", "label": "Test Transaction", "amount": 100.0}
    response = client.post("/api/transactions/", json=tx)
    assert response.status_code == 201
    return response.json()


def test_list_annotations_empty(client, transaction):
    response = client.get(f"/api/annotations/transaction/{transaction['id']}")
    assert response.status_code == 200
    assert response.json() == []


def test_create_annotation(client, transaction):
    data = {"content": "First note"}
    response = client.post(f"/api/annotations/transaction/{transaction['id']}", json=data)
    assert response.status_code == 201
    body = response.json()
    assert body["content"] == "First note"
    assert body["transaction_id"] == transaction["id"]
    assert "id" in body
    assert "created_at" in body


def test_list_annotations(client, transaction):
    client.post(f"/api/annotations/transaction/{transaction['id']}", json={"content": "Note A"})
    client.post(f"/api/annotations/transaction/{transaction['id']}", json={"content": "Note B"})
    response = client.get(f"/api/annotations/transaction/{transaction['id']}")
    assert response.status_code == 200
    contents = [a["content"] for a in response.json()]
    assert "Note A" in contents
    assert "Note B" in contents


def test_update_annotation(client, transaction):
    ann = client.post(
        f"/api/annotations/transaction/{transaction['id']}",
        json={"content": "Old content"},
    ).json()
    response = client.put(f"/api/annotations/{ann['id']}", json={"content": "Updated content"})
    assert response.status_code == 200
    assert response.json()["content"] == "Updated content"


def test_delete_annotation(client, transaction):
    ann = client.post(
        f"/api/annotations/transaction/{transaction['id']}",
        json={"content": "To delete"},
    ).json()
    response = client.delete(f"/api/annotations/{ann['id']}")
    assert response.status_code == 200
    assert response.json()["deleted"] == ann["id"]
    # Verify it no longer appears in the list
    annotations = client.get(f"/api/annotations/transaction/{transaction['id']}").json()
    ids = [a["id"] for a in annotations]
    assert ann["id"] not in ids


def test_annotation_on_nonexistent_transaction(client):
    response = client.get("/api/annotations/transaction/999999")
    assert response.status_code == 404


def test_update_nonexistent_annotation(client):
    response = client.put("/api/annotations/999999", json={"content": "Ghost"})
    assert response.status_code == 404


def test_delete_nonexistent_annotation(client):
    response = client.delete("/api/annotations/999999")
    assert response.status_code == 404
