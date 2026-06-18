import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import pytest


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


def test_preview_attachment_image(client, transaction):
    tx_id = transaction["id"]
    # PNG factice minimal (1x1 pixel, valide pour simuler une image)
    fake_png = (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx"
        b"\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00"
        b"\x00\x00\x00IEND\xaeB`\x82"
    )
    upload = client.post(
        f"/api/attachments/transaction/{tx_id}",
        files={"file": ("photo.png", fake_png, "image/png")},
    )
    assert upload.status_code == 201
    att_id = upload.json()["id"]

    response = client.get(f"/api/attachments/{att_id}/preview")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/png")
    # Content-Disposition ne doit pas contenir "attachment"
    disposition = response.headers.get("content-disposition", "")
    assert "attachment" not in disposition


def test_preview_nonexistent_attachment(client):
    response = client.get("/api/attachments/999999/preview")
    assert response.status_code == 404
