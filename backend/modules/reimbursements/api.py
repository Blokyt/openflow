"""Reimbursements API module — suivi simple des avances et remboursements.

Mode simple : statuts d'usage 'pending' / 'reimbursed' (l'enum conserve aussi
'approved' / 'rejected' pour compatibilité des données), transitions libres
entre statuts, et AUCUNE écriture comptable générée automatiquement. Le module
est un outil de suivi : le trésorier saisit ses sorties d'argent lui-même.
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from backend.core.auth import get_allowed_entity_ids, get_current_user
from backend.core.database import get_conn, row_to_dict

router = APIRouter()


# ---------------------------------------------------------------------------
# Enum de statut (valeurs valides ; aucun workflow imposé en mode simple)
# ---------------------------------------------------------------------------

class ReimbursementStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    reimbursed = "reimbursed"
    rejected = "rejected"


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
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/")
def list_reimbursements(request: Request, status: Optional[str] = None):
    """Liste des remboursements.

    Rattachement à une entité : via la transaction liée (transaction_id ->
    transactions.from_entity_id/to_entity_id) ; un remboursement sans
    transaction liée n'a pas d'entité de rattachement vérifiable et est donc
    exclu de la vue d'un non-admin (deny-by-default, cf. require_session).
    """
    user = get_current_user(request)
    conn = get_conn()
    try:
        allowed = get_allowed_entity_ids(conn, user)
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
        if allowed is not None:
            if not allowed:
                query += " AND 0 = 1"
            else:
                ph = ",".join("?" * len(allowed))
                query += (
                    f" AND r.transaction_id IS NOT NULL "
                    f"AND (t.from_entity_id IN ({ph}) OR t.to_entity_id IN ({ph}))"
                )
                params.extend(list(allowed))
                params.extend(list(allowed))
        # Ordre de travail du trésorier : les avances encore dues d'abord,
        # puis chaque groupe par date réelle de la dépense (pas par date de
        # saisie de la fiche, qui n'a aucun sens métier), la plus récente en tête.
        query += """ ORDER BY CASE WHEN r.status = 'pending' THEN 0 ELSE 1 END,
                     COALESCE(t.date, DATE(r.created_at)) DESC,
                     r.id DESC"""
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
            "reimbursement_transaction_id ne peut pas être fourni à la création.",
        )
    if reimbursement.amount <= 0:
        raise HTTPException(400, "Le montant doit être strictement positif (en centimes).")

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

        # Validation contact + auto-resolve person_name depuis contact_id
        person_name = reimbursement.person_name
        contact_id = reimbursement.contact_id
        if contact_id is not None:
            contact = conn.execute(
                "SELECT name FROM contacts WHERE id = ?", (contact_id,)
            ).fetchone()
            if contact is None:
                raise HTTPException(400, f"Le contact {contact_id} n'existe pas.")
            if not person_name:
                person_name = contact[0]

        # Déduplication : même contact_id + même amount + créé aujourd'hui + statut != rejected.
        # (Sans contact_id, pas de déduplication : comportement volontaire — un
        # remboursement saisi au nom libre peut légitimement être répété.)
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
def get_reimbursement(reimbursement_id: int, request: Request):
    user = get_current_user(request)
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
        allowed = get_allowed_entity_ids(conn, user)
        if allowed is not None:
            tx_id = row["transaction_id"]
            tx = conn.execute(
                "SELECT from_entity_id, to_entity_id FROM transactions WHERE id = ?", (tx_id,)
            ).fetchone() if tx_id is not None else None
            if tx is None or (tx["from_entity_id"] not in allowed and tx["to_entity_id"] not in allowed):
                raise HTTPException(status_code=403, detail="Accès refusé à cette entité")
        return row_to_dict(row)
    finally:
        conn.close()


@router.put("/{reimbursement_id}")
def update_reimbursement(reimbursement_id: int, reimbursement: ReimbursementUpdate):
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

        # Mode simple : on valide uniquement que le statut est une valeur connue.
        # Aucun workflow imposé (toute transition est permise) et aucune écriture
        # comptable n'est générée automatiquement.
        if "status" in updates:
            try:
                new_status = ReimbursementStatus(updates["status"])
            except ValueError:
                raise HTTPException(
                    400,
                    f"Statut '{updates['status']}' invalide. "
                    f"Valeurs autorisées : {[s.value for s in ReimbursementStatus]}",
                )
            updates["status"] = new_status.value

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

        # Interdire la suppression d'un remboursement réglé : repasser d'abord en
        # attente (transition libre en mode simple) pour confirmer l'intention.
        if old_data.get("status") == ReimbursementStatus.reimbursed.value:
            raise HTTPException(
                409,
                "Ce remboursement est déjà réglé (reimbursed). "
                "Repassez-le en attente avant de le supprimer.",
            )

        conn.execute("DELETE FROM reimbursements WHERE id = ?", (reimbursement_id,))
        conn.commit()
        return {"deleted": reimbursement_id}
    finally:
        conn.close()
