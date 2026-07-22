"""Tests du module Trésorerie : poches et transferts inter-poches.

Solde d'une poche = reference_cents + net des transferts (entrants - sortants).
Un transfert ne change pas le total.
"""
import sqlite3


def _pockets(client):
    return client.get("/api/treasury/pockets").json()


def _pocket_by_name(client, name):
    return next(p for p in _pockets(client)["pockets"] if p["name"] == name)


def test_three_default_pockets_seeded(client):
    body = _pockets(client)
    names = sorted(p["name"] for p in body["pockets"])
    assert names == ["Caisse", "Compte", "Livret"]
    assert body["total_cents"] == 0


def test_set_reference_updates_balance_and_total(client):
    compte = _pocket_by_name(client, "Compte")
    client.put(f"/api/treasury/pockets/{compte['id']}", json={"reference_cents": 500000, "reference_date": "2026-07-01"})
    livret = _pocket_by_name(client, "Livret")
    client.put(f"/api/treasury/pockets/{livret['id']}", json={"reference_cents": 120000})
    body = _pockets(client)
    assert body["total_cents"] == 620000
    assert _pocket_by_name(client, "Compte")["balance_cents"] == 500000


def test_transfer_moves_money_without_changing_total(client):
    compte = _pocket_by_name(client, "Compte")
    livret = _pocket_by_name(client, "Livret")
    client.put(f"/api/treasury/pockets/{compte['id']}", json={"reference_cents": 500000})
    client.put(f"/api/treasury/pockets/{livret['id']}", json={"reference_cents": 100000})

    r = client.post("/api/treasury/transfers", json={
        "from_pocket_id": livret["id"], "to_pocket_id": compte["id"],
        "amount_cents": 30000, "date": "2026-07-10", "label": "vir livret",
    })
    assert r.status_code == 201
    body = r.json()
    assert body["total_cents"] == 600000  # inchangé
    assert _pocket_by_name(client, "Compte")["balance_cents"] == 530000
    assert _pocket_by_name(client, "Livret")["balance_cents"] == 70000


def test_transfer_same_pocket_rejected(client):
    compte = _pocket_by_name(client, "Compte")
    r = client.post("/api/treasury/transfers", json={
        "from_pocket_id": compte["id"], "to_pocket_id": compte["id"],
        "amount_cents": 1000, "date": "2026-07-10", "label": "",
    })
    assert r.status_code == 400


def test_transfer_negative_amount_rejected(client):
    compte = _pocket_by_name(client, "Compte")
    livret = _pocket_by_name(client, "Livret")
    r = client.post("/api/treasury/transfers", json={
        "from_pocket_id": compte["id"], "to_pocket_id": livret["id"],
        "amount_cents": -5, "date": "2026-07-10", "label": "",
    })
    assert r.status_code == 400


def test_delete_transfer_reverts_balances(client):
    compte = _pocket_by_name(client, "Compte")
    livret = _pocket_by_name(client, "Livret")
    r = client.post("/api/treasury/transfers", json={
        "from_pocket_id": compte["id"], "to_pocket_id": livret["id"],
        "amount_cents": 20000, "date": "2026-07-10", "label": "",
    })
    tr_id = client.get("/api/treasury/transfers").json()[0]["id"]
    client.delete(f"/api/treasury/transfers/{tr_id}")
    assert _pocket_by_name(client, "Compte")["balance_cents"] == 0
    assert _pocket_by_name(client, "Livret")["balance_cents"] == 0


def test_create_and_delete_pocket(client):
    r = client.post("/api/treasury/pockets", json={"name": "Coffre"})
    assert r.status_code == 201
    coffre = _pocket_by_name(client, "Coffre")
    r = client.delete(f"/api/treasury/pockets/{coffre['id']}")
    assert r.status_code == 200
    assert all(p["name"] != "Coffre" for p in _pockets(client)["pockets"])


def test_cannot_delete_pocket_used_by_transfer(client):
    compte = _pocket_by_name(client, "Compte")
    livret = _pocket_by_name(client, "Livret")
    client.post("/api/treasury/transfers", json={
        "from_pocket_id": compte["id"], "to_pocket_id": livret["id"],
        "amount_cents": 1000, "date": "2026-07-10", "label": "",
    })
    r = client.delete(f"/api/treasury/pockets/{compte['id']}")
    assert r.status_code == 409


def test_align_bank_absorbs_ecart(client_and_db):
    client, db_path = client_and_db
    # Crée un compte bancaire avec un solde, et relie la poche Compte dessus.
    interne = client.post("/api/entities/", json={"name": "Asso", "type": "internal"}).json()["id"]
    acc = client.post("/api/bank_reconciliation/accounts", json={"entity_id": interne, "label": "CE"}).json()["id"]
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE bank_accounts SET balance_cents = 587426 WHERE id = ?", (acc,))
    conn.commit(); conn.close()

    compte = _pocket_by_name(client, "Compte")
    client.put(f"/api/treasury/pockets/{compte['id']}", json={"bank_account_id": acc})
    # Un transfert crée un écart avec la banque.
    livret = _pocket_by_name(client, "Livret")
    client.post("/api/treasury/transfers", json={
        "from_pocket_id": compte["id"], "to_pocket_id": livret["id"],
        "amount_cents": 10000, "date": "2026-07-10", "label": "",
    })
    p = _pocket_by_name(client, "Compte")
    assert p["bank_balance_cents"] == 587426
    assert p["balance_cents"] == -10000  # reference 0 - transfert 10000

    r = client.post(f"/api/treasury/pockets/{compte['id']}/align-bank")
    assert r.status_code == 200
    assert _pocket_by_name(client, "Compte")["balance_cents"] == 587426  # aligné
