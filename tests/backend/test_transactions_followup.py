"""Tests — suivi de transaction : switch « Justifié » et infos de suivi en liste.

Le trésorier suit deux choses par transaction :
- « Remboursé » : porté par la fiche de remboursement (source de vérité unique,
  module reimbursements) — la liste expose reimb_id pour basculer le statut.
- « Justifié » : booléen manuel sur la transaction (indépendant de la présence
  de pièces jointes, qui est exposée séparément via attachment_count).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from tests.backend.conftest import MINIMAL_PDF


def _entities(client):
    ext = client.post("/api/entities/", json={"name": "Ext", "type": "external"}).json()
    club = client.post("/api/entities/", json={"name": "Club", "type": "internal"}).json()
    return ext["id"], club["id"]


def _tx(client, src, dst, label="tx", date="2026-01-15", amount=1000):
    r = client.post("/api/transactions/", json={
        "date": date, "label": label, "amount": amount,
        "from_entity_id": src, "to_entity_id": dst,
    })
    assert r.status_code == 201, r.text
    return r.json()


def test_justified_defaults_to_false(client):
    src, dst = _entities(client)
    tx = _tx(client, src, dst)
    assert tx["justified"] == 0
    assert tx["justified_at"] is None

    r = client.get("/api/transactions/")
    assert r.status_code == 200
    item = next(t for t in r.json()["items"] if t["id"] == tx["id"])
    assert item["justified"] == 0


def test_toggle_justified_on_off(client):
    src, dst = _entities(client)
    tx = _tx(client, src, dst)

    r = client.put(f"/api/transactions/{tx['id']}", json={"justified": True})
    assert r.status_code == 200, r.text
    assert r.json()["justified"] == 1
    assert r.json()["justified_at"] is not None

    r = client.put(f"/api/transactions/{tx['id']}", json={"justified": False})
    assert r.status_code == 200, r.text
    assert r.json()["justified"] == 0
    assert r.json()["justified_at"] is None


def test_filter_justified(client):
    src, dst = _entities(client)
    tx_yes = _tx(client, src, dst, label="justifiée")
    tx_no = _tx(client, src, dst, label="non justifiée")
    client.put(f"/api/transactions/{tx_yes['id']}", json={"justified": True})

    r = client.get("/api/transactions/?justified=1")
    assert r.status_code == 200
    ids = [t["id"] for t in r.json()["items"]]
    assert tx_yes["id"] in ids
    assert tx_no["id"] not in ids

    r = client.get("/api/transactions/?justified=0")
    assert r.status_code == 200
    ids = [t["id"] for t in r.json()["items"]]
    assert tx_no["id"] in ids
    assert tx_yes["id"] not in ids

    r = client.get("/api/transactions/?justified=2")
    assert r.status_code == 400


def test_justified_toggle_exempt_from_closed_period_lock(client):
    """Le suivi n'est pas une écriture comptable : basculer « justifié » sur une
    transaction d'un exercice clôturé passe sans force, contrairement à une
    modification comptable (libellé, montant…)."""
    fy = client.post("/api/budget/fiscal-years", json={"name": "Clos", "start_date": "2024-09-01"}).json()
    src, dst = _entities(client)
    tx = _tx(client, src, dst, date="2024-10-15")
    r = client.post(f"/api/budget/fiscal-years/{fy['id']}/close", json={"end_date": "2025-08-31"})
    assert r.status_code == 200, r.text

    # Suivi seul : passe sans force.
    r = client.put(f"/api/transactions/{tx['id']}", json={"justified": True})
    assert r.status_code == 200, r.text
    assert r.json()["justified"] == 1

    # Modification comptable : toujours verrouillée.
    r = client.put(f"/api/transactions/{tx['id']}", json={"label": "modifiée"})
    assert r.status_code == 409

    # Mélange suivi + comptable : verrouillé aussi (le suivi ne sert pas de cheval de Troie).
    r = client.put(f"/api/transactions/{tx['id']}", json={"justified": False, "label": "modifiée"})
    assert r.status_code == 409


def test_list_exposes_attachment_count(client):
    src, dst = _entities(client)
    tx_with = _tx(client, src, dst, label="avec pièce")
    tx_without = _tx(client, src, dst, label="sans pièce")

    r = client.post(
        f"/api/attachments/transaction/{tx_with['id']}",
        files={"file": ("facture.pdf", MINIMAL_PDF, "application/pdf")},
    )
    assert r.status_code == 201, r.text

    r = client.get("/api/transactions/")
    assert r.status_code == 200
    items = {t["id"]: t for t in r.json()["items"]}
    assert items[tx_with["id"]]["attachment_count"] == 1
    assert items[tx_without["id"]]["attachment_count"] == 0


def test_list_exposes_reimb_id(client):
    src, dst = _entities(client)
    tx = _tx(client, src, dst, label="avance")
    reimb = client.post("/api/reimbursements/", json={
        "transaction_id": tx["id"], "person_name": "Alice",
        "amount": 1000, "status": "pending",
    }).json()

    r = client.get("/api/transactions/")
    assert r.status_code == 200
    item = next(t for t in r.json()["items"] if t["id"] == tx["id"])
    assert item["reimb_id"] == reimb["id"]
    assert item["reimb_status"] == "pending"
