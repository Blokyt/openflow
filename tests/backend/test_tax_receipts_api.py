import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_receipt(client, **kwargs):
    payload = {
        "contact_id": 1,
        "amount": 100.0,
        "date": "2026-03-15",
        "fiscal_year": "2026",
        "purpose": "Don association",
        **kwargs,
    }
    resp = client.post("/api/tax_receipts/", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

def test_create_tax_receipt(client):
    r = make_receipt(client)
    assert r["number"].startswith("RF-2026-")
    assert r["amount"] == 100.0
    assert r["fiscal_year"] == "2026"
    assert r["purpose"] == "Don association"
    assert "generated_at" in r


def test_create_auto_number_format(client):
    r = make_receipt(client, fiscal_year="2025")
    assert r["number"].startswith("RF-2025-")
    parts = r["number"].split("-")
    assert len(parts) == 3
    assert len(parts[2]) == 3  # zero-padded 3 digits


def test_create_increments_number(client):
    r1 = make_receipt(client)
    r2 = make_receipt(client)
    seq1 = int(r1["number"].split("-")[2])
    seq2 = int(r2["number"].split("-")[2])
    assert seq2 == seq1 + 1


# ---------------------------------------------------------------------------
# List & filter
# ---------------------------------------------------------------------------

def test_list_tax_receipts(client):
    make_receipt(client)
    resp = client.get("/api/tax_receipts/")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1


def test_list_filter_by_fiscal_year(client):
    make_receipt(client, fiscal_year="2024")
    make_receipt(client, fiscal_year="2025")
    resp = client.get("/api/tax_receipts/?fiscal_year=2024")
    assert resp.status_code == 200
    results = resp.json()
    assert all(r["fiscal_year"] == "2024" for r in results)


# ---------------------------------------------------------------------------
# Get
# ---------------------------------------------------------------------------

def test_get_tax_receipt(client):
    r = make_receipt(client)
    resp = client.get(f"/api/tax_receipts/{r['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == r["id"]


def test_get_tax_receipt_not_found(client):
    resp = client.get("/api/tax_receipts/999999")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

def test_update_tax_receipt(client):
    r = make_receipt(client)
    resp = client.put(f"/api/tax_receipts/{r['id']}", json={"amount": 250.0, "purpose": "Updated"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["amount"] == 250.0
    assert data["purpose"] == "Updated"


def test_update_tax_receipt_not_found(client):
    resp = client.put("/api/tax_receipts/999999", json={"amount": 50.0})
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

def test_delete_tax_receipt(client):
    r = make_receipt(client)
    resp = client.delete(f"/api/tax_receipts/{r['id']}")
    assert resp.status_code == 200
    assert resp.json()["deleted"] == r["id"]
    assert client.get(f"/api/tax_receipts/{r['id']}").status_code == 404


def test_delete_tax_receipt_not_found(client):
    resp = client.delete("/api/tax_receipts/999999")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Next-number
# ---------------------------------------------------------------------------

def test_next_number(client):
    resp = client.get("/api/tax_receipts/next-number?fiscal_year=2026")
    assert resp.status_code == 200
    number = resp.json()["number"]
    assert number.startswith("RF-2026-")


def test_next_number_increments(client):
    resp1 = client.get("/api/tax_receipts/next-number?fiscal_year=2026")
    n1 = resp1.json()["number"]
    make_receipt(client, fiscal_year="2026")
    resp2 = client.get("/api/tax_receipts/next-number?fiscal_year=2026")
    n2 = resp2.json()["number"]
    seq1 = int(n1.split("-")[2])
    seq2 = int(n2.split("-")[2])
    assert seq2 == seq1 + 1


def test_next_number_different_years_independent(client):
    make_receipt(client, fiscal_year="2026")
    make_receipt(client, fiscal_year="2026")
    resp = client.get("/api/tax_receipts/next-number?fiscal_year=2027")
    assert resp.status_code == 200
    number = resp.json()["number"]
    assert number == "RF-2027-001"
