"""Tests for the forecasting module API."""
import os
import sys
from datetime import date
from dateutil.relativedelta import relativedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_transaction(client, date_str: str, amount: float, label: str = "Test tx"):
    payload = {"date": date_str, "label": label, "amount": amount}
    resp = client.post("/api/transactions/", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def month_ago(n: int) -> str:
    """Return first day of the month N months in the past (YYYY-MM-DD)."""
    d = date.today().replace(day=1) - relativedelta(months=n)
    return d.isoformat()


# ---------------------------------------------------------------------------
# Structure tests
# ---------------------------------------------------------------------------

def test_projection_returns_correct_structure(client):
    """GET /projection must return the expected top-level keys."""
    resp = client.get("/api/forecasting/projection")
    assert resp.status_code == 200
    data = resp.json()
    assert "current_balance" in data
    assert "avg_monthly_income" in data
    assert "avg_monthly_expenses" in data
    assert "projection" in data
    assert isinstance(data["projection"], list)


def test_projection_default_months_is_6(client):
    """Without ?months param, projection must contain 6 entries."""
    resp = client.get("/api/forecasting/projection")
    assert resp.status_code == 200
    assert len(resp.json()["projection"]) == 6


def test_projection_custom_months(client):
    """?months=3 returns exactly 3 projection entries."""
    resp = client.get("/api/forecasting/projection?months=3")
    assert resp.status_code == 200
    assert len(resp.json()["projection"]) == 3


def test_projection_month_labels_are_sequential(client):
    """Projection months must be consecutive, starting next month."""
    resp = client.get("/api/forecasting/projection?months=6")
    assert resp.status_code == 200
    projection = resp.json()["projection"]
    today = date.today()
    for i, entry in enumerate(projection, start=1):
        expected = (today.replace(day=1) + relativedelta(months=i)).strftime("%Y-%m")
        assert entry["month"] == expected, f"Month mismatch at index {i}"


def test_projection_each_entry_has_month_and_balance(client):
    """Each projection entry must have 'month' and 'projected_balance' keys."""
    resp = client.get("/api/forecasting/projection")
    assert resp.status_code == 200
    for entry in resp.json()["projection"]:
        assert "month" in entry
        assert "projected_balance" in entry
        assert isinstance(entry["projected_balance"], (int, float))


# ---------------------------------------------------------------------------
# Logic tests — inject known transactions then verify computation
# ---------------------------------------------------------------------------

def test_projection_with_income_transactions(client):
    """With income transactions in the window, avg_monthly_income must be > 0."""
    # Insert 6 income transactions spread across the last 6 months
    for i in range(1, 7):
        make_transaction(client, month_ago(i), 1000.0, label=f"Income fc test m{i}")

    resp = client.get("/api/forecasting/projection")
    assert resp.status_code == 200
    data = resp.json()
    assert data["avg_monthly_income"] > 0


def test_projection_with_expense_transactions(client):
    """With expense transactions in the window, avg_monthly_expenses must be > 0."""
    for i in range(1, 7):
        make_transaction(client, month_ago(i), -500.0, label=f"Expense fc test m{i}")

    resp = client.get("/api/forecasting/projection")
    assert resp.status_code == 200
    data = resp.json()
    assert data["avg_monthly_expenses"] > 0


def test_projection_balance_increases_with_net_positive_flow(client):
    """Each projected month must grow when avg_income > avg_expenses.

    The shared DB may have pre-existing transactions that make the absolute
    balance negative.  We therefore only verify that consecutive projected
    months are increasing (i.e. the step delta is positive), which is
    determined solely by avg_monthly_income - avg_monthly_expenses.
    """
    # Inject very dominant income: 10 000 income vs 100 expenses per month.
    # With this ratio the net is +9 900/month regardless of pre-existing data.
    for i in range(1, 7):
        make_transaction(client, month_ago(i), 10_000.0, label=f"BigIncome2 fc {i}")
        make_transaction(client, month_ago(i), -100.0, label=f"SmallExp2 fc {i}")

    resp = client.get("/api/forecasting/projection?months=6")
    assert resp.status_code == 200
    data = resp.json()
    projection = data["projection"]

    # Verify step-by-step growth (positive delta each month)
    balances = [data["current_balance"]] + [e["projected_balance"] for e in projection]
    for idx in range(1, len(balances)):
        assert balances[idx] > balances[idx - 1], (
            f"Expected balance to grow at step {idx}: "
            f"{balances[idx]} > {balances[idx - 1]}"
        )


def test_projection_balance_decreases_with_net_negative_flow(client):
    """Each projected month must shrink when avg_expenses > avg_income.

    Same isolation strategy: inject very dominant expenses so the net delta
    is clearly negative regardless of pre-existing DB content.
    """
    for i in range(1, 7):
        make_transaction(client, month_ago(i), 100.0, label=f"SmallInc2 fc {i}")
        make_transaction(client, month_ago(i), -10_000.0, label=f"BigExp2 fc {i}")

    resp = client.get("/api/forecasting/projection?months=6")
    assert resp.status_code == 200
    data = resp.json()
    projection = data["projection"]

    balances = [data["current_balance"]] + [e["projected_balance"] for e in projection]
    for idx in range(1, len(balances)):
        assert balances[idx] < balances[idx - 1], (
            f"Expected balance to shrink at step {idx}: "
            f"{balances[idx]} < {balances[idx - 1]}"
        )
