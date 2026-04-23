"""Tests vérifiant que record_audit est bien câblé sur les mutations des modules."""
import os
import sys
import sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_audit_entries(db_path, table_name=None, action=None):
    """Récupère les entrées audit_log directement depuis la DB."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        q = "SELECT * FROM audit_log WHERE 1=1"
        params = []
        if table_name:
            q += " AND table_name = ?"
            params.append(table_name)
        if action:
            q += " AND action = ?"
            params.append(action)
        q += " ORDER BY id DESC"
        return [dict(r) for r in conn.execute(q, params).fetchall()]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------

def test_create_category_logs_audit(client_and_db):
    client, db_path = client_and_db
    resp = client.post("/api/categories/", json={"name": "Audit Test Cat"})
    assert resp.status_code == 201
    cat_id = resp.json()["id"]

    entries = _get_audit_entries(db_path, table_name="categories", action="CREATE")
    matching = [e for e in entries if e["record_id"] == cat_id]
    assert len(matching) == 1, f"Expected 1 CREATE audit entry for categories#{cat_id}, got {len(matching)}"
    assert matching[0]["table_name"] == "categories"
    assert matching[0]["action"] == "CREATE"
    assert matching[0]["new_value"] is not None


def test_update_category_logs_audit(client_and_db):
    client, db_path = client_and_db
    cat = client.post("/api/categories/", json={"name": "Before"}).json()
    resp = client.put(f"/api/categories/{cat['id']}", json={"name": "After"})
    assert resp.status_code == 200

    entries = _get_audit_entries(db_path, table_name="categories", action="UPDATE")
    matching = [e for e in entries if e["record_id"] == cat["id"]]
    assert len(matching) == 1
    assert matching[0]["old_value"] is not None
    assert matching[0]["new_value"] is not None


def test_delete_category_logs_audit(client_and_db):
    client, db_path = client_and_db
    cat = client.post("/api/categories/", json={"name": "To Delete"}).json()
    resp = client.delete(f"/api/categories/{cat['id']}")
    assert resp.status_code == 200

    entries = _get_audit_entries(db_path, table_name="categories", action="DELETE")
    matching = [e for e in entries if e["record_id"] == cat["id"]]
    assert len(matching) == 1
    assert matching[0]["old_value"] is not None


# ---------------------------------------------------------------------------
# Reimbursements
# ---------------------------------------------------------------------------

def test_create_reimbursement_logs_audit(client_and_db):
    client, db_path = client_and_db
    resp = client.post("/api/reimbursements/", json={"person_name": "Audit User", "amount": 50.0})
    assert resp.status_code == 201
    rembo_id = resp.json()["id"]

    entries = _get_audit_entries(db_path, table_name="reimbursements", action="CREATE")
    matching = [e for e in entries if e["record_id"] == rembo_id]
    assert len(matching) == 1
    assert matching[0]["new_value"] is not None


def test_update_reimbursement_logs_audit(client_and_db):
    client, db_path = client_and_db
    rembo = client.post("/api/reimbursements/", json={"person_name": "Test", "amount": 10.0}).json()
    resp = client.put(f"/api/reimbursements/{rembo['id']}", json={"amount": 20.0})
    assert resp.status_code == 200

    entries = _get_audit_entries(db_path, table_name="reimbursements", action="UPDATE")
    matching = [e for e in entries if e["record_id"] == rembo["id"]]
    assert len(matching) == 1
    assert matching[0]["old_value"] is not None
    assert matching[0]["new_value"] is not None


def test_delete_reimbursement_logs_audit(client_and_db):
    client, db_path = client_and_db
    rembo = client.post("/api/reimbursements/", json={"person_name": "Del", "amount": 5.0}).json()
    resp = client.delete(f"/api/reimbursements/{rembo['id']}")
    assert resp.status_code == 200

    entries = _get_audit_entries(db_path, table_name="reimbursements", action="DELETE")
    matching = [e for e in entries if e["record_id"] == rembo["id"]]
    assert len(matching) == 1
    assert matching[0]["old_value"] is not None


# ---------------------------------------------------------------------------
# Budget — fiscal_years
# ---------------------------------------------------------------------------

def test_create_fiscal_year_logs_audit(client_and_db):
    client, db_path = client_and_db
    resp = client.post("/api/budget/fiscal-years", json={
        "name": "FY Audit Test",
        "start_date": "2025-01-01",
        "end_date": "2025-12-31",
    })
    assert resp.status_code == 201
    fy_id = resp.json()["id"]

    entries = _get_audit_entries(db_path, table_name="fiscal_years", action="CREATE")
    matching = [e for e in entries if e["record_id"] == fy_id]
    assert len(matching) == 1
    assert matching[0]["new_value"] is not None


def test_update_fiscal_year_logs_audit(client_and_db):
    client, db_path = client_and_db
    fy = client.post("/api/budget/fiscal-years", json={
        "name": "FY Update Audit",
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
    }).json()
    resp = client.put(f"/api/budget/fiscal-years/{fy['id']}", json={"notes": "mise à jour"})
    assert resp.status_code == 200

    entries = _get_audit_entries(db_path, table_name="fiscal_years", action="UPDATE")
    matching = [e for e in entries if e["record_id"] == fy["id"]]
    assert len(matching) == 1
    assert matching[0]["old_value"] is not None


def test_delete_fiscal_year_logs_audit(client_and_db):
    client, db_path = client_and_db
    fy = client.post("/api/budget/fiscal-years", json={
        "name": "FY Del Audit",
        "start_date": "2023-01-01",
        "end_date": "2023-12-31",
    }).json()
    resp = client.delete(f"/api/budget/fiscal-years/{fy['id']}")
    assert resp.status_code == 200

    entries = _get_audit_entries(db_path, table_name="fiscal_years", action="DELETE")
    matching = [e for e in entries if e["record_id"] == fy["id"]]
    assert len(matching) == 1
    assert matching[0]["old_value"] is not None


# ---------------------------------------------------------------------------
# Budget — allocations
# ---------------------------------------------------------------------------

def test_create_allocation_logs_audit(client_and_db):
    client, db_path = client_and_db
    # Crée une entité interne et un exercice
    ent = client.post("/api/entities/", json={"name": "BDA Alloc Audit", "type": "internal"}).json()
    fy = client.post("/api/budget/fiscal-years", json={
        "name": "FY Alloc Audit",
        "start_date": "2022-01-01",
        "end_date": "2022-12-31",
    }).json()
    resp = client.post(f"/api/budget/fiscal-years/{fy['id']}/allocations", json={
        "entity_id": ent["id"],
        "amount": 1000.0,
    })
    assert resp.status_code == 201
    alloc_id = resp.json()["id"]

    entries = _get_audit_entries(db_path, table_name="budget_allocations", action="CREATE")
    matching = [e for e in entries if e["record_id"] == alloc_id]
    assert len(matching) == 1
    assert matching[0]["new_value"] is not None


# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------

def test_create_entity_logs_audit(client_and_db):
    client, db_path = client_and_db
    resp = client.post("/api/entities/", json={"name": "Entite Audit", "type": "internal"})
    assert resp.status_code == 201
    ent_id = resp.json()["id"]

    entries = _get_audit_entries(db_path, table_name="entities", action="CREATE")
    matching = [e for e in entries if e["record_id"] == ent_id]
    assert len(matching) == 1
    assert matching[0]["new_value"] is not None


def test_update_entity_logs_audit(client_and_db):
    client, db_path = client_and_db
    ent = client.post("/api/entities/", json={"name": "Ent Before", "type": "internal"}).json()
    resp = client.put(f"/api/entities/{ent['id']}", json={"name": "Ent After"})
    assert resp.status_code == 200

    entries = _get_audit_entries(db_path, table_name="entities", action="UPDATE")
    matching = [e for e in entries if e["record_id"] == ent["id"]]
    assert len(matching) == 1
    assert matching[0]["old_value"] is not None
    assert matching[0]["new_value"] is not None


def test_delete_entity_logs_audit(client_and_db):
    client, db_path = client_and_db
    ent = client.post("/api/entities/", json={"name": "Ent To Delete", "type": "internal"}).json()
    resp = client.delete(f"/api/entities/{ent['id']}")
    assert resp.status_code == 200

    entries = _get_audit_entries(db_path, table_name="entities", action="DELETE")
    matching = [e for e in entries if e["record_id"] == ent["id"]]
    assert len(matching) == 1
    assert matching[0]["old_value"] is not None


# ---------------------------------------------------------------------------
# Budget — allocations (update + delete)
# ---------------------------------------------------------------------------

def test_update_allocation_logs_audit(client_and_db):
    client, db_path = client_and_db
    # Crée une entité interne et un exercice
    ent = client.post("/api/entities/", json={"name": "BDA Update Audit", "type": "internal"}).json()
    fy = client.post("/api/budget/fiscal-years", json={
        "name": "FY Update Alloc Audit",
        "start_date": "2021-01-01",
        "end_date": "2021-12-31",
    }).json()
    alloc = client.post(f"/api/budget/fiscal-years/{fy['id']}/allocations", json={
        "entity_id": ent["id"],
        "amount": 500.0,
    }).json()
    resp = client.put(f"/api/budget/allocations/{alloc['id']}", json={"amount": 750.0})
    assert resp.status_code == 200

    entries = _get_audit_entries(db_path, table_name="budget_allocations", action="UPDATE")
    matching = [e for e in entries if e["record_id"] == alloc["id"]]
    assert len(matching) == 1
    assert matching[0]["old_value"] is not None
    assert matching[0]["new_value"] is not None


def test_delete_allocation_logs_audit(client_and_db):
    client, db_path = client_and_db
    # Crée une entité interne et un exercice
    ent = client.post("/api/entities/", json={"name": "BDA Delete Audit", "type": "internal"}).json()
    fy = client.post("/api/budget/fiscal-years", json={
        "name": "FY Delete Alloc Audit",
        "start_date": "2020-01-01",
        "end_date": "2020-12-31",
    }).json()
    alloc = client.post(f"/api/budget/fiscal-years/{fy['id']}/allocations", json={
        "entity_id": ent["id"],
        "amount": 200.0,
    }).json()
    resp = client.delete(f"/api/budget/allocations/{alloc['id']}")
    assert resp.status_code == 200

    entries = _get_audit_entries(db_path, table_name="budget_allocations", action="DELETE")
    matching = [e for e in entries if e["record_id"] == alloc["id"]]
    assert len(matching) == 1
    assert matching[0]["old_value"] is not None
