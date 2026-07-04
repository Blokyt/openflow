"""Tests unitaires de backend/core/auth.py (hachage, tokens, sessions)."""
import sqlite3

import pytest

from backend.core.auth import (
    create_session,
    delete_session,
    hash_password,
    hash_token,
    verify_password,
)


def test_hash_password_roundtrip():
    stored = hash_password("mot-de-passe-solide")
    assert stored.startswith("scrypt$")
    assert verify_password("mot-de-passe-solide", stored)
    assert not verify_password("mauvais", stored)


def test_hash_password_unique_salt():
    assert hash_password("x" * 12) != hash_password("x" * 12)


def test_verify_password_malformed_hash():
    assert not verify_password("peu-importe", "n-importe-quoi")
    assert not verify_password("peu-importe", "")


def test_session_lifecycle(db_path):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        conn.execute(
            "INSERT INTO users (email, display_name, password_hash, is_admin, is_active, created_at) "
            "VALUES ('a@b.c', 'A', 'x', 0, 1, '2026-01-01T00:00:00+00:00')"
        )
        user_id = conn.execute("SELECT id FROM users").fetchone()["id"]
        token = create_session(conn, user_id)
        conn.commit()
        row = conn.execute("SELECT * FROM sessions").fetchone()
        assert row["token_hash"] == hash_token(token)
        assert row["token_hash"] != token  # jamais stocké en clair
        assert row["expires_at"] > row["created_at"]
        delete_session(conn, token)
        conn.commit()
        assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0
    finally:
        conn.close()
