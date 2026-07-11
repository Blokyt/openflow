"""Soumissions de transactions : les trésoriers proposent, l'admin valide."""
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from backend.core.auth import get_allowed_entity_ids, get_current_user, require_admin
from backend.core.database import get_conn, row_to_dict

router = APIRouter()

VALID_STATUSES = {"pending", "approved", "rejected", "cancelled"}

# SELECT enrichi commun à toutes les lectures (noms d'entités, catégorie, auteurs).
_SELECT = """SELECT s.*,
       e.name AS entity_name,
       ce.name AS counterparty_name,
       c.name AS category_name, c.color AS category_color,
       u.display_name AS submitted_by_name, u.email AS submitted_by_email,
       ru.display_name AS reviewed_by_name
FROM transaction_submissions s
LEFT JOIN entities e ON s.entity_id = e.id
LEFT JOIN entities ce ON s.counterparty_entity_id = ce.id
LEFT JOIN categories c ON s.category_id = c.id
LEFT JOIN users u ON s.submitted_by = u.id
LEFT JOIN users ru ON s.reviewed_by = ru.id"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fetch_serialized(conn, submission_id: int):
    row = conn.execute(_SELECT + " WHERE s.id = ?", (submission_id,)).fetchone()
    return row_to_dict(row) if row is not None else None


class SubmissionCreate(BaseModel):
    date: str
    label: str
    description: str = ""
    amount: int  # centimes, strictement positif ; le sens vient de direction
    category_id: Optional[int] = None
    entity_id: int
    counterparty_entity_id: int
    direction: Literal["expense", "income"]


@router.post("/", status_code=201)
def create_submission(sub: SubmissionCreate, request: Request):
    user = get_current_user(request)
    if sub.amount <= 0:
        raise HTTPException(status_code=400, detail="Le montant doit être strictement positif")
    if sub.entity_id == sub.counterparty_entity_id:
        raise HTTPException(status_code=400, detail="L'entité et la contrepartie doivent être différentes")
    conn = get_conn()
    try:
        # Périmètre d'écriture : seules les entités où le user est TREASURER
        # (le rôle viewer ne suffit pas). Admin : partout (None).
        treasurer_ids = get_allowed_entity_ids(conn, user, role="treasurer")
        if treasurer_ids is not None and sub.entity_id not in treasurer_ids:
            raise HTTPException(status_code=403, detail="Vous n'êtes pas trésorier de cette entité")
        entity = conn.execute("SELECT type FROM entities WHERE id = ?", (sub.entity_id,)).fetchone()
        if entity is None or entity["type"] != "internal":
            raise HTTPException(status_code=400, detail="entity_id doit référencer une entité interne existante")
        counterparty = conn.execute(
            "SELECT type FROM entities WHERE id = ?", (sub.counterparty_entity_id,)
        ).fetchone()
        if counterparty is None or counterparty["type"] != "external":
            raise HTTPException(status_code=400, detail="counterparty_entity_id doit référencer une entité externe existante")
        if sub.category_id is not None:
            cat = conn.execute("SELECT id FROM categories WHERE id = ?", (sub.category_id,)).fetchone()
            if cat is None:
                raise HTTPException(status_code=400, detail=f"Catégorie {sub.category_id} introuvable")
        now = _now()
        cur = conn.execute(
            """INSERT INTO transaction_submissions
               (date, label, description, amount, category_id, entity_id,
                counterparty_entity_id, direction, status, submitted_by, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)""",
            (sub.date, sub.label, sub.description, sub.amount, sub.category_id,
             sub.entity_id, sub.counterparty_entity_id, sub.direction, user["id"], now, now),
        )
        data = _fetch_serialized(conn, cur.lastrowid)
        conn.commit()
        return data
    finally:
        conn.close()


@router.get("/mine")
def list_my_submissions(request: Request):
    """Suivi de ses propres soumissions (tous statuts)."""
    user = get_current_user(request)
    conn = get_conn()
    try:
        rows = conn.execute(
            _SELECT + " WHERE s.submitted_by = ? ORDER BY s.created_at DESC, s.id DESC",
            (user["id"],),
        ).fetchall()
        return [row_to_dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/")
def list_submissions(status: Optional[str] = None, admin: dict = Depends(require_admin)):
    """File de validation : réservée à l'admin (GET non couvert par la garde centrale)."""
    if status is not None and status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Statut invalide : {status}")
    conn = get_conn()
    try:
        sql = _SELECT
        params = []
        if status is not None:
            sql += " WHERE s.status = ?"
            params.append(status)
        sql += " ORDER BY s.created_at DESC, s.id DESC"
        return [row_to_dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


@router.get("/{submission_id}")
def get_submission(submission_id: int, request: Request):
    user = get_current_user(request)
    conn = get_conn()
    try:
        data = _fetch_serialized(conn, submission_id)
        if data is None:
            raise HTTPException(status_code=404, detail=f"Soumission {submission_id} introuvable")
        if not user["is_admin"] and data["submitted_by"] != user["id"]:
            raise HTTPException(status_code=403, detail="Accès refusé à cette soumission")
        return data
    finally:
        conn.close()


def _date_in_closed_period(conn, date: str) -> bool:
    """Copie locale du verrou de clôture de transactions/api.py (pas d'import
    inter-modules : la table peut ne pas exister si le module budget est inactif)."""
    try:
        row = conn.execute(
            """SELECT 1 FROM fiscal_years
               WHERE end_date IS NOT NULL
                 AND ? BETWEEN start_date AND end_date""",
            (date,),
        ).fetchone()
        return row is not None
    except Exception:
        return False


class RejectPayload(BaseModel):
    comment: str


@router.post("/{submission_id}/approve")
def approve_submission(submission_id: int, force: bool = False, admin: dict = Depends(require_admin)):
    """Crée la vraie transaction (from/to déduits de entité + contrepartie +
    direction), re-lie les justificatifs, marque la soumission approuvée.
    Tout est commité en une seule transaction SQLite."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM transaction_submissions WHERE id = ?", (submission_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Soumission {submission_id} introuvable")
        if row["status"] != "pending":
            raise HTTPException(status_code=409, detail="Seule une soumission en attente peut être approuvée")
        if not force and _date_in_closed_period(conn, row["date"]):
            raise HTTPException(status_code=409, detail="Exercice clôturé : approuver quand même ?")
        # Les entités peuvent avoir disparu depuis la soumission (FK OFF).
        for field in ("entity_id", "counterparty_entity_id"):
            if conn.execute("SELECT 1 FROM entities WHERE id = ?", (row[field],)).fetchone() is None:
                raise HTTPException(status_code=400, detail=f"L'entité référencée par {field} n'existe plus")
        # La catégorie peut aussi avoir disparu depuis la soumission (FK OFF) :
        # on approuve quand même, la transaction est créée sans catégorie.
        category_id = row["category_id"]
        if category_id is not None:
            if conn.execute("SELECT 1 FROM categories WHERE id = ?", (category_id,)).fetchone() is None:
                category_id = None
        if row["direction"] == "expense":
            from_id, to_id = row["entity_id"], row["counterparty_entity_id"]
        else:
            from_id, to_id = row["counterparty_entity_id"], row["entity_id"]
        submitter = conn.execute(
            "SELECT email FROM users WHERE id = ?", (row["submitted_by"],)
        ).fetchone()
        created_by = submitter["email"] if submitter else ""
        now = _now()
        cur = conn.execute(
            """INSERT INTO transactions
               (date, label, description, amount, category_id, contact_id, created_by,
                from_entity_id, to_entity_id, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?)""",
            (row["date"], row["label"], row["description"], row["amount"],
             category_id, created_by, from_id, to_id, now, now),
        )
        tx_id = cur.lastrowid
        # Justificatifs re-liés à la transaction, submission_id conservé (historique).
        conn.execute(
            "UPDATE attachments SET transaction_id = ? WHERE submission_id = ?",
            (tx_id, submission_id),
        )
        # Garde CAS : le statut n'est basculé que s'il est ENCORE 'pending' au
        # moment de l'écriture. Sous WAL + busy_timeout, le verrou d'écriture
        # SQLite sérialise deux approbations concurrentes ; la perdante voit
        # rowcount=0 et rollback, donc la transaction insérée ci-dessus est
        # annulée (jamais de double écriture comptable).
        cur = conn.execute(
            """UPDATE transaction_submissions
               SET status = 'approved', reviewed_by = ?, reviewed_at = ?,
                   transaction_id = ?, updated_at = ?
               WHERE id = ? AND status = 'pending'""",
            (admin["id"], now, tx_id, now, submission_id),
        )
        if cur.rowcount == 0:
            conn.rollback()
            raise HTTPException(status_code=409, detail="Cette soumission a déjà été traitée entretemps")
        data = _fetch_serialized(conn, submission_id)
        conn.commit()
        return data
    finally:
        conn.close()


@router.post("/{submission_id}/reject")
def reject_submission(submission_id: int, payload: RejectPayload, admin: dict = Depends(require_admin)):
    comment = payload.comment.strip()
    if not comment:
        raise HTTPException(status_code=400, detail="Un commentaire est requis pour refuser une soumission")
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT status FROM transaction_submissions WHERE id = ?", (submission_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Soumission {submission_id} introuvable")
        if row["status"] != "pending":
            raise HTTPException(status_code=409, detail="Seule une soumission en attente peut être refusée")
        now = _now()
        cur = conn.execute(
            """UPDATE transaction_submissions
               SET status = 'rejected', reviewed_by = ?, reviewed_at = ?,
                   review_comment = ?, updated_at = ?
               WHERE id = ? AND status = 'pending'""",
            (admin["id"], now, comment, now, submission_id),
        )
        if cur.rowcount == 0:
            conn.rollback()
            raise HTTPException(status_code=409, detail="Cette soumission a déjà été traitée entretemps")
        data = _fetch_serialized(conn, submission_id)
        conn.commit()
        return data
    finally:
        conn.close()


@router.post("/{submission_id}/cancel")
def cancel_submission(submission_id: int, request: Request):
    """L'auteur (ou l'admin) annule une soumission encore en attente."""
    user = get_current_user(request)
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT submitted_by, status FROM transaction_submissions WHERE id = ?",
            (submission_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Soumission {submission_id} introuvable")
        if not user["is_admin"] and row["submitted_by"] != user["id"]:
            raise HTTPException(status_code=403, detail="Seul l'auteur peut annuler sa soumission")
        if row["status"] != "pending":
            raise HTTPException(status_code=409, detail="Seule une soumission en attente peut être annulée")
        cur = conn.execute(
            "UPDATE transaction_submissions SET status = 'cancelled', updated_at = ? "
            "WHERE id = ? AND status = 'pending'",
            (_now(), submission_id),
        )
        if cur.rowcount == 0:
            conn.rollback()
            raise HTTPException(status_code=409, detail="Seule une soumission en attente peut être annulée")
        data = _fetch_serialized(conn, submission_id)
        conn.commit()
        return data
    finally:
        conn.close()
