"""Annotations API module for OpenFlow."""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

# Project root is 3 levels up from this file: backend/modules/annotations/api.py
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "openflow.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


class AnnotationCreate(BaseModel):
    content: str


class AnnotationUpdate(BaseModel):
    content: Optional[str] = None


@router.get("/transaction/{tx_id}")
def list_annotations(tx_id: int):
    conn = get_conn()
    try:
        # Verify transaction exists
        tx = conn.execute("SELECT id FROM transactions WHERE id = ?", (tx_id,)).fetchone()
        if tx is None:
            raise HTTPException(status_code=404, detail=f"Transaction {tx_id} not found")
        cur = conn.execute(
            "SELECT * FROM annotations WHERE transaction_id = ? ORDER BY created_at ASC",
            (tx_id,),
        )
        return [row_to_dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


@router.post("/transaction/{tx_id}", status_code=201)
def create_annotation(tx_id: int, annotation: AnnotationCreate):
    now = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    try:
        # Verify transaction exists
        tx = conn.execute("SELECT id FROM transactions WHERE id = ?", (tx_id,)).fetchone()
        if tx is None:
            raise HTTPException(status_code=404, detail=f"Transaction {tx_id} not found")
        cur = conn.execute(
            "INSERT INTO annotations (transaction_id, content, created_at) VALUES (?, ?, ?)",
            (tx_id, annotation.content, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM annotations WHERE id = ?", (cur.lastrowid,)).fetchone()
        return row_to_dict(row)
    finally:
        conn.close()


@router.put("/{id}")
def update_annotation(id: int, annotation: AnnotationUpdate):
    conn = get_conn()
    try:
        existing = conn.execute("SELECT * FROM annotations WHERE id = ?", (id,)).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail=f"Annotation {id} not found")

        updates = annotation.model_dump(exclude_unset=True)
        if not updates:
            return row_to_dict(existing)

        set_clauses = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [id]

        conn.execute(
            f"UPDATE annotations SET {set_clauses} WHERE id = ?",
            values,
        )
        conn.commit()
        row = conn.execute("SELECT * FROM annotations WHERE id = ?", (id,)).fetchone()
        return row_to_dict(row)
    finally:
        conn.close()


@router.delete("/{id}")
def delete_annotation(id: int):
    conn = get_conn()
    try:
        existing = conn.execute("SELECT * FROM annotations WHERE id = ?", (id,)).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail=f"Annotation {id} not found")
        conn.execute("DELETE FROM annotations WHERE id = ?", (id,))
        conn.commit()
        return {"deleted": id}
    finally:
        conn.close()
