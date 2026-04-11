"""Recurring transactions API module for OpenFlow."""
import sqlite3
from datetime import datetime, date, timezone
from dateutil.relativedelta import relativedelta
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

# Project root is 3 levels up from this file: backend/modules/recurring/api.py
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "openflow.db"

VALID_FREQUENCIES = {"weekly", "monthly", "quarterly", "yearly"}


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


class RecurringCreate(BaseModel):
    label: str
    description: str = ""
    amount: float
    category_id: Optional[int] = None
    division_id: Optional[int] = None
    contact_id: Optional[int] = None
    frequency: str
    start_date: str
    end_date: Optional[str] = None
    active: int = 1


class RecurringUpdate(BaseModel):
    label: Optional[str] = None
    description: Optional[str] = None
    amount: Optional[float] = None
    category_id: Optional[int] = None
    division_id: Optional[int] = None
    contact_id: Optional[int] = None
    frequency: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    active: Optional[int] = None


def _next_occurrence(from_date: date, frequency: str) -> date:
    """Calculate next occurrence date based on frequency."""
    if frequency == "weekly":
        return from_date + relativedelta(weeks=1)
    elif frequency == "monthly":
        return from_date + relativedelta(months=1)
    elif frequency == "quarterly":
        return from_date + relativedelta(months=3)
    elif frequency == "yearly":
        return from_date + relativedelta(years=1)
    else:
        raise ValueError(f"Unknown frequency: {frequency}")


@router.get("/")
def list_recurring():
    conn = get_conn()
    try:
        cur = conn.execute("SELECT * FROM recurring_transactions ORDER BY id DESC")
        return [row_to_dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


@router.post("/", status_code=201)
def create_recurring(rec: RecurringCreate):
    if rec.frequency not in VALID_FREQUENCIES:
        raise HTTPException(status_code=400, detail=f"Invalid frequency '{rec.frequency}'. Must be one of: {', '.join(sorted(VALID_FREQUENCIES))}")
    now = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    try:
        cur = conn.execute(
            """INSERT INTO recurring_transactions
               (label, description, amount, category_id, division_id, contact_id,
                frequency, start_date, end_date, last_generated, active, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)""",
            (
                rec.label,
                rec.description,
                rec.amount,
                rec.category_id,
                rec.division_id,
                rec.contact_id,
                rec.frequency,
                rec.start_date,
                rec.end_date,
                rec.active,
                now,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM recurring_transactions WHERE id = ?", (cur.lastrowid,)).fetchone()
        return row_to_dict(row)
    finally:
        conn.close()


# IMPORTANT: /generate must be declared BEFORE /{rec_id} to avoid FastAPI
# treating "generate" as a rec_id path parameter.
@router.post("/generate")
def generate_transactions():
    """Generate pending transactions for all active recurring transactions."""
    today = date.today()
    now_iso = datetime.now(timezone.utc).isoformat()
    generated = []

    conn = get_conn()
    try:
        recurrings = conn.execute(
            "SELECT * FROM recurring_transactions WHERE active = 1"
        ).fetchall()

        for rec in recurrings:
            rec = row_to_dict(rec)
            frequency = rec["frequency"]
            start_date = date.fromisoformat(rec["start_date"])
            end_date = date.fromisoformat(rec["end_date"]) if rec["end_date"] else None

            # Determine the base date for the next occurrence
            if rec["last_generated"]:
                last_generated = date.fromisoformat(rec["last_generated"][:10])
                next_date = _next_occurrence(last_generated, frequency)
            else:
                # Never generated: first occurrence is start_date
                next_date = start_date

            # Generate all pending occurrences
            new_last_generated = None
            while next_date <= today:
                if end_date and next_date > end_date:
                    break

                # Insert a transaction for this occurrence
                tx_cur = conn.execute(
                    """INSERT INTO transactions
                       (date, label, description, amount, category_id, division_id,
                        contact_id, created_by, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        next_date.isoformat(),
                        rec["label"],
                        rec["description"],
                        rec["amount"],
                        rec["category_id"],
                        rec["division_id"],
                        rec["contact_id"],
                        "recurring",
                        now_iso,
                        now_iso,
                    ),
                )
                tx_row = conn.execute(
                    "SELECT * FROM transactions WHERE id = ?", (tx_cur.lastrowid,)
                ).fetchone()
                generated.append(row_to_dict(tx_row))
                new_last_generated = next_date

                next_date = _next_occurrence(next_date, frequency)

            # Update last_generated if new transactions were created
            if new_last_generated is not None:
                conn.execute(
                    "UPDATE recurring_transactions SET last_generated = ? WHERE id = ?",
                    (new_last_generated.isoformat(), rec["id"]),
                )

        conn.commit()
        return generated
    finally:
        conn.close()


@router.get("/{rec_id}")
def get_recurring(rec_id: int):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM recurring_transactions WHERE id = ?", (rec_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Recurring transaction {rec_id} not found")
        return row_to_dict(row)
    finally:
        conn.close()


@router.put("/{rec_id}")
def update_recurring(rec_id: int, rec: RecurringUpdate):
    conn = get_conn()
    try:
        existing = conn.execute(
            "SELECT * FROM recurring_transactions WHERE id = ?", (rec_id,)
        ).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail=f"Recurring transaction {rec_id} not found")

        updates = rec.model_dump(exclude_unset=True)
        if not updates:
            return row_to_dict(existing)

        if "frequency" in updates and updates["frequency"] not in VALID_FREQUENCIES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid frequency '{updates['frequency']}'. Must be one of: {', '.join(sorted(VALID_FREQUENCIES))}",
            )

        set_clauses = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [rec_id]

        conn.execute(
            f"UPDATE recurring_transactions SET {set_clauses} WHERE id = ?",
            values,
        )
        conn.commit()
        row = conn.execute("SELECT * FROM recurring_transactions WHERE id = ?", (rec_id,)).fetchone()
        return row_to_dict(row)
    finally:
        conn.close()


@router.delete("/{rec_id}")
def delete_recurring(rec_id: int):
    conn = get_conn()
    try:
        existing = conn.execute(
            "SELECT * FROM recurring_transactions WHERE id = ?", (rec_id,)
        ).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail=f"Recurring transaction {rec_id} not found")
        conn.execute("DELETE FROM recurring_transactions WHERE id = ?", (rec_id,))
        conn.commit()
        return {"deleted": rec_id}
    finally:
        conn.close()
