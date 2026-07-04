"""Périmètre d'entités : héritage sur le sous-arbre via CTE récursive."""
import sqlite3

import pytest
from fastapi import HTTPException

from backend.core.auth import get_allowed_entity_ids, require_entity_access

NOW = "2026-01-01T00:00:00+00:00"


def _entity(conn, name, parent_id=None):
    cur = conn.execute(
        "INSERT INTO entities (name, type, parent_id, is_default, color, position, created_at, updated_at) "
        "VALUES (?, 'internal', ?, 0, '#000000', 0, ?, ?)",
        (name, parent_id, NOW, NOW),
    )
    return cur.lastrowid


def _conn(db_path):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def test_admin_sees_everything(db_path):
    conn = _conn(db_path)
    try:
        assert get_allowed_entity_ids(conn, {"id": 1, "is_admin": 1}) is None
    finally:
        conn.close()


def test_subtree_inheritance(db_path):
    conn = _conn(db_path)
    try:
        bda = _entity(conn, "BDA")
        gastro = _entity(conn, "Gastronomine", bda)
        cave = _entity(conn, "Cave", gastro)
        ccmp = _entity(conn, "CCMP", bda)
        conn.execute(
            "INSERT INTO users (email, display_name, password_hash, is_admin, is_active, created_at) "
            "VALUES ('t@c.fr', 'T', 'x', 0, 1, ?)", (NOW,))
        uid = conn.execute("SELECT id FROM users WHERE email='t@c.fr'").fetchone()["id"]
        conn.execute(
            "INSERT INTO user_entity_roles (user_id, entity_id, role, created_at) "
            "VALUES (?, ?, 'treasurer', ?)", (uid, gastro, NOW))
        conn.commit()
        allowed = get_allowed_entity_ids(conn, {"id": uid, "is_admin": 0})
        assert allowed == {gastro, cave}   # le sous-arbre, pas le parent ni le frère
        assert bda not in allowed and ccmp not in allowed
    finally:
        conn.close()


def test_no_role_no_access(db_path):
    conn = _conn(db_path)
    try:
        conn.execute(
            "INSERT INTO users (email, display_name, password_hash, is_admin, is_active, created_at) "
            "VALUES ('v@c.fr', 'V', 'x', 0, 1, ?)", (NOW,))
        uid = conn.execute("SELECT id FROM users WHERE email='v@c.fr'").fetchone()["id"]
        conn.commit()
        assert get_allowed_entity_ids(conn, {"id": uid, "is_admin": 0}) == set()
    finally:
        conn.close()


def test_require_entity_access(db_path):
    conn = _conn(db_path)
    try:
        bda = _entity(conn, "BDA")
        gastro = _entity(conn, "Gastronomine", bda)
        conn.execute(
            "INSERT INTO users (email, display_name, password_hash, is_admin, is_active, created_at) "
            "VALUES ('t2@c.fr', 'T', 'x', 0, 1, ?)", (NOW,))
        uid = conn.execute("SELECT id FROM users WHERE email='t2@c.fr'").fetchone()["id"]
        conn.execute(
            "INSERT INTO user_entity_roles (user_id, entity_id, role, created_at) "
            "VALUES (?, ?, 'viewer', ?)", (uid, gastro, NOW))
        conn.commit()
        user = {"id": uid, "is_admin": 0}
        require_entity_access(conn, user, gastro)          # ne lève pas
        with pytest.raises(HTTPException) as exc:
            require_entity_access(conn, user, bda)
        assert exc.value.status_code == 403
        require_entity_access(conn, {"id": 0, "is_admin": 1}, bda)  # admin passe
    finally:
        conn.close()
