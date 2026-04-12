"""Invoices API module for OpenFlow."""
import sqlite3
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core.database import get_conn, row_to_dict

router = APIRouter()




class InvoiceLineCreate(BaseModel):
    description: str
    quantity: float = 1.0
    unit_price: float


class InvoiceCreate(BaseModel):
    type: str = "invoice"
    contact_id: Optional[int] = None
    date: str
    due_date: Optional[str] = None
    status: str = "draft"
    tax_rate: float = 0.0
    notes: str = ""
    transaction_id: Optional[int] = None
    lines: List[InvoiceLineCreate] = []


class InvoiceUpdate(BaseModel):
    type: Optional[str] = None
    contact_id: Optional[int] = None
    date: Optional[str] = None
    due_date: Optional[str] = None
    status: Optional[str] = None
    tax_rate: Optional[float] = None
    notes: Optional[str] = None
    transaction_id: Optional[int] = None
    lines: Optional[List[InvoiceLineCreate]] = None


def _generate_number(conn: sqlite3.Connection, inv_type: str) -> str:
    """Generate the next invoice/quote number for the current year."""
    year = datetime.now().year
    prefix = "FAC" if inv_type == "invoice" else "DEV"
    # Find max sequence for this type and year
    cur = conn.execute(
        "SELECT number FROM invoices WHERE type = ? AND number LIKE ?",
        (inv_type, f"{prefix}-{year}-%"),
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
    return f"{prefix}-{year}-{next_seq:03d}"


def _get_invoice_with_lines(conn: sqlite3.Connection, invoice_id: int) -> Optional[dict]:
    row = conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
    if row is None:
        return None
    result = row_to_dict(row)
    lines_cur = conn.execute(
        "SELECT * FROM invoice_lines WHERE invoice_id = ? ORDER BY id ASC",
        (invoice_id,),
    )
    result["lines"] = [row_to_dict(r) for r in lines_cur.fetchall()]
    return result


def _insert_lines(conn: sqlite3.Connection, invoice_id: int, lines: List[InvoiceLineCreate]):
    for line in lines:
        line_total = line.quantity * line.unit_price
        conn.execute(
            """INSERT INTO invoice_lines (invoice_id, description, quantity, unit_price, total)
               VALUES (?, ?, ?, ?, ?)""",
            (invoice_id, line.description, line.quantity, line.unit_price, line_total),
        )


def _compute_totals(lines: List[InvoiceLineCreate], tax_rate: float):
    subtotal = sum(l.quantity * l.unit_price for l in lines)
    total = subtotal * (1 + tax_rate / 100)
    return subtotal, total


@router.get("/")
def list_invoices(
    type: Optional[str] = None,
    status: Optional[str] = None,
):
    conn = get_conn()
    try:
        query = "SELECT * FROM invoices WHERE 1=1"
        params = []
        if type:
            query += " AND type = ?"
            params.append(type)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY date DESC, id DESC"
        cur = conn.execute(query, params)
        return [row_to_dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


@router.post("/", status_code=201)
def create_invoice(invoice: InvoiceCreate):
    now = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    try:
        number = _generate_number(conn, invoice.type)
        subtotal, total = _compute_totals(invoice.lines, invoice.tax_rate)
        cur = conn.execute(
            """INSERT INTO invoices
               (number, type, contact_id, date, due_date, status, subtotal, tax_rate, total,
                notes, transaction_id, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                number,
                invoice.type,
                invoice.contact_id,
                invoice.date,
                invoice.due_date,
                invoice.status,
                subtotal,
                invoice.tax_rate,
                total,
                invoice.notes,
                invoice.transaction_id,
                now,
                now,
            ),
        )
        invoice_id = cur.lastrowid
        _insert_lines(conn, invoice_id, invoice.lines)
        conn.commit()
        result = _get_invoice_with_lines(conn, invoice_id)
        return result
    finally:
        conn.close()


# IMPORTANT: /next-number must be declared BEFORE /{invoice_id} to avoid FastAPI
# treating "next-number" as an invoice_id path parameter.
@router.get("/next-number")
def get_next_number(type: str = "invoice"):
    conn = get_conn()
    try:
        return {"number": _generate_number(conn, type)}
    finally:
        conn.close()


@router.get("/{invoice_id}")
def get_invoice(invoice_id: int):
    conn = get_conn()
    try:
        result = _get_invoice_with_lines(conn, invoice_id)
        if result is None:
            raise HTTPException(status_code=404, detail=f"Invoice {invoice_id} not found")
        return result
    finally:
        conn.close()


@router.put("/{invoice_id}")
def update_invoice(invoice_id: int, invoice: InvoiceUpdate):
    now = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    try:
        existing = conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail=f"Invoice {invoice_id} not found")

        updates = invoice.model_dump(exclude_unset=True)
        lines = updates.pop("lines", None)

        if updates:
            # Recompute totals if lines or tax_rate changed
            if lines is not None or "tax_rate" in updates:
                tax_rate = updates.get("tax_rate", existing["tax_rate"])
                if lines is not None:
                    line_objs = [InvoiceLineCreate(**l) if isinstance(l, dict) else l for l in lines]
                else:
                    # Load existing lines
                    existing_lines = conn.execute(
                        "SELECT * FROM invoice_lines WHERE invoice_id = ?", (invoice_id,)
                    ).fetchall()
                    line_objs = [
                        InvoiceLineCreate(
                            description=r["description"],
                            quantity=r["quantity"],
                            unit_price=r["unit_price"],
                        )
                        for r in existing_lines
                    ]
                subtotal, total = _compute_totals(line_objs, tax_rate)
                updates["subtotal"] = subtotal
                updates["total"] = total

            set_clauses = ", ".join(f"{k} = ?" for k in updates)
            set_clauses += ", updated_at = ?"
            values = list(updates.values()) + [now, invoice_id]
            conn.execute(
                f"UPDATE invoices SET {set_clauses} WHERE id = ?",
                values,
            )
        else:
            conn.execute("UPDATE invoices SET updated_at = ? WHERE id = ?", (now, invoice_id))

        if lines is not None:
            conn.execute("DELETE FROM invoice_lines WHERE invoice_id = ?", (invoice_id,))
            line_objs = [InvoiceLineCreate(**l) if isinstance(l, dict) else l for l in lines]
            _insert_lines(conn, invoice_id, line_objs)
            # Recompute totals based on new lines if not already done
            if "tax_rate" not in updates and lines is not None and "subtotal" not in updates:
                tax_rate = existing["tax_rate"]
                subtotal, total = _compute_totals(line_objs, tax_rate)
                conn.execute(
                    "UPDATE invoices SET subtotal = ?, total = ? WHERE id = ?",
                    (subtotal, total, invoice_id),
                )

        conn.commit()
        result = _get_invoice_with_lines(conn, invoice_id)
        return result
    finally:
        conn.close()


@router.delete("/{invoice_id}")
def delete_invoice(invoice_id: int):
    conn = get_conn()
    try:
        existing = conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail=f"Invoice {invoice_id} not found")
        # Lines are deleted via CASCADE
        conn.execute("DELETE FROM invoices WHERE id = ?", (invoice_id,))
        conn.commit()
        return {"deleted": invoice_id}
    finally:
        conn.close()


@router.post("/{invoice_id}/convert")
def convert_quote_to_invoice(invoice_id: int):
    """Convert a quote (devis) to an invoice (facture)."""
    now = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    try:
        existing = conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail=f"Invoice {invoice_id} not found")
        if existing["type"] != "quote":
            raise HTTPException(status_code=400, detail="Only quotes can be converted to invoices")

        new_number = _generate_number(conn, "invoice")
        conn.execute(
            "UPDATE invoices SET type = 'invoice', number = ?, status = 'draft', updated_at = ? WHERE id = ?",
            (new_number, now, invoice_id),
        )
        conn.commit()
        result = _get_invoice_with_lines(conn, invoice_id)
        return result
    finally:
        conn.close()
