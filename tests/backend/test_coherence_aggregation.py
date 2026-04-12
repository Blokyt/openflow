"""Coherence tests: aggregation calculations across modules."""
import csv
import io
import pytest


# ============================================================
# BUDGET
# ============================================================

def test_budget_status_spent_matches_transactions(client):
    """Budget spent must equal sum of matching transactions."""
    # Create category
    cat = client.post("/api/categories/", json={"name": "Fournitures", "color": "#ff0000", "icon": "box", "position": 1}).json()
    cat_id = cat["id"]
    # Create budget for this category
    client.post("/api/budget/", json={
        "category_id": cat_id, "period_start": "2025-01-01",
        "period_end": "2025-12-31", "amount": 5000,
    })
    # Create transactions in this category
    client.post("/api/transactions/", json={"date": "2025-03-01", "label": "Achat 1", "amount": -200.0, "category_id": cat_id})
    client.post("/api/transactions/", json={"date": "2025-06-01", "label": "Achat 2", "amount": -300.0, "category_id": cat_id})
    # Transaction outside period — should NOT count
    client.post("/api/transactions/", json={"date": "2024-12-31", "label": "Ancien", "amount": -100.0, "category_id": cat_id})

    status = client.get("/api/budget/status").json()
    assert len(status) >= 1
    budget = status[0]
    # spent should be -500 (sum of -200 + -300, not the 2024 one)
    assert budget["spent"] == pytest.approx(-500.0)
    # remaining = 5000 - abs(-500) = 4500
    assert budget["remaining"] == pytest.approx(4500.0)


def test_budget_status_no_transactions(client):
    """Budget with no matching transactions: spent=0, remaining=full amount."""
    cat = client.post("/api/categories/", json={"name": "Vide", "color": "#000", "icon": "x", "position": 1}).json()
    client.post("/api/budget/", json={
        "category_id": cat["id"], "period_start": "2025-01-01",
        "period_end": "2025-12-31", "amount": 1000,
    })
    status = client.get("/api/budget/status").json()
    budget = status[0]
    assert budget["spent"] == pytest.approx(0.0)
    assert budget["remaining"] == pytest.approx(1000.0)


def test_budget_status_ignores_other_categories(client):
    """Budget for category A must not count transactions in category B."""
    cat_a = client.post("/api/categories/", json={"name": "A", "color": "#f00", "icon": "a", "position": 1}).json()
    cat_b = client.post("/api/categories/", json={"name": "B", "color": "#0f0", "icon": "b", "position": 2}).json()
    client.post("/api/budget/", json={
        "category_id": cat_a["id"], "period_start": "2025-01-01",
        "period_end": "2025-12-31", "amount": 1000,
    })
    # Transaction in category B — should NOT affect budget A
    client.post("/api/transactions/", json={"date": "2025-06-01", "label": "B tx", "amount": -500.0, "category_id": cat_b["id"]})
    # Transaction in category A
    client.post("/api/transactions/", json={"date": "2025-06-01", "label": "A tx", "amount": -100.0, "category_id": cat_a["id"]})

    status = client.get("/api/budget/status").json()
    budget = [b for b in status if b["category_id"] == cat_a["id"]][0]
    assert budget["spent"] == pytest.approx(-100.0)


# ============================================================
# DIVISIONS
# ============================================================

def test_division_summary_matches_transactions(client):
    """Division summary must match manual sum of its transactions."""
    div = client.post("/api/divisions/", json={"name": "Marketing", "description": "dept"}).json()
    div_id = div["id"]
    client.post("/api/transactions/", json={"date": "2025-06-01", "label": "Revenu", "amount": 800.0, "division_id": div_id})
    client.post("/api/transactions/", json={"date": "2025-06-02", "label": "Depense", "amount": -300.0, "division_id": div_id})

    summary = client.get(f"/api/divisions/{div_id}/summary").json()
    assert summary["income"] == pytest.approx(800.0)
    assert summary["expenses"] == pytest.approx(-300.0)
    assert summary["balance"] == pytest.approx(500.0)
    # Verify: balance = income + expenses
    assert summary["balance"] == pytest.approx(summary["income"] + summary["expenses"])


def test_division_summary_empty(client):
    """Division with no transactions: all zeros."""
    div = client.post("/api/divisions/", json={"name": "Vide", "description": ""}).json()
    summary = client.get(f"/api/divisions/{div['id']}/summary").json()
    assert summary["income"] == pytest.approx(0.0)
    assert summary["expenses"] == pytest.approx(0.0)
    assert summary["balance"] == pytest.approx(0.0)


