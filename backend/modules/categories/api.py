"""Categories CRUD API."""

import sqlite3

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

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
def get_tree():
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM categories ORDER BY position, id").fetchall()
        nodes = {r["id"]: {**row_to_dict(r), "children": [], "tx_count": 0, "tx_total": 0.0} for r in rows}

        # Aggregate transaction counts and totals per category
        tx_rows = conn.execute(
            "SELECT category_id, COUNT(*) AS cnt, SUM(amount) AS total "
            "FROM transactions WHERE category_id IS NOT NULL GROUP BY category_id"
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
