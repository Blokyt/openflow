"""Reimbursements API module — Lot D : workflow comptable."""
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core.database import get_conn, row_to_dict

router = APIRouter()


# ---------------------------------------------------------------------------
# Enum de statut
# ---------------------------------------------------------------------------

class ReimbursementStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    reimbursed = "reimbursed"
    rejected = "rejected"


# Transitions autorisées : depuis -> ensemble des cibles valides
_ALLOWED_TRANSITIONS: dict[ReimbursementStatus, set[ReimbursementStatus]] = {
    ReimbursementStatus.pending: {
        ReimbursementStatus.approved,
        ReimbursementStatus.rejected,
    },
    ReimbursementStatus.approved: {
        ReimbursementStatus.reimbursed,
        ReimbursementStatus.rejected,
        ReimbursementStatus.pending,
    },
    ReimbursementStatus.rejected: {
        ReimbursementStatus.pending,
    },
    ReimbursementStatus.reimbursed: set(),  # terminal
}


# ---------------------------------------------------------------------------
# Modèles Pydantic
# ---------------------------------------------------------------------------

class ReimbursementCreate(BaseModel):
    transaction_id: Optional[int] = None
    contact_id: Optional[int] = None
    person_name: str = ""
    amount: int
    status: ReimbursementStatus = ReimbursementStatus.pending
    reimbursed_date: Optional[str] = None
    reimbursement_transaction_id: Optional[int] = None
    notes: str = ""
    force: bool = False  # bypass déduplication, non persisté


class ReimbursementUpdate(BaseModel):
    transaction_id: Optional[int] = None
    contact_id: Optional[int] = None
    person_name: Optional[str] = None
    amount: Optional[int] = None
    status: Optional[ReimbursementStatus] = None
    reimbursed_date: Optional[str] = None
    reimbursement_transaction_id: Optional[int] = None
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_divers_entity(conn):
    """Retourne l'id de l'entité externe 'divers', ou None."""
    row = conn.execute("SELECT id FROM entities WHERE is_divers = 1 LIMIT 1").fetchone()
    return row["id"] if row else None