def test_division_summary_ignores_other_divisions(client):
    """Division summary must not include transactions from other divisions."""
    div_a = client.post("/api/divisions/", json={"name": "A", "description": ""}).json()
    div_b = client.post("/api/divisions/", json={"name": "B", "description": ""}).json()
    client.post("/api/transactions/", json={"date": "2025-06-01", "label": "A", "amount": 100.0, "division_id": div_a["id"]})
    client.post("/api/transactions/", json={"date": "2025-06-01", "label": "B", "amount": 999.0, "division_id": div_b["id"]})

    summary_a = client.get(f"/api/divisions/{div_a['id']}/summary").json()
    assert summary_a["income"] == pytest.approx(100.0)
    assert summary_a["balance"] == pytest.approx(100.0)


# ============================================================
# EXPORT
# ============================================================

def test_export_summary_csv_totals(client):
    """Export summary CSV per-category totals must match transaction data."""
    cat = client.post("/api/categories/", json={"name": "Services", "color": "#00f", "icon": "s", "position": 1}).json()
    client.post("/api/transactions/", json={"date": "2025-06-01", "label": "Revenu", "amount": 200.0, "category_id": cat["id"]})
    client.post("/api/transactions/", json={"date": "2025-06-02", "label": "Depense", "amount": -50.0, "category_id": cat["id"]})

    resp = client.get("/api/export/summary/csv")
    assert resp.status_code == 200
    reader = csv.DictReader(io.StringIO(resp.text))
    rows = list(reader)
    services_row = next((r for r in rows if r["category_name"] == "Services"), None)
    assert services_row is not None
    assert float(services_row["total_income"]) == pytest.approx(200.0)
    assert float(services_row["total_expenses"]) == pytest.approx(-50.0)
    assert float(services_row["net"]) == pytest.approx(150.0)


def test_export_summary_csv_uncategorized(client):
    """Transactions without category appear as 'Sans categorie'."""
    client.post("/api/transactions/", json={"date": "2025-06-01", "label": "Inconnu", "amount": 100.0})

    resp = client.get("/api/export/summary/csv")
    reader = csv.DictReader(io.StringIO(resp.text))
    rows = list(reader)
    uncat = next((r for r in rows if r["category_name"] == "Sans categorie"), None)
    assert uncat is not None
    assert float(uncat["total_income"]) == pytest.approx(100.0)


def test_export_transactions_csv_date_filter(client):
    """Export CSV with date filter must only include matching transactions."""
    client.post("/api/transactions/", json={"date": "2025-01-15", "label": "Janvier", "amount": 100.0})
    client.post("/api/transactions/", json={"date": "2025-06-15", "label": "Juin", "amount": 200.0})
    client.post("/api/transactions/", json={"date": "2025-12-15", "label": "Decembre", "amount": 300.0})

    resp = client.get("/api/export/transactions/csv?date_from=2025-06-01&date_to=2025-06-30")
    assert resp.status_code == 200
    reader = csv.DictReader(io.StringIO(resp.text))
    rows = list(reader)
    assert len(rows) == 1
    assert rows[0]["label"] == "Juin"


def test_export_empty_db(client):
    """Export with no transactions: CSV has headers only."""
    resp = client.get("/api/export/transactions/csv")
    assert resp.status_code == 200
    lines = resp.text.strip().split("\n")
    assert len(lines) == 1  # Header only


# ============================================================
# GRANTS
# ============================================================

def test_grants_summary_arithmetic(client):
    """Grants summary: total_pending = total_granted - total_received."""
    resp = client.post("/api/grants/", json={
        "name": "Subvention A", "amount_granted": 10000,
        "amount_received": 3000, "status": "active", "date_granted": "2025-01-15",
    })
    assert resp.status_code == 201, resp.text
    resp = client.post("/api/grants/", json={
        "name": "Subvention B", "amount_granted": 5000,
        "amount_received": 5000, "status": "completed", "date_granted": "2025-03-01",
    })
    assert resp.status_code == 201, resp.text

    summary = client.get("/api/grants/summary").json()
    assert summary["total_granted"] == pytest.approx(15000.0)
    assert summary["total_received"] == pytest.approx(8000.0)
    assert summary["total_pending"] == pytest.approx(7000.0)
    # Verify arithmetic identity
    assert summary["total_pending"] == pytest.approx(
        summary["total_granted"] - summary["total_received"]
    )


