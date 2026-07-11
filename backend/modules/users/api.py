"""API du module users : authentification, comptes, rôles, invitations."""
import json as _json
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from backend.core.auth import (
    MIN_PASSWORD_LENGTH,
    SESSION_COOKIE,
    SESSION_TTL_DAYS,
    create_session,
    delete_session,
    get_allowed_entity_ids,
    get_current_user,
    hash_password,
    hash_token,
    require_admin,
    verify_password,
)
from backend.core.database import get_conn
from backend.core.rate_limit import limiter
from backend.modules.users.lockout import lockout_remaining_seconds, record_login_event

router = APIRouter()

INVITATION_TTL_HOURS = 72

# Hachage factice : le login vérifie toujours UN mot de passe, que l'email
# existe ou non, pour un temps de réponse constant (anti-énumération).
_DUMMY_HASH = hash_password("dummy-timing-equalizer")


class LoginPayload(BaseModel):
    email: str
    password: str


class RoleItem(BaseModel):
    entity_id: int
    role: Literal["treasurer", "viewer"]


class RolesPayload(BaseModel):
    roles: list[RoleItem]


class UserUpdatePayload(BaseModel):
    display_name: Optional[str] = None
    is_admin: Optional[bool] = None
    is_active: Optional[bool] = None


class InvitationPayload(BaseModel):
    email: str
    is_admin: bool = False
    roles: list[RoleItem] = Field(default_factory=list)


class AcceptPayload(BaseModel):
    token: str
    display_name: str
    password: str


class PasswordPayload(BaseModel):
    current_password: str
    new_password: str


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
        allowed = sorted(get_allowed_entity_ids(conn, {"id": user_row["id"], "is_admin": 0}))
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
@limiter.limit("10/minute;30/hour")
def login(request: Request, payload: LoginPayload, response: Response):
    email = payload.email.strip().lower()
    ip = request.client.host if request.client else ""
    user_agent = request.headers.get("user-agent", "")
    conn = get_conn()
    try:
        remaining = lockout_remaining_seconds(conn, email, ip)
        if remaining > 0:
            raise HTTPException(
                status_code=429,
                detail=f"Trop de tentatives échouées. Réessayez dans {remaining} secondes.",
                headers={"Retry-After": str(remaining)},
            )
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        stored = row["password_hash"] if row is not None else _DUMMY_HASH
        ok = verify_password(payload.password, stored)
        if row is None or not ok or not row["is_active"]:
            record_login_event(conn, email, ip, success=False, user_agent=user_agent)
            conn.commit()
            raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")
        token = create_session(conn, row["id"], user_agent)
        conn.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (_now_iso(), row["id"]))
        record_login_event(conn, email, ip, success=True, user_agent=user_agent)
        conn.commit()
        _set_session_cookie(response, request, token)
        return serialize_user(conn, row)
    finally:
        conn.close()


@router.get("/me")
def me(request: Request, user: dict = Depends(get_current_user)):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
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


def _check_no_duplicate_entities(items) -> None:
    """Rejette proprement les rôles en double sur une même entité (UNIQUE(user_id, entity_id))."""
    seen = set()
    for item in items:
        entity_id = item["entity_id"] if isinstance(item, dict) else item.entity_id
        if entity_id in seen:
            raise HTTPException(status_code=400, detail="Entité en double dans les rôles")
        seen.add(entity_id)


def _get_user_or_404(conn, user_id: int):
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Utilisateur {user_id} introuvable")
    return row


@router.get("/", dependencies=[Depends(require_admin)])
def list_users():
    conn = get_conn()
    try:
        out = []
        for row in conn.execute("SELECT * FROM users ORDER BY email").fetchall():
            data = serialize_user(conn, row)
            data["last_login_at"] = row["last_login_at"]
            out.append(data)
        return out
    finally:
        conn.close()


