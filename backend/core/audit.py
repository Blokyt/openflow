"""Lightweight audit helper. Safe to call unconditionally — noop if the
audit_log table doesn't exist (e.g. audit module disabled).
"""
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def record_audit(
    conn: sqlite3.Connection,
    action: str,
    table_name: str,
    record_id: Optional[int],
    old_value: Any = None,
    new_value: Any = None,
    user_name: str = "",
) -> None:
    """Insert an audit_log entry. Silently noop when the table is missing."""
    if not _table_exists(conn, "audit_log"):
        return
    conn.execute(
        """INSERT INTO audit_log
           (timestamp, user_name, action, table_name, record_id, old_value, new_value)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            datetime.now(timezone.utc).isoformat(),
            user_name,
            action,
            table_name,
            record_id,
            json.dumps(old_value, ensure_ascii=False, default=str) if old_value is not None else None,
            json.dumps(new_value, ensure_ascii=False, default=str) if new_value is not None else None,
        ),
    )
