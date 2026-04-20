"""Smoke tests for the invoices PDF endpoint."""
from fastapi.testclient import TestClient


def test_pdf_endpoint_404_for_missing_invoice(client):
    r = client.get("/api/invoices/99999/pdf")
    assert r.status_code == 404


def test_pdf_endpoint_returns_pdf_bytes(client):
    # Create a minimal invoice first
    # Note: the invoices model uses contact_id (not client_contact_id)
    # and InvoiceLineCreate has no vat_rate field (only description, quantity, unit_price)
    payload = {
        "type": "invoice",
        "contact_id": None,
        "date": "2026-04-20",
        "lines": [{"description": "Test", "quantity": 1, "unit_price": 100.0}],
    }
    create = client.post("/api/invoices/", json=payload)
    assert create.status_code == 201, create.text
    inv_id = create.json()["id"]

    r = client.get(f"/api/invoices/{inv_id}/pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"  # PDF magic bytes
