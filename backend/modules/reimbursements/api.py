"""Reimbursements API module for OpenFlow."""
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core.database import get_conn, row_to_dict
from backend.core.audit import record_audit

router = APIRouter()




class ReimbursementCreate(BaseModel):
    transaction_id: Optional[int] = None
    contact_id: Optional[int] = None
    person_name: str = ""
    amount: float
    status: str = "pending"
    reimbursed_date: Optional[str] = None
    reimbursement_transaction_id: Optional[int] = None
    notes: str = ""


class ReimbursementUpdate(BaseModel):
    transaction_id: Optional[int] = None
    contact_id: Optional[int] = None
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
    now = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    try:
        # Auto-resolve person_name from contact_id if not provided
        person_name = reimbursement.person_name
        contact_id = reimbursement.contact_id
        if contact_id and not person_name:
            contact = conn.execute("SELECT name FROM contacts WHERE id = ?", (contact_id,)).fetchone()
            if contact:
                person_name = contact[0]
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
                reimbursement.status,
                reimbursement.reimbursed_date,
                reimbursement.reimbursement_transaction_id,
                reimbursement.notes,
                now,
                now,
            ),
        )
        new_id = cur.lastrowid
        row = conn.execute("SELECT * FROM reimbursements WHERE id = ?", (new_id,)).fetchone()
        new_data = row_to_dict(row)
        record_audit(conn, "CREATE", "reimbursements", new_id, old_value=None, new_value=new_data)
        conn.commit()
        return new_data
    finally:
        conn.close()


@router.get("/summary")
def get_summary():
    """Return who owes what: group by contact, sum pending amounts."""
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

        old_data = row_to_dict(existing)
        updates = reimbursement.model_dump(exclude_unset=True)
        if not updates:
            return old_data

        set_clauses = ", ".join(f"{k} = ?" for k in updates)
        set_clauses += ", updated_at = ?"
        values = list(updates.values()) + [now, reimbursement_id]

        conn.execute(
            f"UPDATE reimbursements SET {set_clauses} WHERE id = ?",
            values,
        )
        row = conn.execute("SELECT * FROM reimbursements WHERE id = ?", (reimbursement_id,)).fetchone()
        new_data = row_to_dict(row)
        record_audit(conn, "UPDATE", "reimbursements", reimbursement_id, old_value=old_data, new_value=new_data)
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
            raise HTTPException(status_code=404, detail=f"Reimbursement {reimbursement_id} not found")
        old_data = row_to_dict(existing)
        conn.execute("DELETE FROM reimbursements WHERE id = ?", (reimbursement_id,))
        record_audit(conn, "DELETE", "reimbursements", reimbursement_id, old_value=old_data)
        conn.commit()
        return {"deleted": reimbursement_id}
    finally:
        conn.close()
