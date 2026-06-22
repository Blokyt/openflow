"""Tests du module remboursements — mode simple (suivi 2 états).

Le module est un outil de suivi : transitions LIBRES entre statuts, AUCUNE
écriture comptable générée automatiquement. Le trésorier saisit ses sorties
d'argent lui-même.

Convention montants : ENTIERS en CENTIMES, toujours positifs (4250 = 42,50 €).
"""
import os
import sys
import sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import pytest
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_internal_entity(db_path, name="_Internal"):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        "INSERT INTO entities (name, type, parent_id, is_default, is_divers, color, position, created_at, updated_at) "
        "VALUES (?, 'internal', NULL, 0, 0, '#6B7280', 1, ?, ?)",
        (name, now, now),
    )
    eid = cur.lastrowid
    conn.commit()
    conn.close()
    return eid


def _make_external_entity(db_path, name="_External"):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        "INSERT INTO entities (name, type, parent_id, is_default, is_divers, color, position, created_at, updated_at) "
        "VALUES (?, 'external', NULL, 0, 0, '#6B7280', 2, ?, ?)",
        (name, now, now),
    )
    eid = cur.lastrowid
    conn.commit()
    conn.close()
    return eid


def _make_contact(db_path, name="Payeur Test"):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        "INSERT INTO contacts (name, email, created_at, updated_at) VALUES (?, '', ?, ?)",
        (name, now, now),
    )
    cid = cur.lastrowid
    conn.commit()
    conn.close()
    return cid


def _make_transaction(client, db_path, from_id, to_id, amount=5000, label="Dépense test"):
    resp = client.post("/api/transactions/", json={
        "date": "2026-01-15",
        "label": label,
        "amount": amount,
        "from_entity_id": from_id,
        "to_entity_id": to_id,
    })
    assert resp.status_code == 201, resp.json()
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# 1. Transitions LIBRES (mode simple)
# ---------------------------------------------------------------------------

