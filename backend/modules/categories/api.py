"""Categories CRUD API."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from backend.core.database import get_conn, row_to_dict
from backend.core.audit import record_audit

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
            "SELECT category_id, COUNT(*) AS cnt, SUM(ABS(amount)) AS total "
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
        cur = conn.execute(
            "INSERT INTO categories (name, parent_id, color, icon, position) VALUES (?, ?, ?, ?, ?)",
            (data.name, data.parent_id, data.color, data.icon, data.position),
        )
        new_id = cur.lastrowid
        row = conn.execute("SELECT * FROM categories WHERE id = ?", (new_id,)).fetchone()
        new_data = row_to_dict(row)
        record_audit(conn, "CREATE", "categories", new_id, old_value=None, new_value=new_data)
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
        old_data = dict(current)
        name = data.name if data.name is not None else current["name"]
        parent_id = data.parent_id if data.parent_id is not None else current["parent_id"]
        color = data.color if data.color is not None else current["color"]
        icon = data.icon if data.icon is not None else current["icon"]
        position = data.position if data.position is not None else current["position"]
        conn.execute(
            "UPDATE categories SET name=?, parent_id=?, color=?, icon=?, position=? WHERE id=?",
            (name, parent_id, color, icon, position, cat_id),
        )
        updated = conn.execute("SELECT * FROM categories WHERE id = ?", (cat_id,)).fetchone()
        new_data = row_to_dict(updated)
        record_audit(conn, "UPDATE", "categories", cat_id, old_value=old_data, new_value=new_data)
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
        old_data = row_to_dict(row)
        conn.execute("DELETE FROM categories WHERE id = ?", (cat_id,))
        record_audit(conn, "DELETE", "categories", cat_id, old_value=old_data)
        conn.commit()
        return {"deleted": cat_id}
    finally:
        conn.close()
