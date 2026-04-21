"""One-shot: adjust entity_balance_refs to match real BDA allocation model.

Context (April 2026): the BDA's Excel file has no per-club bank account —
clubs are virtual budget envelopes on a single BDA bank account. Until the
Budget & Exercices module is implemented, we align the reference_amount of
each internal entity so that:

- Selecting "Toutes les entités" (consolidated root) shows the real bank
  balance (26 355 €).
- Selecting a club shows its remaining virtual allocation.
- Selecting BDA shows the residual (bank - sum of club allocations).

This script mirrors the behaviour of
`PUT /api/entities/{id}/balance-ref` with auth bypass for a one-shot
adjustment. Log kept here for traceability.
"""
import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


# Targets: reference_amount to set so that the displayed balance equals the
# expected real-world value for the current fiscal year starting 2025-03-01.
# Values below were computed from a backup taken on 2026-04-21.
TARGETS = [
    # (entity_name, reference_amount)
    ("BDA",              24646.15),   # so BDA_own = 25001.24 = 26355 - allocations
    ("Gastronomine",     1386.23),    # so balance = 1200
    ("CCMP",             29.92),      # so balance = 0
    # ("Plume de mines", 0.00),       # already 0, unchanged
    # ("PapiMaMine",     0.00),       # already 0, unchanged
]
REFERENCE_DATE = "2025-03-01"


def apply(db_path: Path, dry_run: bool) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    now = datetime.now(timezone.utc).isoformat()
    try:
        for name, amount in TARGETS:
            row = conn.execute("SELECT id FROM entities WHERE name = ?", (name,)).fetchone()
            if row is None:
                print(f"  [skip] entity '{name}' not found")
                continue
            eid = row["id"]
            before = conn.execute(
                "SELECT reference_amount FROM entity_balance_refs WHERE entity_id = ?", (eid,)
            ).fetchone()
            before_val = before["reference_amount"] if before else None
            print(f"  {name:20} id={eid}  ref {before_val} -> {amount}")
            if not dry_run:
                conn.execute(
                    """INSERT INTO entity_balance_refs (entity_id, reference_date, reference_amount, updated_at)
                       VALUES (?, ?, ?, ?)
                       ON CONFLICT(entity_id) DO UPDATE SET
                         reference_date = excluded.reference_date,
                         reference_amount = excluded.reference_amount,
                         updated_at = excluded.updated_at""",
                    (eid, REFERENCE_DATE, amount, now),
                )
        if not dry_run:
            conn.commit()
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-dir", default=str(Path(__file__).parent.parent))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    db_path = Path(args.project_dir) / "data" / "openflow.db"
    if not db_path.exists():
        raise SystemExit(f"DB not found at {db_path}")

    print(f"Adjusting opening balances (dry_run={args.dry_run})")
    apply(db_path, args.dry_run)
    print("Done." if not args.dry_run else "Dry run — nothing written.")


if __name__ == "__main__":
    main()
