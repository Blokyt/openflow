"""Categories CRUD API."""
import sqlite3
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

DB_PATH = Path(__file__).parent.parent.parent.parent / "data" / "openflow.db"


def get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def row_to_dict(row):
    return dict(row) if row else None


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
        nodes = {r["id"]: {**row_to_dict(r), "children": []} for r in rows}
        roots = []
        for node in nodes.values():
            parent_id = node["parent_id"]
            if parent_id is None or parent_id not in nodes:
                roots.append(node)
            else:
                nodes[parent_id]["children"].append(node)
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
        conn.commit()
        row = conn.execute("SELECT * FROM categories WHERE id = ?", (cur.lastrowid,)).fetchone()
        return row_to_dict(row)
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
        color = data.color if data.color is not None else current["color"]
        icon = data.icon if data.icon is not None else current["icon"]
        position = data.position if data.position is not None else current["position"]
        conn.execute(
            "UPDATE categories SET name=?, parent_id=?, color=?, icon=?, position=? WHERE id=?",
            (name, parent_id, color, icon, position, cat_id),
        )
        conn.commit()
        updated = conn.execute("SELECT * FROM categories WHERE id = ?", (cat_id,)).fetchone()
        return row_to_dict(updated)
    finally:
        conn.close()


@router.delete("/{cat_id}")
def delete_category(cat_id: int):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM categories WHERE id = ?", (cat_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Category not found")
        conn.execute("DELETE FROM categories WHERE id = ?", (cat_id,))
        conn.commit()
        return {"deleted": cat_id}
    finally:
        conn.close()
