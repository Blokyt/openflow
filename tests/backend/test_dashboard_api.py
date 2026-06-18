import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import pytest

def test_get_available_widgets(client):
    response = client.get("/api/dashboard/widgets")
    assert response.status_code == 200
    widgets = response.json()
    assert isinstance(widgets, list)
    ids = [w["id"] for w in widgets]
    assert "current_balance" in ids

def test_get_layout(client):
    response = client.get("/api/dashboard/layout")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_save_layout(client):
    layout = [
        {"widget_id": "current_balance", "module_id": "dashboard", "position_x": 0, "position_y": 0, "size": "quarter", "visible": True},
    ]
    response = client.put("/api/dashboard/layout", json=layout)
    assert response.status_code == 200
    saved = client.get("/api/dashboard/layout").json()
    assert len(saved) >= 1

def test_get_summary(client):
    response = client.get("/api/dashboard/summary")
    assert response.status_code == 200
    data = response.json()
    assert "balance" in data
    assert "total_income" in data
    assert "total_expenses" in data


def test_summary_filters_by_period(client):
    # Default injected pair is internal -> external, so both count as global expenses.
    assert client.post("/api/transactions/", json={"date": "2025-03-15", "label": "in-period", "amount": 5000}).status_code == 201
    assert client.post("/api/transactions/", json={"date": "2020-01-01", "label": "out-period", "amount": 3000}).status_code == 201

    full = client.get("/api/dashboard/summary").json()
    assert full["total_expenses"] == 8000
    assert full["transaction_count"] == 2

    scoped = client.get("/api/dashboard/summary", params={"date_from": "2025-01-01", "date_to": "2025-12-31"}).json()
    assert scoped["total_expenses"] == 5000
    assert scoped["transaction_count"] == 1
    # "Solde actuel" stays the real current balance, independent of the period.
    assert scoped["balance"] == full["balance"]


def test_recent_filters_by_period(client):
    client.post("/api/transactions/", json={"date": "2025-06-01", "label": "recent-in", "amount": 4000})
    client.post("/api/transactions/", json={"date": "2019-06-01", "label": "recent-out", "amount": 2000})
    recent = client.get("/api/dashboard/recent", params={"date_from": "2025-01-01", "date_to": "2025-12-31"}).json()
    labels = [t["label"] for t in recent]
    assert "recent-in" in labels
    assert "recent-out" not in labels
