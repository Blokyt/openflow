"""Tests for from_entity_id / to_entity_id on transactions."""
import os
import sys
import sqlite3
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_entity(client, name, type_="internal", **kwargs):
    payload = {"name": name, "type": type_, **kwargs}
    resp = client.post("/api/entities/", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_tx(client, label="TX", amount=100.0, **kwargs):
    payload = {"date": "2025-06-01", "label": label, "amount": amount, **kwargs}
    resp = client.post("/api/transactions/", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Create with entity IDs
# ---------------------------------------------------------------------------

def test_create_transaction_with_entity_ids(client):
    """Create transaction with from/to entity IDs → 201, fields returned."""
    root = _create_entity(client, "Root")
    ext = _create_entity(client, "External", type_="external")

    resp = client.post("/api/transactions/", json={
        "date": "2025-06-01",
        "label": "Sale",
        "amount": 500.0,
        "from_entity_id": ext["id"],
        "to_entity_id": root["id"],
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["from_entity_id"] == ext["id"]
    assert data["to_entity_id"] == root["id"]


def test_create_transaction_without_entity_ids(client):
    """Create transaction without from/to entity IDs → 422 (rule: JAMAIS null)."""
    # Pass explicit None so the conftest auto-injection doesn't fill defaults.
    resp = client.post("/api/transactions/", json={
        "date": "2025-06-01",
        "label": "Legacy TX",
        "amount": 100.0,
        "from_entity_id": None,
        "to_entity_id": None,
    })
    assert resp.status_code == 422


def test_create_transaction_with_unknown_entity(client):
    """Create transaction with non-existing entity → 400."""
    root = _create_entity(client, "RootUnknown")
    resp = client.post("/api/transactions/", json={
        "date": "2025-06-01",
        "label": "Bad",
        "amount": 1.0,
        "from_entity_id": root["id"],
        "to_entity_id": 99999,
    })
    assert resp.status_code == 400


def test_update_transaction_to_null_entity_rejected(client):
    """PUT with explicit null for from/to entity → 400."""
    root = _create_entity(client, "RootNullUpd")
    ext = _create_entity(client, "ExtNullUpd", type_="external")
    tx = _create_tx(client, label="NoNull", from_entity_id=ext["id"], to_entity_id=root["id"])
    resp = client.put(f"/api/transactions/{tx['id']}", json={"from_entity_id": None})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Filter by entity_id
# ---------------------------------------------------------------------------

def test_filter_transactions_by_entity_id(client):
    """Filter by entity_id returns only transactions involving that entity."""
    root = _create_entity(client, "Root2")
    other = _create_entity(client, "Other", type_="external")
    unrelated = _create_entity(client, "Unrelated", type_="external")

    # Transaction involving root
    tx1 = _create_tx(client, label="TX with root", from_entity_id=other["id"], to_entity_id=root["id"])
    # Transaction NOT involving root
    _create_tx(client, label="TX without root", from_entity_id=unrelated["id"], to_entity_id=unrelated["id"])

    resp = client.get(f"/api/transactions/?entity_id={root['id']}")
    assert resp.status_code == 200
    ids = [t["id"] for t in resp.json()]
    assert tx1["id"] in ids
    # Transactions without root entity should not be returned
    for tx in resp.json():
        assert tx["from_entity_id"] == root["id"] or tx["to_entity_id"] == root["id"]


def test_filter_by_entity_id_matches_from_or_to(client):
    """entity_id filter works for both from_entity_id and to_entity_id."""
    root = _create_entity(client, "BothSides")
    ext = _create_entity(client, "Ext1", type_="external")

    tx_as_to = _create_tx(client, label="income", from_entity_id=ext["id"], to_entity_id=root["id"])
    tx_as_from = _create_tx(client, label="expense", amount=-100.0, from_entity_id=root["id"], to_entity_id=ext["id"])

    resp = client.get(f"/api/transactions/?entity_id={root['id']}")
    assert resp.status_code == 200
    ids = [t["id"] for t in resp.json()]
    assert tx_as_to["id"] in ids
    assert tx_as_from["id"] in ids


def test_filter_by_entity_id_include_children(client):
    """include_children=true returns transactions from the entity subtree."""
    parent = _create_entity(client, "ParentEnt")
    child = _create_entity(client, "ChildEnt", parent_id=parent["id"])
    ext = _create_entity(client, "ExtForChildren", type_="external")

    # Transaction linked to child
    tx_child = _create_tx(client, label="child tx", from_entity_id=ext["id"], to_entity_id=child["id"])
    # Transaction linked to parent directly
    tx_parent = _create_tx(client, label="parent tx", from_entity_id=ext["id"], to_entity_id=parent["id"])
    # Unrelated transaction
    _create_tx(client, label="unrelated", from_entity_id=ext["id"], to_entity_id=ext["id"])

    resp = client.get(f"/api/transactions/?entity_id={parent['id']}&include_children=true")
    assert resp.status_code == 200
    ids = [t["id"] for t in resp.json()]
    assert tx_parent["id"] in ids
    assert tx_child["id"] in ids


def test_filter_by_entity_id_no_children(client):
    """include_children=false (default) does not include child entity transactions."""
    parent = _create_entity(client, "ParentNoChild")
    child = _create_entity(client, "ChildNoChild", parent_id=parent["id"])
    ext = _create_entity(client, "ExtNoChild", type_="external")

    # Transaction linked to child only
    tx_child = _create_tx(client, label="child only tx", from_entity_id=ext["id"], to_entity_id=child["id"])
    # Transaction linked to parent
    tx_parent = _create_tx(client, label="parent only tx", from_entity_id=ext["id"], to_entity_id=parent["id"])

    resp = client.get(f"/api/transactions/?entity_id={parent['id']}&include_children=false")
    assert resp.status_code == 200
    ids = [t["id"] for t in resp.json()]
    assert tx_parent["id"] in ids
    assert tx_child["id"] not in ids


# ---------------------------------------------------------------------------
# Update entity IDs
# ---------------------------------------------------------------------------

def test_update_transaction_entity_ids(client):
    """PUT /{id} can update from_entity_id and to_entity_id."""
    root = _create_entity(client, "RootUpdate")
    ext = _create_entity(client, "ExtUpdate", type_="external")

    tmp = _create_entity(client, "TmpUpdate", type_="external")
    tx = _create_tx(client, label="ToUpdate", from_entity_id=tmp["id"], to_entity_id=root["id"])

    resp = client.put(f"/api/transactions/{tx['id']}", json={
        "from_entity_id": ext["id"],
        "to_entity_id": root["id"],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["from_entity_id"] == ext["id"]
    assert data["to_entity_id"] == root["id"]


def test_update_transaction_clears_entity_ids(client):
    """PUT /{id} can set entity IDs then update other fields without losing them."""
    root = _create_entity(client, "RootClear")
    ext = _create_entity(client, "ExtClear", type_="external")

    tx = _create_tx(client, label="ClearTest", from_entity_id=ext["id"], to_entity_id=root["id"])

    # Update label only — entity IDs should be preserved
    resp = client.put(f"/api/transactions/{tx['id']}", json={"label": "Updated Label"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["label"] == "Updated Label"
    assert data["from_entity_id"] == ext["id"]
    assert data["to_entity_id"] == root["id"]


# ---------------------------------------------------------------------------
# Migration helper
# ---------------------------------------------------------------------------

def test_migration_helper_backfill(client_and_db):
    """run_backfill creates root + divers entities and backfills transactions."""
    client, db_path = client_and_db
    from backend.modules.entities.migration_helper import run_backfill

    # Insert legacy transactions directly (API now enforces from/to — we simulate pre-migration rows)
    now = "2025-01-15T00:00:00"
    conn_seed = sqlite3.connect(str(db_path))
    conn_seed.execute(
        "INSERT INTO transactions (date, label, description, amount, created_at, updated_at) VALUES (?,?,?,?,?,?)",
        ("2025-01-15", "Income", "", 500.0, now, now),
    )
    conn_seed.execute(
        "INSERT INTO transactions (date, label, description, amount, created_at, updated_at) VALUES (?,?,?,?,?,?)",
        ("2025-01-20", "Expense", "", -200.0, now, now),
    )
    conn_seed.commit()
    conn_seed.close()

    # Run backfill
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    result = run_backfill(conn, "config.test.yaml")
    conn.close()

    assert result["status"] == "done"
    assert result["transactions_updated"] == 2
    assert "root_id" in result
    assert "divers_id" in result

    # Verify entities were created
    entities_resp = client.get("/api/entities/")
    assert entities_resp.status_code == 200
    # Note: client uses a copy of the DB; re-open to check directly
    conn2 = sqlite3.connect(str(db_path))
    conn2.row_factory = sqlite3.Row
    entities = conn2.execute("SELECT * FROM entities").fetchall()
    assert len(entities) == 2

    # Verify transactions were backfilled
    txs = conn2.execute("SELECT * FROM transactions WHERE from_entity_id IS NOT NULL").fetchall()
    assert len(txs) == 2

    root_id = result["root_id"]
    divers_id = result["divers_id"]

    # Income (amount >= 0): from=divers, to=root
    income = conn2.execute("SELECT * FROM transactions WHERE label = 'Income'").fetchone()
    assert income["from_entity_id"] == divers_id
    assert income["to_entity_id"] == root_id

    # Expense (amount < 0): from=root, to=divers
    expense = conn2.execute("SELECT * FROM transactions WHERE label = 'Expense'").fetchone()
    assert expense["from_entity_id"] == root_id
    assert expense["to_entity_id"] == divers_id

    conn2.close()


def test_migration_helper_skipped_when_entities_exist(client_and_db):
    """run_backfill returns 'skipped' if entities already exist."""
    client, db_path = client_and_db
    from backend.modules.entities.migration_helper import run_backfill

    # Create an entity first
    client.post("/api/entities/", json={"name": "PreExisting", "type": "internal"})

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    result = run_backfill(conn, "config.test.yaml")
    conn.close()

    assert result["status"] == "skipped"
    assert "reason" in result
