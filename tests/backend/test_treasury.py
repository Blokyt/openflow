"""Tests Trésorerie : poches (bancaire lecture seule / manuelle) et mouvements.

Poche manuelle : solde = reference_cents + net des mouvements postérieurs à la
date de référence. Poche reliée à la banque : solde = solde bancaire, lecture
seule (pas de mouvement manuel). Rentrée augmente le total, sortie le diminue,
transfert le conserve.
"""
import sqlite3


def _pockets(client):
    return client.get("/api/treasury/pockets").json()


def _by_name(client, name):
    return next(p for p in _pockets(client)["pockets"] if p["name"] == name)


def _set_manual(client, pocket, cents, date="2020-01-01"):
    client.put(f"/api/treasury/pockets/{pocket['id']}", json={"reference_cents": cents, "reference_date": date})


# ─── Poches par défaut ────────────────────────────────────────────────────────

def test_three_default_pockets(client):
    body = _pockets(client)
    assert sorted(p["name"] for p in body["pockets"]) == ["Caisse", "Compte", "Livret"]
    assert body["total_cents"] == 0
    assert all(p["bank_linked"] is False for p in body["pockets"])


def test_reference_sets_balance(client):
    compte = _by_name(client, "Compte")
    _set_manual(client, compte, 500000)
    assert _by_name(client, "Compte")["balance_cents"] == 500000
    assert _pockets(client)["total_cents"] == 500000


# ─── Mouvements ───────────────────────────────────────────────────────────────

def test_transfer_conserves_total(client):
    compte, livret = _by_name(client, "Compte"), _by_name(client, "Livret")
    _set_manual(client, compte, 500000); _set_manual(client, livret, 100000)
    r = client.post("/api/treasury/movements", json={
        "from_pocket_id": livret["id"], "to_pocket_id": compte["id"],
        "amount_cents": 30000, "date": "2026-07-10", "label": "vir",
    })
    assert r.status_code == 201
    assert r.json()["total_cents"] == 600000
    assert _by_name(client, "Compte")["balance_cents"] == 530000
    assert _by_name(client, "Livret")["balance_cents"] == 70000


def test_income_increases_total(client):
    livret = _by_name(client, "Livret")
    _set_manual(client, livret, 100000)
    r = client.post("/api/treasury/movements", json={
        "from_pocket_id": None, "to_pocket_id": livret["id"],
        "amount_cents": 3000, "date": "2026-07-10", "label": "Intérêts",
    })
    assert r.json()["total_cents"] == 103000
    assert _by_name(client, "Livret")["balance_cents"] == 103000


def test_expense_decreases_total(client):
    caisse = _by_name(client, "Caisse")
    _set_manual(client, caisse, 10000)
    r = client.post("/api/treasury/movements", json={
        "from_pocket_id": caisse["id"], "to_pocket_id": None,
        "amount_cents": 2500, "date": "2026-07-10", "label": "achat",
    })
    assert r.json()["total_cents"] == 7500


def test_movement_before_reference_date_ignored(client):
    caisse = _by_name(client, "Caisse")
    _set_manual(client, caisse, 10000, date="2026-07-01")
    # Mouvement daté AVANT la référence : ignoré (déjà inclus dans le solde t).
    client.post("/api/treasury/movements", json={
        "from_pocket_id": None, "to_pocket_id": caisse["id"],
        "amount_cents": 5000, "date": "2026-06-15", "label": "vieux",
    })
    assert _by_name(client, "Caisse")["balance_cents"] == 10000


def test_movement_requires_a_pocket(client):
    r = client.post("/api/treasury/movements", json={
        "from_pocket_id": None, "to_pocket_id": None,
        "amount_cents": 1000, "date": "2026-07-10", "label": "",
    })
    assert r.status_code == 400


def test_delete_movement_reverts(client):
    compte, livret = _by_name(client, "Compte"), _by_name(client, "Livret")
    client.post("/api/treasury/movements", json={
        "from_pocket_id": compte["id"], "to_pocket_id": livret["id"],
        "amount_cents": 20000, "date": "2026-07-10", "label": "",
    })
    mv_id = client.get("/api/treasury/movements").json()[0]["id"]
    client.delete(f"/api/treasury/movements/{mv_id}")
    assert _by_name(client, "Compte")["balance_cents"] == 0
    assert _by_name(client, "Livret")["balance_cents"] == 0


# ─── Poche bancaire : lecture seule ───────────────────────────────────────────

def test_bank_linked_pocket_is_readonly_and_uses_bank_balance(client_and_db):
    client, db_path = client_and_db
    interne = client.post("/api/entities/", json={"name": "Asso", "type": "internal"}).json()["id"]
    acc = client.post("/api/bank_reconciliation/accounts", json={"entity_id": interne, "label": "CE"}).json()["id"]
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE bank_accounts SET balance_cents = 587426 WHERE id = ?", (acc,)); conn.commit(); conn.close()

    compte = _by_name(client, "Compte")
    client.put(f"/api/treasury/pockets/{compte['id']}", json={"bank_account_id": acc})
    p = _by_name(client, "Compte")
    assert p["bank_linked"] is True
    assert p["synced"] is True
    assert p["balance_cents"] == 587426  # = solde banque

    # Un mouvement manuel sur une poche bancaire est refusé.
    livret = _by_name(client, "Livret")
    r = client.post("/api/treasury/movements", json={
        "from_pocket_id": compte["id"], "to_pocket_id": livret["id"],
        "amount_cents": 1000, "date": "2026-07-10", "label": "",
    })
    assert r.status_code == 400


def test_annual_rate_stored(client):
    livret = _by_name(client, "Livret")
    client.put(f"/api/treasury/pockets/{livret['id']}", json={"annual_rate": 3.0})
    assert _by_name(client, "Livret")["annual_rate"] == 3.0


def test_cannot_delete_pocket_used_by_movement(client):
    compte, livret = _by_name(client, "Compte"), _by_name(client, "Livret")
    client.post("/api/treasury/movements", json={
        "from_pocket_id": compte["id"], "to_pocket_id": livret["id"],
        "amount_cents": 1000, "date": "2026-07-10", "label": "",
    })
    assert client.delete(f"/api/treasury/pockets/{compte['id']}").status_code == 409
