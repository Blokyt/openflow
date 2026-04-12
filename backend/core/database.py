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
    conn = sqlite3.connect(str(_db_path))
    conn.row_factory = sqlite3.Row
    return conn


def row_to_dict(row: sqlite3.Row) -> dict:
    """Convert a sqlite3.Row to a plain dict."""
    return dict(row)
