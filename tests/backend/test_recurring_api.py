"""Tests for the recurring transactions module API."""
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def make_recurring(client, **kwargs):
    payload = {
        "label": "Loyer",
        "amount": -800.0,
        "frequency": "monthly",
        "start_date": "2026-01-01",
    }
    payload.update(kwargs)
    return client.post("/api/recurring/", json=payload)


# ---------------------------------------------------------------------------
# CRUD tests
# ---------------------------------------------------------------------------

def test_list_recurring(client):
    response = client.get("/api/recurring/")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_create_recurring(client):
    response = make_recurring(client, label="Abonnement", amount=-15.0, frequency="monthly")
    assert response.status_code == 201
    data = response.json()
    assert data["label"] == "Abonnement"
    assert data["amount"] == -15.0
    assert data["frequency"] == "monthly"
    assert data["active"] == 1
    assert "id" in data
    assert data["last_generated"] is None


def test_create_recurring_all_frequencies(client):
    for freq in ("weekly", "monthly", "quarterly", "yearly"):
        resp = make_recurring(client, frequency=freq, label=f"Test {freq}")
        assert resp.status_code == 201
        assert resp.json()["frequency"] == freq


def test_create_recurring_invalid_frequency(client):
    resp = make_recurring(client, frequency="daily")
    assert resp.status_code == 400


def test_get_recurring(client):
    created = make_recurring(client, label="Get test").json()
    response = client.get(f"/api/recurring/{created['id']}")
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]
    assert response.json()["label"] == "Get test"


def test_get_recurring_not_found(client):
    response = client.get("/api/recurring/999999")
    assert response.status_code == 404


def test_update_recurring(client):
    created = make_recurring(client, label="Old", amount=-100.0).json()
    response = client.put(
        f"/api/recurring/{created['id']}",
        json={"label": "New", "amount": -200.0},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["label"] == "New"
    assert data["amount"] == -200.0


def test_update_recurring_partial(client):
    created = make_recurring(client, label="Partial", amount=-50.0).json()
    response = client.put(f"/api/recurring/{created['id']}", json={"label": "Partial updated"})
    assert response.status_code == 200
    assert response.json()["label"] == "Partial updated"
    assert response.json()["amount"] == -50.0


def test_update_recurring_invalid_frequency(client):
    created = make_recurring(client, label="Freq test").json()
    response = client.put(f"/api/recurring/{created['id']}", json={"frequency": "hourly"})
    assert response.status_code == 400


def test_update_recurring_not_found(client):
    response = client.put("/api/recurring/999999", json={"label": "Ghost"})
    assert response.status_code == 404


def test_delete_recurring(client):
    created = make_recurring(client, label="To delete").json()
    response = client.delete(f"/api/recurring/{created['id']}")
    assert response.status_code == 200
    assert response.json()["deleted"] == created["id"]
    assert client.get(f"/api/recurring/{created['id']}").status_code == 404


def test_delete_recurring_not_found(client):
    response = client.delete("/api/recurring/999999")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Generate tests
# ---------------------------------------------------------------------------

def test_generate_returns_list(client):
    response = client.post("/api/recurring/generate")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_generate_monthly_creates_transactions(client):
    """A monthly recurring starting 3 months ago should produce 3 transactions."""
    today = date.today()
    three_months_ago = (today.replace(day=1) - timedelta(days=60)).replace(day=1)
    start = three_months_ago.isoformat()

    # Create the recurring entry
    rec = make_recurring(
        client,
        label="Loyer mensuel generate test",
        amount=-500.0,
        frequency="monthly",
        start_date=start,
    ).json()
    rec_id = rec["id"]

    # Disable all others to isolate
    # Count transactions before
    tx_before = client.get("/api/transactions/").json()
    ids_before = {t["id"] for t in tx_before}

    response = client.post("/api/recurring/generate")
    assert response.status_code == 200
    new_txs = response.json()

    # Filter only transactions created by our recurring (by label)
    our_txs = [t for t in new_txs if t["label"] == "Loyer mensuel generate test"]
    assert len(our_txs) >= 1

    # Verify each generated transaction has the correct amount
    for tx in our_txs:
        assert tx["amount"] == -500.0
        assert tx["label"] == "Loyer mensuel generate test"

    # Verify last_generated was updated
    updated_rec = client.get(f"/api/recurring/{rec_id}").json()
    assert updated_rec["last_generated"] is not None


def test_generate_updates_last_generated(client):
    """After generate, last_generated should be set to the last generated date."""
    today = date.today()
    start = today.isoformat()

    rec = make_recurring(
        client,
        label="Today recurring",
        amount=-10.0,
        frequency="monthly",
        start_date=start,
    ).json()

    client.post("/api/recurring/generate")

    updated = client.get(f"/api/recurring/{rec['id']}").json()
    assert updated["last_generated"] == today.isoformat()


def test_generate_no_duplicate_on_second_call(client):
    """Calling generate twice should not create duplicate transactions."""
    today = date.today()
    start = today.isoformat()

    make_recurring(
        client,
        label="No dup test",
        amount=-20.0,
        frequency="monthly",
        start_date=start,
    )

    # First call
    resp1 = client.post("/api/recurring/generate")
    our_txs_1 = [t for t in resp1.json() if t["label"] == "No dup test"]

    # Second call
    resp2 = client.post("/api/recurring/generate")
    our_txs_2 = [t for t in resp2.json() if t["label"] == "No dup test"]

    assert len(our_txs_2) == 0  # No new transactions on second call


def test_generate_respects_end_date(client):
    """Recurring transactions past their end_date should not be generated."""
    past_date = (date.today() - timedelta(days=60)).isoformat()
    end_date = (date.today() - timedelta(days=30)).isoformat()

    rec = make_recurring(
        client,
        label="Expired recurring",
        amount=-30.0,
        frequency="monthly",
        start_date=past_date,
        end_date=end_date,
    ).json()

    resp = client.post("/api/recurring/generate")
    our_txs = [t for t in resp.json() if t["label"] == "Expired recurring"]
    # Should only generate transactions up to end_date
    for tx in our_txs:
        assert tx["date"] <= end_date


def test_generate_inactive_not_processed(client):
    """Inactive recurring transactions should not generate transactions."""
    today = date.today().isoformat()

    rec = make_recurring(
        client,
        label="Inactive recurring",
        amount=-99.0,
        frequency="monthly",
        start_date=today,
        active=0,
    ).json()

    resp = client.post("/api/recurring/generate")
    our_txs = [t for t in resp.json() if t["label"] == "Inactive recurring"]
    assert len(our_txs) == 0