class TestStateTransitionsSimple:
    def test_pending_to_approved_ok(self, client):
        r = client.post("/api/reimbursements/", json={"person_name": "Alice", "amount": 1000})
        rid = r.json()["id"]
        resp = client.put(f"/api/reimbursements/{rid}", json={"status": "approved"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"

    def test_pending_to_rejected_ok(self, client):
        r = client.post("/api/reimbursements/", json={"person_name": "Bob", "amount": 500})
        rid = r.json()["id"]
        resp = client.put(f"/api/reimbursements/{rid}", json={"status": "rejected"})
        assert resp.status_code == 200

    def test_pending_to_reimbursed_ok(self, client):
        """Mode simple : la coche directe pending -> reimbursed est autorisée."""
        r = client.post("/api/reimbursements/", json={"person_name": "Carol", "amount": 2000})
        rid = r.json()["id"]
        resp = client.put(
            f"/api/reimbursements/{rid}",
            json={"status": "reimbursed", "reimbursed_date": "2026-06-22"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "reimbursed"
        assert resp.json()["reimbursed_date"] == "2026-06-22"

    def test_reimbursed_to_pending_ok(self, client):
        """Mode simple : on peut remettre un remboursement en attente."""
        r = client.post("/api/reimbursements/", json={"person_name": "Dan", "amount": 1500})
        rid = r.json()["id"]
        client.put(f"/api/reimbursements/{rid}", json={"status": "reimbursed"})
        resp = client.put(f"/api/reimbursements/{rid}", json={"status": "pending"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "pending"

    def test_invalid_status_rejected(self, client):
        """Un statut inconnu renvoie 400 (guard métier) ou 422 (validation Pydantic)."""
        r = client.post("/api/reimbursements/", json={"person_name": "Eve", "amount": 100})
        rid = r.json()["id"]
        resp = client.put(f"/api/reimbursements/{rid}", json={"status": "wat"})
        assert resp.status_code in (400, 422)


# ---------------------------------------------------------------------------
# 2. Aucune écriture comptable générée automatiquement
# ---------------------------------------------------------------------------

class TestNoAutoDisbursement:
    def test_reimbursed_creates_no_transaction(self, client, db_path):
        """Passer à reimbursed ne crée AUCUNE transaction de décaissement."""
        from_id = _make_internal_entity(db_path, "IntNoDisb")
        to_id = _make_external_entity(db_path, "ExtNoDisb")
        tx_id = _make_transaction(client, db_path, from_id, to_id, amount=8000)
        r = client.post("/api/reimbursements/", json={
            "person_name": "Jean", "amount": 8000, "transaction_id": tx_id,
        })
        rid = r.json()["id"]
        resp = client.put(f"/api/reimbursements/{rid}", json={"status": "reimbursed"})
        assert resp.status_code == 200
        assert resp.json()["reimbursement_transaction_id"] is None

        conn = sqlite3.connect(str(db_path))
        n = conn.execute(
            "SELECT COUNT(*) FROM transactions WHERE label LIKE 'Remboursement%'"
        ).fetchone()[0]
        conn.close()
        assert n == 0


# ---------------------------------------------------------------------------
# 3. Édition d'une transaction : le remboursement lié est préservé (régression)
# ---------------------------------------------------------------------------

class TestTransactionEditPreservesReimbursement:
    def test_editing_date_keeps_reimbursed_status(self, client, db_path):
        """Changer la date d'une transaction NE doit PAS réinitialiser le
        remboursement lié (bug : il repassait en attente)."""
        contact_id = _make_contact(db_path, "Rémy Level")
        from_id = _make_internal_entity(db_path, "ClubEdit")
        to_id = _make_external_entity(db_path, "FournisseurEdit")
        tx = client.post("/api/transactions/", json={
            "date": "2026-03-01", "label": "Avance Rémy", "amount": 4574,
            "from_entity_id": from_id, "to_entity_id": to_id,
            "payer_contact_id": contact_id,
        }).json()
        tx_id = tx["id"]

        reimbs = [x for x in client.get("/api/reimbursements/").json() if x["transaction_id"] == tx_id]
        assert len(reimbs) == 1
        rid = reimbs[0]["id"]
        assert reimbs[0]["status"] == "pending"

        # On marque le remboursement comme réglé.
        client.put(f"/api/reimbursements/{rid}", json={"status": "reimbursed", "reimbursed_date": "2026-06-22"})

        # On édite la transaction (changement de date) ; le formulaire renvoie le MÊME payeur.
        resp = client.put(f"/api/transactions/{tx_id}", json={"date": "2026-07-01", "payer_contact_id": contact_id})
        assert resp.status_code == 200

        # Le remboursement doit RESTER réglé, même id.
        r2 = client.get(f"/api/reimbursements/{rid}").json()
        assert r2["status"] == "reimbursed"

    def test_changing_payer_replaces_reimbursement(self, client, db_path):
        """Changer réellement le payeur remplace le suivi (nouveau, en attente)."""
        c1 = _make_contact(db_path, "Payeur Un")
        c2 = _make_contact(db_path, "Payeur Deux")
        from_id = _make_internal_entity(db_path, "ClubPayer")
        to_id = _make_external_entity(db_path, "FournisseurPayer")
        tx = client.post("/api/transactions/", json={
            "date": "2026-03-01", "label": "Avance", "amount": 3000,
            "from_entity_id": from_id, "to_entity_id": to_id, "payer_contact_id": c1,
        }).json()
        tx_id = tx["id"]

        client.put(f"/api/transactions/{tx_id}", json={"payer_contact_id": c2})

        reimbs = [x for x in client.get("/api/reimbursements/").json() if x["transaction_id"] == tx_id]
        assert len(reimbs) == 1
        assert reimbs[0]["contact_id"] == c2
        assert reimbs[0]["status"] == "pending"

    def test_editing_amount_resyncs_pending_reimbursement(self, client, db_path):
        """Si l'avance est encore en attente, corriger le montant de la transaction
        resynchronise le montant du suivi."""
        contact_id = _make_contact(db_path, "Resync Test")
        from_id = _make_internal_entity(db_path, "ClubResync")
        to_id = _make_external_entity(db_path, "FournisseurResync")
        tx = client.post("/api/transactions/", json={
            "date": "2026-03-01", "label": "Avance", "amount": 5000,
            "from_entity_id": from_id, "to_entity_id": to_id, "payer_contact_id": contact_id,
        }).json()
        tx_id = tx["id"]
        client.put(f"/api/transactions/{tx_id}", json={"amount": 6000, "payer_contact_id": contact_id})
        reimbs = [x for x in client.get("/api/reimbursements/").json() if x["transaction_id"] == tx_id]
        assert reimbs[0]["amount"] == 6000
        assert reimbs[0]["status"] == "pending"


# ---------------------------------------------------------------------------
# 4. Suppression
# ---------------------------------------------------------------------------

class TestDeletion:
    def test_delete_pending_ok(self, client):
        r = client.post("/api/reimbursements/", json={"person_name": "DeletePending", "amount": 100})
        rid = r.json()["id"]
        assert client.delete(f"/api/reimbursements/{rid}").status_code == 200

    def test_delete_approved_ok(self, client):
        r = client.post("/api/reimbursements/", json={"person_name": "DeleteApproved", "amount": 200})
        rid = r.json()["id"]
        client.put(f"/api/reimbursements/{rid}", json={"status": "approved"})
        assert client.delete(f"/api/reimbursements/{rid}").status_code == 200

    def test_delete_reimbursed_returns_409(self, client):
        """Supprimer un remboursement réglé est refusé (409) : repasser en attente d'abord."""
        r = client.post("/api/reimbursements/", json={"person_name": "Réglé", "amount": 900})
        rid = r.json()["id"]
        client.put(f"/api/reimbursements/{rid}", json={"status": "reimbursed"})
        resp = client.delete(f"/api/reimbursements/{rid}")
        assert resp.status_code == 409
        assert "attente" in resp.json()["detail"].lower()

    def test_repending_then_delete_ok(self, client):
        """Après repassage en attente, la suppression d'un remboursement réglé est permise."""
        r = client.post("/api/reimbursements/", json={"person_name": "ReglePuisSupr", "amount": 700})
        rid = r.json()["id"]
        client.put(f"/api/reimbursements/{rid}", json={"status": "reimbursed"})
        client.put(f"/api/reimbursements/{rid}", json={"status": "pending"})
        assert client.delete(f"/api/reimbursements/{rid}").status_code == 200


# ---------------------------------------------------------------------------
# 5. Déduplication à la création
# ---------------------------------------------------------------------------

class TestDeduplication:
    def test_duplicate_with_contact_returns_409(self, client, db_path):
        contact_id = _make_contact(db_path, "Dedup Contact")
        r1 = client.post("/api/reimbursements/", json={
            "person_name": "Dedup Contact", "amount": 5500, "contact_id": contact_id,
        })
        assert r1.status_code == 201
        r2 = client.post("/api/reimbursements/", json={
            "person_name": "Dedup Contact", "amount": 5500, "contact_id": contact_id,
        })
        assert r2.status_code == 409

    def test_duplicate_with_force_returns_201(self, client, db_path):
        contact_id = _make_contact(db_path, "Force Contact")
        r1 = client.post("/api/reimbursements/", json={
            "person_name": "Force Contact", "amount": 6000, "contact_id": contact_id,
        })
        assert r1.status_code == 201
        r2 = client.post("/api/reimbursements/", json={
            "person_name": "Force Contact", "amount": 6000, "contact_id": contact_id, "force": True,
        })
        assert r2.status_code == 201

    def test_rejected_does_not_block_dedup(self, client, db_path):
        contact_id = _make_contact(db_path, "Rejected Dedup")
        r1 = client.post("/api/reimbursements/", json={
            "person_name": "Rejected Dedup", "amount": 1100, "contact_id": contact_id,
        })
        assert r1.status_code == 201
        rid = r1.json()["id"]
        client.put(f"/api/reimbursements/{rid}", json={"status": "rejected"})
        r2 = client.post("/api/reimbursements/", json={
            "person_name": "Rejected Dedup", "amount": 1100, "contact_id": contact_id,
        })
        assert r2.status_code == 201

    def test_dedup_no_contact_id_no_check(self, client):
        r1 = client.post("/api/reimbursements/", json={"person_name": "NoContact", "amount": 2000})
        assert r1.status_code == 201
        r2 = client.post("/api/reimbursements/", json={"person_name": "NoContact", "amount": 2000})
        assert r2.status_code == 201


# ---------------------------------------------------------------------------
# 6. Guards à la création
# ---------------------------------------------------------------------------

class TestCreateGuards:
    def test_create_with_reimbursement_transaction_id_returns_400(self, client):
        resp = client.post("/api/reimbursements/", json={
            "person_name": "Bloq", "amount": 500, "reimbursement_transaction_id": 1,
        })
        assert resp.status_code == 400

    def test_create_with_invalid_transaction_id_returns_400(self, client):
        resp = client.post("/api/reimbursements/", json={
            "person_name": "BadTx", "amount": 300, "transaction_id": 999999,
        })
        assert resp.status_code == 400

    def test_create_with_valid_transaction_id_ok(self, client, db_path):
        from_id = _make_internal_entity(db_path, "IntValidTx")
        to_id = _make_external_entity(db_path, "ExtValidTx")
        tx_id = _make_transaction(client, db_path, from_id, to_id, amount=1000)
        resp = client.post("/api/reimbursements/", json={
            "person_name": "ValidTx", "amount": 1000, "transaction_id": tx_id,
        })
        assert resp.status_code == 201

    def test_create_default_status_is_pending(self, client):
        resp = client.post("/api/reimbursements/", json={"person_name": "DefaultStatus", "amount": 100})
        assert resp.status_code == 201
        assert resp.json()["status"] == "pending"
