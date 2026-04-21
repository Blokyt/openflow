"""One-shot backfill: parse 'Payeur: X | Remboursé: Y' strings in transaction
descriptions and materialise them in the reimbursements table.

Idempotent: skips transactions that already have a reimbursement row.

Usage:
    python tools/backfill_reimbursements.py [--dry-run] [--project-dir PATH]
"""
import argparse
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

PAYEUR_RE = re.compile(r"Payeur\s*:\s*([^|]+?)(?=\s*\||$)", re.IGNORECASE)
REMBOURSE_RE = re.compile(r"Rembours[ée]\s*:\s*(oui|non)", re.IGNORECASE)


def _clean_description(desc: str) -> str:
    """Remove Payeur: X and Remboursé: Y segments; keep the rest."""
    parts = [p.strip() for p in desc.split("|")]
    kept = []
    for p in parts:
        low = p.lower()
        if low.startswith("payeur:") or low.startswith("payeur :"):
            continue
        if low.startswith("remboursé:") or low.startswith("remboursé :") or low.startswith("rembourse:") or low.startswith("rembourse :"):
            continue
        if p:
            kept.append(p)
    return " | ".join(kept)


def backfill(conn: sqlite3.Connection, dry_run: bool = False) -> dict:
    conn.row_factory = sqlite3.Row
    now = datetime.now(timezone.utc).isoformat()

    already_linked = {
        r["transaction_id"]
        for r in conn.execute(
            "SELECT transaction_id FROM reimbursements WHERE transaction_id IS NOT NULL"
        ).fetchall()
    }

    candidates = conn.execute(
        "SELECT id, date, amount, description FROM transactions "
        "WHERE description LIKE '%Payeur%' OR description LIKE '%Rembours%'"
    ).fetchall()

    created = 0
    cleaned = 0
    skipped_already = 0
    skipped_no_payeur = 0

    for tx in candidates:
        if tx["id"] in already_linked:
            skipped_already += 1
            continue

        desc = tx["description"] or ""
        m_payeur = PAYEUR_RE.search(desc)
        m_rembourse = REMBOURSE_RE.search(desc)

        if not m_payeur:
            # 'Remboursé:' without Payeur: can't fill person_name — skip
            skipped_no_payeur += 1
            continue

        person = m_payeur.group(1).strip()
        if not person:
            skipped_no_payeur += 1
            continue

        status = "pending"
        reimbursed_date = None
        if m_rembourse and m_rembourse.group(1).lower() == "oui":
            status = "reimbursed"
            reimbursed_date = tx["date"]

        amount = abs(float(tx["amount"]))
        new_desc = _clean_description(desc)

        if dry_run:
            print(f"  tx#{tx['id']}: '{person}' {amount:.2f} {status} -> desc='{new_desc}'")
        else:
            conn.execute(
                """INSERT INTO reimbursements
                   (transaction_id, person_name, amount, status, reimbursed_date, notes, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (tx["id"], person, amount, status, reimbursed_date, "", now, now),
            )
            conn.execute(
                "UPDATE transactions SET description = ?, updated_at = ? WHERE id = ?",
                (new_desc, now, tx["id"]),
            )
            cleaned += 1
        created += 1

    if not dry_run:
        conn.commit()

    return {
        "would_create" if dry_run else "created": created,
        "descriptions_cleaned": cleaned,
        "skipped_already_linked": skipped_already,
        "skipped_no_payeur": skipped_no_payeur,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-dir", default=str(Path(__file__).parent.parent))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    db_path = Path(args.project_dir) / "data" / "openflow.db"
    if not db_path.exists():
        print(f"DB not found at {db_path}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    try:
        report = backfill(conn, dry_run=args.dry_run)
    finally:
        conn.close()

    print("Backfill report:" + (" (dry-run)" if args.dry_run else ""))
    for k, v in report.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
