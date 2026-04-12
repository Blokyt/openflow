"""Coherence tests: invoices, recurring, multi_accounts, annotations, categories."""
import pytest
from datetime import date, timedelta


# ============================================================
# INVOICES — math coherence
# ============================================================

def test_invoice_subtotal_equals_line_sum(client):
    """Invoice subtotal must equal sum of (qty * unit_price) for all lines."""
    resp = client.post("/api/invoices/", json={
        "type": "invoice", "date": "2025-06-01", "due_date": "2025-07-01",
        "tax_rate": 20,
        "lines": [
            {"description": "Service A", "quantity": 2, "unit_price": 500},
            {"description": "Service B", "quantity": 1, "unit_price": 300},
        ],
    })
    assert resp.status_code == 201
    inv = resp.json()
    expected_subtotal = 2 * 500 + 1 * 300  # 1300
    assert inv["subtotal"] == pytest.approx(expected_subtotal)


def test_invoice_total_with_tax(client):
    """Invoice total = subtotal * (1 + tax_rate/100)."""
    resp = client.post("/api/invoices/", json={
        "type": "invoice", "date": "2025-06-01", "due_date": "2025-07-01",
        "tax_rate": 20,
        "lines": [{"description": "Prestation", "quantity": 1, "unit_price": 1000}],
    })
    inv = resp.json()
    assert inv["subtotal"] == pytest.approx(1000.0)
    assert inv["total"] == pytest.approx(1200.0)  # 1000 * 1.20


def test_invoice_total_zero_tax(client):
    """Invoice with tax_rate=0: total = subtotal."""
    resp = client.post("/api/invoices/", json={
        "type": "invoice", "date": "2025-06-01", "due_date": "2025-07-01",
        "tax_rate": 0,
        "lines": [{"description": "Service", "quantity": 3, "unit_price": 100}],
    })
    inv = resp.json()
    assert inv["subtotal"] == pytest.approx(300.0)
    assert inv["total"] == pytest.approx(300.0)


def test_invoice_empty_lines(client):
    """Invoice with no lines: subtotal and total = 0."""
    resp = client.post("/api/invoices/", json={
        "type": "invoice", "date": "2025-06-01", "due_date": "2025-07-01",
        "tax_rate": 20, "lines": [],
    })
    inv = resp.json()
    assert inv["subtotal"] == pytest.approx(0.0)
    assert inv["total"] == pytest.approx(0.0)


def test_invoice_number_sequence(client):
    """Invoice numbers must auto-increment."""
    inv1 = client.post("/api/invoices/", json={
        "type": "invoice", "date": "2025-06-01", "due_date": "2025-07-01",
        "tax_rate": 0, "lines": [{"description": "A", "quantity": 1, "unit_price": 100}],
    }).json()
    inv2 = client.post("/api/invoices/", json={
        "type": "invoice", "date": "2025-06-02", "due_date": "2025-07-02",
        "tax_rate": 0, "lines": [{"description": "B", "quantity": 1, "unit_price": 100}],
    }).json()
    # Numbers should be sequential
    assert inv1["number"] != inv2["number"]
    # Extract sequence numbers
    seq1 = int(inv1["number"].split("-")[-1])
    seq2 = int(inv2["number"].split("-")[-1])
    assert seq2 == seq1 + 1


def test_quote_to_invoice_conversion(client):
    """Converting a quote to invoice should change type and generate invoice number."""
    quote = client.post("/api/invoices/", json={
        "type": "quote", "date": "2025-06-01", "due_date": "2025-07-01",
        "tax_rate": 10,
        "lines": [{"description": "Devis", "quantity": 1, "unit_price": 500}],
    }).json()
    assert quote["type"] == "quote"
    assert quote["number"].startswith("DEV-")

    resp = client.post(f"/api/invoices/{quote['id']}/convert")
    assert resp.status_code == 200
    converted = resp.json()
    assert converted["type"] == "invoice"
    assert converted["number"].startswith("FAC-")
    # Amounts should be preserved
    assert converted["subtotal"] == pytest.approx(quote["subtotal"])
    assert converted["total"] == pytest.approx(quote["total"])


