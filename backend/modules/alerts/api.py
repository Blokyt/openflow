"""Alerts API module for OpenFlow."""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core.balance import compute_legacy_balance
from backend.core.database import get_conn

router = APIRouter()

# Project root is 3 levels up from this file: backend/modules/alerts/api.py
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
CONFIG_PATH = PROJECT_ROOT / "config.yaml"


def row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


class AlertRuleCreate(BaseModel):
    type: str
    label: str
    threshold: Optional[float] = None
    active: int = 1


class AlertRuleUpdate(BaseModel):
    type: Optional[str] = None
    label: Optional[str] = None
    threshold: Optional[float] = None
    active: Optional[int] = None


@router.get("/")
def list_alert_rules():
    """List all alert rules."""
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM alert_rules ORDER BY id").fetchall()
        return [row_to_dict(r) for r in rows]
    finally:
        conn.close()


@router.post("/", status_code=201)
def create_alert_rule(rule: AlertRuleCreate):
    """Create a new alert rule."""
    now = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    try:
        cur = conn.execute(
            """INSERT INTO alert_rules (type, label, threshold, active, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (rule.type, rule.label, rule.threshold, rule.active, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM alert_rules WHERE id = ?", (cur.lastrowid,)).fetchone()
        return row_to_dict(row)
    finally:
        conn.close()


def _compute_balance(conn: sqlite3.Connection) -> float:
    """Compute current balance: reference_amount + sum of transactions since reference_date."""
    return compute_legacy_balance(conn, str(CONFIG_PATH))["balance"]


# IMPORTANT: /check must be declared BEFORE /{rule_id} to avoid FastAPI
# treating "check" as a rule_id path parameter.
@router.get("/check")
def check_alerts():
    """Evaluate all active alert rules against current data and return triggered alerts."""
    conn = get_conn()
    try:
        rules = conn.execute(
            "SELECT * FROM alert_rules WHERE active = 1 ORDER BY id"
        ).fetchall()

        results = []
        for rule in rules:
            rule_dict = row_to_dict(rule)
            triggered = False
            current_value = None
            threshold = rule_dict.get("threshold")

            if rule_dict["type"] == "low_balance":
                current_value = _compute_balance(conn)
                if threshold is not None:
                    triggered = current_value < threshold

            elif rule_dict["type"] == "budget_exceeded":
                # threshold is a percentage (0-100); not implemented beyond structure
                current_value = None
                triggered = False

            else:
                # custom — no automatic evaluation
                current_value = None
                triggered = False

            results.append({
                "rule_id": rule_dict["id"],
                "rule_label": rule_dict["label"],
                "type": rule_dict["type"],
                "triggered": triggered,
                "current_value": current_value,
                "threshold": threshold,
            })

        return results
    finally:
        conn.close()


@router.get("/{rule_id}")
def get_alert_rule(rule_id: int):
    """Get a single alert rule by id."""
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM alert_rules WHERE id = ?", (rule_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Alert rule {rule_id} not found")
        return row_to_dict(row)
    finally:
        conn.close()


@router.put("/{rule_id}")
def update_alert_rule(rule_id: int, rule: AlertRuleUpdate):
    """Update an alert rule."""
    conn = get_conn()
    try:
        existing = conn.execute("SELECT * FROM alert_rules WHERE id = ?", (rule_id,)).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail=f"Alert rule {rule_id} not found")

        updates = rule.model_dump(exclude_unset=True)
        if not updates:
            return row_to_dict(existing)

        set_clauses = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [rule_id]

        conn.execute(
            f"UPDATE alert_rules SET {set_clauses} WHERE id = ?",
            values,
        )
        conn.commit()
        row = conn.execute("SELECT * FROM alert_rules WHERE id = ?", (rule_id,)).fetchone()
        return row_to_dict(row)
    finally:
        conn.close()


@router.delete("/{rule_id}")
def delete_alert_rule(rule_id: int):
    """Delete an alert rule."""
    conn = get_conn()
    try:
        existing = conn.execute("SELECT * FROM alert_rules WHERE id = ?", (rule_id,)).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail=f"Alert rule {rule_id} not found")
        conn.execute("DELETE FROM alert_rules WHERE id = ?", (rule_id,))
        conn.commit()
        return {"deleted": rule_id}
    finally:
        conn.close()
