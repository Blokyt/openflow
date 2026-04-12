"""Entities API module for OpenFlow."""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core.database import get_conn, row_to_dict
from backend.core.balance import compute_entity_balance, compute_consolidated_balance

router = APIRouter()

VALID_TYPES = {"internal", "external"}



class EntityCreate(BaseModel):
    name: str
    description: str = ""
    type: str = "internal"
    parent_id: Optional[int] = None
    is_divers: int = 0
    color: str = "#6B7280"
    position: int = 0


class EntityUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None
    position: Optional[int] = None
    parent_id: Optional[int] = None


class BalanceRefUpdate(BaseModel):
    reference_date: str
    reference_amount: float


# --- CRUD ---

@router.get("/")
def list_entities(type: Optional[str] = None):
    conn = get_conn()
    try:
        query = "SELECT * FROM entities WHERE 1=1"
        params = []
        if type:
            query += " AND type = ?"
            params.append(type)
        query += " ORDER BY position ASC, id ASC"
        return [row_to_dict(r) for r in conn.execute(query, params).fetchall()]
    finally:
        conn.close()


@router.post("/", status_code=201)
def create_entity(entity: EntityCreate):
    if entity.type not in VALID_TYPES:
        raise HTTPException(400, f"Invalid type '{entity.type}'. Must be: {sorted(VALID_TYPES)}")
    if entity.type == "external" and entity.parent_id is not None:
        raise HTTPException(400, "External entities cannot have a parent")

    conn = get_conn()
    try:
        # Enforce unique is_divers
        if entity.is_divers:
            existing = conn.execute("SELECT id FROM entities WHERE is_divers = 1").fetchone()
            if existing:
                raise HTTPException(400, "A 'divers' entity already exists")
            if entity.type != "external":
                raise HTTPException(400, "'divers' entity must be external")

        # Validate parent exists and is internal
        if entity.parent_id is not None:
            parent = conn.execute("SELECT type FROM entities WHERE id = ?", (entity.parent_id,)).fetchone()
            if not parent:
                raise HTTPException(404, f"Parent entity {entity.parent_id} not found")
            if parent["type"] != "internal":
                raise HTTPException(400, "Parent must be an internal entity")

        now = datetime.now(timezone.utc).isoformat()
        cur = conn.execute(
            """INSERT INTO entities (name, description, type, parent_id, is_divers, color, position, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (entity.name, entity.description, entity.type, entity.parent_id,
             entity.is_divers, entity.color, entity.position, now, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM entities WHERE id = ?", (cur.lastrowid,)).fetchone()
        return row_to_dict(row)
    finally:
        conn.close()


@router.get("/tree")
def get_tree():
    """Return hierarchical tree of internal entities."""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM entities WHERE type = 'internal' ORDER BY position ASC, id ASC"
        ).fetchall()
        entities = [row_to_dict(r) for r in rows]

        by_id = {e["id"]: {**e, "children": []} for e in entities}
        roots = []
        for e in entities:
            node = by_id[e["id"]]
            if e["parent_id"] and e["parent_id"] in by_id:
                by_id[e["parent_id"]]["children"].append(node)
            else:
                roots.append(node)
        return roots
    finally:
        conn.close()


@router.get("/{entity_id}")
def get_entity(entity_id: int):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM entities WHERE id = ?", (entity_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Entity not found")
        return row_to_dict(row)
    finally:
        conn.close()


@router.put("/{entity_id}")
def update_entity(entity_id: int, update: EntityUpdate):
    conn = get_conn()
    try:
        existing = conn.execute("SELECT * FROM entities WHERE id = ?", (entity_id,)).fetchone()
        if not existing:
            raise HTTPException(404, "Entity not found")

        fields = {}
        for field in ["name", "description", "color", "position", "parent_id"]:
            val = getattr(update, field, None)
            if val is not None:
                fields[field] = val

        if not fields:
            return row_to_dict(existing)

        if "parent_id" in fields:
            new_parent = fields["parent_id"]
            if new_parent == entity_id:
                raise HTTPException(400, "Entity cannot be its own parent")
            # Walk up from proposed parent to check for cycles
            current = new_parent
            while current:
                row = conn.execute("SELECT parent_id FROM entities WHERE id = ?", (current,)).fetchone()
                if not row:
                    break
                if row["parent_id"] == entity_id:
                    raise HTTPException(400, "Circular parent reference detected")
                current = row["parent_id"]

        fields["updated_at"] = datetime.now(timezone.utc).isoformat()
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        conn.execute(f"UPDATE entities SET {set_clause} WHERE id = ?", list(fields.values()) + [entity_id])
        conn.commit()
        row = conn.execute("SELECT * FROM entities WHERE id = ?", (entity_id,)).fetchone()
        return row_to_dict(row)
    finally:
        conn.close()


@router.delete("/{entity_id}")
def delete_entity(entity_id: int):
    conn = get_conn()
    try:
        existing = conn.execute("SELECT * FROM entities WHERE id = ?", (entity_id,)).fetchone()
        if not existing:
            raise HTTPException(404, "Entity not found")

        # Reject if has children
        children = conn.execute("SELECT id FROM entities WHERE parent_id = ?", (entity_id,)).fetchone()
        if children:
            raise HTTPException(400, "Cannot delete entity with children. Delete children first.")

        # Reject if has transactions (columns may not exist yet if Task 4 not applied)
        try:
            has_tx = conn.execute(
                "SELECT id FROM transactions WHERE from_entity_id = ? OR to_entity_id = ? LIMIT 1",
                (entity_id, entity_id),
            ).fetchone()
            if has_tx:
                raise HTTPException(400, "Cannot delete entity with transactions.")
        except HTTPException:
            raise
        except Exception:
            pass

        conn.execute("DELETE FROM entity_balance_refs WHERE entity_id = ?", (entity_id,))
        conn.execute("DELETE FROM user_entities WHERE entity_id = ?", (entity_id,))
        conn.execute("DELETE FROM entities WHERE id = ?", (entity_id,))
        conn.commit()
        return {"deleted": entity_id}
    finally:
        conn.close()


# --- Balance ---

@router.get("/{entity_id}/balance")
def get_entity_balance(entity_id: int, as_of_date: Optional[str] = None):
    conn = get_conn()
    try:
        entity = conn.execute("SELECT * FROM entities WHERE id = ? AND type = 'internal'", (entity_id,)).fetchone()
        if not entity:
            raise HTTPException(404, "Internal entity not found")
        return compute_entity_balance(conn, entity_id, as_of_date)
    finally:
        conn.close()


@router.get("/{entity_id}/consolidated")
def get_consolidated_balance(entity_id: int, as_of_date: Optional[str] = None):
    conn = get_conn()
    try:
        entity = conn.execute("SELECT * FROM entities WHERE id = ? AND type = 'internal'", (entity_id,)).fetchone()
        if not entity:
            raise HTTPException(404, "Internal entity not found")
        return compute_consolidated_balance(conn, entity_id, as_of_date)
    finally:
        conn.close()


@router.get("/{entity_id}/balance-ref")
def get_balance_ref(entity_id: int):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM entity_balance_refs WHERE entity_id = ?", (entity_id,)).fetchone()
        if not row:
            return {"entity_id": entity_id, "reference_date": None, "reference_amount": 0.0}
        return row_to_dict(row)
    finally:
        conn.close()


@router.put("/{entity_id}/balance-ref")
def update_balance_ref(entity_id: int, ref: BalanceRefUpdate):
    conn = get_conn()
    try:
        entity = conn.execute("SELECT id FROM entities WHERE id = ? AND type = 'internal'", (entity_id,)).fetchone()
        if not entity:
            raise HTTPException(404, "Internal entity not found")

        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """INSERT INTO entity_balance_refs (entity_id, reference_date, reference_amount, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(entity_id) DO UPDATE SET
                   reference_date = excluded.reference_date,
                   reference_amount = excluded.reference_amount,
                   updated_at = excluded.updated_at""",
            (entity_id, ref.reference_date, ref.reference_amount, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM entity_balance_refs WHERE entity_id = ?", (entity_id,)).fetchone()
        return row_to_dict(row)
    finally:
        conn.close()
