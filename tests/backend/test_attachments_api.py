import os
import sys
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
    """Create a transaction to attach files to."""
    tx = {"date": "2026-01-15", "label": "Test Transaction", "amount": 100.0}
    response = client.post("/api/transactions/", json=tx)
    assert response.status_code == 201
    return response.json()


def test_list_attachments_empty(client, transaction):
    response = client.get(f"/api/attachments/transaction/{transaction['id']}")
    assert response.status_code == 200
    assert response.json() == []


def test_upload_attachment(client, transaction):
    tx_id = transaction["id"]
    response = client.post(
        f"/api/attachments/transaction/{tx_id}",
        files={"file": ("test.txt", b"hello world", "text/plain")},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["original_name"] == "test.txt"
    assert body["transaction_id"] == tx_id
    assert body["mime_type"] == "text/plain"
    assert body["size"] == len(b"hello world")
    assert "id" in body
    assert "filename" in body
    assert "created_at" in body


def test_list_attachments(client, transaction):
    tx_id = transaction["id"]
    client.post(
        f"/api/attachments/transaction/{tx_id}",
        files={"file": ("file_a.txt", b"content a", "text/plain")},
    )
    client.post(
        f"/api/attachments/transaction/{tx_id}",
        files={"file": ("file_b.txt", b"content b", "text/plain")},
    )
    response = client.get(f"/api/attachments/transaction/{tx_id}")
    assert response.status_code == 200
    names = [a["original_name"] for a in response.json()]
    assert "file_a.txt" in names
    assert "file_b.txt" in names


def test_download_attachment(client, transaction):
    tx_id = transaction["id"]
    upload = client.post(
        f"/api/attachments/transaction/{tx_id}",
        files={"file": ("download_me.txt", b"file content here", "text/plain")},
    )
    assert upload.status_code == 201
    att_id = upload.json()["id"]

    response = client.get(f"/api/attachments/{att_id}/download")
    assert response.status_code == 200
    assert response.content == b"file content here"


def test_delete_attachment(client, transaction):
    tx_id = transaction["id"]
    upload = client.post(
        f"/api/attachments/transaction/{tx_id}",
        files={"file": ("to_delete.txt", b"bye", "text/plain")},
    )
    assert upload.status_code == 201
    att_id = upload.json()["id"]

    response = client.delete(f"/api/attachments/{att_id}")
    assert response.status_code == 200
    assert response.json()["deleted"] == att_id

    # Verify it no longer appears in the list
    attachments = client.get(f"/api/attachments/transaction/{tx_id}").json()
    ids = [a["id"] for a in attachments]
    assert att_id not in ids


def test_upload_on_nonexistent_transaction(client):
    response = client.post(
        "/api/attachments/transaction/999999",
        files={"file": ("ghost.txt", b"data", "text/plain")},
    )
    assert response.status_code == 404


def test_list_on_nonexistent_transaction(client):
    response = client.get("/api/attachments/transaction/999999")
    assert response.status_code == 404


def test_download_nonexistent_attachment(client):
    response = client.get("/api/attachments/999999/download")
    assert response.status_code == 404


def test_delete_nonexistent_attachment(client):
    response = client.delete("/api/attachments/999999")
    assert response.status_code == 404