@router.get("/login-events", dependencies=[Depends(require_admin)])
def list_login_events(limit: int = 100):
    """Journal des connexions (réussites et échecs), du plus récent au plus ancien."""
    limit = max(1, min(limit, 500))
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT id, email, ip, success, created_at, user_agent FROM login_events "
            "ORDER BY id DESC LIMIT ?", (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.put("/me/password")
def change_my_password(request: Request, payload: PasswordPayload):
    user = get_current_user(request)
    if len(payload.new_password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(status_code=400,
                            detail=f"Mot de passe trop court ({MIN_PASSWORD_LENGTH} caractères minimum)")
    conn = get_conn()
    try:
        row = _get_user_or_404(conn, user["id"])
        if not verify_password(payload.current_password, row["password_hash"]):
            raise HTTPException(status_code=401, detail="Mot de passe actuel incorrect")
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                     (hash_password(payload.new_password), user["id"]))
        # Invalide les autres sessions, garde la courante.
        current = request.cookies.get(SESSION_COOKIE, "")
        conn.execute("DELETE FROM sessions WHERE user_id = ? AND token_hash != ?",
                     (user["id"], hash_token(current)))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@router.post("/invitations", status_code=201)
def create_invitation(request: Request, payload: InvitationPayload):
    email = payload.email.strip().lower()
    conn = get_conn()
    try:
        existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existing is not None:
            raise HTTPException(status_code=400, detail="Un compte existe déjà avec cet email")
        for item in payload.roles:
            if conn.execute("SELECT id FROM entities WHERE id = ?", (item.entity_id,)).fetchone() is None:
                raise HTTPException(status_code=400, detail=f"Entité {item.entity_id} introuvable")
        token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        expires = (now + timedelta(hours=INVITATION_TTL_HOURS)).isoformat()
        cur = conn.execute(
            "INSERT INTO invitations (token_hash, email, is_admin, roles_json, expires_at, used_at, created_by, created_at) "
            "VALUES (?, ?, ?, ?, ?, NULL, ?, ?)",
            (hash_token(token), email, 1 if payload.is_admin else 0,
             _json.dumps([item.model_dump() for item in payload.roles]),
             expires, get_current_user(request)["id"], now.isoformat()),
        )
        conn.commit()
        return {"id": cur.lastrowid, "token": token,
                "url_path": f"/invitation?token={token}",
                "email": email, "expires_at": expires}
    finally:
        conn.close()


@router.get("/invitations", dependencies=[Depends(require_admin)])
def list_invitations():
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT id, email, is_admin, roles_json, expires_at, created_at FROM invitations "
            "WHERE used_at IS NULL ORDER BY created_at DESC").fetchall()
        out = []
        for r in rows:
            data = dict(r)
            data["roles"] = _json.loads(data.pop("roles_json"))
            out.append(data)
        return out
    finally:
        conn.close()


@router.delete("/invitations/{invitation_id}")
def delete_invitation(invitation_id: int):
    conn = get_conn()
    try:
        if conn.execute("SELECT id FROM invitations WHERE id = ?", (invitation_id,)).fetchone() is None:
            raise HTTPException(status_code=404, detail="Invitation introuvable")
        conn.execute("DELETE FROM invitations WHERE id = ?", (invitation_id,))
        conn.commit()
        return {"deleted": invitation_id}
    finally:
        conn.close()


