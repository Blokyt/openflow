"""Multi-users API module for OpenFlow."""
import secrets
import sqlite3
import string
import uuid
from datetime import datetime, timezone
from typing import Optional

import bcrypt
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from backend.core.database import get_conn, row_to_dict
from backend.core.auth import is_root_admin

router = APIRouter()

VALID_ROLES = {"admin", "tresorier", "president", "lecteur"}
VALID_ENTITY_ROLES = {"tresorier", "president", "lecteur"}


# ---------------------------------------------------------------------------
# Password helpers
# ---------------------------------------------------------------------------

def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = row_to_dict(row)
    # Never expose password_hash
    d.pop("password_hash", None)
    return d


def _require_admin_if_users_exist(request: Request):
    """If any users exist, require the caller to be root admin. Raises 403 otherwise."""
    conn = get_conn()
    try:
        user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    finally:
        conn.close()
    if user_count > 0 and not is_root_admin(request):
        raise HTTPException(403, "Admin access required")


def _get_session_user(request: Request):
    """Return user row for the current session cookie, or raise 401."""
    session_id = request.cookies.get("session_id")
    if not session_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    conn = get_conn()
    try:
        session = conn.execute(
            "SELECT user_id FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if session is None:
            raise HTTPException(status_code=401, detail="Invalid or expired session")
        user = conn.execute(
            "SELECT * FROM users WHERE id = ?", (session["user_id"],)
        ).fetchone()
        if user is None:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class UserCreate(BaseModel):
    username: str
    password: str = ""  # Empty = auto-generate
    role: str = "lecteur"
    display_name: str = ""


class UserUpdate(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None
    role: Optional[str] = None
    display_name: Optional[str] = None
    active: Optional[int] = None


class LoginRequest(BaseModel):
    username: str
    password: str


class PasswordChange(BaseModel):
    old_password: str
    new_password: str


class EntityAssignment(BaseModel):
    entity_id: int
    role: str = "lecteur"


# ---------------------------------------------------------------------------
# Auth endpoints (must come BEFORE /{user_id} routes)
# ---------------------------------------------------------------------------

@router.post("/login")
def login(creds: LoginRequest, response: Response):
    conn = get_conn()
    try:
        user = conn.execute(
            "SELECT * FROM users WHERE username = ?", (creds.username,)
        ).fetchone()
        if user is None or not _verify_password(creds.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid username or password")

        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        # Purge stale sessions older than 24h before creating the new one
        conn.execute(
            "DELETE FROM sessions WHERE datetime(created_at) < datetime('now', '-24 hours')"
        )
        conn.execute(
            "INSERT INTO sessions (id, user_id, created_at) VALUES (?, ?, ?)",
            (session_id, user["id"], now),
        )
        conn.commit()
    finally:
        conn.close()

    response.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,
        samesite="strict",
        path="/",
    )
    return {"status": "ok", "username": user["username"]}


@router.post("/logout")
def logout(request: Request, response: Response):
    session_id = request.cookies.get("session_id")
    if session_id:
        conn = get_conn()
        try:
            conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            conn.commit()
        finally:
            conn.close()
    response.delete_cookie(key="session_id", path="/")
    return {"status": "ok"}


@router.get("/me")
def get_me(request: Request):
    user = _get_session_user(request)
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT ue.entity_id, e.name AS entity_name, ue.role
               FROM user_entities ue
               LEFT JOIN entities e ON e.id = ue.entity_id
               WHERE ue.user_id = ?""",
            (user["id"],),
        ).fetchall()
        entities = [dict(r) for r in rows]
    finally:
        conn.close()

    return {
        "id": user["id"],
        "username": user["username"],
        "display_name": user["display_name"],
        "role": user["role"],
        "entities": entities,
    }


@router.put("/me/password")
def change_password(request: Request, body: PasswordChange):
    user = _get_session_user(request)
    if not _verify_password(body.old_password, user["password_hash"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if len(body.new_password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")

    new_hash = _hash_password(body.new_password)
    session_id = request.cookies.get("session_id")
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (new_hash, user["id"]),
        )
        # Invalidate all OTHER sessions for this user
        conn.execute(
            "DELETE FROM sessions WHERE user_id = ? AND id != ?",
            (user["id"], session_id),
        )
        conn.commit()
    finally:
        conn.close()

    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Admin utility endpoints (must come BEFORE /{user_id} routes)
# ---------------------------------------------------------------------------

@router.post("/cleanup-sessions")
def cleanup_sessions(request: Request):
    """Remove stale sessions older than 24h. Admin only."""
    _require_admin_if_users_exist(request)

    conn = get_conn()
    try:
        conn.execute("DELETE FROM sessions WHERE datetime(created_at) < datetime('now', '-24 hours')")
        conn.commit()
        remaining = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        return {"remaining_sessions": remaining}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Entity access endpoints
# ---------------------------------------------------------------------------

@router.get("/{user_id}/entities")
def list_user_entities(user_id: int, request: Request):
    conn = get_conn()
    try:
        user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    finally:
        conn.close()
    if user_count > 0:
        # Allow self or root admin
        current = getattr(request.state, "user", None)
        if current is None or (current["id"] != user_id and not is_root_admin(request)):
            raise HTTPException(403, "Admin access required")
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT ue.entity_id, e.name AS entity_name, ue.role
               FROM user_entities ue
               LEFT JOIN entities e ON e.id = ue.entity_id
               WHERE ue.user_id = ?""",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.post("/{user_id}/entities", status_code=201)
def assign_entity(user_id: int, body: EntityAssignment, request: Request):
    _require_admin_if_users_exist(request)
    if body.role not in VALID_ENTITY_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role '{body.role}'. Must be one of: {', '.join(VALID_ENTITY_ROLES)}",
        )
    conn = get_conn()
    try:
        existing_user = conn.execute(
            "SELECT id FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if existing_user is None:
            raise HTTPException(status_code=404, detail=f"User {user_id} not found")
        try:
            conn.execute(
                "INSERT INTO user_entities (user_id, entity_id, role) VALUES (?, ?, ?)",
                (user_id, body.entity_id, body.role),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            raise HTTPException(
                status_code=400,
                detail=f"User {user_id} already has access to entity {body.entity_id}",
            )
        row = conn.execute(
            """SELECT ue.entity_id, e.name AS entity_name, ue.role
               FROM user_entities ue
               LEFT JOIN entities e ON e.id = ue.entity_id
               WHERE ue.user_id = ? AND ue.entity_id = ?""",
            (user_id, body.entity_id),
        ).fetchone()
        return dict(row)
    finally:
        conn.close()


@router.delete("/{user_id}/entities/{entity_id}")
def remove_entity_access(user_id: int, entity_id: int, request: Request):
    _require_admin_if_users_exist(request)
    conn = get_conn()
    try:
        existing = conn.execute(
            "SELECT id FROM user_entities WHERE user_id = ? AND entity_id = ?",
            (user_id, entity_id),
        ).fetchone()
        if existing is None:
            raise HTTPException(
                status_code=404,
                detail=f"No access entry for user {user_id} / entity {entity_id}",
            )
        conn.execute(
            "DELETE FROM user_entities WHERE user_id = ? AND entity_id = ?",
            (user_id, entity_id),
        )
        conn.commit()
        return {"deleted": {"user_id": user_id, "entity_id": entity_id}}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# User CRUD endpoints
# ---------------------------------------------------------------------------

@router.get("/")
def list_users(request: Request):
    _require_admin_if_users_exist(request)
    conn = get_conn()
    try:
        cur = conn.execute("SELECT * FROM users ORDER BY id ASC")
        return [_row_to_dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


@router.post("/", status_code=201)
def create_user(user: UserCreate, request: Request):
    _require_admin_if_users_exist(request)
    if user.role not in VALID_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role '{user.role}'. Must be one of: {', '.join(VALID_ROLES)}",
        )

    # Auto-generate password if not provided
    raw_password = user.password
    generated = False
    if not raw_password:
        alphabet = string.ascii_letters + string.digits
        raw_password = "".join(secrets.choice(alphabet) for _ in range(10))
        generated = True
    elif len(raw_password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")

    now = datetime.now(timezone.utc).isoformat()
    password_hash = _hash_password(raw_password)

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
            raise HTTPException(
                status_code=400, detail=f"Username '{user.username}' already exists"
            )

        row = conn.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()
        result = _row_to_dict(row)
        # Return generated password ONCE so admin can share it
        if generated:
            result["generated_password"] = raw_password
        return result
    finally:
        conn.close()


@router.get("/{user_id}")
def get_user(user_id: int, request: Request):
    conn = get_conn()
    try:
        user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    finally:
        conn.close()
    if user_count > 0:
        # Allow self or root admin
        current = getattr(request.state, "user", None)
        if current is None or (current["id"] != user_id and not is_root_admin(request)):
            raise HTTPException(403, "Admin access required")
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"User {user_id} not found")
        return _row_to_dict(row)
    finally:
        conn.close()


@router.put("/{user_id}")
def update_user(user_id: int, user: UserUpdate, request: Request):
    _require_admin_if_users_exist(request)
    conn = get_conn()
    try:
        existing = conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail=f"User {user_id} not found")

        updates = user.model_dump(exclude_unset=True)
        if not updates:
            return _row_to_dict(existing)

        if "role" in updates and updates["role"] not in VALID_ROLES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid role '{updates['role']}'. Must be one of: {', '.join(VALID_ROLES)}",
            )

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
def delete_user(user_id: int, request: Request):
    _require_admin_if_users_exist(request)
    conn = get_conn()
    try:
        existing = conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail=f"User {user_id} not found")
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM user_entities WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        return {"deleted": user_id}
    finally:
        conn.close()
