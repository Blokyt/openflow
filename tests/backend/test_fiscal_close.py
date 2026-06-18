"""Tests TDD — Lot C : clôture réelle, report à nouveau, verrou.

Couvre :
1. Opening-balances saisis (upsert + priorité dans get_budget_view)
2. Verrou de clôture sur create/update/delete_transaction
3. Unicité exercice ouvert à la création
4. previous_fiscal_year_id renseigné automatiquement
"""
import os
import sys
import sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _make_fy(client, name="2024-2025", start="2024-09-01", notes=""):
    r = client.post("/api/budget/fiscal-years", json={"name": name, "start_date": start, "notes": notes})
    assert r.status_code == 201, r.text
    return r.json()


def _close_fy(client, fy_id, end_date="2025-08-31"):
    r = client.post(f"/api/budget/fiscal-years/{fy_id}/close", json={"end_date": end_date})
    assert r.status_code == 200, r.text
    return r.json()


def _reopen_fy(client, fy_id):
    """Rouvrir un exercice : mettre end_date à NULL via PUT."""
    r = client.put(f"/api/budget/fiscal-years/{fy_id}", json={"end_date": None})
    assert r.status_code == 200, r.text
    return r.json()


def _make_entities(client):
    src = client.post("/api/entities/", json={"name": "Ext", "type": "external"}).json()
    dst = client.post("/api/entities/", json={"name": "Club", "type": "internal"}).json()
    return src["id"], dst["id"]


# ─── 1. Opening-balances ────────────────────────────────────────────────────

