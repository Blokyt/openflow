import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from fastapi.testclient import TestClient
from backend.main import create_app
import pytest

@pytest.fixture
def client():
    app = create_app(config_path="config.yaml", db_path="data/openflow.db")
    return TestClient(app)

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
