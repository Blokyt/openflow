"""Coherence tests: aggregation calculations across modules."""
import csv
import io
import pytest


# ============================================================
# BUDGET — legacy tests removed; budget module rewritten in 1.2.0
# (see tests/backend/test_budget.py and test_coherence_budget.py)
# ============================================================


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
