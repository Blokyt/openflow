"""Categories CRUD API."""

import sqlite3

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional

from backend.core.auth import get_allowed_entity_ids, get_current_user, require_entity_access
from backend.core.balance import get_subtree_ids
from backend.core.database import get_conn, row_to_dict

router = APIRouter()



class CategoryIn(BaseModel):
    name: str
    parent_id: Optional[int] = None
    color: Optional[str] = "#6B7280"
    icon: Optional[str] = "tag"
    position: Optional[int] = 0


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    parent_id: Optional[int] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    position: Optional[int] = None


@router.get("/")
def list_categories():
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM categories ORDER BY position, id").fetchall()
        return [row_to_dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/tree")
def get_tree(
    request: Request,
    entity_id: Optional[int] = None,
    include_children: bool = False,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    """Arbre des catégories avec statistiques d'usage.

    Les stats (nb de transactions, total) peuvent être bornées au focus global :
    entité (± sous-entités) et période d'exercice — mêmes conventions que le
    reste de l'app, pour que la page Catégories raconte la même histoire.

    Non-admin : entity_id obligatoire (les stats globales toutes entités sont
    réservées à l'admin) et vérifié contre le périmètre du rôle.
    """
    user = get_current_user(request)
    conn = get_conn()
    try:
        allowed = get_allowed_entity_ids(conn, user)
        if allowed is not None:
            if entity_id is None:
                raise HTTPException(status_code=403, detail="Action réservée à l'administrateur")
            require_entity_access(conn, user, entity_id)
        rows = conn.execute("SELECT * FROM categories ORDER BY position, id").fetchall()
        nodes = {r["id"]: {**row_to_dict(r), "children": [], "tx_count": 0, "tx_total": 0.0} for r in rows}

        # Aggregate transaction counts and totals per category
        conds = ["category_id IS NOT NULL"]
        params: list = []
        if entity_id is not None:
            if include_children:
                scope = get_subtree_ids(conn, entity_id)
            else:
                scope = [entity_id]
            ph = ",".join("?" * len(scope))
            conds.append(f"(from_entity_id IN ({ph}) OR to_entity_id IN ({ph}))")
            params.extend(scope)
            params.extend(scope)
        if date_from:
            conds.append("date >= ?")
            params.append(date_from)
        if date_to:
            conds.append("date <= ?")
            params.append(date_to)
        tx_rows = conn.execute(
            "SELECT category_id, COUNT(*) AS cnt, SUM(amount) AS total "
            f"FROM transactions WHERE {' AND '.join(conds)} GROUP BY category_id",
            params,
        ).fetchall()
        for tx_row in tx_rows:
            cat_id = tx_row["category_id"]
            if cat_id in nodes:
                nodes[cat_id]["tx_count"] = tx_row["cnt"]
                nodes[cat_id]["tx_total"] = float(tx_row["total"] or 0.0)

        roots = []
        for node in nodes.values():
            parent_id = node["parent_id"]
            if parent_id is None or parent_id not in nodes:
                roots.append(node)
            else:
                nodes[parent_id]["children"].append(node)

        # Recursively compute descendant aggregates
        def _compute_descendants(node):
            desc_count = node["tx_count"]
            desc_total = node["tx_total"]
            for child in node["children"]:
                _compute_descendants(child)
                desc_count += child["descendant_tx_count"]
                desc_total += child["descendant_tx_total"]
            node["descendant_tx_count"] = desc_count
            node["descendant_tx_total"] = desc_total

        for root in roots:
            _compute_descendants(root)

        return roots
    finally:
        conn.close()


@router.post("/", status_code=201)
def create_category(data: CategoryIn):
    conn = get_conn()
    try:
        # Note : un parent_id inexistant est toléré (la catégorie apparaît à la
        # racine dans get_tree). On ne valide donc pas son existence ici.
        cur = conn.execute(
            "INSERT INTO categories (name, parent_id, color, icon, position) VALUES (?, ?, ?, ?, ?)",
            (data.name, data.parent_id, data.color, data.icon, data.position),
        )
        new_id = cur.lastrowid
        row = conn.execute("SELECT * FROM categories WHERE id = ?", (new_id,)).fetchone()
        new_data = row_to_dict(row)
        conn.commit()
        return new_data
    finally:
        conn.close()


@router.get("/{cat_id}")
def get_category(cat_id: int):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM categories WHERE id = ?", (cat_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Category not found")
        return row_to_dict(row)
    finally:
        conn.close()


@router.get("/{cat_id}/usage")
def get_category_usage(cat_id: int):
    """Impact d'une éventuelle suppression : comptes utilisés par la cascade de delete_category.

    Même approche que la cascade elle-même : les tables des modules optionnels
    (budget_allocations, report_accruals) sont enveloppées dans un try/except
    car ces modules peuvent être désactivés.
    """
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM categories WHERE id = ?", (cat_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Category not found")

        transactions = conn.execute(
            "SELECT COUNT(*) FROM transactions WHERE category_id = ?", (cat_id,)
        ).fetchone()[0]
        children = conn.execute(
            "SELECT COUNT(*) FROM categories WHERE parent_id = ?", (cat_id,)
        ).fetchone()[0]

        allocations = 0
        try:
            allocations = conn.execute(
                "SELECT COUNT(*) FROM budget_allocations WHERE category_id = ?", (cat_id,)
            ).fetchone()[0]
        except sqlite3.OperationalError:
            pass

        accruals = 0
        try:
            accruals = conn.execute(
                "SELECT COUNT(*) FROM report_accruals WHERE category_id = ?", (cat_id,)
            ).fetchone()[0]
        except sqlite3.OperationalError:
            pass

        return {
            "transactions": transactions,
            "allocations": allocations,
            "children": children,
            "accruals": accruals,
        }
    finally:
        conn.close()


