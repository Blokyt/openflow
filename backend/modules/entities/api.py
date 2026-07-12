"""Entities API module for OpenFlow."""
import sqlite3
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from backend.core.auth import get_allowed_entity_ids, get_current_user, require_entity_access
from backend.core.database import get_conn, row_to_dict
from backend.core.balance import compute_entity_balance, compute_consolidated_balance

router = APIRouter()

VALID_TYPES = {"internal", "external"}


def _validate_internal_parent(conn, parent_id: int):
    """Vérifie qu'un parent existe et qu'il est de type 'internal'."""
    parent = conn.execute("SELECT type FROM entities WHERE id = ?", (parent_id,)).fetchone()
    if not parent:
        raise HTTPException(404, f"Parent entity {parent_id} not found")
    if parent["type"] != "internal":
        raise HTTPException(400, "Parent must be an internal entity")


class EntityCreate(BaseModel):
    name: str
    description: str = ""
    type: str = "internal"
    parent_id: Optional[int] = None
    is_divers: int = 0
    color: str = "#6B7280"
    position: int = 0
    balance_mode: Optional[Literal["own", "aggregate"]] = "own"


class EntityUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None
    position: Optional[int] = None
    parent_id: Optional[int] = None
    balance_mode: Optional[Literal["own", "aggregate"]] = None


class BalanceRefUpdate(BaseModel):
    reference_date: Optional[str] = None  # null accepté (date de référence effacée côté UI)
    reference_amount: int  # centimes entiers (cohérent avec le stockage et les calculs de solde)


# --- CRUD ---

