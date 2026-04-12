"""Tax Receipts API module for OpenFlow."""
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core.database import get_conn, row_to_dict

router = APIRouter()




class TaxReceiptCreate(BaseModel):
    contact_id: int
    amount: float
    date: str
    fiscal_year: str
    purpose: str = ""


class TaxReceiptUpdate(BaseModel):
    contact_id: Optional[int] = None
    amount: Optional[float] = None
    date: Optional[str] = None
    fiscal_year: Optional[str] = None
    purpose: Optional[str] = None


def _generate_number(conn: sqlite3.Connection, fiscal_year: str) -> str:
    """Generate the next tax receipt number for the given fiscal year."""
    cur = conn.execute(
        "SELECT number FROM tax_receipts WHERE number LIKE ?",
        (f"RF-{fiscal_year}-%",),
    )
    rows = cur.fetchall()
    max_seq = 0
    for row in rows:
        parts = row[0].split("-")
        if len(parts) == 3:
            try:
                seq = int(parts[2])
                if seq > max_seq:
                    max_seq = seq
            except ValueError:
                pass
    next_seq = max_seq + 1
    return f"RF-{fiscal_year}-{next_seq:03d}"


@router.get("/")
def list_tax_receipts(fiscal_year: Optional[str] = None):
    conn = get_conn()
    try:
        query = "SELECT * FROM tax_receipts WHERE 1=1"
        params = []
        if fiscal_year:
            query += " AND fiscal_year = ?"
            params.append(fiscal_year)
        query += " ORDER BY date DESC, id DESC"
        cur = conn.execute(query, params)
        return [row_to_dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


# IMPORTANT: /next-number must be declared BEFORE /{id} to avoid FastAPI
# treating "next-number" as a path parameter.
@router.get("/next-number")
def get_next_number(fiscal_year: str):
    conn = get_conn()
    try:
        return {"number": _generate_number(conn, fiscal_year)}
    finally:
        conn.close()


@router.post("/", status_code=201)
def create_tax_receipt(receipt: TaxReceiptCreate):
    now = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    try:
        number = _generate_number(conn, receipt.fiscal_year)
        cur = conn.execute(
            """INSERT INTO tax_receipts
               (number, contact_id, amount, date, fiscal_year, purpose, generated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                number,
                receipt.contact_id,
                receipt.amount,
                receipt.date,
                receipt.fiscal_year,
                receipt.purpose,
                now,
            ),
        )
        receipt_id = cur.lastrowid
        conn.commit()
        row = conn.execute("SELECT * FROM tax_receipts WHERE id = ?", (receipt_id,)).fetchone()
        return row_to_dict(row)
    finally:
        conn.close()


@router.get("/{receipt_id}")
def get_tax_receipt(receipt_id: int):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM tax_receipts WHERE id = ?", (receipt_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Tax receipt {receipt_id} not found")
        return row_to_dict(row)
    finally:
        conn.close()


@router.put("/{receipt_id}")
def update_tax_receipt(receipt_id: int, receipt: TaxReceiptUpdate):
    conn = get_conn()
    try:
        existing = conn.execute("SELECT * FROM tax_receipts WHERE id = ?", (receipt_id,)).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail=f"Tax receipt {receipt_id} not found")

        updates = receipt.model_dump(exclude_unset=True)
        if updates:
            set_clauses = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [receipt_id]
            conn.execute(
                f"UPDATE tax_receipts SET {set_clauses} WHERE id = ?",
                values,
            )
            conn.commit()

        row = conn.execute("SELECT * FROM tax_receipts WHERE id = ?", (receipt_id,)).fetchone()
        return row_to_dict(row)
    finally:
        conn.close()


@router.delete("/{receipt_id}")
def delete_tax_receipt(receipt_id: int):
    conn = get_conn()
    try:
        existing = conn.execute("SELECT * FROM tax_receipts WHERE id = ?", (receipt_id,)).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail=f"Tax receipt {receipt_id} not found")
        conn.execute("DELETE FROM tax_receipts WHERE id = ?", (receipt_id,))
        conn.commit()
        return {"deleted": receipt_id}
    finally:
        conn.close()
