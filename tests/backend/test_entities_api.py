"""Tests for the entities API module."""
import os
import sys
import sqlite3
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_internal(client, name="Root", **kwargs):
    payload = {"name": name, "type": "internal", **kwargs}
    return client.post("/api/entities/", json=payload)


def _create_external(client, name="Ext", **kwargs):
    payload = {"name": name, "type": "external", **kwargs}
    return client.post("/api/entities/", json=payload)


# ---------------------------------------------------------------------------
# CRUD tests
# ---------------------------------------------------------------------------

def test_create_internal_root(client):
    """Create a top-level internal entity → 201."""
    resp = _create_internal(client, name="BDA")
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "BDA"
    assert data["type"] == "internal"
    assert data["parent_id"] is None
    assert "id" in data


def test_create_internal_child(client):
    """Create an internal child with a valid parent_id → 201."""
    parent = _create_internal(client, name="Parent").json()
    resp = _create_internal(client, name="Child", parent_id=parent["id"])
    assert resp.status_code == 201
    data = resp.json()
    assert data["parent_id"] == parent["id"]


def test_create_external(client):
    """Create a top-level external entity → 201."""
    resp = _create_external(client, name="Fournisseur")
    assert resp.status_code == 201
    data = resp.json()
    assert data["type"] == "external"
    assert data["parent_id"] is None


def test_create_divers_entity(client):
    """Create the unique 'divers' external entity → 201."""
    resp = client.post("/api/entities/", json={
        "name": "Divers",
        "type": "external",
        "is_divers": 1,
    })
    assert resp.status_code == 201
    assert resp.json()["is_divers"] == 1


def test_reject_second_divers(client):
    """Creating a second is_divers entity → 400."""
    client.post("/api/entities/", json={"name": "D1", "type": "external", "is_divers": 1})
    resp = client.post("/api/entities/", json={"name": "D2", "type": "external", "is_divers": 1})
    assert resp.status_code == 400
    assert "divers" in resp.json()["detail"].lower()


def test_reject_external_with_parent(client):
    """External entity with parent_id → 400."""
    parent = _create_internal(client, name="P").json()
    resp = client.post("/api/entities/", json={
        "name": "Ext",
        "type": "external",
        "parent_id": parent["id"],
    })
    assert resp.status_code == 400


def test_reject_invalid_parent(client):
    """parent_id pointing to non-existent entity → 404."""
    resp = _create_internal(client, name="X", parent_id=9999)
    assert resp.status_code == 404


def test_list_entities_all(client):
    """List all entities returns a list."""
    _create_internal(client, name="A")
    _create_external(client, name="B")
    resp = client.get("/api/entities/")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert len(resp.json()) >= 2


def test_list_entities_filter_by_type(client):
    """Filter list by type=internal only returns internal entities."""
    _create_internal(client, name="Int1")
    _create_external(client, name="Ext1")
    resp = client.get("/api/entities/?type=internal")
    assert resp.status_code == 200
    types = {e["type"] for e in resp.json()}
    assert types == {"internal"}


def test_get_tree_structure(client):
    """Tree endpoint returns parent with children list."""
    parent = _create_internal(client, name="Root").json()
    _create_internal(client, name="Child1", parent_id=parent["id"])
    _create_internal(client, name="Child2", parent_id=parent["id"])

    resp = client.get("/api/entities/tree")
    assert resp.status_code == 200
    tree = resp.json()
    assert isinstance(tree, list)

    # Find the root node in the tree
    root_nodes = [n for n in tree if n["id"] == parent["id"]]
    assert len(root_nodes) == 1
    root_node = root_nodes[0]
    assert "children" in root_node
    assert len(root_node["children"]) == 2


def test_get_tree_excludes_external(client):
    """Tree only contains internal entities."""
    _create_internal(client, name="Int")
    _create_external(client, name="Ext")
    resp = client.get("/api/entities/tree")
    assert resp.status_code == 200
    for node in resp.json():
        assert node["type"] == "internal"


