"""Dashboard API module for OpenFlow."""
import json
import sqlite3
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from backend.core.auth import get_allowed_entity_ids, get_current_user, require_entity_access
from backend.core.balance import (
    compute_consolidated_balance,
    compute_entity_balance,
    compute_legacy_balance,
    get_subtree_ids,
)
from backend.core.database import get_conn, row_to_dict

try:
    # Source de vérité du solde courant. Import protégé : le dashboard doit
    # rester fonctionnel si le module Trésorerie est désinstallé.
    from backend.modules.treasury.service import treasury_total_cents
except Exception:  # pragma: no cover - module Trésorerie absent
    treasury_total_cents = None

router = APIRouter()


def _root_entity_id(conn) -> Optional[int]:
    row = conn.execute(
        "SELECT id FROM entities WHERE is_default = 1 AND parent_id IS NULL"
    ).fetchone()
    return row["id"] if row else None


def _treasury_anchor(conn, entity_id: Optional[int], include_children: bool):
    """Total Trésorerie quand le périmètre couvre toute l'asso, sinon None.

    Le solde courant de l'asso entière est ancré sur la Trésorerie (poches),
    seule source de vérité, et non sur un solde de référence d'entité. Un
    périmètre limité à un club (pas de poches propres) reste sur le calcul
    compta par référence. Renvoie None si la Trésorerie n'est pas configurée.
    """
    if treasury_total_cents is None:
        return None
    root_id = _root_entity_id(conn)
    whole_asso = entity_id is None or (
        root_id is not None and entity_id == root_id and include_children
    )
    if not whole_asso:
        return None
    return treasury_total_cents(conn)

# Message constant pour la garde « entité obligatoire pour un non-admin »,
# partagée par tous les endpoints de vue financière (dashboard et reports).
ENTITY_REQUIRED_MESSAGE = "Une entité est requise pour ce rôle"


def _require_scope(conn, user: dict, entity_id):
    """Non-admin : entity_id obligatoire (400 si absent) + dans le périmètre (403 sinon).
    Admin (`allowed is None`) : inchangé, aucune contrainte."""
    allowed = get_allowed_entity_ids(conn, user)
    if allowed is None:
        return
    if entity_id is None:
        raise HTTPException(status_code=400, detail=ENTITY_REQUIRED_MESSAGE)
    require_entity_access(conn, user, entity_id)

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


def _scope_ids(conn, entity_id: int, include_children: bool) -> list:
    """Périmètre d'entités du focus : l'entité seule, ou son sous-arbre interne.

    Avec un périmètre à une seule entité, la logique « frontière » (flux qui
    entrent/sortent du périmètre) est strictement équivalente à l'ancienne
    logique par entité (from/to = entité), puisque from != to est garanti.
    """
    if include_children:
        return get_subtree_ids(conn, entity_id)
    return [entity_id]


