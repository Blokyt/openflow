"""Authentification et permissions : infrastructure transverse OpenFlow.

Même statut que database.py ou balance.py : les modules importent d'ici,
jamais l'inverse. Les mots de passe sont hachés en scrypt (stdlib), les
tokens (sessions, invitations) ne sont jamais stockés en clair.
"""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

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
