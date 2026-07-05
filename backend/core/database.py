"""Centralized database connection for all OpenFlow modules."""
import sqlite3
from pathlib import Path

_db_path: Path = Path(__file__).parent.parent.parent / "data" / "openflow.db"


def set_db_path(path: str | Path) -> None:
    """Set the database path. Called once by main.py at startup."""
    global _db_path
    _db_path = Path(path)


def get_db_path() -> Path:
    """Return the current database path."""
    return _db_path


def get_conn() -> sqlite3.Connection:
    """Open a connection to the shared SQLite database."""
    conn = sqlite3.connect(str(_db_path), timeout=5.0)
    conn.row_factory = sqlite3.Row
    # Attend jusqu'à 5 s si la base est verrouillée par une autre connexion
    # (un seul worker uvicorn, mais plusieurs requêtes peuvent se chevaucher).
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init_db_pragmas() -> None:
    """Pose les PRAGMA persistants au démarrage de l'app.

    journal_mode=WAL est stocké dans le fichier : le poser une fois suffit,
    toutes les connexions suivantes en héritent (lectures non bloquées par
    les écritures). Appelé par create_app après set_db_path.
    """
    _db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_db_path))
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    finally:
        conn.close()


def row_to_dict(row: sqlite3.Row) -> dict:
    """Convert a sqlite3.Row to a plain dict."""
    return dict(row)
