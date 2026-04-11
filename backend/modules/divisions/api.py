"""Divisions CRUD API."""
import sqlite3
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

DB_PATH = Path(__file__).parent.parent.parent.parent / "data" / "openflow.db"


def get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def row_to_dict(row):
    return dict(row) if row else None


class DivisionIn(BaseModel):
    name: str
    description: Optional[str] = ""
    color: Optional[str] = "#6B7280"
    position: Optional[int] = 0


class DivisionUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None
    position: Optional[int] = None


@router.get("/")
def list_divisions():
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM divisions ORDER BY position, id").fetchall()
        return [row_to_dict(r) for r in rows]
    finally:
        conn.close()


@router.post("/", status_code=201)
def create_division(data: DivisionIn):
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO divisions (name, description, color, position) VALUES (?, ?, ?, ?)",
            (data.name, data.description, data.color, data.position),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM divisions WHERE id = ?", (cur.lastrowid,)).fetchone()
        return row_to_dict(row)
    finally:
        conn.close()


@router.get("/{division_id}")
def get_division(division_id: int):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM divisions WHERE id = ?", (division_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Division not found")
        return row_to_dict(row)
    finally:
        conn.close()


@router.put("/{division_id}")
def update_division(division_id: int, data: DivisionUpdate):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM divisions WHERE id = ?", (division_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Division not found")
        current = row_to_dict(row)
        name = data.name if data.name is not None else current["name"]
        description = data.description if data.description is not None else current["description"]
        color = data.color if data.color is not None else current["color"]
        position = data.position if data.position is not None else current["position"]
        conn.execute(
            "UPDATE divisions SET name=?, description=?, color=?, position=? WHERE id=?",
            (name, description, color, position, division_id),
        )
        conn.commit()
        updated = conn.execute("SELECT * FROM divisions WHERE id = ?", (division_id,)).fetchone()
        return row_to_dict(updated)
    finally:
        conn.close()


@router.delete("/{division_id}")
def delete_division(division_id: int):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM divisions WHERE id = ?", (division_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Division not found")
        conn.execute("DELETE FROM divisions WHERE id = ?", (division_id,))
        conn.commit()
        return {"deleted": division_id}
    finally:
        conn.close()


@router.get("/{division_id}/summary")
def get_division_summary(division_id: int):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM divisions WHERE id = ?", (division_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Division not found")
        result = conn.execute(
            """
            SELECT
                COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) AS income,
                COALESCE(SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END), 0) AS expenses,
                COALESCE(SUM(amount), 0) AS balance
            FROM transactions
            WHERE division_id = ?
            """,
            (division_id,),
        ).fetchone()
        return {
            "division_id": division_id,
            "income": result["income"],
            "expenses": result["expenses"],
            "balance": result["balance"],
        }
    finally:
        conn.close()
