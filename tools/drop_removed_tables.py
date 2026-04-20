"""One-shot: drop tables for modules removed in 2026-04-20 cleanup."""
import sqlite3
from pathlib import Path

REMOVED_TABLES = [
    "alert_rules",
    "accounts",
    "divisions",
    "bank_statements",
    "grants",
    "tax_receipts",
    "recurring_transactions",
    "transfers",  # was for multi_accounts
]

db = Path("data/openflow.db")
conn = sqlite3.connect(db)
for tbl in REMOVED_TABLES:
    try:
        conn.execute(f"DROP TABLE IF EXISTS {tbl}")
        print(f"Dropped: {tbl}")
    except sqlite3.OperationalError as e:
        print(f"Skipped {tbl}: {e}")
conn.commit()
conn.close()
print("Done.")
