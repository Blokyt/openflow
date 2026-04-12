"""Tests for the fec_export module API."""
import csv
import io
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_transaction(client, **kwargs):
    payload = {
        "date": "2025-06-15",
        "label": "FEC Test TX",
        "amount": 100.0,
    }
    payload.update(kwargs)
    resp = client.post("/api/transactions/", json=payload)
    assert resp.status_code == 201
    return resp.json()


def parse_fec_csv(content: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(content), delimiter="|")
    return list(reader)


FEC_COLUMNS = [
    "JournalCode", "JournalLib", "EcritureNum", "EcritureDate",
    "CompteNum", "CompteLib", "CompAuxNum", "CompAuxLib",
    "PieceRef", "PieceDate", "EcritureLib", "Debit", "Credit",
    "EcrtureLet", "DateLet", "ValidDate", "MontantDevise", "Idevise",
]


# ---------------------------------------------------------------------------
# GET /api/fec_export/generate
# ---------------------------------------------------------------------------

def test_generate_returns_200(client):
    response = client.get("/api/fec_export/generate")
    assert response.status_code == 200


def test_generate_content_type_is_csv(client):
    response = client.get("/api/fec_export/generate")
    assert "text/csv" in response.headers["content-type"]


def test_generate_content_disposition_attachment(client):
    response = client.get("/api/fec_export/generate")
    assert "attachment" in response.headers["content-disposition"]


def test_generate_with_fiscal_year_filename(client):
    response = client.get("/api/fec_export/generate?fiscal_year=2025")
    assert "FEC_2025.csv" in response.headers["content-disposition"]


def test_generate_has_all_fec_headers(client):
    make_transaction(client, date="2025-03-01", label="Header Check", amount=50.0)
    response = client.get("/api/fec_export/generate?fiscal_year=2025")
    rows = parse_fec_csv(response.text)
    assert len(rows) > 0
    for col in FEC_COLUMNS:
        assert col in rows[0], f"Missing FEC column: {col}"


def test_generate_income_uses_ve_journal(client):
    make_transaction(client, date="2025-04-01", label="Income TX", amount=200.0)
    response = client.get("/api/fec_export/generate?fiscal_year=2025")
    rows = parse_fec_csv(response.text)
    income_rows = [r for r in rows if r["EcritureLib"] == "Income TX"]
    assert len(income_rows) > 0
    assert income_rows[0]["JournalCode"] == "VE"
    assert income_rows[0]["JournalLib"] == "Ventes"
    assert income_rows[0]["CompteNum"] == "411000"


def test_generate_expense_uses_ac_journal(client):
    make_transaction(client, date="2025-04-02", label="Expense TX", amount=-150.0)
    response = client.get("/api/fec_export/generate?fiscal_year=2025")
    rows = parse_fec_csv(response.text)
    expense_rows = [r for r in rows if r["EcritureLib"] == "Expense TX"]
    assert len(expense_rows) > 0
    assert expense_rows[0]["JournalCode"] == "AC"
    assert expense_rows[0]["JournalLib"] == "Achats"
    assert expense_rows[0]["CompteNum"] == "401000"


def test_generate_income_debit_not_credit(client):
    make_transaction(client, date="2025-05-01", label="Debit Check", amount=300.0)
    response = client.get("/api/fec_export/generate?fiscal_year=2025")
    rows = parse_fec_csv(response.text)
    row = next((r for r in rows if r["EcritureLib"] == "Debit Check"), None)
    assert row is not None
    assert float(row["Debit"]) == pytest.approx(300.0)
    assert float(row["Credit"]) == pytest.approx(0.0)


def test_generate_expense_credit_not_debit(client):
    make_transaction(client, date="2025-05-02", label="Credit Check", amount=-75.0)
    response = client.get("/api/fec_export/generate?fiscal_year=2025")
    rows = parse_fec_csv(response.text)
    row = next((r for r in rows if r["EcritureLib"] == "Credit Check"), None)
    assert row is not None
    assert float(row["Credit"]) == pytest.approx(75.0)
    assert float(row["Debit"]) == pytest.approx(0.0)


def test_generate_date_formatted_yyyymmdd(client):
    make_transaction(client, date="2025-07-20", label="Date Format Check", amount=10.0)
    response = client.get("/api/fec_export/generate?fiscal_year=2025")
    rows = parse_fec_csv(response.text)
    row = next((r for r in rows if r["EcritureLib"] == "Date Format Check"), None)
    assert row is not None
    assert row["EcritureDate"] == "20250720"
    assert row["PieceDate"] == "20250720"


def test_generate_fiscal_year_filter(client):
    make_transaction(client, date="2025-01-15", label="In 2025", amount=50.0)
    make_transaction(client, date="2024-12-31", label="In 2024", amount=50.0)
    response = client.get("/api/fec_export/generate?fiscal_year=2025")
    rows = parse_fec_csv(response.text)
    labels = [r["EcritureLib"] for r in rows]
    assert "In 2025" in labels
    assert "In 2024" not in labels


def test_generate_no_fiscal_year_returns_all(client):
    make_transaction(client, date="2023-06-01", label="Old TX FEC", amount=10.0)
    make_transaction(client, date="2025-06-01", label="New TX FEC", amount=20.0)
    response = client.get("/api/fec_export/generate")
    rows = parse_fec_csv(response.text)
    labels = [r["EcritureLib"] for r in rows]
    assert "Old TX FEC" in labels
    assert "New TX FEC" in labels


def test_generate_ecriture_num_format(client):
    make_transaction(client, date="2025-08-01", label="EcritureNum Test", amount=100.0)
    response = client.get("/api/fec_export/generate?fiscal_year=2025")
    rows = parse_fec_csv(response.text)
    row = next((r for r in rows if r["EcritureLib"] == "EcritureNum Test"), None)
    assert row is not None
    # EcritureNum should be VE or AC followed by 6 digits
    assert len(row["EcritureNum"]) == 8
    assert row["EcritureNum"][:2] in ("VE", "AC")
