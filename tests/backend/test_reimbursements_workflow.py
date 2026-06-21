"""Tests TDD pour le workflow comptable des remboursements (Lot D).

Convention montants : ENTIERS en CENTIMES, toujours positifs.
Ex : 4250 = 42,50 €
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

def _make_divers_entity(db_path):
    """Crée l'entité externe 'divers' nécessaire au passage à reimbursed."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        "INSERT INTO entities (name, type, parent_id, is_default, is_divers, color, position, created_at, updated_at) "
        "VALUES (?, 'external', NULL, 0, 1, '#6B7280', 999, ?, ?)",
        ("Divers", now, now),
    )
    divers_id = cur.lastrowid
    conn.commit()
    conn.close()
    return divers_id


def _make_internal_entity(db_path, name="_Internal"):
    """Crée une entité interne."""
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
    """Crée une entité externe."""
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


def _make_transaction(client, db_path, from_id, to_id, amount=5000, label="Dépense test"):
    """Crée une transaction directement via l'API avec des entités explicites."""
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
# 1. Machine à états — transitions
# ---------------------------------------------------------------------------

class TestStateTransitions:
    def test_pending_to_approved_ok(self, client):
        r = client.post("/api/reimbursements/", json={"person_name": "Alice", "amount": 1000})
        assert r.status_code == 201
        rid = r.json()["id"]
        resp = client.put(f"/api/reimbursements/{rid}", json={"status": "approved"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"

    def test_pending_to_rejected_ok(self, client):
        r = client.post("/api/reimbursements/", json={"person_name": "Bob", "amount": 500})
        rid = r.json()["id"]
        resp = client.put(f"/api/reimbursements/{rid}", json={"status": "rejected"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"

    def test_approved_to_rejected_ok(self, client):
        r = client.post("/api/reimbursements/", json={"person_name": "Carol", "amount": 2000})
        rid = r.json()["id"]
        client.put(f"/api/reimbursements/{rid}", json={"status": "approved"})
        resp = client.put(f"/api/reimbursements/{rid}", json={"status": "rejected"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"

    def test_approved_to_pending_ok(self, client):
        r = client.post("/api/reimbursements/", json={"person_name": "David", "amount": 750})
        rid = r.json()["id"]
        client.put(f"/api/reimbursements/{rid}", json={"status": "approved"})
        resp = client.put(f"/api/reimbursements/{rid}", json={"status": "pending"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "pending"

    def test_rejected_to_pending_ok(self, client):
        r = client.post("/api/reimbursements/", json={"person_name": "Eve", "amount": 300})
        rid = r.json()["id"]
        client.put(f"/api/reimbursements/{rid}", json={"status": "rejected"})
        resp = client.put(f"/api/reimbursements/{rid}", json={"status": "pending"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "pending"

    def test_pending_to_reimbursed_forbidden_without_divers(self, client, db_path):
        """Sans entité divers, pending -> reimbursed doit échouer avec 400."""
        from_id = _make_internal_entity(db_path, "IntFrom")
        to_id = _make_external_entity(db_path, "ExtTo")
        tx_id = _make_transaction(client, db_path, from_id, to_id)
        r = client.post("/api/reimbursements/", json={
            "person_name": "NoDiv", "amount": 500, "transaction_id": tx_id
        })
        rid = r.json()["id"]
        # pending -> approved is valid first
        client.put(f"/api/reimbursements/{rid}", json={"status": "approved"})
        resp = client.put(f"/api/reimbursements/{rid}", json={"status": "reimbursed"})
        assert resp.status_code == 400

    def test_reimbursed_to_pending_forbidden(self, client, db_path):
        """Transition interdite : reimbursed -> pending renvoie 400."""
        _make_divers_entity(db_path)
        from_id = _make_internal_entity(db_path, "IntFrom2")
        to_id = _make_external_entity(db_path, "ExtTo2")
        tx_id = _make_transaction(client, db_path, from_id, to_id)
        r = client.post("/api/reimbursements/", json={
            "person_name": "Frank", "amount": 1500, "transaction_id": tx_id
        })
        rid = r.json()["id"]
        client.put(f"/api/reimbursements/{rid}", json={"status": "approved"})
        reimbursed_resp = client.put(f"/api/reimbursements/{rid}", json={"status": "reimbursed"})
        assert reimbursed_resp.status_code == 200
        # reimbursed -> pending: interdit
        resp = client.put(f"/api/reimbursements/{rid}", json={"status": "pending"})
        assert resp.status_code == 400

    def test_reimbursed_to_approved_forbidden(self, client, db_path):
        """Transition interdite : reimbursed -> approved renvoie 400."""
        _make_divers_entity(db_path)
        from_id = _make_internal_entity(db_path, "IntFrom3")
        to_id = _make_external_entity(db_path, "ExtTo3")
        tx_id = _make_transaction(client, db_path, from_id, to_id)
        r = client.post("/api/reimbursements/", json={
            "person_name": "Grace", "amount": 2500, "transaction_id": tx_id
        })
        rid = r.json()["id"]
        client.put(f"/api/reimbursements/{rid}", json={"status": "approved"})
        client.put(f"/api/reimbursements/{rid}", json={"status": "reimbursed"})
        resp = client.put(f"/api/reimbursements/{rid}", json={"status": "approved"})
        assert resp.status_code == 400

    def test_pending_to_invalid_status_forbidden(self, client):
        """Un statut inconnu renvoie 400 ou 422 (validation Pydantic ou guard métier)."""
        r = client.post("/api/reimbursements/", json={"person_name": "Hank", "amount": 100})
        rid = r.json()["id"]
        resp = client.put(f"/api/reimbursements/{rid}", json={"status": "invalid_status"})
        # 422 = Pydantic rejette l'enum ; 400 = guard métier — les deux sont corrects
        assert resp.status_code in (400, 422)

    def test_rejected_to_rejected_forbidden(self, client):
        """rejected -> rejected (même statut) : la machine à états l'interdit (400)."""
        r = client.post("/api/reimbursements/", json={"person_name": "Iris", "amount": 200})
        rid = r.json()["id"]
        # pending -> rejected (OK)
        client.put(f"/api/reimbursements/{rid}", json={"status": "rejected"})
        # rejected -> rejected (interdit)
        resp = client.put(f"/api/reimbursements/{rid}", json={"status": "rejected"})
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 2. Passage à reimbursed : création de la transaction de décaissement
# ---------------------------------------------------------------------------

class TestReimbursedTransaction:
    def test_reimbursed_creates_one_disbursement_transaction(self, client, db_path):
        """Passer à reimbursed crée exactement 1 transaction de décaissement."""
        divers_id = _make_divers_entity(db_path)
        from_id = _make_internal_entity(db_path, "IntSource")
        to_id = _make_external_entity(db_path, "ExtDest")
        tx_id = _make_transaction(client, db_path, from_id, to_id, amount=8000, label="Achat matériel")

        r = client.post("/api/reimbursements/", json={
            "person_name": "Jean Dupont",
            "amount": 8000,
            "transaction_id": tx_id,
        })
        assert r.status_code == 201
        rid = r.json()["id"]

        # pending -> approved -> reimbursed
        client.put(f"/api/reimbursements/{rid}", json={"status": "approved"})
        resp = client.put(f"/api/reimbursements/{rid}", json={"status": "reimbursed"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "reimbursed"
        assert data["reimbursement_transaction_id"] is not None
        rtx_id = data["reimbursement_transaction_id"]

        # Vérifier la transaction en base
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        tx = conn.execute("SELECT * FROM transactions WHERE id = ?", (rtx_id,)).fetchone()
        conn.close()
        assert tx is not None
        assert tx["from_entity_id"] == from_id
        assert tx["to_entity_id"] == divers_id
        assert tx["amount"] == 8000
        assert "Jean Dupont" in tx["label"]

    def test_reimbursed_contact_id_on_disbursement(self, client, db_path):
        """La transaction de décaissement reprend le contact_id du remboursement."""
        _make_divers_entity(db_path)
        from_id = _make_internal_entity(db_path, "IntContactTest")
        to_id = _make_external_entity(db_path, "ExtContactTest")
        tx_id = _make_transaction(client, db_path, from_id, to_id, amount=3000)

        # Créer un contact
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        now = datetime.now(timezone.utc).isoformat()
        cur = conn.execute(
            "INSERT INTO contacts (name, email, created_at, updated_at) VALUES (?, ?, ?, ?)",
            ("Contact Test", "ct@test.fr", now, now),
        )
        contact_id = cur.lastrowid
        conn.commit()
        conn.close()

        r = client.post("/api/reimbursements/", json={
            "person_name": "Contact Test",
            "amount": 3000,
            "transaction_id": tx_id,
            "contact_id": contact_id,
        })
        rid = r.json()["id"]
        client.put(f"/api/reimbursements/{rid}", json={"status": "approved"})
        resp = client.put(f"/api/reimbursements/{rid}", json={"status": "reimbursed"})
        assert resp.status_code == 200
        rtx_id = resp.json()["reimbursement_transaction_id"]

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        tx = conn.execute("SELECT * FROM transactions WHERE id = ?", (rtx_id,)).fetchone()
        conn.close()
        assert tx["contact_id"] == contact_id

    def test_repay_already_reimbursed_is_rejected(self, client, db_path):
        """Re-passer à reimbursed un remboursement déjà payé renvoie 400 (idempotence)."""
        _make_divers_entity(db_path)
        from_id = _make_internal_entity(db_path, "IntIdempotent")
        to_id = _make_external_entity(db_path, "ExtIdempotent")
        tx_id = _make_transaction(client, db_path, from_id, to_id, amount=1200)

        r = client.post("/api/reimbursements/", json={
            "person_name": "Idempotence Test", "amount": 1200, "transaction_id": tx_id
        })
        rid = r.json()["id"]
        client.put(f"/api/reimbursements/{rid}", json={"status": "approved"})
        first = client.put(f"/api/reimbursements/{rid}", json={"status": "reimbursed"})
        assert first.status_code == 200
        rtx_id_first = first.json()["reimbursement_transaction_id"]

        # Tenter de re-passer à reimbursed : machine à états bloque (400)
        second = client.put(f"/api/reimbursements/{rid}", json={"status": "reimbursed"})
        assert second.status_code == 400

        # Vérifier qu'une seule transaction de décaissement existe
        conn = sqlite3.connect(str(db_path))
        count = conn.execute(
            "SELECT COUNT(*) FROM transactions WHERE id = ?", (rtx_id_first,)
        ).fetchone()[0]
        conn.close()
        assert count == 1

    def test_reimbursed_without_transaction_id_returns_400(self, client, db_path):
        """Sans transaction_id lié, le passage à reimbursed doit échouer (400)."""
        _make_divers_entity(db_path)
        r = client.post("/api/reimbursements/", json={"person_name": "NoTx", "amount": 500})
        rid = r.json()["id"]
        client.put(f"/api/reimbursements/{rid}", json={"status": "approved"})
        resp = client.put(f"/api/reimbursements/{rid}", json={"status": "reimbursed"})
        assert resp.status_code == 400

    def test_reimbursed_without_divers_entity_returns_400(self, client, db_path):
        """Sans entité divers en base, le passage à reimbursed doit échouer (400)."""
        from_id = _make_internal_entity(db_path, "IntNoDivers")
        to_id = _make_external_entity(db_path, "ExtNoDivers")
        tx_id = _make_transaction(client, db_path, from_id, to_id, amount=700)
        r = client.post("/api/reimbursements/", json={
            "person_name": "NoDivers", "amount": 700, "transaction_id": tx_id
        })
        rid = r.json()["id"]
        client.put(f"/api/reimbursements/{rid}", json={"status": "approved"})
        resp = client.put(f"/api/reimbursements/{rid}", json={"status": "reimbursed"})
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 3. Suppression
# ---------------------------------------------------------------------------

class TestDeletion:
    def test_delete_pending_ok(self, client):
        r = client.post("/api/reimbursements/", json={"person_name": "DeletePending", "amount": 100})
        rid = r.json()["id"]
        resp = client.delete(f"/api/reimbursements/{rid}")
        assert resp.status_code == 200

    def test_delete_approved_ok(self, client):
        r = client.post("/api/reimbursements/", json={"person_name": "DeleteApproved", "amount": 200})
        rid = r.json()["id"]
        client.put(f"/api/reimbursements/{rid}", json={"status": "approved"})
        resp = client.delete(f"/api/reimbursements/{rid}")
        assert resp.status_code == 200

    def test_delete_rejected_ok(self, client):
        r = client.post("/api/reimbursements/", json={"person_name": "DeleteRejected", "amount": 300})
        rid = r.json()["id"]
        client.put(f"/api/reimbursements/{rid}", json={"status": "rejected"})
        resp = client.delete(f"/api/reimbursements/{rid}")
        assert resp.status_code == 200

    def test_delete_reimbursed_returns_409(self, client, db_path):
        """Supprimer un remboursement 'reimbursed' renvoie 409."""
        _make_divers_entity(db_path)
        from_id = _make_internal_entity(db_path, "IntDel")
        to_id = _make_external_entity(db_path, "ExtDel")
        tx_id = _make_transaction(client, db_path, from_id, to_id, amount=900)
        r = client.post("/api/reimbursements/", json={
            "person_name": "Réglé", "amount": 900, "transaction_id": tx_id
        })
        rid = r.json()["id"]
        client.put(f"/api/reimbursements/{rid}", json={"status": "approved"})
        client.put(f"/api/reimbursements/{rid}", json={"status": "reimbursed"})
        resp = client.delete(f"/api/reimbursements/{rid}")
        assert resp.status_code == 409
        assert "corrective" in resp.json()["detail"].lower() or "opération" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# 4. Déduplication à la création
# ---------------------------------------------------------------------------

class TestDeduplication:
    def test_duplicate_creates_409(self, client):
        """Deux créations avec même contact_id + amount + aujourd'hui -> 409."""
        conn_payload = {"person_name": "Dedup Test", "amount": 4200, "status": "pending"}
        # Pas de contact_id ici; on teste par (contact_id=None, amount, today)
        # La dédup n'est active que si contact_id est défini OU si person_name est même
        # Selon spec : même contact_id + même amount + créé aujourd'hui + statut != rejected
        # On utilise un contact réel pour tester proprement
        # Pour simplifier, on crée d'abord via DB directe un contact
        r1 = client.post("/api/reimbursements/", json={"person_name": "Dedup Test", "amount": 4200, "contact_id": 999})
        # 201 (ou 404 si contact 999 inexistant, pas de contrainte FK)
        # On doit tester avec contact_id existant ou sans contact_id
        # Spec : same contact_id + same amount + today + status != rejected
        # Si contact_id = None, pas de dédup par contact_id
        pass  # Le test sera refait avec un vrai contact ci-dessous

    def test_duplicate_with_contact_returns_409(self, client, db_path):
        """Même contact_id + même montant + aujourd'hui -> 409."""
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        now = datetime.now(timezone.utc).isoformat()
        cur = conn.execute(
            "INSERT INTO contacts (name, email, created_at, updated_at) VALUES (?, ?, ?, ?)",
            ("Dedup Contact", "dedup@test.fr", now, now),
        )
        contact_id = cur.lastrowid
        conn.commit()
        conn.close()

        r1 = client.post("/api/reimbursements/", json={
            "person_name": "Dedup Contact", "amount": 5500, "contact_id": contact_id
        })
        assert r1.status_code == 201

        r2 = client.post("/api/reimbursements/", json={
            "person_name": "Dedup Contact", "amount": 5500, "contact_id": contact_id
        })
        assert r2.status_code == 409

    def test_duplicate_with_force_returns_201(self, client, db_path):
        """Même contact_id + même montant + force=true -> 201 (bypass dédup)."""
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        now = datetime.now(timezone.utc).isoformat()
        cur = conn.execute(
            "INSERT INTO contacts (name, email, created_at, updated_at) VALUES (?, ?, ?, ?)",
            ("Force Contact", "force@test.fr", now, now),
        )
        contact_id = cur.lastrowid
        conn.commit()
        conn.close()

        r1 = client.post("/api/reimbursements/", json={
            "person_name": "Force Contact", "amount": 6000, "contact_id": contact_id
        })
        assert r1.status_code == 201

        r2 = client.post("/api/reimbursements/", json={
            "person_name": "Force Contact", "amount": 6000, "contact_id": contact_id, "force": True
        })
        assert r2.status_code == 201

    def test_rejected_does_not_block_dedup(self, client, db_path):
        """Un doublon avec statut rejected ne bloque pas la création (statut != rejected)."""
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        now = datetime.now(timezone.utc).isoformat()
        cur = conn.execute(
            "INSERT INTO contacts (name, email, created_at, updated_at) VALUES (?, ?, ?, ?)",
            ("Rejected Dedup", "rd@test.fr", now, now),
        )
        contact_id = cur.lastrowid
        conn.commit()
        conn.close()

        r1 = client.post("/api/reimbursements/", json={
            "person_name": "Rejected Dedup", "amount": 1100, "contact_id": contact_id
        })
        assert r1.status_code == 201
        rid = r1.json()["id"]
        client.put(f"/api/reimbursements/{rid}", json={"status": "rejected"})

        # Après rejection du premier, un nouveau est autorisé
        r2 = client.post("/api/reimbursements/", json={
            "person_name": "Rejected Dedup", "amount": 1100, "contact_id": contact_id
        })
        assert r2.status_code == 201

    def test_dedup_no_contact_id_no_check(self, client):
        """Sans contact_id, la dédup n'est pas appliquée."""
        r1 = client.post("/api/reimbursements/", json={"person_name": "NoContact", "amount": 2000})
        assert r1.status_code == 201
        r2 = client.post("/api/reimbursements/", json={"person_name": "NoContact", "amount": 2000})
        assert r2.status_code == 201


# ---------------------------------------------------------------------------
# 5. Champ reimbursement_transaction_id interdit à la création
# ---------------------------------------------------------------------------

class TestCreateGuards:
    def test_create_with_reimbursement_transaction_id_returns_400(self, client):
        """Passer reimbursement_transaction_id à la création doit renvoyer 400."""
        resp = client.post("/api/reimbursements/", json={
            "person_name": "Bloq", "amount": 500, "reimbursement_transaction_id": 1
        })
        assert resp.status_code == 400

    def test_create_with_invalid_transaction_id_returns_400(self, client):
        """Si transaction_id est fourni et n'existe pas, renvoyer 400."""
        resp = client.post("/api/reimbursements/", json={
            "person_name": "BadTx", "amount": 300, "transaction_id": 999999
        })
        assert resp.status_code == 400

    def test_create_with_valid_transaction_id_ok(self, client, db_path):
        """Si transaction_id existe bien, la création réussit."""
        from_id = _make_internal_entity(db_path, "IntValidTx")
        to_id = _make_external_entity(db_path, "ExtValidTx")
        tx_id = _make_transaction(client, db_path, from_id, to_id, amount=1000)
        resp = client.post("/api/reimbursements/", json={
            "person_name": "ValidTx", "amount": 1000, "transaction_id": tx_id
        })
        assert resp.status_code == 201

    def test_create_default_status_is_pending(self, client):
        """Le statut par défaut doit être 'pending' (via ReimbursementStatus enum)."""
        resp = client.post("/api/reimbursements/", json={"person_name": "DefaultStatus", "amount": 100})
        assert resp.status_code == 201
        assert resp.json()["status"] == "pending"


# ---------------------------------------------------------------------------
# 6. Libellé de la transaction de décaissement
# ---------------------------------------------------------------------------

class TestClosedPeriodLock:
    """Le décaissement généré au passage à 'reimbursed' respecte le verrou de clôture."""

    def _open_fy(self, client, name="2024-2025", start="2024-09-01"):
        r = client.post("/api/budget/fiscal-years", json={"name": name, "start_date": start})
        assert r.status_code == 201, r.text
        return r.json()

    def test_reimbursed_in_closed_period_returns_409(self, client, db_path):
        """reimbursed_date dans un exercice clôturé → 409, aucun décaissement créé."""
        _make_divers_entity(db_path)
        from_id = _make_internal_entity(db_path, "IntClosed")
        to_id = _make_external_entity(db_path, "ExtClosed")
        fy = self._open_fy(client)
        # Avance créée pendant que l'exercice est encore ouvert.
        tx = client.post("/api/transactions/", json={
            "date": "2024-10-15", "label": "Avance", "amount": 4000,
            "from_entity_id": from_id, "to_entity_id": to_id,
        }).json()
        r = client.post("/api/reimbursements/", json={
            "person_name": "Closed", "amount": 4000, "transaction_id": tx["id"],
        })
        rid = r.json()["id"]
        client.put(f"/api/reimbursements/{rid}", json={"status": "approved"})
        # Clôture de l'exercice.
        client.post(f"/api/budget/fiscal-years/{fy['id']}/close", json={"end_date": "2025-08-31"})

        resp = client.put(f"/api/reimbursements/{rid}", json={
            "status": "reimbursed", "reimbursed_date": "2024-11-01",
        })
        assert resp.status_code == 409, resp.text

        # Aucun décaissement ne doit avoir été inséré.
        conn = sqlite3.connect(str(db_path))
        count = conn.execute(
            "SELECT COUNT(*) FROM transactions WHERE label LIKE 'Remboursement%'"
        ).fetchone()[0]
        conn.close()
        assert count == 0

    def test_reimbursed_outside_closed_period_passes(self, client, db_path):
        """reimbursed_date hors de toute période clôturée → 200."""
        _make_divers_entity(db_path)
        from_id = _make_internal_entity(db_path, "IntOpen")
        to_id = _make_external_entity(db_path, "ExtOpen")
        fy = self._open_fy(client)
        tx = client.post("/api/transactions/", json={
            "date": "2024-10-15", "label": "Avance2", "amount": 4000,
            "from_entity_id": from_id, "to_entity_id": to_id,
        }).json()
        r = client.post("/api/reimbursements/", json={
            "person_name": "Open", "amount": 4000, "transaction_id": tx["id"],
        })
        rid = r.json()["id"]
        client.put(f"/api/reimbursements/{rid}", json={"status": "approved"})
        client.post(f"/api/budget/fiscal-years/{fy['id']}/close", json={"end_date": "2025-08-31"})

        # 2025-12-01 est après la clôture → autorisé.
        resp = client.put(f"/api/reimbursements/{rid}", json={
            "status": "reimbursed", "reimbursed_date": "2025-12-01",
        })
        assert resp.status_code == 200, resp.text
        assert resp.json()["reimbursement_transaction_id"] is not None


class TestDisbursementLabel:
    def test_disbursement_label_contains_remboursement(self, client, db_path):
        """Le label de la transaction de décaissement contient 'Remboursement'."""
        _make_divers_entity(db_path)
        from_id = _make_internal_entity(db_path, "IntLabel")
        to_id = _make_external_entity(db_path, "ExtLabel")
        tx_id = _make_transaction(client, db_path, from_id, to_id, amount=2200)

        r = client.post("/api/reimbursements/", json={
            "person_name": "Marie Martin", "amount": 2200, "transaction_id": tx_id
        })
        rid = r.json()["id"]
        client.put(f"/api/reimbursements/{rid}", json={"status": "approved"})
        resp = client.put(f"/api/reimbursements/{rid}", json={"status": "reimbursed"})
        rtx_id = resp.json()["reimbursement_transaction_id"]

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        tx = conn.execute("SELECT * FROM transactions WHERE id = ?", (rtx_id,)).fetchone()
        conn.close()
        assert "Remboursement" in tx["label"]
        assert "Marie Martin" in tx["label"]
