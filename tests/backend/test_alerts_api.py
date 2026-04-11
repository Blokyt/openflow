"""Tests for the alerts module API."""
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

def make_rule(client, **kwargs):
    payload = {
        "type": "low_balance",
        "label": "Test alert",
        "threshold": 100.0,
        "active": 1,
    }
    payload.update(kwargs)
    return client.post("/api/alerts/", json=payload)


# ---------------------------------------------------------------------------
# CRUD tests
# ---------------------------------------------------------------------------

def test_list_alert_rules_empty_or_existing(client):
    response = client.get("/api/alerts/")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_create_alert_rule(client):
    response = make_rule(client, label="Solde bas", threshold=500.0)
    assert response.status_code == 201
    data = response.json()
    assert data["label"] == "Solde bas"
    assert data["threshold"] == 500.0
    assert data["type"] == "low_balance"
    assert data["active"] == 1
    assert "id" in data
    assert "created_at" in data


def test_create_alert_rule_custom_type(client):
    response = make_rule(client, type="custom", label="Alerte custom", threshold=None)
    assert response.status_code == 201
    data = response.json()
    assert data["type"] == "custom"
    assert data["threshold"] is None


def test_get_alert_rule(client):
    created = make_rule(client, label="Get test").json()
    response = client.get(f"/api/alerts/{created['id']}")
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]
    assert response.json()["label"] == "Get test"


def test_get_alert_rule_not_found(client):
    response = client.get("/api/alerts/999999")
    assert response.status_code == 404


def test_update_alert_rule(client):
    created = make_rule(client, label="Old label", threshold=200.0).json()
    response = client.put(
        f"/api/alerts/{created['id']}",
        json={"label": "New label", "threshold": 350.0},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["label"] == "New label"
    assert data["threshold"] == 350.0


def test_update_alert_rule_partial(client):
    created = make_rule(client, label="Partial", threshold=100.0).json()
    response = client.put(f"/api/alerts/{created['id']}", json={"label": "Partial updated"})
    assert response.status_code == 200
    assert response.json()["label"] == "Partial updated"
    # threshold unchanged
    assert response.json()["threshold"] == 100.0


def test_update_alert_rule_not_found(client):
    response = client.put("/api/alerts/999999", json={"label": "Ghost"})
    assert response.status_code == 404


def test_delete_alert_rule(client):
    created = make_rule(client, label="To delete").json()
    response = client.delete(f"/api/alerts/{created['id']}")
    assert response.status_code == 200
    assert response.json()["deleted"] == created["id"]
    # Verify it's gone
    assert client.get(f"/api/alerts/{created['id']}").status_code == 404


def test_delete_alert_rule_not_found(client):
    response = client.delete("/api/alerts/999999")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# /check endpoint tests
# ---------------------------------------------------------------------------

def test_check_returns_list(client):
    response = client.get("/api/alerts/check")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_check_low_balance_triggered(client):
    """Create a low_balance rule with a very high threshold so it triggers."""
    # Create rule with threshold far above any realistic balance
    rule = make_rule(client, label="Solde très bas", threshold=999_999_999.0, active=1).json()

    response = client.get("/api/alerts/check")
    assert response.status_code == 200
    results = response.json()

    # Find our rule in the results
    our_result = next((r for r in results if r["rule_id"] == rule["id"]), None)
    assert our_result is not None
    assert our_result["type"] == "low_balance"
    assert our_result["triggered"] is True
    assert our_result["current_value"] is not None
    assert our_result["threshold"] == 999_999_999.0


def test_check_low_balance_not_triggered(client):
    """Create a low_balance rule with a very low threshold so it does NOT trigger."""
    rule = make_rule(client, label="Seuil plancher", threshold=-999_999_999.0, active=1).json()

    response = client.get("/api/alerts/check")
    assert response.status_code == 200
    results = response.json()

    our_result = next((r for r in results if r["rule_id"] == rule["id"]), None)
    assert our_result is not None
    assert our_result["triggered"] is False


def test_check_inactive_rule_excluded(client):
    """Inactive rules should not appear in /check results."""
    rule = make_rule(client, label="Inactive rule", threshold=100.0, active=0).json()

    response = client.get("/api/alerts/check")
    assert response.status_code == 200
    results = response.json()

    # This rule should not be in the results (active=0)
    our_result = next((r for r in results if r["rule_id"] == rule["id"]), None)
    assert our_result is None


def test_check_result_fields(client):
    """Verify the /check response has the expected fields."""
    make_rule(client, label="Fields check", threshold=50.0, active=1)

    response = client.get("/api/alerts/check")
    assert response.status_code == 200
    results = response.json()
    assert len(results) > 0

    item = results[-1]
    assert "rule_id" in item
    assert "rule_label" in item
    assert "type" in item
    assert "triggered" in item
    assert "current_value" in item
    assert "threshold" in item
