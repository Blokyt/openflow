"""Bank Reconciliation API module for OpenFlow."""
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core.database import get_conn, row_to_dict

router = APIRouter()




class BankStatementEntry(BaseModel):
    date: str
    label: str
    amount: float


class ImportRequest(BaseModel):
    entries: List[BankStatementEntry]


class MatchRequest(BaseModel):
    statement_id: int
    transaction_id: int


def _try_auto_match(conn: sqlite3.Connection, statement_id: int, date: str, amount: float) -> bool:
    """Attempt to auto-match a bank statement entry to a transaction.

    Looks for transactions with the exact same amount and a date within ±3 days.
    If exactly one match is found, auto-matches it and returns True.
    """
    try:
        entry_date = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return False

    date_from = (entry_date - timedelta(days=3)).strftime("%Y-%m-%d")
    date_to = (entry_date + timedelta(days=3)).strftime("%Y-%m-%d")

    cur = conn.execute(
        "SELECT id FROM transactions WHERE amount = ? AND date >= ? AND date <= ?",
        (amount, date_from, date_to),
    )
    matches = cur.fetchall()

    if len(matches) == 1:
        tx_id = matches[0]["id"]
        conn.execute(
            "UPDATE bank_statements SET matched_transaction_id = ?, status = 'matched' WHERE id = ?",
            (tx_id, statement_id),
        )
        return True

    return False


@router.get("/")
def list_statements(status: Optional[str] = None):
    conn = get_conn()
    try:
        query = "SELECT * FROM bank_statements WHERE 1=1"
        params = []
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY date DESC, id DESC"
        cur = conn.execute(query, params)
        return [row_to_dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


@router.post("/import", status_code=201)
def import_statements(body: ImportRequest):
    now = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    try:
        results = []
        for entry in body.entries:
            cur = conn.execute(
                """INSERT INTO bank_statements (date, label, amount, status, imported_at)
                   VALUES (?, ?, ?, 'unmatched', ?)""",
                (entry.date, entry.label, entry.amount, now),
            )
            stmt_id = cur.lastrowid
            _try_auto_match(conn, stmt_id, entry.date, entry.amount)
            row = conn.execute("SELECT * FROM bank_statements WHERE id = ?", (stmt_id,)).fetchone()
            results.append(row_to_dict(row))
        conn.commit()
        return results
    finally:
        conn.close()


@router.get("/suggestions/{statement_id}")
def get_suggestions(statement_id: int):
    conn = get_conn()
    try:
        stmt = conn.execute(
            "SELECT * FROM bank_statements WHERE id = ?", (statement_id,)
        ).fetchone()
        if stmt is None:
            raise HTTPException(status_code=404, detail=f"Statement {statement_id} not found")

        stmt_dict = row_to_dict(stmt)
        if stmt_dict["status"] != "unmatched":
            return []

        try:
            entry_date = datetime.strptime(stmt_dict["date"], "%Y-%m-%d")
        except ValueError:
            return []

        date_from = (entry_date - timedelta(days=5)).strftime("%Y-%m-%d")
        date_to = (entry_date + timedelta(days=5)).strftime("%Y-%m-%d")

        cur = conn.execute(
            "SELECT * FROM transactions WHERE amount = ? AND date >= ? AND date <= ? ORDER BY date",
            (stmt_dict["amount"], date_from, date_to),
        )
        return [row_to_dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


@router.post("/match")
def match_statement(body: MatchRequest):
    conn = get_conn()
    try:
        stmt = conn.execute(
            "SELECT * FROM bank_statements WHERE id = ?", (body.statement_id,)
        ).fetchone()
        if stmt is None:
            raise HTTPException(status_code=404, detail=f"Statement {body.statement_id} not found")

        tx = conn.execute(
            "SELECT * FROM transactions WHERE id = ?", (body.transaction_id,)
        ).fetchone()
        if tx is None:
            raise HTTPException(status_code=404, detail=f"Transaction {body.transaction_id} not found")

        conn.execute(
            "UPDATE bank_statements SET matched_transaction_id = ?, status = 'matched' WHERE id = ?",
            (body.transaction_id, body.statement_id),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM bank_statements WHERE id = ?", (body.statement_id,)
        ).fetchone()
        return row_to_dict(row)
    finally:
        conn.close()


@router.post("/unmatch/{statement_id}")
def unmatch_statement(statement_id: int):
    conn = get_conn()
    try:
        stmt = conn.execute(
            "SELECT * FROM bank_statements WHERE id = ?", (statement_id,)
        ).fetchone()
        if stmt is None:
            raise HTTPException(status_code=404, detail=f"Statement {statement_id} not found")

        conn.execute(
            "UPDATE bank_statements SET matched_transaction_id = NULL, status = 'unmatched' WHERE id = ?",
            (statement_id,),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM bank_statements WHERE id = ?", (statement_id,)
        ).fetchone()
        return row_to_dict(row)
    finally:
        conn.close()


@router.delete("/{statement_id}")
def delete_statement(statement_id: int):
    conn = get_conn()
    try:
        stmt = conn.execute(
            "SELECT * FROM bank_statements WHERE id = ?", (statement_id,)
        ).fetchone()
        if stmt is None:
            raise HTTPException(status_code=404, detail=f"Statement {statement_id} not found")
        conn.execute("DELETE FROM bank_statements WHERE id = ?", (statement_id,))
        conn.commit()
        return {"deleted": statement_id}
    finally:
        conn.close()
