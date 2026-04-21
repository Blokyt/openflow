"""Dashboard API module for OpenFlow."""
import json
import sqlite3
from pathlib import Path
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from backend.core.balance import compute_consolidated_balance, compute_entity_balance, compute_legacy_balance
from backend.core.database import get_conn, row_to_dict

router = APIRouter()

# Project root is 3 levels up from this file: backend/modules/dashboard/api.py
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
CONFIG_PATH = PROJECT_ROOT / "config.yaml"
MODULES_DIR = PROJECT_ROOT / "backend" / "modules"




class WidgetLayout(BaseModel):
    widget_id: str
    module_id: str
    position_x: int = 0
    position_y: int = 0
    size: str = "half"
    visible: bool = True


@router.get("/widgets")
def get_available_widgets():
    """Scan all module manifests and collect dashboard_widgets."""
    widgets = []
    if not MODULES_DIR.exists():
        return widgets
    for mod_dir in sorted(MODULES_DIR.iterdir()):
        manifest_path = mod_dir / "manifest.json"
        if not mod_dir.is_dir() or not manifest_path.exists():
            continue
        try:
            with open(manifest_path, encoding="utf-8") as f:
                manifest = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        module_id = manifest.get("id", mod_dir.name)
        for widget in manifest.get("dashboard_widgets", []):
            widgets.append({**widget, "module_id": module_id})
    return widgets


@router.get("/layout")
def get_layout():
    """Read widget layout from _dashboard system table."""
    conn = get_conn()
    try:
        cur = conn.execute(
            "SELECT id, widget_id, module_id, visible, position FROM _dashboard ORDER BY position ASC"
        )
        rows = cur.fetchall()
        result = []
        for row in rows:
            d = row_to_dict(row)
            # Expand stored position into position_x/position_y for API consumers
            d["position_x"] = d.get("position", 0)
            d["position_y"] = 0
            d["size"] = "half"
            d["visible"] = bool(d.get("visible", 1))
            result.append(d)
        return result
    finally:
        conn.close()


@router.put("/layout")
def save_layout(layout: list[WidgetLayout]):
    """Save widget positions — delete all existing, re-insert."""
    conn = get_conn()
    try:
        conn.execute("DELETE FROM _dashboard")
        for idx, item in enumerate(layout):
            # Store position_x as position; position_y and size are not in the schema
            conn.execute(
                """INSERT INTO _dashboard (widget_id, module_id, visible, position)
                   VALUES (?, ?, ?, ?)""",
                (item.widget_id, item.module_id, 1 if item.visible else 0, item.position_x),
            )
        conn.commit()
        return {"saved": len(layout)}
    finally:
        conn.close()


@router.get("/summary")
def get_summary(entity_id: Optional[int] = None):
    """Compute financial summary from config reference + transactions.

    If entity_id is provided, scope the balance and aggregates to that entity.
    """
    conn = get_conn()
    try:
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='transactions'")
        if cur.fetchone() is None:
            return {"balance": 0.0, "total_income": 0.0, "total_expenses": 0.0, "transaction_count": 0}

        if entity_id is not None:
            bal = compute_entity_balance(conn, entity_id)
            total_income = conn.execute(
                """SELECT COALESCE(SUM(amount), 0) FROM transactions
                   WHERE amount > 0 AND (from_entity_id = ? OR to_entity_id = ?)""",
                (entity_id, entity_id),
            ).fetchone()[0]
            total_expenses = abs(conn.execute(
                """SELECT COALESCE(SUM(amount), 0) FROM transactions
                   WHERE amount < 0 AND (from_entity_id = ? OR to_entity_id = ?)""",
                (entity_id, entity_id),
            ).fetchone()[0])
            transaction_count = conn.execute(
                "SELECT COUNT(*) FROM transactions WHERE from_entity_id = ? OR to_entity_id = ?",
                (entity_id, entity_id),
            ).fetchone()[0]
            balance = bal["balance"]
        else:
            # "Toutes les entités" = consolidated balance of root entity
            root = conn.execute(
                "SELECT id FROM entities WHERE is_default = 1 AND parent_id IS NULL"
            ).fetchone()
            if root:
                consolidated = compute_consolidated_balance(conn, root["id"])
                balance = consolidated["consolidated_balance"]
            else:
                bal = compute_legacy_balance(conn, str(CONFIG_PATH))
                balance = bal["balance"]
            total_income = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE amount > 0"
            ).fetchone()[0]
            total_expenses = abs(conn.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE amount < 0"
            ).fetchone()[0])
            transaction_count = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]

        return {
            "balance": balance,
            "total_income": total_income,
            "total_expenses": total_expenses,
            "transaction_count": transaction_count,
        }
    finally:
        conn.close()


