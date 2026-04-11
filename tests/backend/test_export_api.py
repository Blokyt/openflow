"""Tests for the export module API."""
import csv
import io
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app


@pytest.fixture
def client():
    app = create_app(config_path="config.yaml", db_path="data/openflow.db")
    return TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_transaction(client, **kwargs):
    payload = {
        "date": "2026-03-15",
        "label": "Test TX",
        "amount": 100.0,
    }
    payload.update(kwargs)
    resp = client.post("/api/transactions/", json=payload)
    assert resp.status_code == 201
    return resp.json()


def parse_csv(content: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(content))
    return list(reader)


# ---------------------------------------------------------------------------
# GET /api/export/transactions/csv
# ---------------------------------------------------------------------------

def test_transactions_csv_returns_200(client):
    response = client.get("/api/export/transactions/csv")
    assert response.status_code == 200


def test_transactions_csv_content_type(client):
    response = client.get("/api/export/transactions/csv")
    assert "text/csv" in response.headers["content-type"]


def test_transactions_csv_content_disposition(client):
    response = client.get("/api/export/transactions/csv")
    assert "attachment" in response.headers["content-disposition"]
    assert "transactions.csv" in response.headers["content-disposition"]


def test_transactions_csv_has_header_row(client):
    make_transaction(client, label="CSV Header Test")
    response = client.get("/api/export/transactions/csv")
    rows = parse_csv(response.text)
    assert len(rows) > 0
    assert "id" in rows[0]
    assert "date" in rows[0]
    assert "label" in rows[0]
    assert "amount" in rows[0]


def test_transactions_csv_contains_data(client):
    make_transaction(client, label="CSV Data Row", amount=42.0)
    response = client.get("/api/export/transactions/csv")
    rows = parse_csv(response.text)
    labels = [r["label"] for r in rows]
    assert "CSV Data Row" in labels


def test_transactions_csv_date_filter_from(client):
    make_transaction(client, date="2026-01-10", label="Before Filter", amount=10.0)
    make_transaction(client, date="2026-06-20", label="After Filter", amount=20.0)
    response = client.get("/api/export/transactions/csv?date_from=2026-06-01")
    assert response.status_code == 200
    rows = parse_csv(response.text)
    dates = [r["date"] for r in rows]
    assert all(d >= "2026-06-01" for d in dates)
    assert not any(d < "2026-06-01" for d in dates)


def test_transactions_csv_date_filter_to(client):
    make_transaction(client, date="2026-02-05", label="Early TX", amount=5.0)
    make_transaction(client, date="2026-11-25", label="Late TX", amount=55.0)
    response = client.get("/api/export/transactions/csv?date_to=2026-06-30")
    assert response.status_code == 200
    rows = parse_csv(response.text)
    dates = [r["date"] for r in rows]
    assert all(d <= "2026-06-30" for d in dates)


def test_transactions_csv_date_filter_range(client):
    make_transaction(client, date="2026-03-01", label="In Range", amount=1.0)
    make_transaction(client, date="2026-07-01", label="Out Range", amount=2.0)
    response = client.get("/api/export/transactions/csv?date_from=2026-01-01&date_to=2026-05-31")
    assert response.status_code == 200
    rows = parse_csv(response.text)
    labels = [r["label"] for r in rows]
    assert "In Range" in labels
    assert "Out Range" not in labels


# ---------------------------------------------------------------------------
# GET /api/export/transactions/json
# ---------------------------------------------------------------------------

def test_transactions_json_returns_200(client):
    response = client.get("/api/export/transactions/json")
    assert response.status_code == 200


def test_transactions_json_is_valid_array(client):
    response = client.get("/api/export/transactions/json")
    data = json.loads(response.text)
    assert isinstance(data, list)


def test_transactions_json_content_disposition(client):
    response = client.get("/api/export/transactions/json")
    assert "attachment" in response.headers["content-disposition"]
    assert "transactions.json" in response.headers["content-disposition"]


