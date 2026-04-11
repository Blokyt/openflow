"""Tests for tools/migrate.py."""
import json
import sqlite3
import subprocess
import sys
import shutil
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).parent.parent.parent
MIGRATE_SCRIPT = PROJECT_DIR / "tools" / "migrate.py"
SCHEMA_PATH = PROJECT_DIR / "tools" / "schemas" / "manifest.schema.json"

VALID_MANIFEST = {
    "id": "test_mod",
    "name": "Test Module",
    "description": "A test module",
    "version": "1.0.0",
    "origin": "custom",
    "category": "custom",
    "dependencies": [],
    "menu": {"label": "Test", "icon": "box", "position": 99},
    "api_routes": ["api.py"],
    "db_models": ["models.py"],
    "dashboard_widgets": [],
    "settings_schema": {},
}

MODELS_PY = '''\
"""Database models for test_mod module."""

migrations = {
    "1.0.0": [
        "CREATE TABLE test_items (id INTEGER PRIMARY KEY, name TEXT NOT NULL)",
    ],
}
'''


def make_project(tmp_path):
    """Set up a minimal project with the schema and a test module."""
    # Schema
    schema_dest = tmp_path / "tools" / "schemas" / "manifest.schema.json"
    schema_dest.parent.mkdir(parents=True)
    shutil.copy(SCHEMA_PATH, schema_dest)

    # Module
    mod_dir = tmp_path / "backend" / "modules" / "test_mod"
    mod_dir.mkdir(parents=True)

    manifest = {**VALID_MANIFEST}
    (mod_dir / "manifest.json").write_text(json.dumps(manifest))
    (mod_dir / "api.py").write_text("# api\n")
    (mod_dir / "models.py").write_text(MODELS_PY)

    return tmp_path


def run_migrate(project_dir):
    result = subprocess.run(
        [sys.executable, str(MIGRATE_SCRIPT), "--project-dir", str(project_dir)],
        capture_output=True,
        text=True,
    )
    return result


def test_migrate_creates_tables(tmp_path):
    """migrate.py should apply migrations and create declared tables in the DB."""
    project = make_project(tmp_path)
    result = run_migrate(project)
    assert result.returncode == 0, (
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )

    db_path = project / "data" / "openflow.db"
    assert db_path.exists(), "Database file should have been created"

    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='test_items'"
        )
        row = cur.fetchone()
        assert row is not None, "Table 'test_items' should have been created by migration"
    finally:
        conn.close()


def test_migrate_creates_backup(tmp_path):
    """Running migrate.py a second time should create a backup of the existing DB."""
    project = make_project(tmp_path)

    # First run — creates the DB
    result1 = run_migrate(project)
    assert result1.returncode == 0, (
        f"First run failed\nstdout: {result1.stdout}\nstderr: {result1.stderr}"
    )

    data_dir = project / "data"
    db_path = data_dir / "openflow.db"
    assert db_path.exists()

    # Second run — should create a backup
    result2 = run_migrate(project)
    assert result2.returncode == 0, (
        f"Second run failed\nstdout: {result2.stdout}\nstderr: {result2.stderr}"
    )

    backup_files = list(data_dir.glob("openflow.db.backup.*"))
    assert len(backup_files) >= 1, (
        f"Expected at least one backup file in {data_dir}, found: {list(data_dir.iterdir())}"
    )
