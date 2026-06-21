"""Contrats de montant : les champs stockés en centimes refusent les fractions.

Garantit que reference_amount (balance-ref) et amount (allocation budgétaire)
n'acceptent que des entiers, pour préserver l'égalité entière du bilan.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


def _internal_entity(client, name="Caisse"):
    return client.post("/api/entities/", json={"name": name, "type": "internal"}).json()


def test_balance_ref_rejects_fractional_amount(client):
    e = _internal_entity(client, "CaisseFrac")
    r = client.put(f"/api/entities/{e['id']}/balance-ref", json={
        "reference_date": "2024-01-01", "reference_amount": 500.5,
    })
    assert r.status_code == 422, r.text


def test_balance_ref_accepts_integer_amount(client):
    e = _internal_entity(client, "CaisseInt")
    r = client.put(f"/api/entities/{e['id']}/balance-ref", json={
        "reference_date": "2024-01-01", "reference_amount": 50000,
    })
    assert r.status_code == 200, r.text
    assert r.json()["reference_amount"] == 50000


def test_allocation_rejects_fractional_amount(client):
    fy = client.post("/api/budget/fiscal-years", json={
        "name": "2024-2025", "start_date": "2024-09-01",
    }).json()
    e = _internal_entity(client, "ClubAllocFrac")
    r = client.post(f"/api/budget/fiscal-years/{fy['id']}/allocations", json={
        "entity_id": e["id"], "amount": 100.5,
    })
    assert r.status_code == 422, r.text


def test_allocation_accepts_integer_amount(client):
    fy = client.post("/api/budget/fiscal-years", json={
        "name": "2024-2025", "start_date": "2024-09-01",
    }).json()
    e = _internal_entity(client, "ClubAllocInt")
    r = client.post(f"/api/budget/fiscal-years/{fy['id']}/allocations", json={
        "entity_id": e["id"], "amount": 100000,
    })
    assert r.status_code == 201, r.text
    assert r.json()["amount"] == 100000
