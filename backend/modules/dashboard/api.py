"""Dashboard API module for OpenFlow."""
import json
import sqlite3
from datetime import date
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


def _period_conds(date_from: Optional[str], date_to: Optional[str], col: str = "date"):
    """Build SQL conditions + params bounding `col` to [date_from, date_to].

    Returns (conds, params) where conds is a list of "col >= ?"/"col <= ?"
    snippets to AND together. Empty when no bounds are given, so callers stay
    period-agnostic when no exercise is selected.
    """
    conds: list[str] = []
    params: list = []
    if date_from:
        conds.append(f"{col} >= ?")
        params.append(date_from)
    if date_to:
        conds.append(f"{col} <= ?")
        params.append(date_to)
    return conds, params


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
def get_summary(
    entity_id: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    """Compute financial summary from config reference + transactions.

    If entity_id is provided, scope the aggregates to that entity.
    If date_from/date_to are provided (e.g. an exercise period), the recettes,
    dépenses and transaction count are bounded to that period. The headline
    `balance` always stays the real current balance ("solde actuel"), which is
    a point-in-time figure independent of the selected exercise.
    """
    conn = get_conn()
    try:
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='transactions'")
        if cur.fetchone() is None:
            return {"balance": 0.0, "total_income": 0.0, "total_expenses": 0.0, "transaction_count": 0}

        if entity_id is not None:
            bal = compute_entity_balance(conn, entity_id)
            conds, pp = _period_conds(date_from, date_to)
            income_where = " AND ".join(["to_entity_id = ?"] + conds)
            expense_where = " AND ".join(["from_entity_id = ?"] + conds)
            count_where = " AND ".join(["(from_entity_id = ? OR to_entity_id = ?)"] + conds)
            total_income = conn.execute(
                f"SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE {income_where}",
                (entity_id, *pp),
            ).fetchone()[0]
            total_expenses = conn.execute(
                f"SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE {expense_where}",
                (entity_id, *pp),
            ).fetchone()[0]
            transaction_count = conn.execute(
                f"SELECT COUNT(*) FROM transactions WHERE {count_where}",
                (entity_id, entity_id, *pp),
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
            conds, pp = _period_conds(date_from, date_to, "t.date")
            period_and = ("" if not conds else " AND " + " AND ".join(conds))
            # Recettes globales : flux vers une entité interne venant d'une externe
            total_income = conn.execute(
                f"""SELECT COALESCE(SUM(t.amount), 0) FROM transactions t
                   WHERE t.to_entity_id   IN (SELECT id FROM entities WHERE type='internal')
                     AND (t.from_entity_id IS NULL OR t.from_entity_id NOT IN (SELECT id FROM entities WHERE type='internal'))
                     {period_and}""",
                tuple(pp),
            ).fetchone()[0]
            # Dépenses globales : flux depuis une entité interne vers une externe
            total_expenses = conn.execute(
                f"""SELECT COALESCE(SUM(t.amount), 0) FROM transactions t
                   WHERE t.from_entity_id IN (SELECT id FROM entities WHERE type='internal')
                     AND (t.to_entity_id IS NULL OR t.to_entity_id NOT IN (SELECT id FROM entities WHERE type='internal'))
                     {period_and}""",
                tuple(pp),
            ).fetchone()[0]
            count_conds, cpp = _period_conds(date_from, date_to)
            count_sql = "SELECT COUNT(*) FROM transactions" + (
                " WHERE " + " AND ".join(count_conds) if count_conds else ""
            )
            transaction_count = conn.execute(count_sql, tuple(cpp)).fetchone()[0]

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

    This widget is a trailing "evolution du solde" view anchored on the real
    current balance; it is intentionally NOT bounded to the selected exercise
    (anchoring a past exercise's last month to today's balance would be wrong).
    """
    conn = get_conn()
    try:
        # Current balance
        if entity_id is not None:
            current_balance = compute_entity_balance(conn, entity_id)["balance"]
            # Net flow for the entity = incoming - outgoing (same convention as
            # compute_entity_balance). Incoming = amount when the entity is the
            # destination. Outgoing = amount (already negative) when the entity
            # is the source on an expense. Matches the signed-amount convention
            # used by the transactions API.
            net_rows = conn.execute(
                """SELECT substr(date,1,7) AS month,
                          COALESCE(SUM(CASE
                              WHEN to_entity_id = ? THEN amount
                              WHEN from_entity_id = ? THEN -amount
                              ELSE 0
                          END), 0) AS net
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
                """SELECT substr(date,1,7) AS month,
                          COALESCE(SUM(CASE
                              WHEN t.to_entity_id   IN (SELECT id FROM entities WHERE type='internal')
                               AND (t.from_entity_id IS NULL OR t.from_entity_id NOT IN (SELECT id FROM entities WHERE type='internal'))
                              THEN t.amount
                              WHEN t.from_entity_id IN (SELECT id FROM entities WHERE type='internal')
                               AND (t.to_entity_id IS NULL OR t.to_entity_id NOT IN (SELECT id FROM entities WHERE type='internal'))
                              THEN -t.amount
                              ELSE 0
                          END), 0) AS net
                   FROM transactions t
                   GROUP BY month ORDER BY month"""
            ).fetchall()

        nets_by_month = {r["month"]: int(r["net"] or 0) for r in net_rows}
        # Generer la liste continue de tous les mois calendaires, du premier mois
        # avec activite jusqu'au mois courant, pour ne pas laisser de trous (un
        # mois sans transaction = solde stable, pas un point manquant).
        today = date.today()
        if nets_by_month:
            first = min(nets_by_month)
            y, m = int(first[:4]), int(first[5:7])
        else:
            y, m = today.year, today.month
        all_months = []
        while (y, m) <= (today.year, today.month):
            all_months.append(f"{y:04d}-{m:02d}")
            m += 1
            if m > 12:
                m, y = 1, y + 1
        # Somme cumulative ancree pour que le dernier mois = solde courant.
        running = 0
        forward = []
        for mth in all_months:
            running += nets_by_month.get(mth, 0)
            forward.append((mth, running))
        # forward contient toujours au moins le mois courant (boucle while ci-dessus).
        offset = current_balance - forward[-1][1]
        series = [{"month": mth, "balance": int(round(v + offset))} for mth, v in forward]
        return series[-months:]
    finally:
        conn.close()


@router.get("/top-categories")
def top_categories(
    entity_id: Optional[int] = None,
    limit: int = 5,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    """Top categories by expense magnitude, optionally bounded to an exercise."""
    conn = get_conn()
    try:
        conds, pp = _period_conds(date_from, date_to, "t.date")
        if entity_id is not None:
            where = " AND ".join(["t.from_entity_id = ?"] + conds)
            rows = conn.execute(
                f"""SELECT c.name AS name, c.color AS color, SUM(t.amount) AS total
                   FROM transactions t
                   LEFT JOIN categories c ON t.category_id = c.id
                   WHERE {where}
                   GROUP BY t.category_id ORDER BY total DESC LIMIT ?""",
                (entity_id, *pp, limit),
            ).fetchall()
        else:
            base = "t.from_entity_id IN (SELECT id FROM entities WHERE type='internal')"
            where = " AND ".join([base] + conds)
            rows = conn.execute(
                f"""SELECT c.name AS name, c.color AS color, SUM(t.amount) AS total
                   FROM transactions t
                   LEFT JOIN categories c ON t.category_id = c.id
                   WHERE {where}
                   GROUP BY t.category_id ORDER BY total DESC LIMIT ?""",
                (*pp, limit),
            ).fetchall()
        return [{"name": r["name"] or "— Sans catégorie —", "color": r["color"] or "#6B7280", "total": r["total"]} for r in rows]
    finally:
        conn.close()


@router.get("/recent")
def recent_transactions(
    entity_id: Optional[int] = None,
    limit: int = 5,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    """Return the N most recent transactions, optionally bounded to an exercise."""
    conn = get_conn()
    try:
        query = """SELECT t.id, t.date, t.label, t.amount,
                          ef.name AS from_entity_name, et.name AS to_entity_name,
                          c.name AS category_name, c.color AS category_color
                   FROM transactions t
                   LEFT JOIN entities ef ON t.from_entity_id = ef.id
                   LEFT JOIN entities et ON t.to_entity_id = et.id
                   LEFT JOIN categories c ON t.category_id = c.id"""
        conds, params = [], []
        if entity_id is not None:
            conds.append("(t.from_entity_id = ? OR t.to_entity_id = ?)")
            params += [entity_id, entity_id]
        period_conds, pp = _period_conds(date_from, date_to, "t.date")
        conds += period_conds
        params += pp
        if conds:
            query += " WHERE " + " AND ".join(conds)
        query += " ORDER BY t.date DESC, t.id DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        return [row_to_dict(r) for r in rows]
    finally:
        conn.close()
