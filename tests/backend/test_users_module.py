"""Tests du module users : migrations et manifest."""
import json
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent


def test_users_tables_exist(db_path):
    conn = sqlite3.connect(str(db_path))
    try:
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    finally:
        conn.close()
    assert {"users", "sessions", "user_entity_roles", "invitations"} <= tables


def test_users_manifest_valid():
    manifest_path = PROJECT_ROOT / "backend" / "modules" / "users" / "manifest.json"
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)
    assert manifest["id"] == "users"
    assert manifest["category"] == "core"
    assert manifest["requires_admin"] is True
    assert "api.py" in manifest["api_routes"]
