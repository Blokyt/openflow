"""Calcul centralisé des soldes d'entités OpenFlow.

Convention (refonte C1) : `amount` est TOUJOURS positif. Le sens d'une
transaction vient UNIQUEMENT de from_entity_id -> to_entity_id :
  - entrée pour X : transactions où to_entity_id = X
  - sortie pour X : transactions où from_entity_id = X
Solde propre d'une entité = reference + SUM(entrées) - SUM(sorties).

Ce modèle gère correctement les trois cas, y compris les virements internes
(from interne -> to interne), contrairement à l'ancien modèle basé sur le signe.
Les montants sont des entiers de centimes (refonte C2), mais ce module est
agnostique à l'unité : il ne fait que des sommes et des différences.
"""
import sqlite3
from typing import Optional

from backend.core.config import load_config


def compute_legacy_balance(conn: sqlite3.Connection, config_path: str) -> dict:
    """Solde global rétro-compatible pour les modules non entity-aware.

    Avec des entités internes : net = entrées depuis l'extérieur - sorties vers
    l'extérieur, agrégé sur toutes les entités internes. Sans entité (très
    anciens installs) : somme brute des montants.
    """
    try:
        config = load_config(config_path)
        reference_amount = config.balance.amount
        reference_date = config.balance.date
    except Exception:
        reference_amount = 0.0
        reference_date = None

    # config.balance.amount est stocke en EUROS ; tout le reste (transactions,
    # soldes) est en centimes entiers. On normalise en centimes avant addition.
    reference_cents = int(round((reference_amount or 0.0) * 100))

    internal = [r[0] for r in conn.execute(
        "SELECT id FROM entities WHERE type = 'internal'"
    ).fetchall()]

    if internal:
        ph = ",".join("?" * len(internal))
        date_clause = " AND date >= ?" if reference_date else ""
        params = list(internal) + list(internal) + ([reference_date] if reference_date else [])
        # NULL-safe : `NULL NOT IN (...)` vaut NULL (jamais vrai). Une transaction
        # héritée avec from/to NULL serait sinon exclue silencieusement.
        incoming = conn.execute(
            f"SELECT COALESCE(SUM(amount), 0) FROM transactions "
            f"WHERE to_entity_id IN ({ph}) AND (from_entity_id IS NULL OR from_entity_id NOT IN ({ph})){date_clause}",
            params,
        ).fetchone()[0]
        outgoing = conn.execute(
            f"SELECT COALESCE(SUM(amount), 0) FROM transactions "
            f"WHERE from_entity_id IN ({ph}) AND (to_entity_id IS NULL OR to_entity_id NOT IN ({ph})){date_clause}",
            params,
        ).fetchone()[0]
        total = incoming - outgoing
    elif reference_date:
        total = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE date >= ?",
            (reference_date,),
        ).fetchone()[0]
    else:
        total = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM transactions"
        ).fetchone()[0]

    return {
        "balance": reference_cents + total,
        "reference_amount": reference_cents,
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
        try:
            return row["balance_mode"] if row["balance_mode"] else "own"
        except (IndexError, TypeError):
            return row[0] if row[0] else "own"
    except Exception:
        return "own"


def _subtree_ids(conn: sqlite3.Connection, entity_id: int) -> list:
    """IDs de l'entité et de tous ses descendants internes (CTE récursive)."""
    return [
        row[0] for row in conn.execute(
            """WITH RECURSIVE tree(id) AS (
                   SELECT ? UNION ALL
                   SELECT e.id FROM entities e JOIN tree t ON e.parent_id = t.id
                   WHERE e.type = 'internal'
               ) SELECT id FROM tree""",
            (entity_id,),
        ).fetchall()
    ]


def get_subtree_ids(conn: sqlite3.Connection, entity_id: int) -> list:
    """Wrapper public de `_subtree_ids` à l'usage des modules (reports, etc.)."""
    return _subtree_ids(conn, entity_id)


def _compute_aggregate_consolidated(
    conn: sqlite3.Connection,
    entity_id: int,
    as_of_date: Optional[str] = None,
) -> dict:
    """Pour une entité en mode 'aggregate', le consolidé = ref + flux externes
    du sous-arbre (transactions qui traversent la frontière du sous-arbre).
    Les transferts internes au sous-arbre s'annulent et sont ignorés.
    """
    ref = conn.execute(
        "SELECT reference_date, reference_amount FROM entity_balance_refs WHERE entity_id = ?",
        (entity_id,),
    ).fetchone()
    reference_amount = ref["reference_amount"] if ref else 0
    reference_date = ref["reference_date"] if ref else None

    subtree = _subtree_ids(conn, entity_id)
    placeholders = ",".join("?" * len(subtree))

    # Entrant : to dans le sous-arbre, from hors du sous-arbre (NULL-safe).
    conds_in = [
        f"to_entity_id IN ({placeholders})",
        f"(from_entity_id IS NULL OR from_entity_id NOT IN ({placeholders}))",
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

    # Sortant : from dans le sous-arbre, to hors du sous-arbre (NULL-safe).
    conds_out = [
        f"from_entity_id IN ({placeholders})",
        f"(to_entity_id IS NULL OR to_entity_id NOT IN ({placeholders}))",
    ]
    params_out = list(subtree) + list(subtree)
    if reference_date:
        conds_out.append("date >= ?")
        params_out.append(reference_date)
    if as_of_date:
        conds_out.append("date <= ?")
        params_out.append(as_of_date)
    outgoing = conn.execute(
        f"SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE {' AND '.join(conds_out)}",
        params_out,
    ).fetchone()[0]

    external_delta = incoming - outgoing
    consolidated = reference_amount + external_delta

    children = []
    for row in conn.execute(
        "SELECT id FROM entities WHERE parent_id = ? AND type = 'internal'", (entity_id,)
    ).fetchall():
        child_id = row[0] if isinstance(row, tuple) else row["id"]
        children.append(compute_consolidated_balance(conn, child_id, as_of_date))

    own_balance = consolidated - sum(c["consolidated_balance"] for c in children)

    return {
        "entity_id": entity_id,
        "balance": consolidated,
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
    """Solde propre d'une entité interne : reference + entrées - sorties."""
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

    # --- mode 'own' ---
    ref = conn.execute(
        "SELECT reference_date, reference_amount FROM entity_balance_refs WHERE entity_id = ?",
        (entity_id,),
    ).fetchone()
    reference_amount = ref["reference_amount"] if ref else 0
    reference_date = ref["reference_date"] if ref else None

    conditions_in = ["to_entity_id = ?"]
    conditions_out = ["from_entity_id = ?"]
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

    incoming = conn.execute(
        f"SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE {' AND '.join(conditions_in)}",
        params_in,
    ).fetchone()[0]
    outgoing = conn.execute(
        f"SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE {' AND '.join(conditions_out)}",
        params_out,
    ).fetchone()[0]

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
    """Solde consolidé : propre + tous les descendants internes."""
    mode = _get_balance_mode(conn, entity_id)

    if mode == "aggregate":
        return _compute_aggregate_consolidated(conn, entity_id, as_of_date)

    ids = _subtree_ids(conn, entity_id)
    own = compute_entity_balance(conn, entity_id, as_of_date)
    children = []
    consolidated = own["balance"]

    for eid in ids:
        if eid != entity_id:
            child_bal = compute_entity_balance(conn, eid, as_of_date)
            children.append(child_bal)
            consolidated += child_bal["balance"]

    return {
        "entity_id": entity_id,
        "balance": consolidated,
        "own_balance": own["balance"],
        "consolidated_balance": consolidated,
        "children": children,
    }


def compute_entity_balance_for_period(
    conn: sqlite3.Connection,
    entity_id: int,
    start_date: str,
    end_date: str,
    opening: int = 0,
) -> dict:
    """Flux réalisé et solde de clôture d'une entité sur un intervalle de dates.

    net = SUM(amount entrant : to=entity) - SUM(amount sortant : from=entity)
    Renvoie {opening, realized, closing}.
    """
    row = conn.execute(
        """SELECT COALESCE(SUM(CASE
                WHEN to_entity_id = ? THEN amount
                WHEN from_entity_id = ? THEN -amount
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
