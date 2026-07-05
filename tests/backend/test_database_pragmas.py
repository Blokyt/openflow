"""PRAGMA SQLite posés au démarrage : WAL + busy_timeout (un seul worker uvicorn)."""
from backend.core import database


def test_wal_mode_active_after_create_app(app_and_db):
    """create_app appelle init_db_pragmas : la base passe en WAL (persistant)."""
    conn = database.get_conn()
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    finally:
        conn.close()


def test_busy_timeout_on_every_connection(app_and_db):
    conn = database.get_conn()
    try:
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    finally:
        conn.close()
