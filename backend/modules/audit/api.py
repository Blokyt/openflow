"""Audit API module for OpenFlow."""
import sqlite3
from typing import Optional

from fastapi import APIRouter, HTTPException

from backend.core.database import get_conn

router = APIRouter()


def row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


@router.get("/")
def list_audit_entries(
    table_name: Optional[str] = None,
    action: Optional[str] = None,
    limit: Optional[int] = None,
):
    conn = get_conn()
    try:
        query = "SELECT * FROM audit_log WHERE 1=1"
        params = []
        if table_name:
            query += " AND table_name = ?"
            params.append(table_name)
        if action:
            query += " AND action = ?"
            params.append(action)
        query += " ORDER BY id DESC"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        cur = conn.execute(query, params)
        return [row_to_dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


@router.get("/record/{table_name}/{record_id}")
def get_record_audit(table_name: str, record_id: int):
    conn = get_conn()
    try:
        cur = conn.execute(
            "SELECT * FROM audit_log WHERE table_name = ? AND record_id = ? ORDER BY id DESC",
            (table_name, record_id),
        )
        return [row_to_dict(r) for r in cur.fetchall()]
    finally:
        conn.close()
