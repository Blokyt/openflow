"""Centralized balance computation for OpenFlow entities."""
import sqlite3
from typing import Optional

from backend.core.config import load_config


def compute_legacy_balance(conn: sqlite3.Connection, config_path: str) -> dict:
    """Backward-compatible balance: reference_amount + SUM(transactions) since reference_date.

    Used by modules not yet entity-aware. Returns same shape as the old endpoints.
    """
    try:
        config = load_config(config_path)
        reference_amount = config.balance.amount
        reference_date = config.balance.date
    except Exception:
        reference_amount = 0.0
        reference_date = None

    if reference_date:
        total = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE date >= ?",
            (reference_date,),
        ).fetchone()[0]
    else:
        total = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM transactions"
        ).fetchone()[0]

    return {
        "balance": reference_amount + total,
        "reference_amount": reference_amount,
        "reference_date": reference_date,
        "transactions_sum": total,
    }


def compute_entity_balance(
    conn: sqlite3.Connection,
    entity_id: int,
    as_of_date: Optional[str] = None,
) -> dict:
    """Compute balance for an internal entity: reference + incoming - outgoing.

    Incoming = SUM(amount) WHERE to_entity_id = entity_id AND amount > 0
    Outgoing = SUM(ABS(amount)) WHERE from_entity_id = entity_id AND amount < 0
    """
    ref = conn.execute(
        "SELECT reference_date, reference_amount FROM entity_balance_refs WHERE entity_id = ?",
        (entity_id,),
    ).fetchone()

    reference_amount = ref["reference_amount"] if ref else 0.0
    reference_date = ref["reference_date"] if ref else None

    conditions_in = ["to_entity_id = ?"]
    conditions_out = ["from_entity_id = ?", "amount < 0"]
    params_in = [entity_id]
    params_out = [entity_id]

    if reference_date:
        conditions_in.append("date >= ?")
        conditions_out.append("date >= ?")
        params_in.append(reference_date)
        params_out.append(reference_date)
    if as_of_date:
        conditions_in.append("date <= ?")
        conditions_out.append("date <= ?")
        params_in.append(as_of_date)
        params_out.append(as_of_date)

    where_in = " AND ".join(conditions_in)
    where_out = " AND ".join(conditions_out)

    try:
        incoming = conn.execute(
            f"SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE {where_in}",
            params_in,
        ).fetchone()[0]

        outgoing = conn.execute(
            f"SELECT COALESCE(SUM(ABS(amount)), 0) FROM transactions WHERE {where_out}",
            params_out,
        ).fetchone()[0]
    except Exception:
        # from_entity_id / to_entity_id columns not yet added (Task 4)
        incoming = 0.0
        outgoing = 0.0

    transactions_sum = incoming - outgoing

    return {
        "entity_id": entity_id,
        "balance": reference_amount + transactions_sum,
        "reference_amount": reference_amount,
        "reference_date": reference_date,
        "transactions_sum": transactions_sum,
    }


def compute_consolidated_balance(
    conn: sqlite3.Connection,
    entity_id: int,
    as_of_date: Optional[str] = None,
) -> dict:
    """Consolidated balance: own + all descendant internal entities (recursive CTE)."""
    rows = conn.execute(
        """WITH RECURSIVE tree(id) AS (
            SELECT ? UNION ALL
            SELECT e.id FROM entities e JOIN tree t ON e.parent_id = t.id
            WHERE e.type = 'internal'
        ) SELECT id FROM tree""",
        (entity_id,),
    ).fetchall()

    own = compute_entity_balance(conn, entity_id, as_of_date)
    children = []
    consolidated = own["balance"]

    for row in rows:
        eid = row[0] if isinstance(row, tuple) else row["id"]
        if eid != entity_id:
            child_bal = compute_entity_balance(conn, eid, as_of_date)
            children.append(child_bal)
            consolidated += child_bal["balance"]

    return {
        "entity_id": entity_id,
        "own_balance": own["balance"],
        "consolidated_balance": consolidated,
        "children": children,
    }


def compute_entity_balance_for_period(
    conn: sqlite3.Connection,
    entity_id: int,
    start_date: str,
    end_date: str,
    opening: float = 0.0,
) -> dict:
    """Realized flow and closing balance for an entity on a date interval.

    Uses the same sign convention as compute_entity_balance:
        net = SUM(amount when to_entity=entity) + SUM(amount when from_entity=entity AND amount<0)

    Returns {opening, realized, closing}.
    """
    row = conn.execute(
        """SELECT COALESCE(SUM(CASE
                WHEN to_entity_id = ? THEN amount
                WHEN from_entity_id = ? AND amount < 0 THEN amount
                ELSE 0
            END), 0) AS realized
           FROM transactions
           WHERE date BETWEEN ? AND ?
             AND (from_entity_id = ? OR to_entity_id = ?)""",
        (entity_id, entity_id, start_date, end_date, entity_id, entity_id),
    ).fetchone()
    realized = row[0] if not hasattr(row, "keys") else row["realized"]
    return {
        "opening": opening,
        "realized": realized,
        "closing": opening + realized,
    }
