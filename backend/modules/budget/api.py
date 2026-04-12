"""Budget Previsionnel API module for OpenFlow."""
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core.database import get_conn

router = APIRouter()


def row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


class BudgetCreate(BaseModel):
    category_id: Optional[int] = None
    division_id: Optional[int] = None
    entity_id: Optional[int] = None
    period_start: str
    period_end: str
    amount: float
    label: str = ""


class BudgetUpdate(BaseModel):
    category_id: Optional[int] = None
    division_id: Optional[int] = None
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    amount: Optional[float] = None
    label: Optional[str] = None


@router.get("/")
def list_budgets(period: Optional[str] = None):
    """List all budgets. Optional ?period=2026 filter matches budgets whose range overlaps the year."""
    conn = get_conn()
    try:
        query = "SELECT * FROM budgets WHERE 1=1"
        params = []
        if period:
            # Filter budgets that overlap the given year
            year_start = f"{period}-01-01"
            year_end = f"{period}-12-31"
            query += " AND period_start <= ? AND period_end >= ?"
            params.extend([year_end, year_start])
        query += " ORDER BY period_start, id"
        cur = conn.execute(query, params)
        return [row_to_dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


@router.post("/", status_code=201)
def create_budget(budget: BudgetCreate):
    now = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    try:
        cur = conn.execute(
            """INSERT INTO budgets
               (category_id, division_id, entity_id, period_start, period_end, amount, label, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                budget.category_id,
                budget.division_id,
                budget.entity_id,
                budget.period_start,
                budget.period_end,
                budget.amount,
                budget.label,
                now,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM budgets WHERE id = ?", (cur.lastrowid,)).fetchone()
        return row_to_dict(row)
    finally:
        conn.close()


# IMPORTANT: /status must be declared BEFORE /{budget_id} to avoid FastAPI
# treating "status" as a budget_id path parameter.
@router.get("/status")
def get_status():
    """For each budget, compute budgeted amount, spent amount and remaining."""
    conn = get_conn()
    try:
        budgets = conn.execute("SELECT * FROM budgets ORDER BY period_start, id").fetchall()
        result = []
        for b in budgets:
            b_dict = row_to_dict(b)
            entity_id = b_dict.get("entity_id")
            # Sum transactions matching category_id within the budget date range
            if b["category_id"] is not None:
                if entity_id is not None:
                    cur = conn.execute(
                        """SELECT COALESCE(SUM(amount), 0) FROM transactions
                           WHERE category_id = ?
                             AND date >= ?
                             AND date <= ?
                             AND (from_entity_id = ? OR to_entity_id = ?)""",
                        (b["category_id"], b["period_start"], b["period_end"], entity_id, entity_id),
                    )
                else:
                    cur = conn.execute(
                        """SELECT COALESCE(SUM(amount), 0) FROM transactions
                           WHERE category_id = ?
                             AND date >= ?
                             AND date <= ?""",
                        (b["category_id"], b["period_start"], b["period_end"]),
                    )
            else:
                if entity_id is not None:
                    # No category filter, but entity filter: sum entity transactions in the period
                    cur = conn.execute(
                        """SELECT COALESCE(SUM(amount), 0) FROM transactions
                           WHERE date >= ? AND date <= ?
                             AND (from_entity_id = ? OR to_entity_id = ?)""",
                        (b["period_start"], b["period_end"], entity_id, entity_id),
                    )
                else:
                    # No category filter: sum all transactions in the period
                    cur = conn.execute(
                        """SELECT COALESCE(SUM(amount), 0) FROM transactions
                           WHERE date >= ? AND date <= ?""",
                        (b["period_start"], b["period_end"]),
                    )
            spent = cur.fetchone()[0]
            b_dict["budgeted"] = b["amount"]
            b_dict["spent"] = spent
            b_dict["remaining"] = b["amount"] - abs(spent)
            result.append(b_dict)
        return result
    finally:
        conn.close()


@router.get("/{budget_id}")
def get_budget(budget_id: int):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM budgets WHERE id = ?", (budget_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Budget {budget_id} not found")
        return row_to_dict(row)
    finally:
        conn.close()


@router.put("/{budget_id}")
def update_budget(budget_id: int, budget: BudgetUpdate):
    conn = get_conn()
    try:
        existing = conn.execute("SELECT * FROM budgets WHERE id = ?", (budget_id,)).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail=f"Budget {budget_id} not found")

        updates = budget.model_dump(exclude_unset=True)
        if not updates:
            return row_to_dict(existing)

        set_clauses = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [budget_id]

        conn.execute(
            f"UPDATE budgets SET {set_clauses} WHERE id = ?",
            values,
        )
        conn.commit()
        row = conn.execute("SELECT * FROM budgets WHERE id = ?", (budget_id,)).fetchone()
        return row_to_dict(row)
    finally:
        conn.close()


@router.delete("/{budget_id}")
def delete_budget(budget_id: int):
    conn = get_conn()
    try:
        existing = conn.execute("SELECT * FROM budgets WHERE id = ?", (budget_id,)).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail=f"Budget {budget_id} not found")
        conn.execute("DELETE FROM budgets WHERE id = ?", (budget_id,))
        conn.commit()
        return {"deleted": budget_id}
    finally:
        conn.close()