def _frontier_case_sql(scope: list) -> tuple:
    """Expression CASE signée pour le flux net du périmètre + params.

    +amount quand l'argent entre dans le périmètre depuis l'extérieur,
    -amount quand il en sort. Les mouvements internes au périmètre valent 0.
    """
    ph = ",".join("?" * len(scope))
    sql = f"""CASE
        WHEN to_entity_id IN ({ph})
         AND (from_entity_id IS NULL OR from_entity_id NOT IN ({ph}))
        THEN amount
        WHEN from_entity_id IN ({ph})
         AND (to_entity_id IS NULL OR to_entity_id NOT IN ({ph}))
        THEN -amount
        ELSE 0
    END"""
    return sql, list(scope) * 4


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
    request: Request,
    entity_id: Optional[int] = None,
    include_children: bool = False,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    """Compute financial summary from config reference + transactions.

    If entity_id is provided, scope the aggregates to that entity ; with
    include_children=true the scope is the whole subtree (solde consolidé,
    flux traversant la frontière du sous-arbre — les virements internes au
    périmètre sont neutres).
    If date_from/date_to are provided (e.g. an exercise period), the recettes,
    dépenses and transaction count are bounded to that period. The headline
    `balance` always stays the real current balance ("solde actuel"), which is
    a point-in-time figure independent of the selected exercise.
    """
    user = get_current_user(request)
    conn = get_conn()
    try:
        _require_scope(conn, user, entity_id)
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='transactions'")
        if cur.fetchone() is None:
            return {
                "balance": 0.0, "total_income": 0.0, "total_expenses": 0.0, "transaction_count": 0,
                "reference_date": None, "reference_amount": None,
            }

        if entity_id is not None:
            # Référence de l'entité elle-même : même sémantique qu'en mode
            # 'aggregate' (compute_consolidated_balance y lit la référence de
            # entity_id, jamais celle d'un descendant), donc on l'utilise aussi
            # pour le solde consolidé en mode 'own' (qui n'expose pas de
            # référence unique agrégée sur le sous-arbre).
            own = compute_entity_balance(conn, entity_id)
            reference_date = own.get("reference_date")
            reference_amount = own.get("reference_amount")
            if include_children:
                balance = compute_consolidated_balance(conn, entity_id)["consolidated_balance"]
            else:
                balance = own["balance"]
            scope = _scope_ids(conn, entity_id, include_children)
            ph = ",".join("?" * len(scope))
            conds, pp = _period_conds(date_from, date_to)
            income_where = " AND ".join([
                f"to_entity_id IN ({ph})",
                f"(from_entity_id IS NULL OR from_entity_id NOT IN ({ph}))",
            ] + conds)
            expense_where = " AND ".join([
                f"from_entity_id IN ({ph})",
                f"(to_entity_id IS NULL OR to_entity_id NOT IN ({ph}))",
            ] + conds)
            count_where = " AND ".join([
                f"(from_entity_id IN ({ph}) OR to_entity_id IN ({ph}))",
            ] + conds)
            total_income = conn.execute(
                f"SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE {income_where}",
                (*scope, *scope, *pp),
            ).fetchone()[0]
            total_expenses = conn.execute(
                f"SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE {expense_where}",
                (*scope, *scope, *pp),
            ).fetchone()[0]
            transaction_count = conn.execute(
                f"SELECT COUNT(*) FROM transactions WHERE {count_where}",
                (*scope, *scope, *pp),
            ).fetchone()[0]
        else:
            # "Toutes les entités" = consolidated balance of root entity
            root = conn.execute(
                "SELECT id FROM entities WHERE is_default = 1 AND parent_id IS NULL"
            ).fetchone()
            if root:
                consolidated = compute_consolidated_balance(conn, root["id"])
                balance = consolidated["consolidated_balance"]
                # Référence de la racine elle-même (cf. remarque ci-dessus sur
                # le mode 'own' : pas de référence unique agrégée sur le sous-arbre).
                root_ref = compute_entity_balance(conn, root["id"])
                reference_date = root_ref.get("reference_date")
                reference_amount = root_ref.get("reference_amount")
            else:
                bal = compute_legacy_balance(conn, str(CONFIG_PATH))
                balance = bal["balance"]
                reference_date = bal.get("reference_date")
                reference_amount = bal.get("reference_amount")
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

        # Ancrage sur la Trésorerie pour l'asso entière : le solde courant suit
        # le total des poches et la référence d'entité disparaît de l'affichage.
        anchor = _treasury_anchor(conn, entity_id, include_children)
        balance_source = "reference"
        if anchor is not None:
            balance = anchor
            reference_date = None
            reference_amount = None
            balance_source = "treasury"

        return {
            "balance": balance,
            "total_income": total_income,
            "total_expenses": total_expenses,
            "transaction_count": transaction_count,
            "reference_date": reference_date,
            "reference_amount": reference_amount,
            "balance_source": balance_source,
        }
    finally:
        conn.close()


