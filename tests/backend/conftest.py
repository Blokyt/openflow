"""Shared fixtures for backend tests — isolated DB per test."""
import json
import os
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
        try:
            migrations = load_migrations(models_path)
        except Exception:
            continue
        apply_migrations(conn, module_id, migrations, None, target_version)
    conn.close()


@pytest.fixture
def db_path(tmp_path):
    """Return the path to the isolated test DB (for tests that need raw access)."""
    db_file = tmp_path / "test.db"
    _init_db(str(db_file))
    return db_file


@pytest.fixture
def client(db_path):
    """TestClient backed by the same isolated DB as db_path."""
    app = create_app(config_path="config.test.yaml", db_path=str(db_path))
    return TestClient(app)


@pytest.fixture
def client_and_db(db_path):
    """TestClient + raw DB path for tests that need both."""
    app = create_app(config_path="config.test.yaml", db_path=str(db_path))
    return TestClient(app), db_path
