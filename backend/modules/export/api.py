"""Export API module for OpenFlow."""
import csv
import io
import json
import sqlite3
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from backend.core.database import get_conn, row_to_dict

router = APIRouter()




def _fetch_transactions(
    conn: sqlite3.Connection,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    entity_id: Optional[int] = None,
) -> list[dict]:
    query = "SELECT * FROM transactions WHERE 1=1"
    params = []
    if date_from:
        query += " AND date >= ?"
        params.append(date_from)
    if date_to:
        query += " AND date <= ?"
        params.append(date_to)
    if entity_id is not None:
        query += " AND (from_entity_id = ? OR to_entity_id = ?)"
        params.extend([entity_id, entity_id])
    query += " ORDER BY date DESC, id DESC"
    cur = conn.execute(query, params)
    return [row_to_dict(r) for r in cur.fetchall()]


@router.get("/transactions/csv")
def export_transactions_csv(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    entity_id: Optional[int] = None,
):
    """Export all transactions as a CSV file."""
    conn = get_conn()
    try:
        rows = _fetch_transactions(conn, date_from, date_to, entity_id)
    finally:
        conn.close()

    output = io.StringIO()
    if rows:
        fieldnames = list(rows[0].keys())
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    else:
        output.write("")

    output.seek(0)

    def iter_content():
        yield output.read()

    return StreamingResponse(
        iter_content(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=transactions.csv"},
    )


@router.get("/transactions/json")
def export_transactions_json(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    entity_id: Optional[int] = None,
):
    """Export all transactions as a JSON file."""
    conn = get_conn()
    try:
        rows = _fetch_transactions(conn, date_from, date_to, entity_id)
    finally:
        conn.close()

    content = json.dumps(rows, ensure_ascii=False, indent=2)

    def iter_content():
        yield content

    return StreamingResponse(
        iter_content(),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=transactions.json"},
    )


@router.get("/summary/csv")
def export_summary_csv(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    entity_id: Optional[int] = None,
):
    """Export a summary by category as a CSV file (category_name, total_income, total_expenses, net)."""
    conn = get_conn()
    try:
        query = """
            SELECT
                COALESCE(c.name, 'Sans categorie') AS category_name,
                COALESCE(SUM(CASE WHEN t.amount > 0 THEN t.amount ELSE 0 END), 0) AS total_income,
                COALESCE(SUM(CASE WHEN t.amount < 0 THEN t.amount ELSE 0 END), 0) AS total_expenses,
                COALESCE(SUM(t.amount), 0) AS net
            FROM transactions t
            LEFT JOIN categories c ON t.category_id = c.id
            WHERE 1=1
        """
        params = []
        if date_from:
            query += " AND t.date >= ?"
            params.append(date_from)
        if date_to:
            query += " AND t.date <= ?"
            params.append(date_to)
        if entity_id is not None:
            query += " AND (t.from_entity_id = ? OR t.to_entity_id = ?)"
            params.extend([entity_id, entity_id])
        query += " GROUP BY COALESCE(c.name, 'Sans categorie') ORDER BY category_name"
        cur = conn.execute(query, params)
        rows = [row_to_dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

    output = io.StringIO()
    fieldnames = ["category_name", "total_income", "total_expenses", "net"]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    output.seek(0)

    def iter_content():
        yield output.read()

    return StreamingResponse(
        iter_content(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=summary.csv"},
    )