def test_upsert_opening_balance_creates_row(client):
    """PUT opening-balance crée une ligne en DB."""
    fy = _make_fy(client)
    _, eid = _make_entities(client)

    r = client.put(
        f"/api/budget/fiscal-years/{fy['id']}/opening-balances/{eid}",
        json={"amount": 150000, "source": "relevé bancaire", "notes": "solde réel"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["amount"] == 150000
    assert data["source"] == "relevé bancaire"
    assert data["entity_id"] == eid
    assert data["fiscal_year_id"] == fy["id"]


def test_upsert_opening_balance_is_idempotent(client):
    """PUT deux fois sur le même (fy, entity) : le deuxième écrase le premier."""
    fy = _make_fy(client)
    _, eid = _make_entities(client)

    client.put(
        f"/api/budget/fiscal-years/{fy['id']}/opening-balances/{eid}",
        json={"amount": 100000, "source": "v1"},
    )
    r = client.put(
        f"/api/budget/fiscal-years/{fy['id']}/opening-balances/{eid}",
        json={"amount": 200000, "source": "v2"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["amount"] == 200000


def test_get_opening_balances_list(client):
    """GET opening-balances renvoie la liste pour l'exercice."""
    fy = _make_fy(client)
    _, eid1 = _make_entities(client)
    eid2 = client.post("/api/entities/", json={"name": "Club2", "type": "internal"}).json()["id"]

    client.put(
        f"/api/budget/fiscal-years/{fy['id']}/opening-balances/{eid1}",
        json={"amount": 50000},
    )
    client.put(
        f"/api/budget/fiscal-years/{fy['id']}/opening-balances/{eid2}",
        json={"amount": 80000},
    )

    r = client.get(f"/api/budget/fiscal-years/{fy['id']}/opening-balances")
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) == 2
    amounts = {row["entity_id"]: row["amount"] for row in rows}
    assert amounts[eid1] == 50000
    assert amounts[eid2] == 80000


def test_budget_view_uses_saisi_opening_balance(client):
    """Si un opening-balance saisi existe pour (fy, entity), get_budget_view l'utilise
    comme opening à la place du calcul dynamique."""
    fy = _make_fy(client)
    ext_id, eid = _make_entities(client)

    # Crée une transaction AVANT l'exercice (contribuerait normalement à l'opening calculé).
    client.post("/api/transactions/", json={
        "date": "2024-05-01", "label": "avant fy", "amount": 10000,
        "from_entity_id": ext_id, "to_entity_id": eid,
    })

    # Saisit un opening-balance manuellement.
    opening_saisi = 250000  # 2500 €
    client.put(
        f"/api/budget/fiscal-years/{fy['id']}/opening-balances/{eid}",
        json={"amount": opening_saisi, "source": "virement initial"},
    )

    r = client.get(f"/api/budget/view?fiscal_year_id={fy['id']}")
    assert r.status_code == 200, r.text
    data = r.json()
    club = next(x for x in data["entities"] if x["entity_id"] == eid)

    # Le solde saisi (250000) doit primer sur le calcul dynamique (10000).
    assert club["opening_balance"] == 250000


def test_budget_view_falls_back_to_computed_when_no_opening_balance(client):
    """Sans opening-balance saisi, get_budget_view calcule le solde dynamiquement."""
    fy = _make_fy(client)
    ext_id, eid = _make_entities(client)

    client.post("/api/transactions/", json={
        "date": "2024-05-01", "label": "avant fy", "amount": 30000,
        "from_entity_id": ext_id, "to_entity_id": eid,
    })

    r = client.get(f"/api/budget/view?fiscal_year_id={fy['id']}")
    assert r.status_code == 200, r.text
    data = r.json()
    club = next(x for x in data["entities"] if x["entity_id"] == eid)

    # Calcul dynamique : tx avant fy → entrant pour eid → +30000.
    assert club["opening_balance"] == 30000


# ─── 2. Verrou de clôture ────────────────────────────────────────────────────

def test_create_transaction_in_closed_period_returns_409(client):
    """Créer une transaction dont la date tombe dans un exercice clôturé → 409."""
    fy = _make_fy(client, "2024-2025", "2024-09-01")
    _close_fy(client, fy["id"], "2025-08-31")

    ext_id, eid = _make_entities(client)
    r = client.post("/api/transactions/", json={
        "date": "2024-10-15",  # dans l'exercice clôturé
        "label": "interdit", "amount": 5000,
        "from_entity_id": ext_id, "to_entity_id": eid,
    })
    assert r.status_code == 409, r.text
    assert "clôturé" in r.json()["detail"].lower() or "cloture" in r.json()["detail"].lower() \
        or "exercice" in r.json()["detail"].lower()


def test_create_transaction_after_reopen_passes(client):
    """Rouvrir l'exercice (end_date → NULL) puis créer la tx : 201."""
    fy = _make_fy(client, "2024-2025", "2024-09-01")
    _close_fy(client, fy["id"], "2025-08-31")

    # Réouverture
    _reopen_fy(client, fy["id"])

    ext_id, eid = _make_entities(client)
    r = client.post("/api/transactions/", json={
        "date": "2024-10-15",
        "label": "maintenant permis", "amount": 5000,
        "from_entity_id": ext_id, "to_entity_id": eid,
    })
    assert r.status_code == 201, r.text


def test_update_transaction_date_to_closed_period_returns_409(client):
    """Modifier la date d'une tx pour la faire tomber dans un exercice clôturé → 409."""
    fy = _make_fy(client, "2024-2025", "2024-09-01")
    _close_fy(client, fy["id"], "2025-08-31")

    ext_id, eid = _make_entities(client)
    # Crée la tx dans une période ouverte
    tx = client.post("/api/transactions/", json={
        "date": "2025-10-15",  # hors de la période clôturée
        "label": "tx libre", "amount": 1000,
        "from_entity_id": ext_id, "to_entity_id": eid,
    }).json()

    # Tente de déplacer dans la période clôturée
    r = client.put(f"/api/transactions/{tx['id']}", json={"date": "2024-11-01"})
    assert r.status_code == 409, r.text


def test_update_transaction_already_in_closed_period_returns_409(client):
    """Modifier une tx existante déjà dans une période clôturée → 409 (même sans changer la date)."""
    fy = _make_fy(client, "2024-2025", "2024-09-01")
    ext_id, eid = _make_entities(client)

    # Crée la tx pendant que l'exercice est ouvert
    tx = client.post("/api/transactions/", json={
        "date": "2024-10-15",
        "label": "tx existante", "amount": 1000,
        "from_entity_id": ext_id, "to_entity_id": eid,
    }).json()
    assert tx.get("id"), tx

    # Clôt l'exercice
    _close_fy(client, fy["id"], "2025-08-31")

    # Tente une modification (label seul, date inchangée)
    r = client.put(f"/api/transactions/{tx['id']}", json={"label": "modif interdite"})
    assert r.status_code == 409, r.text


def test_delete_transaction_in_closed_period_returns_409(client):
    """Supprimer une tx dont la date tombe dans un exercice clôturé → 409."""
    fy = _make_fy(client, "2024-2025", "2024-09-01")
    ext_id, eid = _make_entities(client)

    tx = client.post("/api/transactions/", json={
        "date": "2024-10-15",
        "label": "à supprimer", "amount": 2000,
        "from_entity_id": ext_id, "to_entity_id": eid,
    }).json()

    _close_fy(client, fy["id"], "2025-08-31")

    r = client.delete(f"/api/transactions/{tx['id']}")
    assert r.status_code == 409, r.text


def test_create_transaction_outside_closed_period_passes(client):
    """Une tx dont la date est EN DEHORS de toute période clôturée passe normalement."""
    fy = _make_fy(client, "2024-2025", "2024-09-01")
    _close_fy(client, fy["id"], "2025-08-31")

    ext_id, eid = _make_entities(client)
    # 2025-10-01 est après la clôture (2025-08-31) → pas bloqué
    r = client.post("/api/transactions/", json={
        "date": "2025-10-01",
        "label": "tx autorisée", "amount": 3000,
        "from_entity_id": ext_id, "to_entity_id": eid,
    })
    assert r.status_code == 201, r.text


# ─── 3. Unicité exercice ouvert ──────────────────────────────────────────────

def test_cannot_create_two_open_fiscal_years(client):
    """Impossible de créer deux exercices ouverts (le 2e → 400)."""
    _make_fy(client, "2024-2025", "2024-09-01")
    r = client.post("/api/budget/fiscal-years", json={
        "name": "2025-2026", "start_date": "2025-09-01",
    })
    assert r.status_code == 400, r.text
    assert "ouvert" in r.json()["detail"].lower()


def test_can_create_second_fiscal_year_after_close(client):
    """Après clôture du premier, on peut créer le deuxième."""
    fy1 = _make_fy(client, "2024-2025", "2024-09-01")
    _close_fy(client, fy1["id"], "2025-08-31")

    r = client.post("/api/budget/fiscal-years", json={
        "name": "2025-2026", "start_date": "2025-09-01",
    })
    assert r.status_code == 201, r.text


# ─── 4. previous_fiscal_year_id ─────────────────────────────────────────────

def test_previous_fiscal_year_id_set_on_creation(client):
    """À la création du 2e exercice, previous_fiscal_year_id pointe vers le 1er."""
    fy1 = _make_fy(client, "2024-2025", "2024-09-01")
    _close_fy(client, fy1["id"], "2025-08-31")

    r = client.post("/api/budget/fiscal-years", json={
        "name": "2025-2026", "start_date": "2025-09-01",
    })
    assert r.status_code == 201, r.text
    fy2 = r.json()
    assert fy2.get("previous_fiscal_year_id") == fy1["id"], (
        f"previous_fiscal_year_id attendu={fy1['id']}, obtenu={fy2.get('previous_fiscal_year_id')}"
    )


def test_first_fiscal_year_has_no_previous(client):
    """Le premier exercice créé n'a pas de previous_fiscal_year_id."""
    fy1 = _make_fy(client, "2024-2025", "2024-09-01")
    assert fy1.get("previous_fiscal_year_id") is None


def test_budget_view_uses_explicit_previous_link(client):
    """get_budget_view utilise previous_fiscal_year_id s'il est renseigné."""
    fy1 = _make_fy(client, "2024-2025", "2024-09-01")

    ext_id, eid = _make_entities(client)
    # Tx N-1 : créée pendant que fy1 est encore ouvert.
    r_n1 = client.post("/api/transactions/", json={
        "date": "2024-10-15", "label": "n-1", "amount": 10000,
        "from_entity_id": eid, "to_entity_id": ext_id,
    })
    assert r_n1.status_code == 201, r_n1.text

    _close_fy(client, fy1["id"], "2025-08-31")

    fy2 = client.post("/api/budget/fiscal-years", json={
        "name": "2025-2026", "start_date": "2025-09-01",
    }).json()

    # Tx N : dans fy2 (ouvert).
    client.post("/api/transactions/", json={
        "date": "2025-10-15", "label": "n", "amount": 14000,
        "from_entity_id": eid, "to_entity_id": ext_id,
    })

    data = client.get(f"/api/budget/view?fiscal_year_id={fy2['id']}").json()
    assert data["previous_fiscal_year_id"] == fy1["id"]
    club = next(x for x in data["entities"] if x["entity_id"] == eid)
    assert round(club["realized_n_minus_1"], 2) == -10000
