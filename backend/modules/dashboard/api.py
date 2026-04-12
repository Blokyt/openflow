"""Dashboard API module for OpenFlow."""
import json
import sqlite3
from pathlib import Path
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from backend.core.balance import compute_legacy_balance
from backend.core.database import get_conn

router = APIRouter()

# Project root is 3 levels up from this file: backend/modules/dashboard/api.py
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
CONFIG_PATH = PROJECT_ROOT / "config.yaml"
MODULES_DIR = PROJECT_ROOT / "backend" / "modules"


def row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


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
def get_summary():
    """Compute financial summary from config reference + transactions."""
    conn = get_conn()
    try:
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='transactions'")
        if cur.fetchone() is None:
            return {"balance": 0.0, "total_income": 0.0, "total_expenses": 0.0, "transaction_count": 0}

        bal = compute_legacy_balance(conn, str(CONFIG_PATH))

        total_income = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE amount > 0"
        ).fetchone()[0]
        total_expenses = abs(conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE amount < 0"
        ).fetchone()[0])
        transaction_count = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]

        return {
            "balance": bal["balance"],
            "total_income": total_income,
            "total_expenses": total_expenses,
            "transaction_count": transaction_count,
        }
    finally:
        conn.close()
