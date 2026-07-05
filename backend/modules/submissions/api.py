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
            "SELECT id FROM entities WHERE id = ?", (sub.counterparty_entity_id,)
        ).fetchone()
        if counterparty is None:
            raise HTTPException(status_code=400, detail="counterparty_entity_id ne référence aucune entité")
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