def test_transactions_json_contains_data(client):
    make_transaction(client, label="JSON Export TX", amount=77.0)
    response = client.get("/api/export/transactions/json")
    data = json.loads(response.text)
    labels = [tx["label"] for tx in data]
    assert "JSON Export TX" in labels


def test_transactions_json_record_has_fields(client):
    make_transaction(client, label="JSON Fields", amount=33.0)
    response = client.get("/api/export/transactions/json")
    data = json.loads(response.text)
    assert len(data) > 0
    record = next(r for r in data if r["label"] == "JSON Fields")
    assert "id" in record
    assert "date" in record
    assert "amount" in record


def test_transactions_json_date_filter(client):
    make_transaction(client, date="2026-04-01", label="April JSON", amount=4.0)
    make_transaction(client, date="2026-09-01", label="Sept JSON", amount=9.0)
    response = client.get("/api/export/transactions/json?date_from=2026-08-01")
    assert response.status_code == 200
    data = json.loads(response.text)
    labels = [tx["label"] for tx in data]
    assert "Sept JSON" in labels
    assert "April JSON" not in labels


# ---------------------------------------------------------------------------
# GET /api/export/summary/csv
# ---------------------------------------------------------------------------

def test_summary_csv_returns_200(client):
    response = client.get("/api/export/summary/csv")
    assert response.status_code == 200


def test_summary_csv_content_type(client):
    response = client.get("/api/export/summary/csv")
    assert "text/csv" in response.headers["content-type"]


def test_summary_csv_content_disposition(client):
    response = client.get("/api/export/summary/csv")
    assert "attachment" in response.headers["content-disposition"]
    assert "summary.csv" in response.headers["content-disposition"]


def test_summary_csv_has_expected_columns(client):
    # Create a transaction so there's at least one row
    make_transaction(client, label="Summary Col Check", amount=50.0)
    response = client.get("/api/export/summary/csv")
    rows = parse_csv(response.text)
    assert len(rows) > 0
    assert "category_name" in rows[0]
    assert "total_income" in rows[0]
    assert "total_expenses" in rows[0]
    assert "net" in rows[0]


def test_summary_csv_income_expense_net(client):
    """Create a category with one income and one expense, verify summary values."""
    cat_resp = client.post("/api/categories/", json={"name": "Export Test Cat"})
    assert cat_resp.status_code == 201
    cat_id = cat_resp.json()["id"]

    make_transaction(client, date="2026-05-01", label="Income", amount=200.0, category_id=cat_id)
    make_transaction(client, date="2026-05-02", label="Expense", amount=-80.0, category_id=cat_id)

    response = client.get("/api/export/summary/csv")
    assert response.status_code == 200
    rows = parse_csv(response.text)

    row = next((r for r in rows if r["category_name"] == "Export Test Cat"), None)
    assert row is not None
    assert float(row["total_income"]) == pytest.approx(200.0)
    assert float(row["total_expenses"]) == pytest.approx(-80.0)
    assert float(row["net"]) == pytest.approx(120.0)


def test_summary_csv_date_filter(client):
    cat_resp = client.post("/api/categories/", json={"name": "Summary Filter Cat"})
    assert cat_resp.status_code == 201
    cat_id = cat_resp.json()["id"]

    make_transaction(client, date="2026-01-15", label="Jan", amount=100.0, category_id=cat_id)
    make_transaction(client, date="2026-08-15", label="Aug", amount=300.0, category_id=cat_id)

    # Filter to only January
    response = client.get("/api/export/summary/csv?date_from=2026-01-01&date_to=2026-03-31")
    assert response.status_code == 200
    rows = parse_csv(response.text)

    row = next((r for r in rows if r["category_name"] == "Summary Filter Cat"), None)
    assert row is not None
    assert float(row["total_income"]) == pytest.approx(100.0)
    # August transaction should not be included
    assert float(row["net"]) == pytest.approx(100.0)