@router.get("/timeseries")
def get_timeseries(
    request: Request,
    entity_id: Optional[int] = None,
    months: int = 12,
    include_children: bool = False,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    """Return monthly balance evolution: list of {month: 'YYYY-MM', balance: float}.

    We compute the current balance, then walk backwards in time to reconstruct
    balance at the end of each past month. This avoids any reference-amount
    accounting ambiguity for consolidated views.

    Sans bornes, la vue est glissante : les `months` derniers mois ancrés sur
    le solde courant. Avec date_from/date_to (exercice sélectionné), la série
    est découpée sur cette fenêtre — chaque point reste le solde de fin de
    mois historique, donc la fenêtre d'un exercice passé est exacte.
    """
    user = get_current_user(request)
    conn = get_conn()
    try:
        _require_scope(conn, user, entity_id)
        # Current balance
        if entity_id is not None:
            if include_children:
                current_balance = compute_consolidated_balance(conn, entity_id)["consolidated_balance"]
            else:
                current_balance = compute_entity_balance(conn, entity_id)["balance"]
            # Flux net mensuel du périmètre (frontière du sous-arbre : les
            # virements internes au périmètre sont neutres). Même convention
            # de signe que compute_entity_balance.
            scope = _scope_ids(conn, entity_id, include_children)
            case_sql, case_params = _frontier_case_sql(scope)
            ph = ",".join("?" * len(scope))
            net_rows = conn.execute(
                f"""SELECT substr(date,1,7) AS month,
                          COALESCE(SUM({case_sql}), 0) AS net
                   FROM transactions
                   WHERE from_entity_id IN ({ph}) OR to_entity_id IN ({ph})
                   GROUP BY month ORDER BY month""",
                (*case_params, *scope, *scope),
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

        # Même ancrage que /summary : pour l'asso entière, la série se cale sur le
        # total Trésorerie courant (le dernier point = ce total), les variations
        # mensuelles restant reconstituées depuis les flux compta.
        anchor = _treasury_anchor(conn, entity_id, include_children)
        if anchor is not None:
            current_balance = anchor

        nets_by_month = {r["month"]: int(r["net"] or 0) for r in net_rows}
        # Generer la liste continue de tous les mois calendaires, du premier mois
        # avec activite jusqu'au mois courant, pour ne pas laisser de trous (un
        # mois sans transaction = solde stable, pas un point manquant).
        today = date.today()
        if nets_by_month:
            first = min(nets_by_month)
            # Si une fenêtre explicite commence avant la première activité,
            # on matérialise aussi ces mois-là (solde stable à la référence).
            if date_from and date_from[:7] < first:
                first = date_from[:7]
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
        # Fenêtre d'exercice explicite : on découpe la série historique (chaque
        # point est un solde de fin de mois exact) au lieu du glissement N mois.
        if date_from or date_to:
            lo = date_from[:7] if date_from else "0000-00"
            hi = date_to[:7] if date_to else "9999-99"
            return [p for p in series if lo <= p["month"] <= hi]
        return series[-months:]
    finally:
        conn.close()


@router.get("/top-categories")
def top_categories(
    request: Request,
    entity_id: Optional[int] = None,
    include_children: bool = False,
    limit: int = 5,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    """Top categories by expense magnitude, optionally bounded to an exercise.

    Avec include_children, seules les dépenses qui SORTENT du sous-arbre
    comptent : un virement interne au périmètre n'est pas une dépense du groupe.
    """
    user = get_current_user(request)
    conn = get_conn()
    try:
        _require_scope(conn, user, entity_id)
        conds, pp = _period_conds(date_from, date_to, "t.date")
        if entity_id is not None:
            scope = _scope_ids(conn, entity_id, include_children)
            ph = ",".join("?" * len(scope))
            where = " AND ".join([
                f"t.from_entity_id IN ({ph})",
                f"(t.to_entity_id IS NULL OR t.to_entity_id NOT IN ({ph}))",
            ] + conds)
            rows = conn.execute(
                f"""SELECT t.category_id AS category_id, c.name AS name, c.color AS color, SUM(t.amount) AS total
                   FROM transactions t
                   LEFT JOIN categories c ON t.category_id = c.id
                   WHERE {where}
                   GROUP BY t.category_id ORDER BY total DESC LIMIT ?""",
                (*scope, *scope, *pp, limit),
            ).fetchall()
        else:
            base = "t.from_entity_id IN (SELECT id FROM entities WHERE type='internal')"
            where = " AND ".join([base] + conds)
            rows = conn.execute(
                f"""SELECT t.category_id AS category_id, c.name AS name, c.color AS color, SUM(t.amount) AS total
                   FROM transactions t
                   LEFT JOIN categories c ON t.category_id = c.id
                   WHERE {where}
                   GROUP BY t.category_id ORDER BY total DESC LIMIT ?""",
                (*pp, limit),
            ).fetchall()
        return [
            {
                "category_id": r["category_id"],
                "name": r["name"] or "— Sans catégorie —",
                "color": r["color"] or "#6B7280",
                "total": r["total"],
            }
            for r in rows
        ]
    finally:
        conn.close()


@router.get("/recent")
def recent_transactions(
    request: Request,
    entity_id: Optional[int] = None,
    include_children: bool = False,
    limit: int = 5,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    """Return the N most recent transactions, optionally bounded to an exercise."""
    user = get_current_user(request)
    conn = get_conn()
    try:
        _require_scope(conn, user, entity_id)
        query = """SELECT t.id, t.date, t.label, t.amount,
                          ef.name AS from_entity_name, et.name AS to_entity_name,
                          ef.type AS from_entity_type, et.type AS to_entity_type,
                          c.name AS category_name, c.color AS category_color
                   FROM transactions t
                   LEFT JOIN entities ef ON t.from_entity_id = ef.id
                   LEFT JOIN entities et ON t.to_entity_id = et.id
                   LEFT JOIN categories c ON t.category_id = c.id"""
        conds, params = [], []
        if entity_id is not None:
            scope = _scope_ids(conn, entity_id, include_children)
            ph = ",".join("?" * len(scope))
            conds.append(f"(t.from_entity_id IN ({ph}) OR t.to_entity_id IN ({ph}))")
            params += list(scope) + list(scope)
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