def _valid_invitation(conn, token: str):
    row = conn.execute(
        "SELECT * FROM invitations WHERE token_hash = ? AND used_at IS NULL AND expires_at > ?",
        (hash_token(token), _now_iso()),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Invitation invalide ou expirée")
    return row


@router.get("/invitations/preview")
def preview_invitation(token: str):
    conn = get_conn()
    try:
        return {"email": _valid_invitation(conn, token)["email"]}
    finally:
        conn.close()


@router.post("/invitations/accept")
@limiter.limit("5/minute;20/hour")
def accept_invitation(request: Request, payload: AcceptPayload, response: Response):
    if len(payload.password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(status_code=400,
                            detail=f"Mot de passe trop court ({MIN_PASSWORD_LENGTH} caractères minimum)")
    conn = get_conn()
    try:
        inv = _valid_invitation(conn, payload.token)
        now = _now_iso()
        roles = _json.loads(inv["roles_json"])
        _check_no_duplicate_entities(roles)
        try:
            cur = conn.execute(
                "INSERT INTO users (email, display_name, password_hash, is_admin, is_active, created_at) "
                "VALUES (?, ?, ?, ?, 1, ?)",
                (inv["email"], payload.display_name.strip() or inv["email"],
                 hash_password(payload.password), inv["is_admin"], now),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="Un compte existe déjà avec cet email")
        user_id = cur.lastrowid
        for item in roles:
            # L'entité a pu être supprimée entre l'invitation et l'acceptation :
            # on ignore le rôle plutôt que de créer un rôle orphelin (mêmes
            # garde-fous que set_user_roles, mais silencieux ici car l'invité
            # n'a pas la main sur la liste de rôles).
            if conn.execute("SELECT id FROM entities WHERE id = ?", (item["entity_id"],)).fetchone() is None:
                continue
            conn.execute(
                "INSERT INTO user_entity_roles (user_id, entity_id, role, created_at) VALUES (?, ?, ?, ?)",
                (user_id, item["entity_id"], item["role"], now))
        conn.execute("UPDATE invitations SET used_at = ? WHERE id = ?", (now, inv["id"]))
        token = create_session(conn, user_id, request.headers.get("user-agent", ""))
        conn.commit()
        _set_session_cookie(response, request, token)
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return serialize_user(conn, row)
    finally:
        conn.close()


@router.put("/{user_id}")
def update_user(user_id: int, payload: UserUpdatePayload, request: Request):
    me_id = get_current_user(request)["id"]
    conn = get_conn()
    try:
        row = _get_user_or_404(conn, user_id)
        if user_id == me_id and (payload.is_admin is False or payload.is_active is False):
            raise HTTPException(status_code=400,
                                detail="Impossible de retirer ses propres droits administrateur")
        fields, values = [], []
        if payload.display_name is not None:
            fields.append("display_name = ?"); values.append(payload.display_name.strip())
        if payload.is_admin is not None:
            fields.append("is_admin = ?"); values.append(1 if payload.is_admin else 0)
        if payload.is_active is not None:
            fields.append("is_active = ?"); values.append(1 if payload.is_active else 0)
            if payload.is_active is False:
                conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        if fields:
            values.append(user_id)
            conn.execute(f"UPDATE users SET {', '.join(fields)} WHERE id = ?", values)
            conn.commit()
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return serialize_user(conn, row)
    finally:
        conn.close()


@router.put("/{user_id}/roles")
def set_user_roles(user_id: int, payload: RolesPayload):
    conn = get_conn()
    try:
        _get_user_or_404(conn, user_id)
        _check_no_duplicate_entities(payload.roles)
        for item in payload.roles:
            if conn.execute("SELECT id FROM entities WHERE id = ?", (item.entity_id,)).fetchone() is None:
                raise HTTPException(status_code=400, detail=f"Entité {item.entity_id} introuvable")
        conn.execute("DELETE FROM user_entity_roles WHERE user_id = ?", (user_id,))
        now = _now_iso()
        for item in payload.roles:
            conn.execute(
                "INSERT INTO user_entity_roles (user_id, entity_id, role, created_at) VALUES (?, ?, ?, ?)",
                (user_id, item.entity_id, item.role, now))
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return serialize_user(conn, row)
    finally:
        conn.close()


@router.delete("/{user_id}/sessions")
def revoke_sessions(user_id: int):
    conn = get_conn()
    try:
        _get_user_or_404(conn, user_id)
        cur = conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        conn.commit()
        return {"deleted": cur.rowcount}
    finally:
        conn.close()
