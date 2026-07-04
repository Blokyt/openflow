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
from backend.core.rate_limit import limiter
from backend.core.auth import SESSION_COOKIE, hash_token
from backend.core.auth import hash_password as _hash_password
from tools.migrate import ensure_system_tables, load_migrations, apply_migrations

ADMIN_EMAIL = "admin@test.local"
ADMIN_SESSION_TOKEN = "test-admin-session-token"
# Hash précalculé UNE fois (scrypt coûte ~100 ms), mot de passe "admin-test-password".
_ADMIN_HASH = _hash_password("admin-test-password")

FAR_FUTURE = "2099-01-01T00:00:00+00:00"
PAST = "2020-01-01T00:00:00+00:00"


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Reset le compteur du limiter slowapi entre chaque test.

    Le limiter est un singleton global (MemoryStorage). Sans reset, les
    compteurs s'accumulent entre tests de la même session pytest et font
    passer le seuil de 5/15min bien avant le test dédié au rate limiting.
    """
    limiter._storage.reset()
    yield
    limiter._storage.reset()


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
    conn.execute(
        "INSERT INTO users (email, display_name, password_hash, is_admin, is_active, created_at) "
        "VALUES (?, 'Admin Test', ?, 1, 1, ?)",
        (ADMIN_EMAIL, _ADMIN_HASH, PAST),
    )
    conn.commit()
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


def _open_session(db_path, email, token):
    """Insère une session directement en DB (évite un login scrypt par test).

    INSERT OR IGNORE : certains tests dépendent à la fois de `client` et de
    `client_and_db` (via une fixture intermédiaire) sur le même app_and_db ;
    les deux fixtures posent alors la même session admin, ce qui violerait
    l'unicité de token_hash sans cet idempotence.
    """
    conn = sqlite3.connect(str(db_path))
    try:
        user_id = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()[0]
        conn.execute(
            "INSERT OR IGNORE INTO sessions (token_hash, user_id, created_at, expires_at, last_seen_at, user_agent) "
            "VALUES (?, ?, ?, ?, ?, '')",
            (hash_token(token), user_id, PAST, FAR_FUTURE, PAST),
        )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def app_and_db(db_path):
    app = create_app(config_path="config.test.yaml", db_path=str(db_path), bootstrap=False)
    return app, db_path


@pytest.fixture
def client(app_and_db):
    """TestClient authentifié en admin, backé par une DB isolée."""
    app, db_path = app_and_db
    tc = TestClient(app)
    _open_session(db_path, ADMIN_EMAIL, ADMIN_SESSION_TOKEN)
    tc.cookies.set(SESSION_COOKIE, ADMIN_SESSION_TOKEN)
    _install_default_entity_injection(tc, db_path)
    return tc


@pytest.fixture
def client_and_db(app_and_db):
    app, db_path = app_and_db
    tc = TestClient(app)
    _open_session(db_path, ADMIN_EMAIL, ADMIN_SESSION_TOKEN)
    tc.cookies.set(SESSION_COOKIE, ADMIN_SESSION_TOKEN)
    _install_default_entity_injection(tc, db_path)
    return tc, db_path


@pytest.fixture
def login_as(app_and_db):
    """Fabrique un TestClient authentifié pour un user arbitraire.

    roles : liste de tuples (entity_id, "treasurer" | "viewer").
    """
    app, db_path = app_and_db
    counter = {"n": 0}

    def _make(email, *, is_admin=False, roles=None):
        counter["n"] += 1
        token = f"test-session-{counter['n']}-{email}"
        conn = sqlite3.connect(str(db_path))
        try:
            now = PAST
            cur = conn.execute(
                "INSERT INTO users (email, display_name, password_hash, is_admin, is_active, created_at) "
                "VALUES (?, ?, 'x', ?, 1, ?)",
                (email.lower(), email.split("@")[0], 1 if is_admin else 0, now),
            )
            user_id = cur.lastrowid
            for entity_id, role in roles or []:
                conn.execute(
                    "INSERT INTO user_entity_roles (user_id, entity_id, role, created_at) VALUES (?, ?, ?, ?)",
                    (user_id, entity_id, role, now),
                )
            conn.execute(
                "INSERT INTO sessions (token_hash, user_id, created_at, expires_at, last_seen_at, user_agent) "
                "VALUES (?, ?, ?, ?, ?, '')",
                (hash_token(token), user_id, now, FAR_FUTURE, now),
            )
            conn.commit()
        finally:
            conn.close()
        tc = TestClient(app)
        tc.cookies.set(SESSION_COOKIE, token)
        return tc

    return _make