@router.get("/")
def list_entities(request: Request, type: Optional[str] = None):
    user = get_current_user(request)
    conn = get_conn()
    try:
        query = "SELECT * FROM entities WHERE 1=1"
        params = []
        if type:
            query += " AND type = ?"
            params.append(type)
        allowed = get_allowed_entity_ids(conn, user)
        if allowed is not None:
            # Périmètre du rôle + toutes les entités externes (contreparties
            # nécessaires à l'affichage, jamais rattachées à un sous-arbre interne).
            if allowed:
                placeholders = ",".join("?" * len(allowed))
                query += f" AND (id IN ({placeholders}) OR type = 'external')"
                params.extend(list(allowed))
            else:
                query += " AND type = 'external'"
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
            _validate_internal_parent(conn, entity.parent_id)

        # Only root entities (parent_id IS NULL) can use 'aggregate' mode
        balance_mode = entity.balance_mode or "own"
        if balance_mode == "aggregate" and entity.parent_id is not None:
            raise HTTPException(400, "Only root entities (parent_id = null) can use balance_mode='aggregate'")

        now = datetime.now(timezone.utc).isoformat()
        cur = conn.execute(
            """INSERT INTO entities (name, description, type, parent_id, is_divers, color, position, balance_mode, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (entity.name, entity.description, entity.type, entity.parent_id,
             entity.is_divers, entity.color, entity.position, balance_mode, now, now),
        )
        new_id = cur.lastrowid
        row = conn.execute("SELECT * FROM entities WHERE id = ?", (new_id,)).fetchone()
        new_data = row_to_dict(row)
        conn.commit()
        return new_data
    finally:
        conn.close()


@router.get("/tree")
def get_tree(request: Request):
    """Return hierarchical tree of internal entities."""
    user = get_current_user(request)
    conn = get_conn()
    try:
        allowed = get_allowed_entity_ids(conn, user)
        query = "SELECT * FROM entities WHERE type = 'internal'"
        params = []
        if allowed is not None:
            if not allowed:
                return []
            placeholders = ",".join("?" * len(allowed))
            query += f" AND id IN ({placeholders})"
            params.extend(list(allowed))
        query += " ORDER BY position ASC, id ASC"
        rows = conn.execute(query, params).fetchall()
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
def get_entity(entity_id: int, request: Request):
    user = get_current_user(request)
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM entities WHERE id = ?", (entity_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Entity not found")
        allowed = get_allowed_entity_ids(conn, user)
        # Les entités externes restent visibles (contreparties), même hors périmètre.
        if allowed is not None and row["type"] != "external" and entity_id not in allowed:
            raise HTTPException(403, "Accès refusé à cette entité")
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

        old_data = row_to_dict(existing)
        # exclude_unset distingue « champ non fourni » de « fourni à null ».
        provided = update.model_dump(exclude_unset=True)
        fields = {}
        for field in ["name", "description", "color", "position", "parent_id", "balance_mode"]:
            if field not in provided:
                continue
            val = provided[field]
            # parent_id peut être explicitement null (détacher l'entité vers la
            # racine) ; les autres champs ignorent null pour ne pas écraser.
            if val is None and field != "parent_id":
                continue
            fields[field] = val

        if not fields:
            return row_to_dict(existing)

        # Validate balance_mode: only root entities can use 'aggregate'
        if "balance_mode" in fields and fields["balance_mode"] == "aggregate":
            parent_id = fields.get("parent_id", existing["parent_id"])
            if parent_id is not None:
                raise HTTPException(400, "Only root entities (parent_id = null) can use balance_mode='aggregate'")

        if "parent_id" in fields:
            new_parent = fields["parent_id"]
            if new_parent == entity_id:
                raise HTTPException(400, "Entity cannot be its own parent")
            # parent_id explicitement null = détacher vers la racine, toujours
            # autorisé sans validation. Sinon, le nouveau parent doit exister
            # et être 'internal' (même contrainte qu'à la création).
            if new_parent is not None:
                _validate_internal_parent(conn, new_parent)
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
        row = conn.execute("SELECT * FROM entities WHERE id = ?", (entity_id,)).fetchone()
        new_data = row_to_dict(row)
        conn.commit()
        return new_data
    finally:
        conn.close()


@router.delete("/{entity_id}")
def delete_entity(entity_id: int):
    conn = get_conn()
    try:
        existing = conn.execute("SELECT * FROM entities WHERE id = ?", (entity_id,)).fetchone()
        if not existing:
            raise HTTPException(404, "Entity not found")

        old_data = row_to_dict(existing)

        # L'entité par défaut porte la vue globale du dashboard : la supprimer
        # changerait silencieusement le calcul de solde. Refus explicite.
        if old_data.get("is_default"):
            raise HTTPException(400, "Impossible de supprimer l'entité par défaut.")

        # Reject if has children
        children = conn.execute("SELECT id FROM entities WHERE parent_id = ?", (entity_id,)).fetchone()
        if children:
            raise HTTPException(400, "Impossible de supprimer une entité qui a des sous-entités. Supprimez d'abord les sous-entités.")

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
        # Rôles utilisateurs visant cette entité : sinon rôle fantôme persistant.
        conn.execute("DELETE FROM user_entity_roles WHERE entity_id = ?", (entity_id,))
        # Cascade vers les modules optionnels (PRAGMA foreign_keys OFF). Ignorée si le
        # module est désactivé (tables inexistantes -> pas de 500). report_accruals
        # est DÉTACHÉ (entity_id NULL), pas supprimé, comme delete_category : sinon
        # une créance/dette disparaîtrait silencieusement du bilan.
        for stmt in (
            "DELETE FROM fiscal_year_opening_balances WHERE entity_id = ?",
            "DELETE FROM budget_allocations WHERE entity_id = ?",
            "UPDATE report_accruals SET entity_id = NULL WHERE entity_id = ?",
        ):
            try:
                conn.execute(stmt, (entity_id,))
            except sqlite3.OperationalError:
                pass
        conn.execute("DELETE FROM entities WHERE id = ?", (entity_id,))
        conn.commit()
        return {"deleted": entity_id}
    finally:
        conn.close()


# --- Balance ---

@router.get("/{entity_id}/balance")
def get_entity_balance(entity_id: int, request: Request, as_of_date: Optional[str] = None):
    user = get_current_user(request)
    conn = get_conn()
    try:
        require_entity_access(conn, user, entity_id)
        entity = conn.execute("SELECT * FROM entities WHERE id = ? AND type = 'internal'", (entity_id,)).fetchone()
        if not entity:
            raise HTTPException(404, "Internal entity not found")
        return compute_entity_balance(conn, entity_id, as_of_date)
    finally:
        conn.close()


@router.get("/{entity_id}/consolidated")
def get_consolidated_balance(entity_id: int, request: Request, as_of_date: Optional[str] = None):
    user = get_current_user(request)
    conn = get_conn()
    try:
        require_entity_access(conn, user, entity_id)
        entity = conn.execute("SELECT * FROM entities WHERE id = ? AND type = 'internal'", (entity_id,)).fetchone()
        if not entity:
            raise HTTPException(404, "Internal entity not found")
        return compute_consolidated_balance(conn, entity_id, as_of_date)
    finally:
        conn.close()


@router.get("/{entity_id}/balance-ref")
def get_balance_ref(entity_id: int, request: Request):
    user = get_current_user(request)
    conn = get_conn()
    try:
        require_entity_access(conn, user, entity_id)
        row = conn.execute("SELECT * FROM entity_balance_refs WHERE entity_id = ?", (entity_id,)).fetchone()
        if not row:
            return {"entity_id": entity_id, "reference_date": None, "reference_amount": 0}
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
        row = conn.execute("SELECT * FROM entity_balance_refs WHERE entity_id = ?", (entity_id,)).fetchone()
        new_data = row_to_dict(row)
        conn.commit()
        return new_data
    finally:
        conn.close()
