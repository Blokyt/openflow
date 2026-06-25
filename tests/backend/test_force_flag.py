"""Tests — franchissement du verrou de clôture via ?force=true.

Le verrou d'exercice clôturé reste actif par défaut (cf test_fiscal_close.py) mais
devient franchissable quand l'appelant passe explicitement force=true (confirmation
« Modifier quand même ? » côté UI).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


def _make_fy(client, name="2024-2025", start="2024-09-01"):
    r = client.post("/api/budget/fiscal-years", json={"name": name, "start_date": start})
    assert r.status_code == 201, r.text
    return r.json()


def _close_fy(client, fy_id, end_date="2025-08-31"):
    r = client.post(f"/api/budget/fiscal-years/{fy_id}/close", json={"end_date": end_date})
    assert r.status_code == 200, r.text
    return r.json()


def _entities(client):
    ext = client.post("/api/entities/", json={"name": "Ext", "type": "external"}).json()
    club = client.post("/api/entities/", json={"name": "Club", "type": "internal"}).json()
    return ext["id"], club["id"]


def test_create_in_closed_period_with_force_returns_201(client):
    fy = _make_fy(client)
    _close_fy(client, fy["id"])
    ext, club = _entities(client)
    r = client.post("/api/transactions/?force=true", json={
        "date": "2024-10-15", "label": "forcée", "amount": 5000,
        "from_entity_id": club, "to_entity_id": ext,
    })
    assert r.status_code == 201, r.text


def test_update_in_closed_period_with_force_returns_200(client):
    fy = _make_fy(client)
    ext, club = _entities(client)
    tx = client.post("/api/transactions/", json={
        "date": "2024-10-15", "label": "tx", "amount": 1000,
        "from_entity_id": club, "to_entity_id": ext,
    }).json()
    _close_fy(client, fy["id"])
    r = client.put(f"/api/transactions/{tx['id']}?force=true", json={"label": "modifiée"})
    assert r.status_code == 200, r.text
    assert r.json()["label"] == "modifiée"


def test_delete_in_closed_period_with_force_returns_200(client):
    fy = _make_fy(client)
    ext, club = _entities(client)
    tx = client.post("/api/transactions/", json={
        "date": "2024-10-15", "label": "tx", "amount": 1000,
        "from_entity_id": club, "to_entity_id": ext,
    }).json()
    _close_fy(client, fy["id"])
    r = client.delete(f"/api/transactions/{tx['id']}?force=true")
    assert r.status_code == 200, r.text


def test_create_without_force_still_returns_409(client):
    """Garde-fou conservé : sans force, le verrou bloque toujours."""
    fy = _make_fy(client)
    _close_fy(client, fy["id"])
    ext, club = _entities(client)
    r = client.post("/api/transactions/", json={
        "date": "2024-10-15", "label": "bloquée", "amount": 5000,
        "from_entity_id": club, "to_entity_id": ext,
    })
    assert r.status_code == 409, r.text


def test_force_does_not_bypass_amount_validation(client):
    """force ne contourne QUE le verrou de clôture, pas les autres validations."""
    fy = _make_fy(client)
    _close_fy(client, fy["id"])
    ext, club = _entities(client)
    r = client.post("/api/transactions/?force=true", json={
        "date": "2024-10-15", "label": "négative", "amount": -100,
        "from_entity_id": club, "to_entity_id": ext,
    })
    assert r.status_code == 400, r.text
