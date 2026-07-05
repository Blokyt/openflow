"""Module submissions : création et lectures scopées."""
import sqlite3

NOW = "2026-01-01T00:00:00+00:00"


def _entity(db_path, name, type="internal", parent_id=None):
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute(
            "INSERT INTO entities (name, type, parent_id, is_default, color, position, created_at, updated_at) "
            "VALUES (?, ?, ?, 0, '#000000', 0, ?, ?)",
            (name, type, parent_id, NOW, NOW),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def test_submissions_module_active(client):
    mods = client.get("/api/modules").json()
    assert any(m["id"] == "submissions" for m in mods)


def test_submissions_table_exists(client_and_db):
    _, db_path = client_and_db
    conn = sqlite3.connect(str(db_path))
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(transaction_submissions)").fetchall()}
    finally:
        conn.close()
    assert {
        "id", "date", "label", "description", "amount", "category_id",
        "entity_id", "counterparty_entity_id", "direction", "status",
        "submitted_by", "reviewed_by", "reviewed_at", "review_comment",
        "transaction_id", "created_at", "updated_at",
    } <= cols
