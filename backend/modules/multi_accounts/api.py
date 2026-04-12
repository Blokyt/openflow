"""Multi-accounts API module for OpenFlow."""
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core.database import get_conn, row_to_dict

router = APIRouter()

VALID_TYPES = {"checking", "savings", "cash"}




# --- Pydantic models ---

class AccountCreate(BaseModel):
    name: str
    type: str = "checking"
    description: str = ""
    initial_balance: float = 0.0
    color: str = "#6B7280"
    position: int = 0


class AccountUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    description: Optional[str] = None
    initial_balance: Optional[float] = None
    color: Optional[str] = None
    position: Optional[int] = None


class TransferCreate(BaseModel):
    from_account_id: int
    to_account_id: int
    amount: float
    date: str
    label: str = ""


# --- Account endpoints ---

@router.get("/")
def list_accounts():
    conn = get_conn()
    try:
        cur = conn.execute("SELECT * FROM accounts ORDER BY position ASC, id ASC")
        return [row_to_dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


@router.post("/", status_code=201)
def create_account(account: AccountCreate):
    if account.type not in VALID_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid type '{account.type}'. Must be one of: {sorted(VALID_TYPES)}")
    now = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    try:
        cur = conn.execute(
            """INSERT INTO accounts (name, type, description, initial_balance, color, position, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (account.name, account.type, account.description, account.initial_balance, account.color, account.position, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM accounts WHERE id = ?", (cur.lastrowid,)).fetchone()
        return row_to_dict(row)
    finally:
        conn.close()


# IMPORTANT: /balances and /transfers must be declared BEFORE /{account_id}
@router.get("/balances")
def get_balances():
    conn = get_conn()
    try:
        accounts = [row_to_dict(r) for r in conn.execute("SELECT * FROM accounts ORDER BY position ASC, id ASC").fetchall()]
        result = []
        for acc in accounts:
            acc_id = acc["id"]
            incoming = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM transfers WHERE to_account_id = ?",
                (acc_id,),
            ).fetchone()[0]
            outgoing = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM transfers WHERE from_account_id = ?",
                (acc_id,),
            ).fetchone()[0]
            balance = acc["initial_balance"] + incoming - outgoing
            result.append({
                **acc,
                "balance": balance,
                "incoming": incoming,
                "outgoing": outgoing,
            })
        return result
    finally:
        conn.close()


@router.get("/transfers")
def list_transfers():
    conn = get_conn()
    try:
        cur = conn.execute("SELECT * FROM transfers ORDER BY date DESC, id DESC")
        return [row_to_dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


@router.post("/transfers", status_code=201)
def create_transfer(transfer: TransferCreate):
    if transfer.from_account_id == transfer.to_account_id:
        raise HTTPException(status_code=400, detail="from_account_id and to_account_id must be different")
    if transfer.amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be positive")

    now = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    try:
        # Verify both accounts exist
        from_acc = conn.execute("SELECT id FROM accounts WHERE id = ?", (transfer.from_account_id,)).fetchone()
        if from_acc is None:
            raise HTTPException(status_code=404, detail=f"Account {transfer.from_account_id} not found")
        to_acc = conn.execute("SELECT id FROM accounts WHERE id = ?", (transfer.to_account_id,)).fetchone()
        if to_acc is None:
            raise HTTPException(status_code=404, detail=f"Account {transfer.to_account_id} not found")

        label = transfer.label or "Virement"

        # Create the outgoing transaction (negative) on from_account
        from_tx = conn.execute(
            """INSERT INTO transactions (date, label, description, amount, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (transfer.date, label, f"Virement sortant", -transfer.amount, now, now),
        )
        from_tx_id = from_tx.lastrowid

        # Create the incoming transaction (positive) on to_account
        to_tx = conn.execute(
            """INSERT INTO transactions (date, label, description, amount, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (transfer.date, label, f"Virement entrant", transfer.amount, now, now),
        )
        to_tx_id = to_tx.lastrowid

        # Create the transfer record linking both
        cur = conn.execute(
            """INSERT INTO transfers (from_account_id, to_account_id, amount, date, label, from_transaction_id, to_transaction_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (transfer.from_account_id, transfer.to_account_id, transfer.amount, transfer.date, label, from_tx_id, to_tx_id, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM transfers WHERE id = ?", (cur.lastrowid,)).fetchone()
        return row_to_dict(row)
    finally:
        conn.close()


@router.get("/{account_id}")
def get_account(account_id: int):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Account {account_id} not found")
        return row_to_dict(row)
    finally:
        conn.close()


@router.put("/{account_id}")
def update_account(account_id: int, account: AccountUpdate):
    conn = get_conn()
    try:
        existing = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail=f"Account {account_id} not found")

        updates = account.model_dump(exclude_unset=True)
        if not updates:
            return row_to_dict(existing)

        if "type" in updates and updates["type"] not in VALID_TYPES:
            raise HTTPException(status_code=400, detail=f"Invalid type '{updates['type']}'. Must be one of: {sorted(VALID_TYPES)}")

        set_clauses = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [account_id]
        conn.execute(f"UPDATE accounts SET {set_clauses} WHERE id = ?", values)
        conn.commit()
        row = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        return row_to_dict(row)
    finally:
        conn.close()


@router.delete("/{account_id}")
def delete_account(account_id: int):
    conn = get_conn()
    try:
        existing = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail=f"Account {account_id} not found")
        conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
        conn.commit()
        return {"deleted": account_id}
    finally:
        conn.close()
