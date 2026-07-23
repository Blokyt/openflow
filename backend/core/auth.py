"""Authentification et permissions : infrastructure transverse OpenFlow.

Même statut que database.py ou balance.py : les modules importent d'ici,
jamais l'inverse. Les mots de passe sont hachés en scrypt (stdlib), les
tokens (sessions, invitations) ne sont jamais stockés en clair.
"""
import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from fastapi import Depends, HTTPException, Request

from backend.core.database import get_conn

SESSION_COOKIE = "openflow_session"
SESSION_TTL_DAYS = 30
MIN_PASSWORD_LENGTH = 10

# Paramètres scrypt : n=2^15, r=8, p=1 (coût mémoire ~32 Mo par hachage).
_SCRYPT_N = 2 ** 15
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_MAXMEM = 64 * 1024 * 1024
_SCRYPT_DKLEN = 64


def _now() -> datetime:
    return datetime.now(timezone.utc)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(
        password.encode("utf-8"), salt=salt,
        n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P,
        maxmem=_SCRYPT_MAXMEM, dklen=_SCRYPT_DKLEN,
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt_hex, hash_hex = stored.split("$")
        if algo != "scrypt":
            return False
        expected = bytes.fromhex(hash_hex)
        dk = hashlib.scrypt(
            password.encode("utf-8"), salt=bytes.fromhex(salt_hex),
            n=int(n), r=int(r), p=int(p),
            maxmem=_SCRYPT_MAXMEM, dklen=len(expected),
        )
        return hmac.compare_digest(dk, expected)
    except (ValueError, TypeError):
        return False


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(conn, user_id: int, user_agent: str = "") -> str:
    """Insère une session et renvoie le token en clair (l'appelant commite)."""
    token = secrets.token_urlsafe(32)
    now = _now()
    conn.execute(
        "INSERT INTO sessions (token_hash, user_id, created_at, expires_at, last_seen_at, user_agent) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            hash_token(token), user_id, now.isoformat(),
            (now + timedelta(days=SESSION_TTL_DAYS)).isoformat(),
            now.isoformat(), user_agent[:256],
        ),
    )
    return token


def delete_session(conn, token: str) -> None:
    conn.execute("DELETE FROM sessions WHERE token_hash = ?", (hash_token(token),))


# Routes accessibles sans session (login et acceptation d'invitation).
PUBLIC_API_PATHS = {
    "/api/users/login",
    "/api/users/invitations/preview",
    "/api/users/invitations/accept",
    "/api/users/reset/preview",
    "/api/users/reset/accept",
}

# Mutations autorisées aux non-admins (gestion de leur propre compte).
NON_ADMIN_MUTATIONS = {
    "/api/users/login",
    "/api/users/logout",
    "/api/users/me",
    "/api/users/me/password",
    "/api/users/invitations/accept",
    "/api/submissions/",
}

# Mutations non-admin dont le chemin contient un paramètre : motifs regex.
# La vérification FINE (propriétaire, statut, périmètre) reste dans l'endpoint ;
# ici on ne fait qu'ouvrir le passage de la garde centrale.
NON_ADMIN_MUTATION_PATTERNS = [
    re.compile(r"^/api/submissions/\d+/cancel$"),
    # Upload d'un justificatif sur SA soumission pending (vérif fine dans l'endpoint).
    re.compile(r"^/api/attachments/submission/\d+$"),
    # Suppression d'un justificatif : l'endpoint n'autorise un non-admin QUE sur
    # une pièce liée à sa propre soumission pending.
    re.compile(r"^/api/attachments/\d+$"),
]


def is_non_admin_mutation(path: str) -> bool:
    return path in NON_ADMIN_MUTATIONS or any(p.match(path) for p in NON_ADMIN_MUTATION_PATTERNS)


