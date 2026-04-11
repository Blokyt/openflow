"""Tiers (Contacts) API module for OpenFlow."""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

# Project root is 3 levels up from this file: backend/modules/tiers/api.py
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "openflow.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


class ContactCreate(BaseModel):
    name: str
    type: str = "other"
    email: str = ""
    phone: str = ""
    address: str = ""
    notes: str = ""


class ContactUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None


@router.get("/")
def list_contacts(
    type: Optional[str] = None,
    search: Optional[str] = None,
):
    conn = get_conn()
    try:
        query = "SELECT * FROM contacts WHERE 1=1"
        params = []
        if type:
            query += " AND type = ?"
            params.append(type)
        if search:
            query += " AND (name LIKE ? OR email LIKE ? OR phone LIKE ?)"
            params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
        query += " ORDER BY name ASC, id ASC"
        cur = conn.execute(query, params)
        return [row_to_dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


@router.post("/", status_code=201)
def create_contact(contact: ContactCreate):
    now = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    try:
        cur = conn.execute(
            """INSERT INTO contacts
               (name, type, email, phone, address, notes, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                contact.name,
                contact.type,
                contact.email,
                contact.phone,
                contact.address,
                contact.notes,
                now,
                now,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM contacts WHERE id = ?", (cur.lastrowid,)).fetchone()
        return row_to_dict(row)
    finally:
        conn.close()


@router.get("/{contact_id}/transactions")
def get_contact_transactions(contact_id: int):
    conn = get_conn()
    try:
        existing = conn.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail=f"Contact {contact_id} not found")
        cur = conn.execute(
            "SELECT * FROM transactions WHERE contact_id = ? ORDER BY date DESC, id DESC",
            (contact_id,),
        )
        return [row_to_dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


@router.get("/{contact_id}")
def get_contact(contact_id: int):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Contact {contact_id} not found")
        return row_to_dict(row)
    finally:
        conn.close()


@router.put("/{contact_id}")
def update_contact(contact_id: int, contact: ContactUpdate):
    now = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    try:
        existing = conn.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail=f"Contact {contact_id} not found")

        updates = contact.model_dump(exclude_unset=True)
        if not updates:
            return row_to_dict(existing)

        set_clauses = ", ".join(f"{k} = ?" for k in updates)
        set_clauses += ", updated_at = ?"
        values = list(updates.values()) + [now, contact_id]

        conn.execute(
            f"UPDATE contacts SET {set_clauses} WHERE id = ?",
            values,
        )
        conn.commit()
        row = conn.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()
        return row_to_dict(row)
    finally:
        conn.close()


@router.delete("/{contact_id}")
def delete_contact(contact_id: int):
    conn = get_conn()
    try:
        existing = conn.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail=f"Contact {contact_id} not found")
        conn.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))
        conn.commit()
        return {"deleted": contact_id}
    finally:
        conn.close()