def test_get_single_entity(client):
    """GET /{id} returns 200 for existing entity."""
    entity = _create_internal(client, name="Solo").json()
    resp = client.get(f"/api/entities/{entity['id']}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Solo"


def test_get_entity_not_found(client):
    """GET /{id} returns 404 for missing entity."""
    resp = client.get("/api/entities/99999")
    assert resp.status_code == 404


def test_update_entity_name(client):
    """PUT /{id} updates the entity name."""
    entity = _create_internal(client, name="Old Name").json()
    resp = client.put(f"/api/entities/{entity['id']}", json={"name": "New Name"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "New Name"


def test_update_entity_color(client):
    """PUT /{id} updates the entity color."""
    entity = _create_internal(client, name="Colorful").json()
    resp = client.put(f"/api/entities/{entity['id']}", json={"color": "#FF0000"})
    assert resp.status_code == 200
    assert resp.json()["color"] == "#FF0000"


def test_update_entity_not_found(client):
    """PUT on missing entity → 404."""
    resp = client.put("/api/entities/99999", json={"name": "X"})
    assert resp.status_code == 404


def test_delete_entity(client):
    """DELETE /{id} removes the entity → 200."""
    entity = _create_internal(client, name="ToDelete").json()
    resp = client.delete(f"/api/entities/{entity['id']}")
    assert resp.status_code == 200
    assert resp.json()["deleted"] == entity["id"]
    # Verify it's gone
    assert client.get(f"/api/entities/{entity['id']}").status_code == 404


def test_delete_entity_with_children_rejected(client):
    """DELETE entity that has children → 400."""
    parent = _create_internal(client, name="Parent").json()
    _create_internal(client, name="Child", parent_id=parent["id"])
    resp = client.delete(f"/api/entities/{parent['id']}")
    assert resp.status_code == 400
    assert "children" in resp.json()["detail"].lower()


def test_delete_entity_not_found(client):
    """DELETE missing entity → 404."""
    resp = client.delete("/api/entities/99999")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Balance tests
# ---------------------------------------------------------------------------

def test_balance_endpoint_returns_correct_shape(client):
    """GET /{id}/balance returns a dict with balance fields."""
    entity = _create_internal(client, name="BalanceTest").json()
    resp = client.get(f"/api/entities/{entity['id']}/balance")
    assert resp.status_code == 200
    data = resp.json()
    assert "balance" in data
    assert "reference_amount" in data
    assert "transactions_sum" in data
    assert data["entity_id"] == entity["id"]


def test_balance_endpoint_external_not_found(client):
    """GET /{id}/balance on external entity → 404."""
    ext = _create_external(client, name="ExtBalance").json()
    resp = client.get(f"/api/entities/{ext['id']}/balance")
    assert resp.status_code == 404


def test_consolidated_balance_sums_children(client_and_db):
    """GET /{id}/consolidated returns own + children balances."""
    client, db_path = client_and_db

    parent = _create_internal(client, name="Parent").json()
    child = _create_internal(client, name="Child", parent_id=parent["id"]).json()

    # Set balance refs directly via API
    client.put(f"/api/entities/{parent['id']}/balance-ref", json={
        "reference_date": "2025-01-01",
        "reference_amount": 1000.0,
    })
    client.put(f"/api/entities/{child['id']}/balance-ref", json={
        "reference_date": "2025-01-01",
        "reference_amount": 500.0,
    })

    resp = client.get(f"/api/entities/{parent['id']}/consolidated")
    assert resp.status_code == 200
    data = resp.json()
    assert "own_balance" in data
    assert "consolidated_balance" in data
    assert "children" in data
    assert data["own_balance"] == pytest.approx(1000.0)
    assert data["consolidated_balance"] == pytest.approx(1500.0)
    assert len(data["children"]) == 1


def test_consolidated_balance_external_not_found(client):
    """GET /{id}/consolidated on external entity → 404."""
    ext = _create_external(client, name="ExtConsolidated").json()
    resp = client.get(f"/api/entities/{ext['id']}/consolidated")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Balance ref CRUD
# ---------------------------------------------------------------------------

def test_balance_ref_default(client):
    """GET /{id}/balance-ref returns default zero values if none set."""
    entity = _create_internal(client, name="RefDefault").json()
    resp = client.get(f"/api/entities/{entity['id']}/balance-ref")
    assert resp.status_code == 200
    data = resp.json()
    assert data["entity_id"] == entity["id"]
    assert data["reference_date"] is None
    assert data["reference_amount"] == pytest.approx(0.0)


def test_balance_ref_put_and_get(client):
    """PUT /{id}/balance-ref sets values, GET returns them."""
    entity = _create_internal(client, name="RefSet").json()

    put_resp = client.put(f"/api/entities/{entity['id']}/balance-ref", json={
        "reference_date": "2025-06-01",
        "reference_amount": 2500.0,
    })
    assert put_resp.status_code == 200
    put_data = put_resp.json()
    assert put_data["reference_date"] == "2025-06-01"
    assert put_data["reference_amount"] == pytest.approx(2500.0)

    get_resp = client.get(f"/api/entities/{entity['id']}/balance-ref")
    assert get_resp.status_code == 200
    assert get_resp.json()["reference_amount"] == pytest.approx(2500.0)


def test_balance_ref_update_overwrites(client):
    """PUT /{id}/balance-ref twice — second call overwrites first."""
    entity = _create_internal(client, name="RefUpdate").json()

    client.put(f"/api/entities/{entity['id']}/balance-ref", json={
        "reference_date": "2025-01-01",
        "reference_amount": 100.0,
    })
    client.put(f"/api/entities/{entity['id']}/balance-ref", json={
        "reference_date": "2025-06-01",
        "reference_amount": 999.0,
    })

    resp = client.get(f"/api/entities/{entity['id']}/balance-ref")
    assert resp.status_code == 200
    assert resp.json()["reference_amount"] == pytest.approx(999.0)
    assert resp.json()["reference_date"] == "2025-06-01"


def test_balance_ref_put_external_rejected(client):
    """PUT balance-ref on external entity → 404."""
    ext = _create_external(client, name="ExtRef").json()
    resp = client.put(f"/api/entities/{ext['id']}/balance-ref", json={
        "reference_date": "2025-01-01",
        "reference_amount": 0.0,
    })
    assert resp.status_code == 404
