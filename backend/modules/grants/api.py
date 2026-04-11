"""Grants API module for OpenFlow."""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

# Project root is 3 levels up from this file: backend/modules/grants/api.py
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "openflow.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


class GrantCreate(BaseModel):
    name: str
    grantor_contact_id: Optional[int] = None
    amount_granted: float
    amount_received: float = 0
    date_granted: str
    date_received: Optional[str] = None
    purpose: str = ""
    status: str = "pending"
    notes: str = ""


class GrantUpdate(BaseModel):
    name: Optional[str] = None
    grantor_contact_id: Optional[int] = None
    amount_granted: Optional[float] = None
    amount_received: Optional[float] = None
    date_granted: Optional[str] = None
    date_received: Optional[str] = None
    purpose: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None


@router.get("/")
def list_grants(status: Optional[str] = None):
    conn = get_conn()
    try:
        query = "SELECT * FROM grants WHERE 1=1"
        params = []
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY date_granted DESC, id DESC"
        cur = conn.execute(query, params)
        return [row_to_dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


@router.post("/", status_code=201)
def create_grant(grant: GrantCreate):
    now = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    try:
        cur = conn.execute(
            """INSERT INTO grants
               (name, grantor_contact_id, amount_granted, amount_received,
                date_granted, date_received, purpose, status, notes, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                grant.name,
                grant.grantor_contact_id,
                grant.amount_granted,
                grant.amount_received,
                grant.date_granted,
                grant.date_received,
                grant.purpose,
                grant.status,
                grant.notes,
                now,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM grants WHERE id = ?", (cur.lastrowid,)).fetchone()
        return row_to_dict(row)
    finally:
        conn.close()


@router.get("/summary")
def get_summary():
    """Return totals: total granted, total received, total pending."""
    conn = get_conn()
    try:
        cur = conn.execute(
            """SELECT
                COALESCE(SUM(amount_granted), 0) AS total_granted,
                COALESCE(SUM(amount_received), 0) AS total_received,
                COALESCE(SUM(amount_granted - amount_received), 0) AS total_pending
               FROM grants"""
        )
        row = cur.fetchone()
        return row_to_dict(row)
    finally:
        conn.close()


@router.get("/{grant_id}")
def get_grant(grant_id: int):
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM grants WHERE id = ?", (grant_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Grant {grant_id} not found")
        return row_to_dict(row)
    finally:
        conn.close()


@router.put("/{grant_id}")
def update_grant(grant_id: int, grant: GrantUpdate):
    conn = get_conn()
    try:
        existing = conn.execute(
            "SELECT * FROM grants WHERE id = ?", (grant_id,)
        ).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail=f"Grant {grant_id} not found")

        updates = grant.model_dump(exclude_unset=True)
        if not updates:
            return row_to_dict(existing)

        set_clauses = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [grant_id]

        conn.execute(
            f"UPDATE grants SET {set_clauses} WHERE id = ?",
            values,
        )
        conn.commit()
        row = conn.execute("SELECT * FROM grants WHERE id = ?", (grant_id,)).fetchone()
        return row_to_dict(row)
    finally:
        conn.close()


@router.delete("/{grant_id}")
def delete_grant(grant_id: int):
    conn = get_conn()
    try:
        existing = conn.execute(
            "SELECT * FROM grants WHERE id = ?", (grant_id,)
        ).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail=f"Grant {grant_id} not found")
        conn.execute("DELETE FROM grants WHERE id = ?", (grant_id,))
        conn.commit()
        return {"deleted": grant_id}
    finally:
        conn.close()
