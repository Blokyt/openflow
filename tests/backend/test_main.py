import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.main import create_app


def test_app_serves_modules_endpoint(client):
    response = client.get("/api/modules")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_app_config_endpoint(client):
    response = client.get("/api/config")
    assert response.status_code == 200
    data = response.json()
    assert "entity" in data
    assert "modules" in data


def test_app_all_modules_endpoint(client):
    response = client.get("/api/modules/all")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