@router.put("/{cat_id}")
def update_category(cat_id: int, data: CategoryUpdate):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM categories WHERE id = ?", (cat_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Category not found")
        current = row_to_dict(row)
        name = data.name if data.name is not None else current["name"]
        parent_id = data.parent_id if data.parent_id is not None else current["parent_id"]
        # Détection de cycle quand on (re)définit le parent (un parent_id
        # inexistant reste toléré : la catégorie sera traitée comme racine).
        if data.parent_id is not None:
            if data.parent_id == cat_id:
                raise HTTPException(400, "Une catégorie ne peut pas être son propre parent")
            ancestor, seen = data.parent_id, set()
            while ancestor is not None and ancestor not in seen:
                if ancestor == cat_id:
                    raise HTTPException(400, "Cycle détecté dans la hiérarchie des catégories")
                seen.add(ancestor)
                r = conn.execute("SELECT parent_id FROM categories WHERE id = ?", (ancestor,)).fetchone()
                ancestor = r["parent_id"] if r else None
        color = data.color if data.color is not None else current["color"]
        icon = data.icon if data.icon is not None else current["icon"]
        position = data.position if data.position is not None else current["position"]
        conn.execute(
            "UPDATE categories SET name=?, parent_id=?, color=?, icon=?, position=? WHERE id=?",
            (name, parent_id, color, icon, position, cat_id),
        )
        updated = conn.execute("SELECT * FROM categories WHERE id = ?", (cat_id,)).fetchone()
        new_data = row_to_dict(updated)
        conn.commit()
        return new_data
    finally:
        conn.close()


@router.delete("/{cat_id}")
def delete_category(cat_id: int):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM categories WHERE id = ?", (cat_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Category not found")
        # Cascade manuelle (PRAGMA foreign_keys OFF) pour éviter les références
        # orphelines : enfants rattachés à la racine, transactions dé-catégorisées,
        # lignes des modules optionnels nettoyées (ignorées si le module est absent).
        conn.execute("UPDATE categories SET parent_id = NULL WHERE parent_id = ?", (cat_id,))
        conn.execute("UPDATE transactions SET category_id = NULL WHERE category_id = ?", (cat_id,))
        for stmt in (
            "DELETE FROM budget_allocations WHERE category_id = ?",
            "DELETE FROM category_account_map WHERE category_id = ?",
            "UPDATE report_accruals SET category_id = NULL WHERE category_id = ?",
        ):
            try:
                conn.execute(stmt, (cat_id,))
            except sqlite3.OperationalError:
                pass
        conn.execute("DELETE FROM categories WHERE id = ?", (cat_id,))
        conn.commit()
        return {"deleted": cat_id}
    finally:
        conn.close()
