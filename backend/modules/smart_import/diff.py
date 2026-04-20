"""Diff logic: match parsed transactions against existing DB rows.

Matching key: (date, normalized label). If found:
- same amount → unchanged
- different amount → modified
If not found → new.
"""
import sqlite3


def _norm(s: str) -> str:
    return (s or "").strip().lower()


def compute_diff(conn: sqlite3.Connection, drafts: list) -> dict:
    """Classify drafts into new/modified/unchanged and return summary + details.

    Args:
        conn: sqlite3 connection
        drafts: list of TransactionDraft

    Returns:
        {
            "stats": {"new": int, "modified": int, "unchanged": int, "total": int},
            "items": [
                {"status": "new|modified|unchanged",
                 "draft": {date, label, amount, ...},
                 "existing": {id, amount} or None}
            ]
        }
    """
    # Build an index of existing transactions
    existing = conn.execute(
        "SELECT id, date, label, amount FROM transactions"
    ).fetchall()

    index = {}
    for row in existing:
        key = (row["date"], _norm(row["label"]))
        index.setdefault(key, []).append({"id": row["id"], "amount": row["amount"]})

    items = []
    stats = {"new": 0, "modified": 0, "unchanged": 0, "total": len(drafts)}

    # Track which existing IDs we've matched to avoid double-matching
    used_ids = set()

    for draft in drafts:
        key = (draft.date, _norm(draft.label))
        candidates = index.get(key, [])
        # Find first candidate not yet matched
        match = next((c for c in candidates if c["id"] not in used_ids), None)

        draft_dict = {
            "date": draft.date,
            "label": draft.label,
            "amount": round(draft.amount, 2),
            "description": draft.description,
            "category_hint": draft.category_hint,
        }

        if match is None:
            items.append({"status": "new", "draft": draft_dict, "existing": None})
            stats["new"] += 1
        else:
            used_ids.add(match["id"])
            if abs(match["amount"] - draft.amount) < 0.005:
                items.append({
                    "status": "unchanged",
                    "draft": draft_dict,
                    "existing": {"id": match["id"], "amount": round(match["amount"], 2)},
                })
                stats["unchanged"] += 1
            else:
                items.append({
                    "status": "modified",
                    "draft": draft_dict,
                    "existing": {"id": match["id"], "amount": round(match["amount"], 2)},
                })
                stats["modified"] += 1

    return {"stats": stats, "items": items}
