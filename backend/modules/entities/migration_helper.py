"""Backfill existing transactions with from_entity_id / to_entity_id."""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from backend.core.config import load_config


def run_backfill(conn: sqlite3.Connection, config_path: str):
    """
    1. Create root entity from config.yaml if no entities exist
    2. Create 'Divers' external entity if not exists
    3. Backfill transactions:
       - amount < 0: from=root, to=divers
       - amount >= 0: from=divers, to=root
    """
    now = datetime.now(timezone.utc).isoformat()

    # Check if entities already exist
    count = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
    if count > 0:
        return {"status": "skipped", "reason": "entities already exist"}

    # Create root entity from config
    try:
        config = load_config(config_path)
        name = config.entity.name
        ref_date = config.balance.date
        ref_amount = config.balance.amount
    except Exception:
        name = "Mon Entite"
        ref_date = "2025-01-01"
        ref_amount = 0.0

    conn.execute(
        """INSERT INTO entities (name, description, type, is_default, created_at, updated_at)
           VALUES (?, 'Entite racine', 'internal', 1, ?, ?)""",
        (name, now, now),
    )
    root_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    conn.execute(
        """INSERT INTO entity_balance_refs (entity_id, reference_date, reference_amount, updated_at)
           VALUES (?, ?, ?, ?)""",
        (root_id, ref_date, ref_amount, now),
    )

    # Create Divers entity
    conn.execute(
        """INSERT INTO entities (name, description, type, is_divers, created_at, updated_at)
           VALUES ('Divers', 'Tiers non identifie', 'external', 1, ?, ?)""",
        (now, now),
    )
    divers_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Backfill transactions
    # Expenses: from=root, to=divers
    conn.execute(
        "UPDATE transactions SET from_entity_id = ?, to_entity_id = ? WHERE amount < 0 AND from_entity_id IS NULL",
        (root_id, divers_id),
    )
    # Income: from=divers, to=root
    conn.execute(
        "UPDATE transactions SET from_entity_id = ?, to_entity_id = ? WHERE amount >= 0 AND from_entity_id IS NULL",
        (divers_id, root_id),
    )

    conn.commit()

    updated = conn.execute("SELECT COUNT(*) FROM transactions WHERE from_entity_id IS NOT NULL").fetchone()[0]
    return {"status": "done", "root_id": root_id, "divers_id": divers_id, "transactions_updated": updated}
