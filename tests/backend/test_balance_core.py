"""Tests for the centralized balance computation."""
import sqlite3
import pytest
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent


def _make_db(tmp_path):
    """Create a minimal test DB with required tables."""
    db = tmp_path / "test.db"
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        label TEXT NOT NULL,
        amount REAL NOT NULL,
        from_entity_id INTEGER,
        to_entity_id INTEGER
    )""")
    conn.execute("""CREATE TABLE entity_balance_refs (
        entity_id INTEGER PRIMARY KEY,
        reference_date TEXT NOT NULL,
        reference_amount REAL NOT NULL DEFAULT 0.0,
        updated_at TEXT NOT NULL
    )""")
    conn.execute("""CREATE TABLE entities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        type TEXT NOT NULL DEFAULT 'internal',
        parent_id INTEGER
    )""")
    conn.commit()
    return conn


def test_legacy_balance_empty(tmp_path):
    from backend.core.balance import compute_legacy_balance
    conn = _make_db(tmp_path)
    result = compute_legacy_balance(conn, str(PROJECT_ROOT / "config.test.yaml"))
    conn.close()
    assert result["transactions_sum"] == pytest.approx(0.0)


def test_legacy_balance_with_transactions(tmp_path):
    from backend.core.balance import compute_legacy_balance
    conn = _make_db(tmp_path)
    conn.execute("INSERT INTO transactions (date, label, amount) VALUES ('2025-06-01', 'A', 500)")
    conn.execute("INSERT INTO transactions (date, label, amount) VALUES ('2025-06-02', 'B', -200)")
    conn.commit()
    result = compute_legacy_balance(conn, str(PROJECT_ROOT / "config.test.yaml"))
    conn.close()
    assert result["transactions_sum"] == pytest.approx(300.0)


def test_entity_balance_empty(tmp_path):
    from backend.core.balance import compute_entity_balance
    conn = _make_db(tmp_path)
    conn.execute("INSERT INTO entities (id, name, type) VALUES (1, 'BDA', 'internal')")
    conn.execute("INSERT INTO entity_balance_refs (entity_id, reference_date, reference_amount, updated_at) VALUES (1, '2025-01-01', 1000, '2025-01-01')")
    conn.commit()
    result = compute_entity_balance(conn, 1)
    conn.close()
    assert result["balance"] == pytest.approx(1000.0)
    assert result["reference_amount"] == pytest.approx(1000.0)
    assert result["transactions_sum"] == pytest.approx(0.0)


def test_entity_balance_with_transactions(tmp_path):
    from backend.core.balance import compute_entity_balance
    conn = _make_db(tmp_path)
    conn.execute("INSERT INTO entities (id, name, type) VALUES (1, 'BDA', 'internal')")
    conn.execute("INSERT INTO entities (id, name, type) VALUES (2, 'Fournisseur', 'external')")
    conn.execute("INSERT INTO entity_balance_refs (entity_id, reference_date, reference_amount, updated_at) VALUES (1, '2025-01-01', 1000, '2025-01-01')")
    conn.execute("INSERT INTO transactions (date, label, amount, from_entity_id, to_entity_id) VALUES ('2025-06-01', 'Vente', 500, 2, 1)")
    conn.execute("INSERT INTO transactions (date, label, amount, from_entity_id, to_entity_id) VALUES ('2025-06-02', 'Achat', -300, 1, 2)")
    conn.commit()
    result = compute_entity_balance(conn, 1)
    conn.close()
    assert result["balance"] == pytest.approx(1200.0)


def test_entity_balance_ignores_unrelated(tmp_path):
    from backend.core.balance import compute_entity_balance
    conn = _make_db(tmp_path)
    conn.execute("INSERT INTO entities (id, name, type) VALUES (1, 'BDA', 'internal')")
    conn.execute("INSERT INTO entities (id, name, type) VALUES (2, 'Club', 'internal')")
    conn.execute("INSERT INTO entities (id, name, type) VALUES (3, 'Ext', 'external')")
    conn.execute("INSERT INTO entity_balance_refs (entity_id, reference_date, reference_amount, updated_at) VALUES (1, '2025-01-01', 0, '2025-01-01')")
    conn.execute("INSERT INTO transactions (date, label, amount, from_entity_id, to_entity_id) VALUES ('2025-06-01', 'X', -100, 2, 3)")
    conn.commit()
    result = compute_entity_balance(conn, 1)
    conn.close()
    assert result["balance"] == pytest.approx(0.0)


def test_consolidated_balance(tmp_path):
    from backend.core.balance import compute_consolidated_balance
    conn = _make_db(tmp_path)
    conn.execute("INSERT INTO entities (id, name, type, parent_id) VALUES (1, 'BDA', 'internal', NULL)")
    conn.execute("INSERT INTO entities (id, name, type, parent_id) VALUES (2, 'Gastro', 'internal', 1)")
    conn.execute("INSERT INTO entities (id, name, type) VALUES (3, 'Ext', 'external')")
    conn.execute("INSERT INTO entity_balance_refs (entity_id, reference_date, reference_amount, updated_at) VALUES (1, '2025-01-01', 1000, '2025-01-01')")
    conn.execute("INSERT INTO entity_balance_refs (entity_id, reference_date, reference_amount, updated_at) VALUES (2, '2025-01-01', 500, '2025-01-01')")
    conn.execute("INSERT INTO transactions (date, label, amount, from_entity_id, to_entity_id) VALUES ('2025-06-01', 'Don', 200, 3, 1)")
    conn.execute("INSERT INTO transactions (date, label, amount, from_entity_id, to_entity_id) VALUES ('2025-06-02', 'Dep', -100, 2, 3)")
    conn.commit()
    result = compute_consolidated_balance(conn, 1)
    conn.close()
    assert result["own_balance"] == pytest.approx(1200.0)
    assert result["consolidated_balance"] == pytest.approx(1600.0)


def test_entity_balance_no_ref(tmp_path):
    from backend.core.balance import compute_entity_balance
    conn = _make_db(tmp_path)
    conn.execute("INSERT INTO entities (id, name, type) VALUES (1, 'BDA', 'internal')")
    conn.execute("INSERT INTO transactions (date, label, amount, from_entity_id, to_entity_id) VALUES ('2025-06-01', 'In', 300, 2, 1)")
    conn.commit()
    result = compute_entity_balance(conn, 1)
    conn.close()
    assert result["reference_amount"] == pytest.approx(0.0)
    assert result["balance"] == pytest.approx(300.0)
