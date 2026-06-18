import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import pytest


def _create(client, name="Alice Dupont", type="client", **kwargs):
    payload = {"name": name, "type": type, **kwargs}
    r = client.post("/api/tiers/", json=payload)
    assert r.status_code == 201
    return r.json()


# ─── Format paginé ────────────────────────────────────────────────────────────

def test_list_returns_paginated_format(client):
    r = client.get("/api/tiers/")
    assert r.status_code == 200
    data = r.json()
    assert "total" in data
    assert "items" in data
    assert isinstance(data["items"], list)
    assert isinstance(data["total"], int)


def test_list_contacts_empty(client):
    r = client.get("/api/tiers/")
    assert r.status_code == 200
    assert r.json()["total"] == 0
    assert r.json()["items"] == []


def test_pagination_limit_offset(client):
    for i in range(5):
        _create(client, name=f"Contact {i:02d}")
    r_all = client.get("/api/tiers/?limit=5&offset=0")
    assert len(r_all.json()["items"]) == 5
    assert r_all.json()["total"] == 5

    r_page1 = client.get("/api/tiers/?limit=2&offset=0")
    r_page2 = client.get("/api/tiers/?limit=2&offset=2")
    ids_p1 = [c["id"] for c in r_page1.json()["items"]]
    ids_p2 = [c["id"] for c in r_page2.json()["items"]]
    assert len(ids_p1) == 2
    assert len(ids_p2) == 2
    assert not set(ids_p1) & set(ids_p2)  # pages disjointes


# ─── CRUD ─────────────────────────────────────────────────────────────────────

def test_create_contact(client):
    r = client.post("/api/tiers/", json={"name": "Alice Dupont", "type": "client", "email": "alice@example.com"})
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "Alice Dupont"
    assert data["type"] == "client"
    assert data["email"] == "alice@example.com"
    assert "id" in data


def test_get_contact(client):
    c = _create(client, name="Bob Martin", type="supplier")
    r = client.get(f"/api/tiers/{c['id']}")
    assert r.status_code == 200
    assert r.json()["name"] == "Bob Martin"


def test_get_contact_not_found(client):
    assert client.get("/api/tiers/999999").status_code == 404


def test_update_contact(client):
    c = _create(client, name="Old Name", type="member")
    r = client.put(f"/api/tiers/{c['id']}", json={"name": "New Name", "phone": "0600000000"})
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "New Name"
    assert data["phone"] == "0600000000"
    assert data["type"] == "member"


def test_delete_contact(client):
    c = _create(client, name="To Delete", type="other")
    r = client.delete(f"/api/tiers/{c['id']}")
    assert r.status_code == 200
    assert r.json()["deleted"] == c["id"]
    assert client.get(f"/api/tiers/{c['id']}").status_code == 404


def test_default_type_is_other(client):
    c = client.post("/api/tiers/", json={"name": "No Type"}).json()
    assert c["type"] == "other"


# ─── Filtres ──────────────────────────────────────────────────────────────────

def test_filter_by_type(client):
    _create(client, name="Client One", type="client")
    _create(client, name="Supplier One", type="supplier")
    r = client.get("/api/tiers/?type=client")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) >= 1
    assert all(c["type"] == "client" for c in items)


def test_filter_by_search(client):
    _create(client, name="Recherche Unique XYZ", type="client")
    r = client.get("/api/tiers/?search=Unique XYZ")
    assert r.status_code == 200
    items = r.json()["items"]
    assert any("Unique XYZ" in c["name"] for c in items)


def test_search_not_found_returns_empty(client):
    r = client.get("/api/tiers/?search=ZZZInexistant999")
    assert r.status_code == 200
    assert r.json()["total"] == 0
    assert r.json()["items"] == []


# ─── Transactions liées ───────────────────────────────────────────────────────

def test_get_contact_transactions_empty(client):
    c = _create(client, name="Sans transaction")
    r = client.get(f"/api/tiers/{c['id']}/transactions")
    assert r.status_code == 200
    assert r.json() == []


def test_get_contact_transactions_not_found(client):
    assert client.get("/api/tiers/999999/transactions").status_code == 404


# ─── Fusion ───────────────────────────────────────────────────────────────────

def test_merge_contacts(client):
    source = _create(client, name="Source Contact", type="client")
    target = _create(client, name="Target Contact", type="fournisseur")

    r = client.post(f"/api/tiers/{source['id']}/merge-into/{target['id']}")
    assert r.status_code == 200
    data = r.json()
    assert data["merged"] == source["id"]
    assert data["into"] == target["id"]

    # source supprimé
    assert client.get(f"/api/tiers/{source['id']}").status_code == 404
    # target toujours présent
    assert client.get(f"/api/tiers/{target['id']}").status_code == 200


def test_merge_source_not_found(client):
    target = _create(client, name="Target")
    r = client.post(f"/api/tiers/999999/merge-into/{target['id']}")
    assert r.status_code == 404


def test_merge_target_not_found(client):
    source = _create(client, name="Source")
    r = client.post(f"/api/tiers/{source['id']}/merge-into/999999")
    assert r.status_code == 404


def test_merge_same_contact(client):
    c = _create(client, name="Self")
    r = client.post(f"/api/tiers/{c['id']}/merge-into/{c['id']}")
    assert r.status_code == 400
