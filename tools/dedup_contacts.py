"""
dedup_contacts.py — Interactive deduplication of contacts in data/openflow.db.

Algorithm:
  1. Load all contacts.
  2. Normalize names (strip accents, lowercase, strip spaces) and group by
     SequenceMatcher similarity >= 0.82.
  3. For each group > 1 contact:
       - Show candidates with their transaction / reimbursement counts.
       - Propose a canonical: most total refs, tie-break on lowest id
         (earliest created; within same ref count, lowest id = oldest row).
  4. Merge: UPDATE transactions + reimbursements → canonical id, DELETE dups.
  5. Write audit_log entries (silently noop if table is absent).
  6. Print summary.

Flags:
  --dry-run   print plan only, no DB changes
  --auto      accept all proposed canonicals without interactive prompt
  --db PATH   override DB path (default: data/openflow.db)
"""

import argparse
import difflib
import json
import sqlite3
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

# UTF-8 output on all platforms
sys.stdout.reconfigure(encoding="utf-8")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DEFAULT_DB = Path(__file__).parent.parent / "data" / "openflow.db"


def normalize(name: str) -> str:
    """Strip accents, lowercase, collapse whitespace — used for similarity only."""
    nfkd = unicodedata.normalize("NFKD", name).encode("ASCII", "ignore").decode()
    return " ".join(nfkd.lower().split())


def similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def group_duplicates(contacts: list[dict]) -> list[list[dict]]:
    """
    Return groups of contacts whose normalized names are pairwise similar
    (SequenceMatcher ratio >= 0.82).  Uses single-linkage clustering so a
    chain of near-matches is merged into one group.
    """
    THRESHOLD = 0.82
    n = len(contacts)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    norms = [normalize(c["name"]) for c in contacts]
    for i in range(n):
        for j in range(i + 1, n):
            if similarity(norms[i], norms[j]) >= THRESHOLD:
                union(i, j)

    groups: dict[int, list[dict]] = {}
    for i, c in enumerate(contacts):
        root = find(i)
        groups.setdefault(root, []).append(c)

    return [g for g in groups.values() if len(g) > 1]


def has_diacritics(name: str) -> bool:
    """Return True if name contains at least one non-ASCII character (accent, etc.)."""
    return name != unicodedata.normalize("NFKD", name).encode("ASCII", "ignore").decode()


