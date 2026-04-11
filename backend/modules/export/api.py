"""Export API module for OpenFlow."""
import csv
import io
import json
import sqlite3
from pathlib import Path
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

router = APIRouter()

# Project root is 3 levels up from this file: backend/modules/export/api.py
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "openflow.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


def _fetch_transactions(
    conn: sqlite3.Connection,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> list[dict]:
    query = "SELECT * FROM transactions WHERE 1=1"
    params = []
    if date_from:
        query += " AND date >= ?"
        params.append(date_from)
    if date_to:
        query += " AND date <= ?"
        params.append(date_to)
    query += " ORDER BY date DESC, id DESC"
    cur = conn.execute(query, params)
    return [row_to_dict(r) for r in cur.fetchall()]


@router.get("/transactions/csv")
def export_transactions_csv(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    """Export all transactions as a CSV file."""
    conn = get_conn()
    try:
        rows = _fetch_transactions(conn, date_from, date_to)
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
):
    """Export all transactions as a JSON file."""
    conn = get_conn()
    try:
        rows = _fetch_transactions(conn, date_from, date_to)
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
