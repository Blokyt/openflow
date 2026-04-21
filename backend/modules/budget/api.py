"""Budget & Exercices API module for OpenFlow."""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core.database import get_conn, row_to_dict

router = APIRouter()


# ─── Pydantic models ─────────────────────────────────────────────────────────

class FiscalYearCreate(BaseModel):
    name: str
    start_date: str
    end_date: str
    is_current: bool = False
    notes: str = ""


class FiscalYearUpdate(BaseModel):
    name: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    is_current: Optional[bool] = None
    notes: Optional[str] = None


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _set_single_current(conn, fiscal_year_id: int) -> None:
    """Atomically flip is_current so only the given year is marked current."""
    conn.execute("UPDATE fiscal_years SET is_current = 0 WHERE id != ?", (fiscal_year_id,))
    conn.execute("UPDATE fiscal_years SET is_current = 1 WHERE id = ?", (fiscal_year_id,))


# ─── Fiscal years CRUD ──────────────────────────────────────────────────────

@router.get("/fiscal-years")
def list_fiscal_years():
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM fiscal_years ORDER BY start_date DESC"
        ).fetchall()
        return [row_to_dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/fiscal-years/current")
def get_current_fiscal_year():
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM fiscal_years WHERE is_current = 1 LIMIT 1"
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Aucun exercice marqué actif")
        return row_to_dict(row)
    finally:
        conn.close()


@router.post("/fiscal-years", status_code=201)
def create_fiscal_year(body: FiscalYearCreate):
    if body.start_date >= body.end_date:
        raise HTTPException(400, "start_date doit être antérieur à end_date")
    now = _now()
    conn = get_conn()
    try:
        dup = conn.execute("SELECT id FROM fiscal_years WHERE name = ?", (body.name,)).fetchone()
        if dup is not None:
            raise HTTPException(409, f"Un exercice nommé '{body.name}' existe déjà")
        cur = conn.execute(
            """INSERT INTO fiscal_years
               (name, start_date, end_date, is_current, notes, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (body.name, body.start_date, body.end_date,
             1 if body.is_current else 0, body.notes, now, now),
        )
        fy_id = cur.lastrowid
        if body.is_current:
            _set_single_current(conn, fy_id)
        conn.commit()
        row = conn.execute("SELECT * FROM fiscal_years WHERE id = ?", (fy_id,)).fetchone()
        return row_to_dict(row)
    finally:
        conn.close()


@router.put("/fiscal-years/{fy_id}")
def update_fiscal_year(fy_id: int, body: FiscalYearUpdate):
    now = _now()
    conn = get_conn()
    try:
        existing = conn.execute("SELECT * FROM fiscal_years WHERE id = ?", (fy_id,)).fetchone()
        if existing is None:
            raise HTTPException(404, f"Exercice {fy_id} introuvable")

        updates = body.model_dump(exclude_unset=True)
        if not updates:
            return row_to_dict(existing)

        new_start = updates.get("start_date", existing["start_date"])
        new_end = updates.get("end_date", existing["end_date"])
        if new_start >= new_end:
            raise HTTPException(400, "start_date doit être antérieur à end_date")

        if "is_current" in updates:
            updates["is_current"] = 1 if updates["is_current"] else 0

        set_clause = ", ".join(f"{k} = ?" for k in updates) + ", updated_at = ?"
        values = list(updates.values()) + [now, fy_id]
        conn.execute(f"UPDATE fiscal_years SET {set_clause} WHERE id = ?", values)
        if updates.get("is_current") == 1:
            _set_single_current(conn, fy_id)
        conn.commit()
        row = conn.execute("SELECT * FROM fiscal_years WHERE id = ?", (fy_id,)).fetchone()
        return row_to_dict(row)
    finally:
        conn.close()


@router.delete("/fiscal-years/{fy_id}")
def delete_fiscal_year(fy_id: int):
    conn = get_conn()
    try:
        existing = conn.execute("SELECT * FROM fiscal_years WHERE id = ?", (fy_id,)).fetchone()
        if existing is None:
            raise HTTPException(404, f"Exercice {fy_id} introuvable")
        # Applicative cascade (PRAGMA foreign_keys OFF in this project)
        conn.execute("DELETE FROM budget_allocations WHERE fiscal_year_id = ?", (fy_id,))
        conn.execute("DELETE FROM fiscal_year_opening_balances WHERE fiscal_year_id = ?", (fy_id,))
        conn.execute("DELETE FROM fiscal_years WHERE id = ?", (fy_id,))
        conn.commit()
        return {"deleted": fy_id}
    finally:
        conn.close()