@router.get("/timeseries")
def get_timeseries(entity_id: Optional[int] = None, months: int = 12):
    """Return monthly balance evolution: list of {month: 'YYYY-MM', balance: float}.

    We compute the current balance, then walk backwards in time to reconstruct
    balance at the end of each past month. This avoids any reference-amount
    accounting ambiguity for consolidated views.
    """
    conn = get_conn()
    try:
        # Current balance
        if entity_id is not None:
            current_balance = compute_entity_balance(conn, entity_id)["balance"]
            net_rows = conn.execute(
                """SELECT substr(date,1,7) AS month,
                          SUM(CASE WHEN to_entity_id = ? THEN amount
                                   WHEN from_entity_id = ? THEN -amount
                                   ELSE 0 END) AS net
                   FROM transactions
                   WHERE from_entity_id = ? OR to_entity_id = ?
                   GROUP BY month ORDER BY month""",
                (entity_id, entity_id, entity_id, entity_id),
            ).fetchall()
        else:
            root = conn.execute(
                "SELECT id FROM entities WHERE is_default = 1 AND parent_id IS NULL"
            ).fetchone()
            if root:
                current_balance = compute_consolidated_balance(conn, root["id"])["consolidated_balance"]
            else:
                current_balance = compute_legacy_balance(conn, str(CONFIG_PATH))["balance"]
            net_rows = conn.execute(
                """SELECT substr(date,1,7) AS month, SUM(amount) AS net
                   FROM transactions GROUP BY month ORDER BY month"""
            ).fetchall()

        nets = [(r["month"], r["net"] or 0.0) for r in net_rows]
        # Build cumulative-at-end-of-month series by forward sum, anchored so
        # that the last month equals current_balance.
        forward = []
        running = 0.0
        for m, n in nets:
            running += n
            forward.append((m, running))
        offset = current_balance - (forward[-1][1] if forward else 0.0)
        series = [{"month": m, "balance": round(v + offset, 2)} for m, v in forward]
        return series[-months:]
    finally:
        conn.close()


@router.get("/top-categories")
def top_categories(entity_id: Optional[int] = None, limit: int = 5):
    """Top categories by expense magnitude."""
    conn = get_conn()
    try:
        if entity_id is not None:
            rows = conn.execute(
                """SELECT c.name AS name, c.color AS color, SUM(ABS(t.amount)) AS total
                   FROM transactions t
                   LEFT JOIN categories c ON t.category_id = c.id
                   WHERE t.amount < 0 AND (t.from_entity_id = ? OR t.to_entity_id = ?)
                   GROUP BY t.category_id ORDER BY total DESC LIMIT ?""",
                (entity_id, entity_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT c.name AS name, c.color AS color, SUM(ABS(t.amount)) AS total
                   FROM transactions t
                   LEFT JOIN categories c ON t.category_id = c.id
                   WHERE t.amount < 0
                   GROUP BY t.category_id ORDER BY total DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [{"name": r["name"] or "— Sans catégorie —", "color": r["color"] or "#6B7280", "total": r["total"]} for r in rows]
    finally:
        conn.close()


@router.get("/recent")
def recent_transactions(entity_id: Optional[int] = None, limit: int = 5):
    """Return the N most recent transactions with entity names."""
    conn = get_conn()
    try:
        query = """SELECT t.id, t.date, t.label, t.amount,
                          ef.name AS from_entity_name, et.name AS to_entity_name,
                          c.name AS category_name, c.color AS category_color
                   FROM transactions t
                   LEFT JOIN entities ef ON t.from_entity_id = ef.id
                   LEFT JOIN entities et ON t.to_entity_id = et.id
                   LEFT JOIN categories c ON t.category_id = c.id"""
        params: list = []
        if entity_id is not None:
            query += " WHERE t.from_entity_id = ? OR t.to_entity_id = ?"
            params += [entity_id, entity_id]
        query += " ORDER BY t.date DESC, t.id DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        return [row_to_dict(r) for r in rows]
    finally:
        conn.close()