def test_grants_summary_empty(client):
    """No grants: all zeros."""
    summary = client.get("/api/grants/summary").json()
    assert summary["total_granted"] == pytest.approx(0.0)
    assert summary["total_received"] == pytest.approx(0.0)
    assert summary["total_pending"] == pytest.approx(0.0)


# ============================================================
# REIMBURSEMENTS
# ============================================================

def test_reimbursements_summary_groups_by_person(client):
    """Summary groups pending reimbursements by person with correct totals."""
    client.post("/api/reimbursements/", json={"person_name": "Alice", "amount": 150, "description": "Taxi", "status": "pending"})
    client.post("/api/reimbursements/", json={"person_name": "Alice", "amount": 50, "description": "Repas", "status": "pending"})
    client.post("/api/reimbursements/", json={"person_name": "Bob", "amount": 200, "description": "Train", "status": "pending"})
    # Reimbursed — should NOT appear in summary
    client.post("/api/reimbursements/", json={"person_name": "Alice", "amount": 100, "description": "Ancien", "status": "reimbursed"})

    summary = client.get("/api/reimbursements/summary").json()
    alice = next((s for s in summary if s["person_name"] == "Alice"), None)
    bob = next((s for s in summary if s["person_name"] == "Bob"), None)
    assert alice is not None
    assert alice["total_pending"] == pytest.approx(200.0)
    assert alice["count"] == 2
    assert bob is not None
    assert bob["total_pending"] == pytest.approx(200.0)
    assert bob["count"] == 1


def test_reimbursements_summary_empty(client):
    """No pending reimbursements: empty summary."""
    summary = client.get("/api/reimbursements/summary").json()
    assert summary == []


# ============================================================
# FEC EXPORT
# ============================================================

def test_fec_export_debit_credit_exclusive(client):
    """In FEC export, each row must have debit OR credit, never both non-zero."""
    client.post("/api/transactions/", json={"date": "2025-06-01", "label": "Revenu", "amount": 500.0})
    client.post("/api/transactions/", json={"date": "2025-06-02", "label": "Depense", "amount": -300.0})

    resp = client.get("/api/fec_export/generate?fiscal_year=2025")
    assert resp.status_code == 200
    reader = csv.DictReader(io.StringIO(resp.text), delimiter="|")
    rows = list(reader)
    assert len(rows) == 2
    for row in rows:
        debit = float(row["Debit"])
        credit = float(row["Credit"])
        # One must be zero
        assert debit == 0.0 or credit == 0.0
        # They can't both be zero (unless amount=0)
        assert debit > 0 or credit > 0


def test_fec_export_income_is_debit(client):
    """Positive amounts (income) should be Debit entries."""
    client.post("/api/transactions/", json={"date": "2025-06-01", "label": "Vente", "amount": 1000.0})
    resp = client.get("/api/fec_export/generate?fiscal_year=2025")
    reader = csv.DictReader(io.StringIO(resp.text), delimiter="|")
    rows = list(reader)
    assert len(rows) == 1
    assert float(rows[0]["Debit"]) == pytest.approx(1000.0)
    assert float(rows[0]["Credit"]) == pytest.approx(0.0)


def test_fec_export_expense_is_credit(client):
    """Negative amounts (expenses) should be Credit entries."""
    client.post("/api/transactions/", json={"date": "2025-06-01", "label": "Achat", "amount": -500.0})
    resp = client.get("/api/fec_export/generate?fiscal_year=2025")
    reader = csv.DictReader(io.StringIO(resp.text), delimiter="|")
    rows = list(reader)
    assert len(rows) == 1
    assert float(rows[0]["Debit"]) == pytest.approx(0.0)
    assert float(rows[0]["Credit"]) == pytest.approx(500.0)


def test_fec_export_fiscal_year_filter(client):
    """FEC export with fiscal_year must only include transactions from that year."""
    client.post("/api/transactions/", json={"date": "2025-06-01", "label": "2025", "amount": 100.0})
    client.post("/api/transactions/", json={"date": "2024-06-01", "label": "2024", "amount": 200.0})

    resp = client.get("/api/fec_export/generate?fiscal_year=2025")
    reader = csv.DictReader(io.StringIO(resp.text), delimiter="|")
    rows = list(reader)
    assert len(rows) == 1
    assert "2025" in rows[0].get("EcritureDate", rows[0].get("JournalDate", ""))
