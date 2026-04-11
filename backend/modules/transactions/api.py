"""Transactions API module for OpenFlow."""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core.config import load_config

router = APIRouter()

# Project root is 3 levels up from this file: backend/modules/transactions/api.py
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "openflow.db"
CONFIG_PATH = PROJECT_ROOT / "config.yaml"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


class TransactionCreate(BaseModel):
    date: str
    label: str
    description: str = ""
    amount: float
    category_id: Optional[int] = None
    division_id: Optional[int] = None
    contact_id: Optional[int] = None
    created_by: str = ""


class TransactionUpdate(BaseModel):
    date: Optional[str] = None
    label: Optional[str] = None
    description: Optional[str] = None
    amount: Optional[float] = None
    category_id: Optional[int] = None
    division_id: Optional[int] = None
    contact_id: Optional[int] = None
    created_by: Optional[str] = None


@router.get("/")
def list_transactions(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    category_id: Optional[int] = None,
    search: Optional[str] = None,
):
    conn = get_conn()
    try:
        query = "SELECT * FROM transactions WHERE 1=1"
        params = []
        if date_from:
            query += " AND date >= ?"
            params.append(date_from)
        if date_to:
            query += " AND date <= ?"
            params.append(date_to)
        if category_id is not None:
            query += " AND category_id = ?"
            params.append(category_id)
        if search:
            query += " AND (label LIKE ? OR description LIKE ?)"
            params.extend([f"%{search}%", f"%{search}%"])
        query += " ORDER BY date DESC, id DESC"
        cur = conn.execute(query, params)
        return [row_to_dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


@router.post("/", status_code=201)
def create_transaction(tx: TransactionCreate):
    now = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    try:
        cur = conn.execute(
            """INSERT INTO transactions
               (date, label, description, amount, category_id, division_id, contact_id, created_by, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                tx.date,
                tx.label,
                tx.description,
                tx.amount,
                tx.category_id,
                tx.division_id,
                tx.contact_id,
                tx.created_by,
                now,
                now,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM transactions WHERE id = ?", (cur.lastrowid,)).fetchone()
        return row_to_dict(row)
    finally:
        conn.close()


# IMPORTANT: /balance must be declared BEFORE /{tx_id} to avoid FastAPI
# treating "balance" as a tx_id path parameter.
@router.get("/balance")
def get_balance():
    try:
        config = load_config(str(CONFIG_PATH))
        reference_amount = config.balance.amount
        reference_date = config.balance.date
    except Exception:
        reference_amount = 0.0
        reference_date = None

    conn = get_conn()
    try:
        if reference_date:
            cur = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE date >= ?",
                (reference_date,),
            )
        else:
            cur = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM transactions")
        total = cur.fetchone()[0]
        balance = reference_amount + total
        return {
            "balance": balance,
            "reference_amount": reference_amount,
            "reference_date": reference_date,
            "transactions_sum": total,
        }
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

        set_clauses = ", ".join(f"{k} = ?" for k in updates)
        set_clauses += ", updated_at = ?"
        values = list(updates.values()) + [now, tx_id]

        conn.execute(
            f"UPDATE transactions SET {set_clauses} WHERE id = ?",
            values,
        )
        conn.commit()
        row = conn.execute("SELECT * FROM transactions WHERE id = ?", (tx_id,)).fetchone()
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
        conn.commit()
        return {"deleted": tx_id}
    finally:
        conn.close()
