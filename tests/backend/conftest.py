"""Shared fixtures for backend tests — isolated DB per test."""
import json
import shutil
import sqlite3
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.main import create_app
from tools.migrate import ensure_system_tables, load_migrations, apply_migrations


def _init_db(db_path: str):
    """Create a fresh DB with all module tables."""
    conn = sqlite3.connect(db_path)
    ensure_system_tables(conn)
    modules_dir = PROJECT_ROOT / "backend" / "modules"
    for mod_dir in sorted(modules_dir.iterdir()):
        if not mod_dir.is_dir():
            continue
        manifest_path = mod_dir / "manifest.json"
        models_path = mod_dir / "models.py"
        if not manifest_path.exists() or not models_path.exists():
            continue
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
        module_id = manifest.get("id", mod_dir.name)
        target_version = manifest.get("version", "1.0.0")
        migrations = load_migrations(models_path)
        apply_migrations(conn, module_id, migrations, None, target_version)
    conn.close()


@pytest.fixture(scope="session")
def _db_template(tmp_path_factory):
    """Build the fully-migrated DB once for the entire test session."""
    template = tmp_path_factory.mktemp("template") / "template.db"
    _init_db(str(template))
    return template


@pytest.fixture
def db_path(tmp_path, _db_template):
    """Copy the template DB — avoids re-running migrations per test."""
    db_file = tmp_path / "test.db"
    shutil.copy2(str(_db_template), str(db_file))
    return db_file


def _install_default_entity_injection(client: TestClient, db_path: Path) -> None:
    """Ensure POST/PUT /api/transactions/ calls that omit from/to get a default pair.

    The API enforces non-null from_entity_id/to_entity_id (see bug #1 fix). Many
    legacy tests seed transactions via the API without caring about entity
    structure; rather than rewriting each call site, we transparently inject a
    default pair of entities when omitted. Tests that pass explicit IDs are
    untouched.
    """
    import sqlite3 as _sqlite3
    from datetime import datetime, timezone as _tz

    state = {"from_id": None, "to_id": None}

    def _ensure_default_pair():
        if state["from_id"] is not None:
            return state["from_id"], state["to_id"]
        conn = _sqlite3.connect(str(db_path))
        try:
            now = datetime.now(_tz.utc).isoformat()
            cur = conn.execute(
                "INSERT INTO entities (name, type, parent_id, is_default, color, position, created_at, updated_at) "
                "VALUES (?, 'internal', NULL, 0, '#6B7280', 900, ?, ?)",
                ("_TestDefaultFrom", now, now),
            )
            from_id = cur.lastrowid
            cur = conn.execute(
                "INSERT INTO entities (name, type, parent_id, is_default, color, position, created_at, updated_at) "
                "VALUES (?, 'external', NULL, 0, '#6B7280', 901, ?, ?)",
                ("_TestDefaultTo", now, now),
            )
            to_id = cur.lastrowid
            conn.commit()
        finally:
            conn.close()
        state["from_id"] = from_id
        state["to_id"] = to_id
        return from_id, to_id

    original_post = client.post
    original_put = client.put

    def _inject(payload):
        if not isinstance(payload, dict):
            return payload
        if "from_entity_id" in payload and "to_entity_id" in payload:
            return payload
        from_id, to_id = _ensure_default_pair()
        payload = dict(payload)
        payload.setdefault("from_entity_id", from_id)
        payload.setdefault("to_entity_id", to_id)
        return payload

    def patched_post(url, *args, **kwargs):
        if url == "/api/transactions/" and "json" in kwargs:
            kwargs["json"] = _inject(kwargs["json"])
        return original_post(url, *args, **kwargs)

    def patched_put(url, *args, **kwargs):
        return original_put(url, *args, **kwargs)

    client.post = patched_post  # type: ignore[method-assign]
    client.put = patched_put  # type: ignore[method-assign]


@pytest.fixture
def client(db_path):
    """TestClient backed by the same isolated DB as db_path."""
    app = create_app(config_path="config.test.yaml", db_path=str(db_path), bootstrap=False)
    tc = TestClient(app)
    _install_default_entity_injection(tc, db_path)
    return tc


@pytest.fixture
def client_and_db(db_path):
    """TestClient + raw DB path for tests that need both."""
    app = create_app(config_path="config.test.yaml", db_path=str(db_path), bootstrap=False)
    tc = TestClient(app)
    _install_default_entity_injection(tc, db_path)
    return tc, db_path


@pytest.fixture
def authed_client(db_path):
    """TestClient with an admin user already created, logged in, and assigned
    as tresorier on the root entity (so is_root_admin() returns True).

    Use this fixture for tests that hit protected endpoints when multi_users
    is enabled, so the auth middleware lets requests through.
    """
    import sqlite3 as _sqlite3
    from datetime import datetime, timezone as _tz

    app = create_app(config_path="config.test.yaml", db_path=str(db_path), bootstrap=False)
    c = TestClient(app)

    # Create the first admin (public — no users yet, middleware skips)
    user_resp = c.post("/api/multi_users/", json={
        "username": "_test_admin",
        "password": "_test_pass_123",
        "role": "admin",
    })
    user_id = user_resp.json()["id"]

    # Ensure a root entity exists and assign tresorier role to the admin.
    # We do this directly via the DB (before login so is_root_admin works).
    conn = _sqlite3.connect(str(db_path))
    conn.row_factory = _sqlite3.Row
    try:
        # Check if a root (parent_id IS NULL, type='internal', is_default=1) entity exists
        root = conn.execute(
            "SELECT id FROM entities WHERE parent_id IS NULL AND type='internal' AND is_default=1"
        ).fetchone()
        if root is None:
            now = datetime.now(_tz.utc).isoformat()
            cur = conn.execute(
                "INSERT INTO entities (name, type, parent_id, is_default, color, position, created_at, updated_at) "
                "VALUES (?, 'internal', NULL, 1, '#6B7280', 0, ?, ?)",
                ("Root", now, now),
            )
            conn.commit()
            root_id = cur.lastrowid
        else:
            root_id = root["id"]
        # Assign tresorier on root entity
        conn.execute(
            "INSERT OR REPLACE INTO user_entities (user_id, entity_id, role) VALUES (?, ?, 'tresorier')",
            (user_id, root_id),
        )
        conn.commit()
    finally:
        conn.close()

    # Login to obtain session cookie
    c.post("/api/multi_users/login", json={
        "username": "_test_admin",
        "password": "_test_pass_123",
    })
    return c
