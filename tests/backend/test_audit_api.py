import os
import sys
import sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from fastapi.testclient import TestClient
from backend.main import create_app
import pytest


@pytest.fixture
def client():
    app = create_app(config_path="config.yaml", db_path="data/openflow.db")
    return TestClient(app)


@pytest.fixture
def db_path():
    """Return the path to the test database."""
    from pathlib import Path
    project_root = Path(__file__).parent.parent.parent
    return str(project_root / "data" / "openflow.db")


@pytest.fixture
def audit_entry(db_path):
    """Insert a test audit log entry directly via sqlite3 and return its id."""
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(
            """INSERT INTO audit_log (timestamp, user_name, action, table_name, record_id, old_value, new_value)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ("2026-04-11T21:00:00+00:00", "test_user", "update", "transactions", 42,
             '{"amount": 100}', '{"amount": 200}'),
        )
        conn.commit()
        entry_id = cur.lastrowid
    finally:
        conn.close()
    return entry_id


@pytest.fixture(autouse=True)
def cleanup_audit_entries(db_path):
    """Remove all audit_log rows created during tests."""
    yield
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DELETE FROM audit_log WHERE user_name = 'test_user'")
        conn.commit()
    finally:
        conn.close()


def test_list_audit_empty(client):
    """List returns a list (may be empty or contain unrelated rows — just check it's a list)."""
    response = client.get("/api/audit/")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_list_audit_shows_inserted_entry(client, audit_entry):
    """An entry inserted directly via sqlite3 should appear in the list."""
    response = client.get("/api/audit/")
    assert response.status_code == 200
    ids = [e["id"] for e in response.json()]
    assert audit_entry in ids


def test_filter_by_table_name(client, audit_entry):
    response = client.get("/api/audit/?table_name=transactions")
    assert response.status_code == 200
    data = response.json()
    assert all(e["table_name"] == "transactions" for e in data)
    ids = [e["id"] for e in data]
    assert audit_entry in ids


def test_filter_by_action(client, audit_entry):
    response = client.get("/api/audit/?action=update")
    assert response.status_code == 200
    data = response.json()
    assert all(e["action"] == "update" for e in data)
    ids = [e["id"] for e in data]
    assert audit_entry in ids


def test_filter_table_name_no_crash(client):
    """Filtering by a table that has no entries should return an empty list, not crash."""
    response = client.get("/api/audit/?table_name=nonexistent_table")
    assert response.status_code == 200
    assert response.json() == []


def test_filter_action_no_crash(client):
    """Filtering by an unknown action should return empty, not crash."""
    response = client.get("/api/audit/?action=nonexistent_action")
    assert response.status_code == 200
    assert response.json() == []


def test_filter_limit(client, audit_entry, db_path):
    """The limit param should restrict the number of results."""
    # Insert a second entry to ensure there's more than one
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """INSERT INTO audit_log (timestamp, user_name, action, table_name, record_id, old_value, new_value)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ("2026-04-11T22:00:00+00:00", "test_user", "create", "transactions", 43, None, '{"amount": 50}'),
        )
        conn.commit()
    finally:
        conn.close()

    response = client.get("/api/audit/?limit=1")
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_get_record_audit(client, audit_entry):
    """The record endpoint should return audit entries for the specific record."""
    response = client.get("/api/audit/record/transactions/42")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert all(e["table_name"] == "transactions" and e["record_id"] == 42 for e in data)
    ids = [e["id"] for e in data]
    assert audit_entry in ids


def test_get_record_audit_empty(client):
    """Record audit for a record with no entries returns an empty list."""
    response = client.get("/api/audit/record/transactions/999999")
    assert response.status_code == 200
    assert response.json() == []


def test_audit_entry_fields(client, audit_entry):
    """Verify the returned entry has all expected fields."""
    response = client.get("/api/audit/")
    assert response.status_code == 200
    entry = next((e for e in response.json() if e["id"] == audit_entry), None)
    assert entry is not None
    assert "id" in entry
    assert "timestamp" in entry
    assert "user_name" in entry
    assert "action" in entry
    assert "table_name" in entry
    assert "record_id" in entry
    assert "old_value" in entry
    assert "new_value" in entry
