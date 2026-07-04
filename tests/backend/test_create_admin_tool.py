"""Test du script de bootstrap d'un administrateur."""
import sqlite3
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent


def _run(db_path, *args):
    return subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "tools" / "create_admin.py"), *args, "--db", str(db_path)],
        capture_output=True, text=True, cwd=str(PROJECT_ROOT),
    )


def test_create_admin(db_path):
    r = _run(db_path, "vicente@bda.fr", "--name", "Vicente", "--password", "mot-de-passe-solide")
    assert r.returncode == 0, r.stderr
    conn = sqlite3.connect(str(db_path))
    row = conn.execute("SELECT is_admin, is_active FROM users WHERE email = 'vicente@bda.fr'").fetchone()
    conn.close()
    assert row == (1, 1)


def test_create_admin_duplicate_email(db_path):
    _run(db_path, "vicente@bda.fr", "--password", "mot-de-passe-solide")
    r = _run(db_path, "vicente@bda.fr", "--password", "mot-de-passe-solide")
    assert r.returncode != 0


def test_create_admin_short_password(db_path):
    r = _run(db_path, "x@y.fr", "--password", "court")
    assert r.returncode != 0
