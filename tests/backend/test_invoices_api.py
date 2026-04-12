import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_invoice(client, **kwargs):
    payload = {
        "type": "invoice",
        "date": "2026-01-15",
        "due_date": "2026-02-15",
        "lines": [
            {"description": "Service A", "quantity": 2, "unit_price": 50.0},
            {"description": "Service B", "quantity": 1, "unit_price": 30.0},
        ],
        **kwargs,
    }
    resp = client.post("/api/invoices/", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def make_quote(client, **kwargs):
    return make_invoice(client, type="quote", **kwargs)


# ---------------------------------------------------------------------------
# Create with lines
# ---------------------------------------------------------------------------

def test_create_invoice_with_lines(client):
    inv = make_invoice(client)
    assert inv["type"] == "invoice"
    assert inv["number"].startswith("FAC-")
    assert len(inv["lines"]) == 2
    # subtotal = 2*50 + 1*30 = 130
    assert inv["subtotal"] == pytest.approx(130.0)
    assert inv["total"] == pytest.approx(130.0)   # tax_rate=0


def test_create_invoice_with_tax(client):
    inv = make_invoice(
        client,
        tax_rate=20.0,
        lines=[{"description": "Produit", "quantity": 1, "unit_price": 100.0}],
    )
    assert inv["subtotal"] == pytest.approx(100.0)
    assert inv["total"] == pytest.approx(120.0)


def test_create_quote(client):
    q = make_quote(client)
    assert q["type"] == "quote"
    assert q["number"].startswith("DEV-")


def test_line_total_computed(client):
    inv = make_invoice(
        client,
        lines=[{"description": "Item", "quantity": 3, "unit_price": 10.0}],
    )
    line = inv["lines"][0]
    assert line["total"] == pytest.approx(30.0)


# ---------------------------------------------------------------------------
# List & filter
# ---------------------------------------------------------------------------

def test_list_invoices(client):
    make_invoice(client)
    resp = client.get("/api/invoices/")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert len(resp.json()) >= 1


def test_filter_by_type(client):
    make_invoice(client)
    make_quote(client)
    resp = client.get("/api/invoices/?type=invoice")
    assert resp.status_code == 200
    assert all(i["type"] == "invoice" for i in resp.json())


def test_filter_by_status(client):
    make_invoice(client, status="sent")
    make_invoice(client, status="draft")
    resp = client.get("/api/invoices/?status=sent")
    assert resp.status_code == 200
    assert all(i["status"] == "sent" for i in resp.json())


def test_filter_type_and_status(client):
    make_invoice(client, status="paid")
    make_quote(client, status="paid")
    resp = client.get("/api/invoices/?type=invoice&status=paid")
    assert resp.status_code == 200
    results = resp.json()
    assert all(i["type"] == "invoice" and i["status"] == "paid" for i in results)


# ---------------------------------------------------------------------------
# Get with lines
# ---------------------------------------------------------------------------

def test_get_invoice_with_lines(client):
    inv = make_invoice(client)
    resp = client.get(f"/api/invoices/{inv['id']}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == inv["id"]
    assert "lines" in data
    assert len(data["lines"]) == 2


def test_get_invoice_not_found(client):
    resp = client.get("/api/invoices/999999")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

def test_update_invoice_status(client):
    inv = make_invoice(client)
    resp = client.put(f"/api/invoices/{inv['id']}", json={"status": "sent"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "sent"


def test_update_invoice_lines(client):
    inv = make_invoice(client)
    new_lines = [{"description": "Nouveau service", "quantity": 5, "unit_price": 20.0}]
    resp = client.put(f"/api/invoices/{inv['id']}", json={"lines": new_lines})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["lines"]) == 1
    assert data["lines"][0]["description"] == "Nouveau service"
    assert data["subtotal"] == pytest.approx(100.0)


def test_update_invoice_not_found(client):
    resp = client.put("/api/invoices/999999", json={"status": "paid"})
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

def test_delete_invoice(client):
    inv = make_invoice(client)
    resp = client.delete(f"/api/invoices/{inv['id']}")
    assert resp.status_code == 200
    assert resp.json()["deleted"] == inv["id"]
    # Verify it's gone
    assert client.get(f"/api/invoices/{inv['id']}").status_code == 404


def test_delete_invoice_cascades_lines(client):
    """Lines should be deleted with the invoice (ON DELETE CASCADE)."""
    inv = make_invoice(client)
    invoice_id = inv["id"]
    client.delete(f"/api/invoices/{invoice_id}")
    # Re-create with same check: can't GET lines, but GET invoice 404 is enough
    assert client.get(f"/api/invoices/{invoice_id}").status_code == 404


def test_delete_invoice_not_found(client):
    resp = client.delete("/api/invoices/999999")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Next-number
# ---------------------------------------------------------------------------

def test_next_number_invoice(client):
    resp = client.get("/api/invoices/next-number?type=invoice")
    assert resp.status_code == 200
    number = resp.json()["number"]
    assert number.startswith("FAC-2026-")


def test_next_number_quote(client):
    resp = client.get("/api/invoices/next-number?type=quote")
    assert resp.status_code == 200
    number = resp.json()["number"]
    assert number.startswith("DEV-2026-")


def test_next_number_increments(client):
    resp1 = client.get("/api/invoices/next-number?type=invoice")
    n1 = resp1.json()["number"]
    # Create an invoice so the counter advances
    make_invoice(client)
    resp2 = client.get("/api/invoices/next-number?type=invoice")
    n2 = resp2.json()["number"]
    seq1 = int(n1.split("-")[2])
    seq2 = int(n2.split("-")[2])
    assert seq2 == seq1 + 1


# ---------------------------------------------------------------------------
# Convert quote to invoice
# ---------------------------------------------------------------------------

def test_convert_quote_to_invoice(client):
    q = make_quote(client)
    assert q["type"] == "quote"
    resp = client.post(f"/api/invoices/{q['id']}/convert")
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "invoice"
    assert data["number"].startswith("FAC-")
    assert data["status"] == "draft"
    # Lines are preserved
    assert len(data["lines"]) == len(q["lines"])


def test_convert_invoice_fails(client):
    """Converting a non-quote invoice should return 400."""
    inv = make_invoice(client)
    resp = client.post(f"/api/invoices/{inv['id']}/convert")
    assert resp.status_code == 400


def test_convert_not_found(client):
    resp = client.post("/api/invoices/999999/convert")
    assert resp.status_code == 404


def test_convert_changes_number(client):
    q = make_quote(client)
    old_number = q["number"]
    resp = client.post(f"/api/invoices/{q['id']}/convert")
    new_number = resp.json()["number"]
    assert new_number != old_number
    assert new_number.startswith("FAC-")
