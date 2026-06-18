"""Drop tables left behind by the 2026-06-18 reduction to the loi 1901 core.

Removes the data tables of the deleted modules (mandates, invoices, grants,
members, bank_reconciliation, fec_export, annotations, smart_import, audit,
export, multi_users). Idempotent: uses DROP TABLE IF EXISTS, so re-running is
safe. Make a backup of data/openflow.db before running (tools/migrate.py and
the manual copy created during the reduction both produce one).
"""
import sqlite3
from pathlib import Path

ORPHAN_TABLES = [
    "mandates",
    "invoices",
    "invoice_lines",
    "grants",
    "grant_expenses",
    "members",
    "membership_fees",
    "bank_statements",
    "audit_log",
    "annotations",
    "users",
    "sessions",
    "user_entities",
]

DB = Path("data/openflow.db")


def main() -> None:
    conn = sqlite3.connect(str(DB))
    try:
        existing = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        dropped = []
        for tbl in ORPHAN_TABLES:
            if tbl in existing:
                conn.execute(f'DROP TABLE IF EXISTS "{tbl}"')
                dropped.append(tbl)
        conn.commit()
        print("Dropped:", ", ".join(dropped) if dropped else "(none)")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