def test_convert_invoice_fails(client):
    """Cannot convert an invoice (only quotes)."""
    inv = client.post("/api/invoices/", json={
        "type": "invoice", "date": "2025-06-01", "due_date": "2025-07-01",
        "tax_rate": 0, "lines": [{"description": "X", "quantity": 1, "unit_price": 100}],
    }).json()
    resp = client.post(f"/api/invoices/{inv['id']}/convert")
    assert resp.status_code == 400


def test_invoice_update_recalculates_total(client):
    """Updating lines or tax_rate should recalculate subtotal and total."""
    inv = client.post("/api/invoices/", json={
        "type": "invoice", "date": "2025-06-01", "due_date": "2025-07-01",
        "tax_rate": 10,
        "lines": [{"description": "Initial", "quantity": 1, "unit_price": 100}],
    }).json()
    assert inv["total"] == pytest.approx(110.0)

    # Update with new lines
    resp = client.put(f"/api/invoices/{inv['id']}", json={
        "lines": [
            {"description": "New A", "quantity": 2, "unit_price": 200},
            {"description": "New B", "quantity": 1, "unit_price": 100},
        ],
    })
    updated = resp.json()
    assert updated["subtotal"] == pytest.approx(500.0)  # 2*200 + 1*100
    assert updated["total"] == pytest.approx(550.0)  # 500 * 1.10


# ============================================================
# MULTI-ACCOUNTS — transfer coherence
# ============================================================

def test_transfer_net_zero_on_global_balance(client):
    """A transfer between accounts must not affect global transactions balance."""
    # Get initial balance
    initial_bal = client.get("/api/transactions/balance").json()["balance"]

    # Create two accounts
    acc1 = client.post("/api/multi_accounts/", json={
        "name": "Courant", "type": "checking", "initial_balance": 5000,
    }).json()
    acc2 = client.post("/api/multi_accounts/", json={
        "name": "Epargne", "type": "savings", "initial_balance": 2000,
    }).json()

    # Transfer 1000 from acc1 to acc2
    client.post("/api/multi_accounts/transfers", json={
        "from_account_id": acc1["id"], "to_account_id": acc2["id"],
        "amount": 1000, "label": "Virement", "date": "2025-06-01",
    })

    # Global balance should be unchanged (transfer is +1000 and -1000)
    after_bal = client.get("/api/transactions/balance").json()["balance"]
    assert after_bal == pytest.approx(initial_bal)


def test_account_balances_after_transfer(client):
    """Account balances must reflect transfers correctly."""
    acc1 = client.post("/api/multi_accounts/", json={
        "name": "Courant", "type": "checking", "initial_balance": 5000,
    }).json()
    acc2 = client.post("/api/multi_accounts/", json={
        "name": "Epargne", "type": "savings", "initial_balance": 2000,
    }).json()

    client.post("/api/multi_accounts/transfers", json={
        "from_account_id": acc1["id"], "to_account_id": acc2["id"],
        "amount": 1500, "label": "Virement", "date": "2025-06-01",
    })

    balances = client.get("/api/multi_accounts/balances").json()
    bal1 = next(b for b in balances if b["id"] == acc1["id"])
    bal2 = next(b for b in balances if b["id"] == acc2["id"])
    assert bal1["balance"] == pytest.approx(3500.0)  # 5000 - 1500
    assert bal2["balance"] == pytest.approx(3500.0)  # 2000 + 1500


def test_transfer_to_self_rejected(client):
    """Transfer from account to itself must be rejected."""
    acc = client.post("/api/multi_accounts/", json={
        "name": "Test", "type": "checking", "initial_balance": 1000,
    }).json()
    resp = client.post("/api/multi_accounts/transfers", json={
        "from_account_id": acc["id"], "to_account_id": acc["id"],
        "amount": 100, "label": "Self", "date": "2025-06-01",
    })
    assert resp.status_code == 400


def test_transfer_zero_amount_rejected(client):
    """Transfer with amount <= 0 must be rejected."""
    acc1 = client.post("/api/multi_accounts/", json={
        "name": "A", "type": "checking", "initial_balance": 1000,
    }).json()
    acc2 = client.post("/api/multi_accounts/", json={
        "name": "B", "type": "savings", "initial_balance": 1000,
    }).json()
    resp = client.post("/api/multi_accounts/transfers", json={
        "from_account_id": acc1["id"], "to_account_id": acc2["id"],
        "amount": 0, "label": "Zero", "date": "2025-06-01",
    })
    assert resp.status_code == 400


