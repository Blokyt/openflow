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


def _get_balance_mode(conn: sqlite3.Connection, entity_id: int) -> str:
    """Return the balance_mode for an entity, defaulting to 'own'."""
    try:
        row = conn.execute(
            "SELECT balance_mode FROM entities WHERE id = ?", (entity_id,)
        ).fetchone()
        if not row:
            return "own"
        # Handle both sqlite3.Row and plain tuple
        try:
            return row["balance_mode"] if row["balance_mode"] else "own"
        except (IndexError, TypeError):
            return row[0] if row[0] else "own"
    except Exception:
        return "own"


def _compute_aggregate_consolidated(
    conn: sqlite3.Connection,
    entity_id: int,
    as_of_date: Optional[str] = None,
) -> dict:
    """For an aggregate-mode entity, consolidated = ref + external-tx deltas on subtree.

    'External' means transactions that cross the subtree boundary (one side inside,
    the other outside). Internal transfers between subtree members are ignored.
    """
    ref = conn.execute(
        "SELECT reference_date, reference_amount FROM entity_balance_refs WHERE entity_id = ?",
        (entity_id,),
    ).fetchone()
    reference_amount = ref["reference_amount"] if ref else 0.0
    reference_date = ref["reference_date"] if ref else None

    # Build full subtree of internal entities
    subtree = [
        row[0] for row in conn.execute(
            """WITH RECURSIVE tree(id) AS (
                   SELECT ? UNION ALL
                   SELECT e.id FROM entities e JOIN tree t ON e.parent_id = t.id
                   WHERE e.type = 'internal'
               ) SELECT id FROM tree""",
            (entity_id,),
        ).fetchall()
    ]
    placeholders = ",".join("?" * len(subtree))

    # Incoming: to_entity in subtree, from_entity NOT in subtree
    conds_in = [
        f"to_entity_id IN ({placeholders})",
        f"from_entity_id NOT IN ({placeholders})",
    ]
    params_in = list(subtree) + list(subtree)
    if reference_date:
        conds_in.append("date >= ?")
        params_in.append(reference_date)
    if as_of_date:
        conds_in.append("date <= ?")
        params_in.append(as_of_date)
    incoming = conn.execute(
        f"SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE {' AND '.join(conds_in)}",
        params_in,
    ).fetchone()[0]

    # Outgoing: from_entity in subtree, to_entity NOT in subtree, amount < 0
    conds_out = [
        f"from_entity_id IN ({placeholders})",
        f"to_entity_id NOT IN ({placeholders})",
        "amount < 0",
    ]
    params_out = list(subtree) + list(subtree)
    if reference_date:
        conds_out.append("date >= ?")
        params_out.append(reference_date)
    if as_of_date:
        conds_out.append("date <= ?")
        params_out.append(as_of_date)
    outgoing = conn.execute(
        f"SELECT COALESCE(SUM(ABS(amount)), 0) FROM transactions WHERE {' AND '.join(conds_out)}",
        params_out,
    ).fetchone()[0]

    external_delta = incoming - outgoing
    consolidated = reference_amount + external_delta

    # Compute children consolidated for own_balance derivation
    children = []
    for row in conn.execute(
        "SELECT id FROM entities WHERE parent_id = ? AND type = 'internal'", (entity_id,)
    ).fetchall():
        child_id = row[0] if isinstance(row, tuple) else row["id"]
        child_c = compute_consolidated_balance(conn, child_id, as_of_date)
        children.append(child_c)

    own_balance = consolidated - sum(c["consolidated_balance"] for c in children)

    return {
        "entity_id": entity_id,
        "balance": consolidated,  # alias for compat
        "consolidated_balance": consolidated,
        "own_balance": own_balance,
        "reference_amount": reference_amount,
        "reference_date": reference_date,
        "external_delta": external_delta,
        "children": children,
        "mode": "aggregate",
    }


def compute_entity_balance(
    conn: sqlite3.Connection,
    entity_id: int,
    as_of_date: Optional[str] = None,
) -> dict:
    """Compute balance for an internal entity: reference + incoming - outgoing.

    For 'own' mode: direct transactions only.
    For 'aggregate' mode: own = consolidated - sum(children.consolidated).
    """
    mode = _get_balance_mode(conn, entity_id)

    if mode == "aggregate":
        agg = _compute_aggregate_consolidated(conn, entity_id, as_of_date)
        children_sum = sum(c["consolidated_balance"] for c in agg["children"])
        own = agg["consolidated_balance"] - children_sum
        return {
            "entity_id": entity_id,
            "balance": own,
            "reference_amount": agg["reference_amount"],
            "reference_date": agg["reference_date"],
            "transactions_sum": agg["consolidated_balance"] - agg["reference_amount"] - children_sum,
            "mode": "aggregate",
        }

    # --- 'own' mode (unchanged logic) ---
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
        "mode": "own",
    }


def compute_consolidated_balance(
    conn: sqlite3.Connection,
    entity_id: int,
    as_of_date: Optional[str] = None,
) -> dict:
    """Consolidated balance: own + all descendant internal entities (recursive CTE).

    For aggregate-mode entities, delegates to _compute_aggregate_consolidated
    which treats the ref as the full subtree's consolidated value.
    """
    mode = _get_balance_mode(conn, entity_id)

    if mode == "aggregate":
        return _compute_aggregate_consolidated(conn, entity_id, as_of_date)

    # --- 'own' mode (unchanged logic) ---
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
