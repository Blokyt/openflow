"""Tiers (Contacts) API module for OpenFlow."""
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from backend.core.auth import get_allowed_entity_ids, get_current_user
from backend.core.database import get_conn, row_to_dict

router = APIRouter()


def _require_name(raw: str) -> str:
    """Valide et normalise le nom d'un contact : strip, 400 si vide après strip."""
    name = raw.strip()
    if not name:
        raise HTTPException(400, "Le nom du contact est obligatoire.")
    return name

class ContactCreate(BaseModel):
    name: str
    type: str = "other"
    email: str = ""
    phone: str = ""
    address: str = ""
    notes: str = ""


class ContactUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None


@router.get("/")
def list_contacts(
    type: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(80, ge=1),
    offset: int = Query(0, ge=0),
):
    conn = get_conn()
    try:
        where = "WHERE 1=1"
        params: list = []
        if type:
            where += " AND type = ?"
            params.append(type)
        if search:
            where += " AND (name LIKE ? OR email LIKE ? OR phone LIKE ?)"
            params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])

        total = conn.execute(f"SELECT COUNT(*) FROM contacts {where}", params).fetchone()[0]
        rows = conn.execute(
            f"""SELECT c.* FROM contacts c
                LEFT JOIN (
                    SELECT contact_id, MAX(date) as last_date FROM transactions
                    WHERE contact_id IS NOT NULL GROUP BY contact_id
                ) t ON t.contact_id = c.id
                {where}
                ORDER BY COALESCE(t.last_date, '') DESC, c.name ASC, c.id ASC
                LIMIT ? OFFSET ?""",
            params + [limit, offset],
        ).fetchall()
        return {"total": total, "items": [row_to_dict(r) for r in rows]}
    finally:
        conn.close()


@router.post("/", status_code=201)
def create_contact(contact: ContactCreate):
    name = _require_name(contact.name)
    now = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    try:
        cur = conn.execute(
            """INSERT INTO contacts
               (name, type, email, phone, address, notes, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                name,
                contact.type,
                contact.email,
                contact.phone,
                contact.address,
                contact.notes,
                now,
                now,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM contacts WHERE id = ?", (cur.lastrowid,)).fetchone()
        return row_to_dict(row)
    finally:
        conn.close()


@router.get("/{contact_id}/transactions")
def get_contact_transactions(contact_id: int, request: Request):
    user = get_current_user(request)
    conn = get_conn()
    try:
        existing = conn.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail=f"Contact {contact_id} not found")
        # Périmètre : un non-admin ne voit que les transactions touchant une
        # entité de son périmètre (même logique que /api/transactions).
        allowed = get_allowed_entity_ids(conn, user)
        if allowed is not None and not allowed:
            return []
        where = "WHERE t.contact_id = ?"
        params: list = [contact_id]
        if allowed is not None:
            placeholders = ",".join("?" * len(allowed))
            where += f" AND (t.from_entity_id IN ({placeholders}) OR t.to_entity_id IN ({placeholders}))"
            params.extend(list(allowed))
            params.extend(list(allowed))
        # Types d'entités inclus pour que l'UI affiche le sens du flux
        # (recette verte / dépense rouge), comme partout ailleurs.
        cur = conn.execute(
            f"""SELECT t.*, ef.type AS from_entity_type, et.type AS to_entity_type
               FROM transactions t
               LEFT JOIN entities ef ON t.from_entity_id = ef.id
               LEFT JOIN entities et ON t.to_entity_id = et.id
               {where} ORDER BY t.date DESC, t.id DESC""",
            params,
        )
        return [row_to_dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


@router.get("/{contact_id}")
def get_contact(contact_id: int):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Contact {contact_id} not found")
        return row_to_dict(row)
    finally:
        conn.close()


@router.put("/{contact_id}")
def update_contact(contact_id: int, contact: ContactUpdate):
    now = datetime.now(timezone.utc).isoformat()
    conn = get_conn()
    try:
        existing = conn.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail=f"Contact {contact_id} not found")

        updates = contact.model_dump(exclude_unset=True)
        if not updates:
            return row_to_dict(existing)

        # name absent du payload (champ non fourni) : pas dans `updates`, inchangé.
        # name explicitement fourni (y compris null) : on valide et on strip.
        if "name" in updates:
            if updates["name"] is None:
                del updates["name"]
            else:
                updates["name"] = _require_name(updates["name"])

        if not updates:
            return row_to_dict(existing)

        set_clauses = ", ".join(f"{k} = ?" for k in updates)
        set_clauses += ", updated_at = ?"
        values = list(updates.values()) + [now, contact_id]

        conn.execute(
            f"UPDATE contacts SET {set_clauses} WHERE id = ?",
            values,
        )
        conn.commit()
        row = conn.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()
        return row_to_dict(row)
    finally:
        conn.close()


@router.post("/{source_id}/merge-into/{target_id}")
def merge_contacts(source_id: int, target_id: int):
    """Fusionne source dans target : réassigne toutes les FK puis supprime source."""
    conn = get_conn()
    try:
        source = conn.execute("SELECT * FROM contacts WHERE id = ?", (source_id,)).fetchone()
        target = conn.execute("SELECT * FROM contacts WHERE id = ?", (target_id,)).fetchone()
        if source is None:
            raise HTTPException(status_code=404, detail=f"Contact source {source_id} introuvable")
        if target is None:
            raise HTTPException(status_code=404, detail=f"Contact cible {target_id} introuvable")
        if source_id == target_id:
            raise HTTPException(status_code=400, detail="Source et cible identiques")

        for table in ("transactions", "reimbursements"):
            try:
                conn.execute(
                    f"UPDATE {table} SET contact_id = ? WHERE contact_id = ?",
                    (target_id, source_id),
                )
            except sqlite3.OperationalError:
                pass  # table/colonne absente (module non installé) — pas une vraie erreur

        conn.execute("DELETE FROM contacts WHERE id = ?", (source_id,))
        conn.commit()
        return {"merged": source_id, "into": target_id, "target": row_to_dict(target)}
    finally:
        conn.close()


@router.delete("/{contact_id}")
def delete_contact(contact_id: int):
    conn = get_conn()
    try:
        existing = conn.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail=f"Contact {contact_id} not found")
        # Dé-référencer le contact (PRAGMA foreign_keys OFF) pour ne pas laisser
        # de FK orphelines dans les transactions / remboursements.
        for table in ("transactions", "reimbursements"):
            try:
                conn.execute(f"UPDATE {table} SET contact_id = NULL WHERE contact_id = ?", (contact_id,))
            except sqlite3.OperationalError:
                pass
        conn.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))
        conn.commit()
        return {"deleted": contact_id}
    finally:
        conn.close()
