"""Tests for the budget module API."""
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
# Helper
# ---------------------------------------------------------------------------

def make_budget(client, **kwargs):
    payload = {
        "period_start": "2026-01-01",
        "period_end": "2026-12-31",
        "amount": 1000.0,
        "label": "Test budget",
    }
    payload.update(kwargs)
    return client.post("/api/budget/", json=payload)


# ---------------------------------------------------------------------------
# CRUD tests
# ---------------------------------------------------------------------------

def test_list_budgets_empty_or_existing(client):
    response = client.get("/api/budget/")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_create_budget(client):
    response = make_budget(client, label="Fournitures", amount=500.0)
    assert response.status_code == 201
    data = response.json()
    assert data["label"] == "Fournitures"
    assert data["amount"] == 500.0
    assert "id" in data
    assert data["period_start"] == "2026-01-01"
    assert data["period_end"] == "2026-12-31"


def test_create_budget_with_category(client):
    response = make_budget(client, category_id=None, label="Sans categorie")
    assert response.status_code == 201
    assert response.json()["category_id"] is None


def test_get_budget(client):
    created = make_budget(client, label="Get test").json()
    response = client.get(f"/api/budget/{created['id']}")
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]
    assert response.json()["label"] == "Get test"


def test_get_budget_not_found(client):
    response = client.get("/api/budget/999999")
    assert response.status_code == 404


def test_update_budget(client):
    created = make_budget(client, label="Old label", amount=200.0).json()
    response = client.put(
        f"/api/budget/{created['id']}",
        json={"label": "New label", "amount": 350.0},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["label"] == "New label"
    assert data["amount"] == 350.0


def test_update_budget_partial(client):
    created = make_budget(client, label="Partial", amount=100.0).json()
    response = client.put(f"/api/budget/{created['id']}", json={"label": "Partial updated"})
    assert response.status_code == 200
    assert response.json()["label"] == "Partial updated"
    # amount unchanged
    assert response.json()["amount"] == 100.0


def test_update_budget_not_found(client):
    response = client.put("/api/budget/999999", json={"label": "Ghost"})
    assert response.status_code == 404


def test_delete_budget(client):
    created = make_budget(client, label="To delete").json()
    response = client.delete(f"/api/budget/{created['id']}")
    assert response.status_code == 200
    assert response.json()["deleted"] == created["id"]
    # Verify it's gone
    assert client.get(f"/api/budget/{created['id']}").status_code == 404


def test_delete_budget_not_found(client):
    response = client.delete("/api/budget/999999")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Period filter
# ---------------------------------------------------------------------------

def test_list_budgets_period_filter(client):
    # Create a 2025 budget and a 2026 budget
    make_budget(client, period_start="2025-01-01", period_end="2025-12-31", label="Budget 2025")
    make_budget(client, period_start="2026-01-01", period_end="2026-12-31", label="Budget 2026")

    resp_2025 = client.get("/api/budget/?period=2025")
    assert resp_2025.status_code == 200
    labels_2025 = [b["period_start"][:4] for b in resp_2025.json()]
    assert all(y == "2025" for y in labels_2025)

    resp_2026 = client.get("/api/budget/?period=2026")
    assert resp_2026.status_code == 200
    labels_2026 = [b["period_start"][:4] for b in resp_2026.json()]
    assert all(y == "2026" for y in labels_2026)


# ---------------------------------------------------------------------------
# Status computation
# ---------------------------------------------------------------------------

def test_budget_status_returns_list(client):
    make_budget(client, label="Status test", amount=800.0)
    response = client.get("/api/budget/status")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_budget_status_fields(client):
    make_budget(client, label="Fields test", amount=600.0)
    response = client.get("/api/budget/status")
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    item = data[-1]  # last created
    assert "budgeted" in item
    assert "spent" in item
    assert "remaining" in item
    assert item["budgeted"] == item["amount"]


def test_budget_status_computation(client):
    """Create a budget linked to a category, create a transaction in range,
    and verify the status reflects the spending."""
    # Create a category
    cat_resp = client.post("/api/categories/", json={"name": "Test Cat Budget"})
    assert cat_resp.status_code == 201
    cat_id = cat_resp.json()["id"]

    # Create a budget for that category for 2026
    budget_resp = make_budget(
        client,
        category_id=cat_id,
        period_start="2026-01-01",
        period_end="2026-12-31",
        amount=1000.0,
        label="Budget avec cat",
    )
    assert budget_resp.status_code == 201
    budget_id = budget_resp.json()["id"]

    # Create a transaction in the period with the same category
    tx_resp = client.post(
        "/api/transactions/",
        json={
            "date": "2026-06-15",
            "label": "Depense test",
            "amount": -250.0,
            "category_id": cat_id,
        },
    )
    assert tx_resp.status_code == 201

    # Fetch status
    status_resp = client.get("/api/budget/status")
    assert status_resp.status_code == 200
    statuses = status_resp.json()

    # Find our budget in the status list
    our_status = next((s for s in statuses if s["id"] == budget_id), None)
    assert our_status is not None
    assert our_status["budgeted"] == 1000.0
    # spent should reflect the -250 transaction (abs value used in remaining calculation)
    assert our_status["spent"] == -250.0
    assert our_status["remaining"] == 750.0  # 1000 - abs(-250)
