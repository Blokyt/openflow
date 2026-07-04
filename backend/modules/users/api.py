"""API du module users : authentification, comptes, rôles, invitations."""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from backend.core.auth import (
    SESSION_COOKIE,
    SESSION_TTL_DAYS,
    create_session,
    delete_session,
    hash_password,
    hash_token,
    verify_password,
)
from backend.core.database import get_conn
from backend.core.rate_limit import limiter

router = APIRouter()

# Hachage factice : le login vérifie toujours UN mot de passe, que l'email
# existe ou non, pour un temps de réponse constant (anti-énumération).
_DUMMY_HASH = hash_password("dummy-timing-equalizer")


class LoginPayload(BaseModel):
    email: str
    password: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def serialize_user(conn, user_row) -> dict:
    roles = [
        {"entity_id": r["entity_id"], "role": r["role"]}
        for r in conn.execute(
            "SELECT entity_id, role FROM user_entity_roles WHERE user_id = ? ORDER BY entity_id",
            (user_row["id"],),
        ).fetchall()
    ]
    if user_row["is_admin"]:
        allowed = None
    else:
        # Task 5 remplace cette ligne par get_allowed_entity_ids (sous-arbre).
        allowed = sorted({r["entity_id"] for r in roles})
    return {
        "id": user_row["id"],
        "email": user_row["email"],
        "display_name": user_row["display_name"],
        "is_admin": user_row["is_admin"],
        "is_active": user_row["is_active"],
        "roles": roles,
        "allowed_entity_ids": allowed,
    }


def _set_session_cookie(response: Response, request: Request, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE, token,
        httponly=True, samesite="lax",
        secure=request.url.scheme == "https",
        max_age=SESSION_TTL_DAYS * 24 * 3600, path="/",
    )


@router.post("/login")
@limiter.limit("5/minute")
def login(request: Request, payload: LoginPayload, response: Response):
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ?", (payload.email.strip().lower(),)
        ).fetchone()
        stored = row["password_hash"] if row is not None else _DUMMY_HASH
        ok = verify_password(payload.password, stored)
        if row is None or not ok or not row["is_active"]:
            raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")
        token = create_session(conn, row["id"], request.headers.get("user-agent", ""))
        conn.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (_now_iso(), row["id"]))
        conn.commit()
        _set_session_cookie(response, request, token)
        return serialize_user(conn, row)
    finally:
        conn.close()


def _user_from_cookie(request: Request, conn):
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Authentification requise")
    row = conn.execute(
        "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id "
        "WHERE s.token_hash = ? AND s.expires_at > ? AND u.is_active = 1",
        (hash_token(token), _now_iso()),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="Session expirée ou invalide")
    return row


@router.get("/me")
def me(request: Request):
    conn = get_conn()
    try:
        row = _user_from_cookie(request, conn)
        return serialize_user(conn, row)
    finally:
        conn.close()


@router.post("/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        conn = get_conn()
        try:
            delete_session(conn, token)
            conn.commit()
        finally:
            conn.close()
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}
