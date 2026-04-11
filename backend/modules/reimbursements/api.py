"""Reimbursements API module for OpenFlow."""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

# Project root is 3 levels up from this file: backend/modules/reimbursements/api.py
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "openflow.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


class ReimbursementCreate(BaseModel):
    transaction_id: Optional[int] = None
    person_name: str
    amount: float
    status: str = "pending"
    reimbursed_date: Optional[str] = None
    reimbursement_transaction_id: Optional[int] = None
    notes: str = ""


class ReimbursementUpdate(BaseModel):
    transaction_id: Optional[int] = None
    person_name: Optional[str] = None
    amount: Optional[float] = None
    status: Optional[str] = None
    reimbursed_date: Optional[str] = None
    reimbursement_transaction_id: Optional[int] = None
    notes: Optional[str] = None


@router.get("/")
def list_reimbursements(status: Optional[str] = None):
    conn = get_conn()
    try:
        query = "SELECT * FROM reimbursements WHERE 1=1"
        params = []
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC, id DESC"
        cur = conn.execute(query, params)
        return [row_to_dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


@router.post("/", status_code=201)
def create_reimbursement(reimbursement: ReimbursementCreate):
    now = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    try:
        cur = conn.execute(
            """INSERT INTO reimbursements
               (transaction_id, person_name, amount, status, reimbursed_date,
                reimbursement_transaction_id, notes, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                reimbursement.transaction_id,
                reimbursement.person_name,
                reimbursement.amount,
                reimbursement.status,
                reimbursement.reimbursed_date,
                reimbursement.reimbursement_transaction_id,
                reimbursement.notes,
                now,
                now,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM reimbursements WHERE id = ?", (cur.lastrowid,)).fetchone()
        return row_to_dict(row)
    finally:
        conn.close()


@router.get("/summary")
def get_summary():
    """Return who owes what: group by person_name, sum pending amounts."""
    conn = get_conn()
    try:
        cur = conn.execute(
            """SELECT person_name, SUM(amount) as total_pending, COUNT(*) as count
               FROM reimbursements
               WHERE status = 'pending'
               GROUP BY person_name
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
            raise HTTPException(status_code=404, detail=f"Reimbursement {reimbursement_id} not found")
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
            raise HTTPException(status_code=404, detail=f"Reimbursement {reimbursement_id} not found")

        updates = reimbursement.model_dump(exclude_unset=True)
        if not updates:
            return row_to_dict(existing)

        set_clauses = ", ".join(f"{k} = ?" for k in updates)
        set_clauses += ", updated_at = ?"
        values = list(updates.values()) + [now, reimbursement_id]

        conn.execute(
            f"UPDATE reimbursements SET {set_clauses} WHERE id = ?",
            values,
        )
        conn.commit()
        row = conn.execute("SELECT * FROM reimbursements WHERE id = ?", (reimbursement_id,)).fetchone()
        return row_to_dict(row)
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
            raise HTTPException(status_code=404, detail=f"Reimbursement {reimbursement_id} not found")
        conn.execute("DELETE FROM reimbursements WHERE id = ?", (reimbursement_id,))
        conn.commit()
        return {"deleted": reimbursement_id}
    finally:
        conn.close()
