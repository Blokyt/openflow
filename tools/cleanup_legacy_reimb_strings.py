"""One-shot cleanup: strip legacy 'Remboursé: oui/non' strings from transaction descriptions.

Context (April 2026): early versions of the reimbursements module stored the
reimbursement status directly in the transaction description field as
"Remboursé: oui" or "Remboursé: non". That approach was superseded by a
dedicated reimbursements table. Five transactions (IDs 20, 24, 28, 30, 85)
still carry this legacy string as their *entire* description.

This script:
  1. Scans transactions where description matches the legacy pattern.
  2. Only touches rows where the matched string is the *entire* description
     (remainder after stripping is empty/whitespace) — no accidental data loss.
  3. Sets description = '' and updates updated_at.
  4. Is idempotent: a second run finds zero matching rows and does nothing.

When to run: once, after deploying the reimbursements-reconciliation branch.
Manual reconciliation of the four REIMB_MISSING rows (Cyrano, Radio France x2,
frais dossier passace) must be done via the /reimbursements UI — this script
does NOT create reimbursement rows.
"""

import argparse
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

# Matches "Remboursé: oui" / "Remboursé: non" (and any encoding variant of é)
# Anchored so the *entire* description is the pattern (leading/trailing whitespace allowed).
_PATTERN = re.compile(r"^\s*Rembours.*?:\s*(oui|non)\s*$", re.IGNORECASE)

# Broader fallback: description contains "Rembours" at all (used for dry-run scan)
_CONTAINS = re.compile(r"Rembours", re.IGNORECASE)


def _find_rows(conn: sqlite3.Connection) -> list[dict]:
    """Return rows whose description is *entirely* the legacy status string."""
    cursor = conn.execute(
        "SELECT id, label, description FROM transactions WHERE description != ''"
    )
    rows = []
    for row in cursor.fetchall():
        desc = row["description"] or ""
        if _PATTERN.match(desc):
            rows.append({"id": row["id"], "label": row["label"], "description": desc})
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Strip legacy 'Remboursé: oui/non' strings from transaction descriptions."
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Apply changes without interactive confirmation.",
    )
    parser.add_argument(
        "--project-dir",
        default=str(Path(__file__).parent.parent),
        help="Path to the OpenFlow project root (default: parent of tools/).",
    )
    args = parser.parse_args()

    db_path = Path(args.project_dir) / "data" / "openflow.db"
    if not db_path.exists():
        raise SystemExit(f"DB not found at {db_path}")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    try:
        rows = _find_rows(conn)

        if not rows:
            print("0 rows match the legacy pattern — nothing to do (already clean).")
            return

        print(f"{len(rows)} row(s) will be cleaned:")
        for r in rows:
            print(f"  id={r['id']:>4}  label={r['label']!r:40}  desc={r['description']!r}")

        # Confirmation
        if args.yes:
            confirmed = True
        else:
            answer = input("\nApply changes? [y/N] ").strip().lower()
            confirmed = answer in ("y", "yes")

        if not confirmed:
            print("Aborted — no changes made.")
            return

        now = datetime.now(timezone.utc).isoformat()
        for r in rows:
            conn.execute(
                "UPDATE transactions SET description = '', updated_at = ? WHERE id = ?",
                (now, r["id"]),
            )
        conn.commit()
        print(f"{len(rows)} row(s) updated.")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
