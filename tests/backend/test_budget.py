"""Tests for the Budget & Exercices module (1.2.0)."""
import os, sys
import sqlite3
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


def test_budget_tables_exist(client_and_db):
    """After migration 1.2.0, the three new tables exist and legacy `budgets` is gone."""
    _, db_path = client_and_db
    conn = sqlite3.connect(str(db_path))
    try:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
    finally:
        conn.close()
    assert "fiscal_years" in tables
    assert "fiscal_year_opening_balances" in tables
    assert "budget_allocations" in tables
    assert "budgets" not in tables  # legacy dropped
