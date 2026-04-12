"""Authentication middleware and permission helpers."""
import sqlite3
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from backend.core.database import get_conn

PUBLIC_PATHS = {"/api/multi_users/login"}


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Skip auth for non-API routes (frontend static files) and public endpoints
        if not path.startswith("/api/") or path in PUBLIC_PATHS:
            return await call_next(request)

        # If no users exist yet, skip auth (first-time setup)
        conn = get_conn()
        try:
            user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            if user_count == 0:
                return await call_next(request)
        finally:
            conn.close()

        session_id = request.cookies.get("session_id")
        if not session_id:
            return JSONResponse(status_code=401, content={"detail": "Not authenticated"})

        conn = get_conn()
        try:
            session = conn.execute(
                "SELECT user_id FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if not session:
                return JSONResponse(status_code=401, content={"detail": "Invalid session"})

            user = conn.execute(
                "SELECT id, username, display_name, role, active FROM users WHERE id = ?",
                (session["user_id"],),
            ).fetchone()
            if not user or not user["active"]:
                return JSONResponse(status_code=401, content={"detail": "User not found or inactive"})

            entities = conn.execute(
                "SELECT entity_id, role FROM user_entities WHERE user_id = ?",
                (user["id"],),
            ).fetchall()

            request.state.user = dict(user)
            request.state.user_entities = [dict(e) for e in entities]
        finally:
            conn.close()

        return await call_next(request)


def get_current_user(request: Request) -> dict:
    if not hasattr(request.state, "user"):
        raise HTTPException(401, "Not authenticated")
    return request.state.user


def has_entity_access(request: Request, entity_id: int) -> bool:
    """Check if user has any access to entity (direct or via ancestor)."""
    user_entities = getattr(request.state, "user_entities", [])
    accessible_ids = {ue["entity_id"] for ue in user_entities}

    if entity_id in accessible_ids:
        return True

    # Walk up the tree — access to parent grants access to children
    conn = get_conn()
    try:
        current = entity_id
        while current:
            row = conn.execute("SELECT parent_id FROM entities WHERE id = ?", (current,)).fetchone()
            if not row or not row["parent_id"]:
                break
            if row["parent_id"] in accessible_ids:
                return True
            current = row["parent_id"]
    finally:
        conn.close()
    return False


def has_write_access(request: Request, entity_id: int) -> bool:
    """Check if user has tresorier access to entity (direct or via ancestor)."""
    user_entities = getattr(request.state, "user_entities", [])
    tresorier_ids = {ue["entity_id"] for ue in user_entities if ue["role"] == "tresorier"}

    if entity_id in tresorier_ids:
        return True

    conn = get_conn()
    try:
        current = entity_id
        while current:
            row = conn.execute("SELECT parent_id FROM entities WHERE id = ?", (current,)).fetchone()
            if not row or not row["parent_id"]:
                break
            if row["parent_id"] in tresorier_ids:
                return True
            current = row["parent_id"]
    finally:
        conn.close()
    return False


def is_root_admin(request: Request) -> bool:
    """Check if user is tresorier on the root entity."""
    user_entities = getattr(request.state, "user_entities", [])
    tresorier_ids = {ue["entity_id"] for ue in user_entities if ue["role"] == "tresorier"}

    if not tresorier_ids:
        return False

    conn = get_conn()
    try:
        root = conn.execute(
            "SELECT id FROM entities WHERE parent_id IS NULL AND type = 'internal' AND is_default = 1"
        ).fetchone()
        return root is not None and root["id"] in tresorier_ids
    finally:
        conn.close()