def pick_canonical(group: list[dict]) -> dict:
    """
    Canonical selection heuristic (in priority order):
      1. Most total references (tx + rembos) — the "known" contact.
      2. Has diacritics in name (accented = more likely correct spelling, e.g.
         "Joséphine" preferred over "Josephine").
      3. Lowest id (oldest row, inserted first).
    """
    return max(group, key=lambda c: (c["refs"], has_diacritics(c["name"]), -c["id"]))


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def record_audit(conn: sqlite3.Connection, action: str, table_name: str,
                 record_id: int, old_value=None, new_value=None) -> None:
    """Insert an audit_log entry. Silently noop when the table is missing."""
    if not _table_exists(conn, "audit_log"):
        return
    conn.execute(
        """INSERT INTO audit_log
           (timestamp, user_name, action, table_name, record_id, old_value, new_value)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            datetime.now(timezone.utc).isoformat(),
            "dedup_contacts",
            action,
            table_name,
            record_id,
            json.dumps(old_value, ensure_ascii=False, default=str) if old_value is not None else None,
            json.dumps(new_value, ensure_ascii=False, default=str) if new_value is not None else None,
        ),
    )


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def load_contacts(conn: sqlite3.Connection) -> list[dict]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, name, type, email, phone, address, notes, created_at FROM contacts ORDER BY id"
    ).fetchall()

    contacts = []
    for row in rows:
        # Count references
        tx_count = conn.execute(
            "SELECT COUNT(*) FROM transactions WHERE contact_id=?", (row["id"],)
        ).fetchone()[0]
        rembo_count = conn.execute(
            "SELECT COUNT(*) FROM reimbursements WHERE contact_id=?", (row["id"],)
        ).fetchone()[0]
        contacts.append({
            "id": row["id"],
            "name": row["name"],
            "type": row["type"],
            "email": row["email"],
            "phone": row["phone"],
            "created_at": row["created_at"],
            "tx": tx_count,
            "rembos": rembo_count,
            "refs": tx_count + rembo_count,
        })

    conn.row_factory = None
    return contacts


def merge_group(
    conn: sqlite3.Connection,
    canonical: dict,
    duplicates: list[dict],
    dry_run: bool,
) -> None:
    """Migrate all references from `duplicates` to `canonical`, then delete them."""
    dup_ids = [d["id"] for d in duplicates]
    placeholders = ",".join("?" * len(dup_ids))

    print(f"  → Canonical: id={canonical['id']} | {canonical['name']!r}")
    for d in duplicates:
        print(f"    Delete:    id={d['id']} | {d['name']!r}  "
              f"({d['tx']} tx, {d['rembos']} rembos)")

    if dry_run:
        return

    conn.execute(
        f"UPDATE transactions SET contact_id=? WHERE contact_id IN ({placeholders})",
        [canonical["id"]] + dup_ids,
    )
    conn.execute(
        f"UPDATE reimbursements SET contact_id=? WHERE contact_id IN ({placeholders})",
        [canonical["id"]] + dup_ids,
    )

    for dup in duplicates:
        record_audit(
            conn,
            action="DELETE",
            table_name="contacts",
            record_id=dup["id"],
            old_value={
                "id": dup["id"],
                "name": dup["name"],
                "merged_into": canonical["id"],
                "reason": "dedup_contacts: name similarity merge",
            },
        )
        conn.execute("DELETE FROM contacts WHERE id=?", (dup["id"],))

    record_audit(
        conn,
        action="UPDATE",
        table_name="contacts",
        record_id=canonical["id"],
        new_value={
            "merged_from": dup_ids,
            "reason": "dedup_contacts: absorbed duplicates",
        },
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Deduplicate contacts in OpenFlow DB.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print plan without making any changes.")
    parser.add_argument("--auto", action="store_true",
                        help="Accept all proposed canonicals without prompting.")
    parser.add_argument("--db", default=str(DEFAULT_DB),
                        help=f"Path to SQLite DB (default: {DEFAULT_DB})")
    args = parser.parse_args()

    db_path = args.db
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    if args.dry_run:
        print("[DRY-RUN] No changes will be made.\n")

    contacts = load_contacts(conn)
    groups = group_duplicates(contacts)

    if not groups:
        print("No duplicate contacts found.")
        conn.close()
        return

    merged_groups = 0
    deleted_contacts = 0

    for group in groups:
        group_sorted = sorted(group, key=lambda c: (-c["refs"], c["id"]))
        proposed = pick_canonical(group_sorted)
        dup_candidates = [c for c in group_sorted if c["id"] != proposed["id"]]

        print("\n" + "=" * 60)
        print("Duplicate group detected:")
        for c in group_sorted:
            marker = " [proposed canonical]" if c["id"] == proposed["id"] else ""
            print(f"  id={c['id']:4d} | {c['name']:<30s} | type={c['type'] or '':<10s} | "
                  f"tx={c['tx']}, rembos={c['rembos']}{marker}")

        if args.auto or args.dry_run:
            canonical = proposed
        else:
            valid_ids = {str(c["id"]) for c in group}
            while True:
                answer = input(
                    f"\nEnter id of canonical (default={proposed['id']}), "
                    "or 'skip' to skip this group: "
                ).strip()
                if answer == "":
                    canonical = proposed
                    break
                elif answer.lower() == "skip":
                    print("  Skipped.")
                    canonical = None
                    break
                elif answer in valid_ids:
                    canonical = next(c for c in group if str(c["id"]) == answer)
                    break
                else:
                    print(f"  Invalid id. Choose from: {', '.join(sorted(valid_ids))}")

            if canonical is None:
                continue

        duplicates = [c for c in group if c["id"] != canonical["id"]]
        merge_group(conn, canonical, duplicates, dry_run=args.dry_run)

        if not args.dry_run:
            conn.commit()
            merged_groups += 1
            deleted_contacts += len(duplicates)

    print("\n" + "=" * 60)
    if args.dry_run:
        print(f"[DRY-RUN] Would merge {len(groups)} group(s).")
    else:
        print(f"Done. {merged_groups} group(s) merged, {deleted_contacts} contact(s) deleted.")

    conn.close()


if __name__ == "__main__":
    main()