# ============================================================
# RECURRING — generation coherence
# ============================================================

def test_recurring_generate_creates_transactions(client):
    """Generating recurring transactions must create real transactions visible in balance."""
    initial_bal = client.get("/api/transactions/balance").json()["balance"]

    # Create recurring with start_date far in the past so it generates immediately
    past_date = (date.today() - timedelta(days=60)).isoformat()
    client.post("/api/recurring/", json={
        "label": "Loyer mensuel", "amount": -800,
        "frequency": "monthly", "start_date": past_date, "active": 1,
    })

    # Generate — returns a list of created transactions
    resp = client.post("/api/recurring/generate")
    assert resp.status_code == 200
    generated = resp.json()
    assert isinstance(generated, list)
    assert len(generated) >= 1

    # Balance should reflect the new transactions
    new_bal = client.get("/api/transactions/balance").json()["balance"]
    expected_change = -800 * len(generated)
    assert new_bal == pytest.approx(initial_bal + expected_change)


def test_recurring_generate_idempotent(client):
    """Calling generate twice should not duplicate transactions."""
    past_date = (date.today() - timedelta(days=35)).isoformat()
    client.post("/api/recurring/", json={
        "label": "Abonnement", "amount": -50,
        "frequency": "monthly", "start_date": past_date, "active": 1,
    })

    first = client.post("/api/recurring/generate").json()
    assert len(first) >= 1
    second = client.post("/api/recurring/generate").json()
    assert len(second) == 0  # Nothing new to generate


def test_recurring_inactive_not_generated(client):
    """Inactive recurring templates must not generate transactions."""
    past_date = (date.today() - timedelta(days=60)).isoformat()
    client.post("/api/recurring/", json={
        "label": "Inactif", "amount": -100,
        "frequency": "monthly", "start_date": past_date, "active": 0,
    })
    result = client.post("/api/recurring/generate").json()
    assert isinstance(result, list)
    assert len(result) == 0


# ============================================================
# ANNOTATIONS
# ============================================================

def test_annotations_on_transaction(client):
    """Annotations are correctly linked to their transaction."""
    tx = client.post("/api/transactions/", json={
        "date": "2025-06-01", "label": "Test", "amount": 100,
    }).json()

    client.post(f"/api/annotations/transaction/{tx['id']}", json={"content": "Note 1"})
    client.post(f"/api/annotations/transaction/{tx['id']}", json={"content": "Note 2"})

    annotations = client.get(f"/api/annotations/transaction/{tx['id']}").json()
    assert len(annotations) == 2
    contents = [a["content"] for a in annotations]
    assert "Note 1" in contents
    assert "Note 2" in contents


def test_annotations_on_nonexistent_transaction(client):
    """Annotating a non-existent transaction must return 404."""
    resp = client.post("/api/annotations/transaction/99999", json={"content": "Orphan"})
    assert resp.status_code == 404


# ============================================================
# CATEGORIES — tree coherence
# ============================================================

def test_categories_tree_parent_child(client):
    """Category tree must show correct parent-child hierarchy."""
    parent = client.post("/api/categories/", json={
        "name": "Depenses", "color": "#f00", "icon": "folder", "position": 1,
    }).json()
    child = client.post("/api/categories/", json={
        "name": "Fournitures", "color": "#0f0", "icon": "box",
        "position": 2, "parent_id": parent["id"],
    }).json()

    tree = client.get("/api/categories/tree").json()
    parent_node = next((n for n in tree if n["id"] == parent["id"]), None)
    assert parent_node is not None
    assert len(parent_node["children"]) == 1
    assert parent_node["children"][0]["id"] == child["id"]


def test_categories_tree_orphan_at_root(client):
    """Category with non-existent parent_id should appear at root level."""
    cat = client.post("/api/categories/", json={
        "name": "Orphelin", "color": "#000", "icon": "x",
        "position": 1, "parent_id": 99999,
    }).json()

    tree = client.get("/api/categories/tree").json()
    root_ids = [n["id"] for n in tree]
    assert cat["id"] in root_ids