def _create_disbursement_transaction(conn, reimb: dict, now: str) -> int:
    """Crée atomiquement la transaction de décaissement.

    Utilise la même connexion (même commit) que la mise à jour du remboursement.
    Renvoie l'id de la transaction créée, ou lève HTTPException(400).
    """
    tx_id = reimb.get("transaction_id")
    if not tx_id:
        raise HTTPException(
            400,
            "Impossible de générer l'écriture : aucune transaction liée au remboursement.",
        )

    # Récupérer from_entity_id de la transaction liée
    parent_tx = conn.execute(
        "SELECT from_entity_id FROM transactions WHERE id = ?", (tx_id,)
    ).fetchone()
    if not parent_tx:
        raise HTTPException(400, "Transaction liée introuvable.")

    from_entity_id = parent_tx["from_entity_id"]

    # Récupérer l'entité divers
    divers_id = _get_divers_entity(conn)
    if not divers_id:
        raise HTTPException(
            400,
            "Impossible de générer l'écriture : aucune entité 'divers' n'existe en base.",
        )

    person_name = reimb.get("person_name") or ""
    label = f"Remboursement {person_name}".strip()
    amount = reimb["amount"]
    contact_id = reimb.get("contact_id")
    date = reimb.get("reimbursed_date") or now[:10]  # YYYY-MM-DD

    cur = conn.execute(
        """INSERT INTO transactions
               (date, label, description, amount, category_id, contact_id,
                created_by, created_at, updated_at, from_entity_id, to_entity_id)
           VALUES (?, ?, '', ?, NULL, ?, '', ?, ?, ?, ?)""",
        (date, label, amount, contact_id, now, now, from_entity_id, divers_id),
    )
    return cur.lastrowid


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/")
def list_reimbursements(status: Optional[str] = None):
    conn = get_conn()
    try:
        query = """SELECT r.*,
                   t.label AS transaction_label,
                   t.date AS transaction_date,
                   t.amount AS transaction_amount,
                   co.name AS contact_name
            FROM reimbursements r
            LEFT JOIN transactions t ON r.transaction_id = t.id
            LEFT JOIN contacts co ON r.contact_id = co.id
            WHERE 1=1"""
        params = []
        if status:
            query += " AND r.status = ?"
            params.append(status)
        query += " ORDER BY r.created_at DESC, r.id DESC"
        cur = conn.execute(query, params)
        return [row_to_dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


@router.post("/", status_code=201)
def create_reimbursement(reimbursement: ReimbursementCreate):
    # Guard : reimbursement_transaction_id interdit à la création
    if reimbursement.reimbursement_transaction_id is not None:
        raise HTTPException(
            400,
            "reimbursement_transaction_id ne peut pas être fourni à la création "
            "(il est posé automatiquement lors du passage à 'reimbursed').",
        )

    now = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    try:
        # Validation : transaction_id doit exister si fourni
        if reimbursement.transaction_id is not None:
            tx = conn.execute(
                "SELECT id FROM transactions WHERE id = ?", (reimbursement.transaction_id,)
            ).fetchone()
            if not tx:
                raise HTTPException(
                    400,
                    f"La transaction {reimbursement.transaction_id} n'existe pas.",
                )

        # Auto-resolve person_name depuis contact_id
        person_name = reimbursement.person_name
        contact_id = reimbursement.contact_id
        if contact_id and not person_name:
            contact = conn.execute(
                "SELECT name FROM contacts WHERE id = ?", (contact_id,)
            ).fetchone()
            if contact:
                person_name = contact[0]

        # Déduplication : même contact_id + même amount + créé aujourd'hui + statut != rejected
        if contact_id is not None and not reimbursement.force:
            today = now[:10]  # YYYY-MM-DD
            existing_dup = conn.execute(
                """SELECT id FROM reimbursements
                   WHERE contact_id = ?
                     AND amount = ?
                     AND DATE(created_at) = ?
                     AND status != 'rejected'
                   LIMIT 1""",
                (contact_id, reimbursement.amount, today),
            ).fetchone()
            if existing_dup:
                raise HTTPException(
                    409,
                    f"Un remboursement identique (contact {contact_id}, "
                    f"montant {reimbursement.amount} cts) a déjà été créé aujourd'hui. "
                    "Utilisez force=true pour forcer la création.",
                )

        cur = conn.execute(
            """INSERT INTO reimbursements
               (transaction_id, contact_id, person_name, amount, status, reimbursed_date,
                reimbursement_transaction_id, notes, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                reimbursement.transaction_id,
                contact_id,
                person_name,
                reimbursement.amount,
                reimbursement.status.value,
                reimbursement.reimbursed_date,
                None,  # reimbursement_transaction_id toujours None à la création
                reimbursement.notes,
                now,
                now,
            ),
        )
        new_id = cur.lastrowid
        row = conn.execute(
            "SELECT * FROM reimbursements WHERE id = ?", (new_id,)
        ).fetchone()
        new_data = row_to_dict(row)
        conn.commit()
        return new_data
    finally:
        conn.close()


@router.get("/summary")
def get_summary():
    """Retourne qui doit quoi : groupe par contact, somme des montants pending."""
    conn = get_conn()
    try:
        cur = conn.execute(
            """SELECT COALESCE(co.name, r.person_name) AS person_name,
                      r.contact_id,
                      SUM(r.amount) as total_pending,
                      COUNT(*) as count
               FROM reimbursements r
               LEFT JOIN contacts co ON r.contact_id = co.id
               WHERE r.status = 'pending'
               GROUP BY COALESCE(co.name, r.person_name)
               ORDER BY total_pending DESC""",
        )
        return [row_to_dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


@router.get("/{reimbursement_id}")
def get_reimbursement(reimbursement_id: int):
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM reimbursements WHERE id = ?", (reimbursement_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(
                status_code=404,
                detail=f"Reimbursement {reimbursement_id} not found",
            )
        return row_to_dict(row)
    finally:
        conn.close()


@router.put("/{reimbursement_id}")
def update_reimbursement(
    reimbursement_id: int, reimbursement: ReimbursementUpdate
):
    now = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    try:
        existing = conn.execute(
            "SELECT * FROM reimbursements WHERE id = ?", (reimbursement_id,)
        ).fetchone()
        if existing is None:
            raise HTTPException(
                status_code=404,
                detail=f"Reimbursement {reimbursement_id} not found",
            )

        old_data = row_to_dict(existing)

        updates = reimbursement.model_dump(exclude_unset=True)
        if not updates:
            return old_data

        # --- Machine à états ---
        if "status" in updates:
            new_status_raw = updates["status"]
            # Convertir en enum (déjà validé par Pydantic, mais si la valeur est str brute)
            try:
                new_status = ReimbursementStatus(new_status_raw)
            except ValueError:
                raise HTTPException(
                    400,
                    f"Statut '{new_status_raw}' invalide. "
                    f"Valeurs autorisées : {[s.value for s in ReimbursementStatus]}",
                )

            current_status_raw = old_data.get("status", "pending")
            try:
                current_status = ReimbursementStatus(current_status_raw)
            except ValueError:
                # Statut legacy en base non reconnu : autoriser la transition vers pending
                current_status = ReimbursementStatus.pending

            allowed = _ALLOWED_TRANSITIONS.get(current_status, set())
            if new_status not in allowed:
                raise HTTPException(
                    400,
                    f"Transition '{current_status.value}' -> '{new_status.value}' interdite. "
                    f"Transitions autorisées depuis '{current_status.value}' : "
                    f"{[s.value for s in allowed] or '[]'}.",
                )

            # --- Passage à reimbursed : création atomique de la transaction de décaissement ---
            if new_status == ReimbursementStatus.reimbursed:
                # Idempotence : refuser si déjà payé
                if old_data.get("reimbursement_transaction_id") is not None:
                    raise HTTPException(
                        400,
                        "Ce remboursement a déjà été décaissé "
                        f"(transaction #{old_data['reimbursement_transaction_id']}). "
                        "Ne pas créer une seconde écriture de décaissement.",
                    )

                # Préparer le dict du remboursement avec les mises à jour en cours
                merged = {**old_data, **{k: v for k, v in updates.items() if k != "status"}}
                reimb_tx_id = _create_disbursement_transaction(conn, merged, now)
                updates["reimbursement_transaction_id"] = reimb_tx_id

            # Stocker la valeur string de l'enum
            updates["status"] = new_status.value

        # Exclure reimbursement_transaction_id des updates si non géré par la machine à états
        # (ne pas laisser l'appelant poser cette valeur directement via update)

        set_clauses = ", ".join(f"{k} = ?" for k in updates)
        set_clauses += ", updated_at = ?"
        values = list(updates.values()) + [now, reimbursement_id]

        conn.execute(
            f"UPDATE reimbursements SET {set_clauses} WHERE id = ?",
            values,
        )
        row = conn.execute(
            "SELECT * FROM reimbursements WHERE id = ?", (reimbursement_id,)
        ).fetchone()
        new_data = row_to_dict(row)
        conn.commit()
        return new_data
    finally:
        conn.close()


@router.delete("/{reimbursement_id}")
def delete_reimbursement(reimbursement_id: int):
    conn = get_conn()
    try:
        existing = conn.execute(
            "SELECT * FROM reimbursements WHERE id = ?", (reimbursement_id,)
        ).fetchone()
        if existing is None:
            raise HTTPException(
                status_code=404,
                detail=f"Reimbursement {reimbursement_id} not found",
            )
        old_data = row_to_dict(existing)

        # Interdire la suppression d'un remboursement réglé
        if old_data.get("status") == ReimbursementStatus.reimbursed.value:
            raise HTTPException(
                409,
                "Ce remboursement est déjà réglé (reimbursed). "
                "Pour corriger une erreur, créez une opération corrective plutôt que de le supprimer.",
            )

        conn.execute("DELETE FROM reimbursements WHERE id = ?", (reimbursement_id,))
        conn.commit()
        return {"deleted": reimbursement_id}
    finally:
        conn.close()
