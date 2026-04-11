"""Multi-users API module for OpenFlow."""
import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

# Project root is 3 levels up from this file: backend/modules/multi_users/api.py
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "openflow.db"

VALID_ROLES = {"admin", "treasurer", "reader"}


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    # Never expose password_hash
    d.pop("password_hash", None)
    return d


class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "reader"
    display_name: str = ""


class UserUpdate(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None
    role: Optional[str] = None
    display_name: Optional[str] = None
    active: Optional[int] = None


@router.get("/")
def list_users():
    conn = get_conn()
    try:
        cur = conn.execute("SELECT * FROM users ORDER BY id ASC")
        return [_row_to_dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


@router.post("/", status_code=201)
def create_user(user: UserCreate):
    if user.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role '{user.role}'. Must be one of: {', '.join(VALID_ROLES)}")

    now = datetime.now(timezone.utc).isoformat()
    password_hash = _hash_password(user.password)

    conn = get_conn()
    try:
        try:
            cur = conn.execute(
                """INSERT INTO users (username, password_hash, role, display_name, created_at, active)
                   VALUES (?, ?, ?, ?, ?, 1)""",
                (user.username, password_hash, user.role, user.display_name, now),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=400, detail=f"Username '{user.username}' already exists")

        row = conn.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


@router.get("/{user_id}")
def get_user(user_id: int):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"User {user_id} not found")
        return _row_to_dict(row)
    finally:
        conn.close()


@router.put("/{user_id}")
def update_user(user_id: int, user: UserUpdate):
    conn = get_conn()
    try:
        existing = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail=f"User {user_id} not found")

        updates = user.model_dump(exclude_unset=True)
        if not updates:
            return _row_to_dict(existing)

        if "role" in updates and updates["role"] not in VALID_ROLES:
            raise HTTPException(status_code=400, detail=f"Invalid role '{updates['role']}'. Must be one of: {', '.join(VALID_ROLES)}")

        # Hash the password if it's being updated
        if "password" in updates:
            updates["password_hash"] = _hash_password(updates.pop("password"))

        set_clauses = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [user_id]

        try:
            conn.execute(
                f"UPDATE users SET {set_clauses} WHERE id = ?",
                values,
            )
            conn.commit()
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=400, detail="Username already taken")

        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


@router.delete("/{user_id}")
def delete_user(user_id: int):
    conn = get_conn()
    try:
        existing = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail=f"User {user_id} not found")
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        return {"deleted": user_id}
    finally:
        conn.close()
