"""Transactions API module for OpenFlow."""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core.audit import record_audit
from backend.core.balance import compute_legacy_balance
from backend.core.database import get_conn, row_to_dict

router = APIRouter()

# Project root is 3 levels up from this file: backend/modules/transactions/api.py
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
CONFIG_PATH = PROJECT_ROOT / "config.yaml"




class TransactionCreate(BaseModel):
    date: str
    label: str
    description: str = ""
    amount: float
    category_id: Optional[int] = None
    contact_id: Optional[int] = None
    created_by: str = ""
    from_entity_id: int
    to_entity_id: int


class TransactionUpdate(BaseModel):
    date: Optional[str] = None
    label: Optional[str] = None
    description: Optional[str] = None
    amount: Optional[float] = None
    category_id: Optional[int] = None
    contact_id: Optional[int] = None
    created_by: Optional[str] = None
    from_entity_id: Optional[int] = None
    to_entity_id: Optional[int] = None


@router.get("/")
def list_transactions(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    category_id: Optional[int] = None,
    search: Optional[str] = None,
    entity_id: Optional[int] = None,
    include_children: bool = False,
    reimb_status: Optional[str] = None,
):
    conn = get_conn()
    try:
        query = """SELECT t.*,
                   c.name AS category_name, c.color AS category_color,
                   ef.name AS from_entity_name, ef.color AS from_entity_color,
                   et.name AS to_entity_name, et.color AS to_entity_color,
                   co.name AS contact_name,
                   rb.reimb_person_name, rb.reimb_status, rb.reimb_count
            FROM transactions t
            LEFT JOIN categories c ON t.category_id = c.id
            LEFT JOIN entities ef ON t.from_entity_id = ef.id
            LEFT JOIN entities et ON t.to_entity_id = et.id
            LEFT JOIN contacts co ON t.contact_id = co.id
            LEFT JOIN (
                SELECT transaction_id,
                       GROUP_CONCAT(COALESCE(rco.name, r.person_name), ', ') AS reimb_person_name,
                       MIN(r.status) AS reimb_status,
                       COUNT(*) AS reimb_count
                FROM reimbursements r
                LEFT JOIN contacts rco ON r.contact_id = rco.id
                GROUP BY transaction_id
            ) rb ON rb.transaction_id = t.id
            WHERE 1=1"""
        params = []
        if date_from:
            query += " AND t.date >= ?"
            params.append(date_from)
        if date_to:
            query += " AND t.date <= ?"
            params.append(date_to)
        if category_id is not None:
            query += " AND t.category_id = ?"
            params.append(category_id)
        if search:
            query += """ AND (t.label LIKE ? OR t.description LIKE ?
                         OR ef.name LIKE ? OR et.name LIKE ?
                         OR c.name LIKE ? OR co.name LIKE ? OR t.date LIKE ?)"""
            s = f"%{search}%"
            params.extend([s, s, s, s, s, s, s])
        if entity_id is not None:
            if include_children:
                rows = conn.execute(
                    """WITH RECURSIVE subtree(id) AS (
                           SELECT ? AS id
                           UNION ALL
                           SELECT e.id FROM entities e
                           INNER JOIN subtree s ON e.parent_id = s.id
                       )
                       SELECT id FROM subtree""",
                    (entity_id,),
                ).fetchall()
                entity_ids = [r[0] for r in rows]
                placeholders = ",".join("?" * len(entity_ids))
                query += f" AND (t.from_entity_id IN ({placeholders}) OR t.to_entity_id IN ({placeholders}))"
                params.extend(entity_ids)
                params.extend(entity_ids)
            else:
                query += " AND (t.from_entity_id = ? OR t.to_entity_id = ?)"
                params.extend([entity_id, entity_id])
        if reimb_status == "pending":
            query += " AND rb.reimb_status = 'pending'"
        elif reimb_status == "reimbursed":
            query += " AND rb.reimb_status = 'reimbursed'"
        elif reimb_status == "none":
            query += " AND rb.reimb_status IS NULL"
        elif reimb_status is not None:
            raise HTTPException(status_code=400, detail=f"invalid reimb_status: {reimb_status}")
        query += " ORDER BY t.date DESC, t.id DESC"
        cur = conn.execute(query, params)
        return [row_to_dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


@router.post("/", status_code=201)
def create_transaction(tx: TransactionCreate):
    now = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    try:
        for field, value in (("from_entity_id", tx.from_entity_id), ("to_entity_id", tx.to_entity_id)):
            exists = conn.execute("SELECT 1 FROM entities WHERE id = ?", (value,)).fetchone()
            if exists is None:
                raise HTTPException(status_code=400, detail=f"{field}={value} does not reference an existing entity")
        cur = conn.execute(
            """INSERT INTO transactions
               (date, label, description, amount, category_id, contact_id, created_by,
                from_entity_id, to_entity_id, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                tx.date,
                tx.label,
                tx.description,
                tx.amount,
                tx.category_id,
                tx.contact_id,
                tx.created_by,
                tx.from_entity_id,
                tx.to_entity_id,
                now,
                now,
            ),
        )
        new_row = conn.execute("SELECT * FROM transactions WHERE id = ?", (cur.lastrowid,)).fetchone()
        record_audit(conn, "create", "transactions", cur.lastrowid, None, row_to_dict(new_row), tx.created_by)
        conn.commit()
        return row_to_dict(new_row)
    finally:
        conn.close()


# IMPORTANT: /balance must be declared BEFORE /{tx_id} to avoid FastAPI
# treating "balance" as a tx_id path parameter.
@router.get("/balance")
def get_balance():
    conn = get_conn()
    try:
        return compute_legacy_balance(conn, str(CONFIG_PATH))
    finally:
        conn.close()


@router.get("/{tx_id}")
def get_transaction(tx_id: int):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM transactions WHERE id = ?", (tx_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Transaction {tx_id} not found")
        return row_to_dict(row)
    finally:
        conn.close()


@router.put("/{tx_id}")
def update_transaction(tx_id: int, tx: TransactionUpdate):
    now = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    try:
        existing = conn.execute("SELECT * FROM transactions WHERE id = ?", (tx_id,)).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail=f"Transaction {tx_id} not found")

        updates = tx.model_dump(exclude_unset=True)
        if not updates:
            return row_to_dict(existing)

        for field in ("from_entity_id", "to_entity_id"):
            if field in updates:
                if updates[field] is None:
                    raise HTTPException(status_code=400, detail=f"{field} cannot be null")
                exists = conn.execute("SELECT 1 FROM entities WHERE id = ?", (updates[field],)).fetchone()
                if exists is None:
                    raise HTTPException(status_code=400, detail=f"{field}={updates[field]} does not reference an existing entity")

        set_clauses = ", ".join(f"{k} = ?" for k in updates)
        set_clauses += ", updated_at = ?"
        values = list(updates.values()) + [now, tx_id]

        conn.execute(
            f"UPDATE transactions SET {set_clauses} WHERE id = ?",
            values,
        )
        row = conn.execute("SELECT * FROM transactions WHERE id = ?", (tx_id,)).fetchone()
        record_audit(conn, "update", "transactions", tx_id, row_to_dict(existing), row_to_dict(row))
        conn.commit()
        return row_to_dict(row)
    finally:
        conn.close()


@router.delete("/{tx_id}")
def delete_transaction(tx_id: int):
    conn = get_conn()
    try:
        existing = conn.execute("SELECT * FROM transactions WHERE id = ?", (tx_id,)).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail=f"Transaction {tx_id} not found")
        conn.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))
        record_audit(conn, "delete", "transactions", tx_id, row_to_dict(existing), None)
        conn.commit()
        return {"deleted": tx_id}
    finally:
        conn.close()