_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _check_origin(request: Request) -> None:
    """Anti-CSRF : sur une mutation, si le navigateur envoie Origin, il doit
    correspondre au Host. Les clients sans Origin (curl, tests) passent."""
    if request.method not in _MUTATING_METHODS:
        return
    origin = request.headers.get("origin")
    if not origin:
        return
    netloc = urlparse(origin).netloc
    host = request.headers.get("host", "")
    if netloc in ["localhost:5173", "127.0.0.1:5173", "localhost:4173", "127.0.0.1:4173"]:
        return
    if netloc != host:
        raise HTTPException(status_code=403, detail="Origine non autorisée")


def require_session(request: Request) -> None:
    """Dépendance globale : deny-by-default sur /api + garde centrale des écritures."""
    path = request.url.path
    if not path.startswith("/api"):
        return
    _check_origin(request)
    if path in PUBLIC_API_PATHS:
        return
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Authentification requise")
    conn = get_conn()
    try:
        now = _now().isoformat()
        row = conn.execute(
            "SELECT u.*, s.id AS session_id FROM sessions s JOIN users u ON u.id = s.user_id "
            "WHERE s.token_hash = ? AND s.expires_at > ? AND u.is_active = 1",
            (hash_token(token), now),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=401, detail="Session expirée ou invalide")
        conn.execute("UPDATE sessions SET last_seen_at = ? WHERE id = ?", (now, row["session_id"]))
        conn.commit()
        request.state.user = {
            "id": row["id"], "email": row["email"], "display_name": row["display_name"],
            "is_admin": row["is_admin"], "is_active": row["is_active"],
        }
    finally:
        conn.close()
    if request.method in _MUTATING_METHODS and not request.state.user["is_admin"] \
            and not is_non_admin_mutation(path):
        raise HTTPException(status_code=403, detail="Action réservée à l'administrateur")


def get_current_user(request: Request) -> dict:
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentification requise")
    return user


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if not user["is_admin"]:
        raise HTTPException(status_code=403, detail="Action réservée à l'administrateur")
    return user


def get_allowed_entity_ids(conn, user: dict, role: str | None = None):
    """Périmètre du user : None = tout (admin), sinon l'union des sous-arbres
    des entités où il a un rôle. `role` restreint aux lignes de ce rôle
    (ex : "treasurer" pour les écritures). CTE récursive multi-racines : part
    de toutes les entités où le user a un rôle, descend vers leurs enfants, et
    l'UNION (sans ALL) dédoublonne les id partagés par plusieurs sous-arbres.
    Aucun filtre de type : entités internes et externes sont incluses
    indifféremment."""
    if user["is_admin"]:
        return None
    if role is None:
        rows = conn.execute(
            "SELECT entity_id FROM user_entity_roles WHERE user_id = ?", (user["id"],)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT entity_id FROM user_entity_roles WHERE user_id = ? AND role = ?",
            (user["id"], role),
        ).fetchall()
    roots = [r[0] for r in rows]
    if not roots:
        return set()
    placeholders = ",".join("?" * len(roots))
    cur = conn.execute(
        f"""WITH RECURSIVE tree(id) AS (
            SELECT id FROM entities WHERE id IN ({placeholders})
            UNION
            SELECT e.id FROM entities e JOIN tree t ON e.parent_id = t.id
        ) SELECT id FROM tree""",
        roots,
    )
    return {r[0] for r in cur.fetchall()}


def require_entity_access(conn, user: dict, entity_id: int) -> None:
    allowed = get_allowed_entity_ids(conn, user)
    if allowed is None:
        return
    if entity_id not in allowed:
        raise HTTPException(status_code=403, detail="Accès refusé à cette entité")


# Message partagé par les vues financières (dashboard, budget, reports).
ENTITY_REQUIRED_MESSAGE = "Une entité est requise pour ce rôle"


def require_scope(conn, user: dict, entity_id) -> None:
    """Non-admin : entity_id obligatoire (400 si absent) + dans le périmètre
    (403 sinon). Admin (`allowed is None`) : aucune contrainte."""
    allowed = get_allowed_entity_ids(conn, user)
    if allowed is None:
        return
    if entity_id is None:
        raise HTTPException(status_code=400, detail=ENTITY_REQUIRED_MESSAGE)
    require_entity_access(conn, user, entity_id)
