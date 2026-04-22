"""
audit_coherence.py — Compare compta BDA.xlsx (sheet Suivi) against data/openflow.db.

Produces: audit/coherence-diff.md
Run from: openflow/ project root (python tools/audit_coherence.py)
"""

import difflib
import os
import sqlite3
import warnings
from datetime import datetime

# Suppress openpyxl pivot-cache warnings
warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

import openpyxl

# ─── Paths ───────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXCEL_PATH = os.path.join(BASE_DIR, "..", "compta BDA.xlsx")
DB_PATH = os.path.join(BASE_DIR, "data", "openflow.db")
OUTPUT_PATH = os.path.join(BASE_DIR, "audit", "coherence-diff.md")
EXCEL_SHEET = "Suivi"

# ─── Constants ───────────────────────────────────────────────────────────────
FUZZY_THRESHOLD = 0.7
AMOUNT_TOLERANCE = 0.01


# ─── Helpers ─────────────────────────────────────────────────────────────────

def fuzzy_ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def fmt_amount(v) -> str:
    if v is None:
        return ""
    return f"{v:,.2f}"


def esc_md(s) -> str:
    """Escape pipe characters for Markdown tables."""
    if s is None:
        return ""
    return str(s).replace("|", "\\|").replace("\n", " ")


# ─── Load Excel ──────────────────────────────────────────────────────────────

def load_excel_rows():
    """Return list of dicts from Suivi sheet (skipping empty rows)."""
    wb = openpyxl.load_workbook(EXCEL_PATH, read_only=True, data_only=True)
    ws = wb[EXCEL_SHEET]
    rows_iter = ws.iter_rows(values_only=True)
    header = next(rows_iter)  # skip header

    rows = []
    for raw in rows_iter:
        if not any(v is not None for v in raw):
            continue
        date_val, motif, categorie, depense, recette, payeur, rembourse, facture = (
            raw + (None,) * (8 - len(raw))
        )[:8]

        # Normalize date
        if isinstance(date_val, datetime):
            date_str = date_val.strftime("%Y-%m-%d")
        elif isinstance(date_val, str) and date_val.strip():
            try:
                date_str = datetime.strptime(date_val.strip(), "%Y-%m-%d").strftime("%Y-%m-%d")
            except ValueError:
                date_str = date_val.strip()
        else:
            date_str = None

        # Normalize amounts — Excel stores absolute values
        depense_v = float(depense) if depense is not None else None
        recette_v = float(recette) if recette is not None else None
        amount_abs = depense_v if depense_v is not None else recette_v
        sign = "depense" if depense_v is not None else "recette"

        label = str(motif).strip() if motif else ""
        category = str(categorie).strip().lower() if categorie else ""
        payer_str = str(payeur).strip() if payeur else None
        reimb_flag = isinstance(rembourse, str) and rembourse.lower() == "oui"

        rows.append(
            {
                "date": date_str,
                "label": label,
                "category_raw": str(categorie).strip() if categorie else "",
                "category": category,
                "amount_abs": amount_abs,
                "sign": sign,
                "depense": depense_v,
                "recette": recette_v,
                "payer": payer_str,
                "rembourse": reimb_flag,
                "facture": str(facture).strip() if facture else None,
            }
        )

    wb.close()
    return rows


# ─── Load DB ─────────────────────────────────────────────────────────────────

def load_db(conn):
    """Return dicts for transactions, categories, reimbursements, contacts."""
    conn.row_factory = sqlite3.Row

    cur = conn.cursor()
    cur.execute("SELECT id, date, label, amount, category_id FROM transactions ORDER BY date")
    transactions = [dict(r) for r in cur.fetchall()]

    cur.execute("SELECT id, name FROM categories")
    categories = {r["id"]: r["name"] for r in cur.fetchall()}

    cur.execute("SELECT id, name FROM contacts")
    contacts = {r["id"]: r["name"] for r in cur.fetchall()}

    cur.execute(
        "SELECT id, transaction_id, person_name, amount, status, contact_id FROM reimbursements"
    )
    reimbursements = [dict(r) for r in cur.fetchall()]

    # Index reimbursements by transaction_id
    reimb_by_tx = {}
    for r in reimbursements:
        reimb_by_tx.setdefault(r["transaction_id"], []).append(r)

    return transactions, categories, contacts, reimb_by_tx


# ─── Matching ────────────────────────────────────────────────────────────────

def match_rows(excel_rows, db_transactions, categories):
    """
    Match each Excel row to a DB transaction.

    Returns:
        matched: list of (excel_idx, db_tx, ratio)
        missing: list of excel_idx  (Excel row not found in DB)
        orphans: set of db tx id    (DB tx not matched)
        ambiguous: list of (excel_idx, candidates)  (multiple candidates, best < threshold)
        field_diffs: list of dicts
    """
    # Build date+amount index for DB transactions
    db_index = {}  # (date, amount_abs_rounded) → list of db_tx
    for tx in db_transactions:
        key = (tx["date"], round(abs(tx["amount"]), 2))
        db_index.setdefault(key, []).append(tx)

    matched = []          # (excel_idx, db_tx, ratio)
    missing = []          # excel_idx
    ambiguous_list = []   # (excel_idx, best_tx, best_ratio, candidates_count)
    field_diffs = []      # dicts

    matched_db_ids = set()

    for i, ex in enumerate(excel_rows):
        if ex["date"] is None or ex["amount_abs"] is None:
            # Row with no date or no amount — treat as missing (can't match DB)
            missing.append(i)
            continue

        key = (ex["date"], round(ex["amount_abs"], 2))
        candidates = db_index.get(key, [])

        # Tolerance: also check ±0.01
        if not candidates:
            for k, v in db_index.items():
                if k[0] == ex["date"] and abs(k[1] - ex["amount_abs"]) <= AMOUNT_TOLERANCE:
                    candidates = v
                    break

        if not candidates:
            missing.append(i)
            continue

        # Score candidates by label fuzzy ratio
        scored = [(fuzzy_ratio(ex["label"], tx["label"]), tx) for tx in candidates]
        scored.sort(key=lambda x: -x[0])
        best_ratio, best_tx = scored[0]

        if len(candidates) > 1 and best_ratio < FUZZY_THRESHOLD:
            # Multiple candidates, none clearly matches
            ambiguous_list.append((i, best_tx, best_ratio, len(candidates)))
            # Still record the best match to avoid orphaning
            matched.append((i, best_tx, best_ratio))
            matched_db_ids.add(best_tx["id"])
        else:
            matched.append((i, best_tx, best_ratio))
            matched_db_ids.add(best_tx["id"])

            # Field diffs for good matches
            if best_ratio >= FUZZY_THRESHOLD:
                # Label diff
                if best_ratio < 1.0 and best_ratio < 0.9:
                    field_diffs.append(
                        {
                            "date": ex["date"],
                            "excel_label": ex["label"],
                            "db_label": best_tx["label"],
                            "field": "label",
                            "excel_val": ex["label"],
                            "db_val": best_tx["label"],
                            "ratio": best_ratio,
                        }
                    )

                # Category diff
                db_cat_name = categories.get(best_tx["category_id"], "").lower().strip()
                ex_cat = ex["category"].lower().strip()
                if ex_cat and db_cat_name and ex_cat != db_cat_name:
                    # Allow partial match (e.g. "gastro" vs "gastronomie" — skip if one contains other)
                    if ex_cat not in db_cat_name and db_cat_name not in ex_cat:
                        field_diffs.append(
                            {
                                "date": ex["date"],
                                "excel_label": ex["label"],
                                "db_label": best_tx["label"],
                                "field": "category",
                                "excel_val": ex["category_raw"],
                                "db_val": categories.get(best_tx["category_id"], "(none)"),
                            }
                        )

                # Sign / direction diff
                # DB: negative = expense, positive = income
                db_sign = "depense" if best_tx["amount"] < 0 else "recette"
                if db_sign != ex["sign"]:
                    field_diffs.append(
                        {
                            "date": ex["date"],
                            "excel_label": ex["label"],
                            "db_label": best_tx["label"],
                            "field": "sign",
                            "excel_val": ex["sign"],
                            "db_val": db_sign,
                        }
                    )

    orphan_ids = [tx["id"] for tx in db_transactions if tx["id"] not in matched_db_ids]

    return matched, missing, orphan_ids, ambiguous_list, field_diffs


# ─── Reimbursement checks ─────────────────────────────────────────────────────

def check_reimbursements(excel_rows, matched, reimb_by_tx, contacts):
    """
    Return list of reimbursement discrepancy dicts.
    Each dict has: code, date, label, detail
    """
    issues = []
    matched_excel_indices = {ex_i for ex_i, _, _ in matched}

    # Build map excel_idx → (db_tx, ratio) for matched pairs
    match_map = {ex_i: (tx, ratio) for ex_i, tx, ratio in matched}

    for ex_i, ex in enumerate(excel_rows):
        tx_entry = match_map.get(ex_i)

        if ex["rembourse"]:
            if tx_entry is None:
                # Can't check — already MISSING
                continue
            db_tx, ratio = tx_entry
            tx_id = db_tx["id"]
            reimbs = reimb_by_tx.get(tx_id, [])

            if not reimbs:
                issues.append(
                    {
                        "code": "REIMB_MISSING",
                        "date": ex["date"],
                        "label": ex["label"],
                        "detail": "Excel dit remboursé, aucun enregistrement DB",
                    }
                )
            else:
                for r in reimbs:
                    if r["status"] != "reimbursed":
                        issues.append(
                            {
                                "code": "REIMB_NOT_SETTLED",
                                "date": ex["date"],
                                "label": ex["label"],
                                "detail": f"Statut DB = '{r['status']}' (attendu: reimbursed)",
                            }
                        )

                    # Check payer name vs person_name / contact
                    if ex["payer"]:
                        db_person = r["person_name"] or ""
                        contact_name = contacts.get(r["contact_id"], "") if r["contact_id"] else ""
                        best_name_ratio = max(
                            fuzzy_ratio(ex["payer"], db_person),
                            fuzzy_ratio(ex["payer"], contact_name),
                        )
                        if best_name_ratio < FUZZY_THRESHOLD:
                            issues.append(
                                {
                                    "code": "REIMB_PAYER_MISMATCH",
                                    "date": ex["date"],
                                    "label": ex["label"],
                                    "detail": (
                                        f"Excel payeur='{ex['payer']}', "
                                        f"DB person_name='{db_person}'"
                                    ),
                                }
                            )
        else:
            # Excel does NOT say remboursé — check if DB has a reimbursement anyway
            if tx_entry is None:
                continue
            db_tx, _ = tx_entry
            tx_id = db_tx["id"]
            reimbs = reimb_by_tx.get(tx_id, [])
            if reimbs:
                issues.append(
                    {
                        "code": "REIMB_EXTRA",
                        "date": ex["date"],
                        "label": ex["label"],
                        "detail": (
                            f"DB a {len(reimbs)} remboursement(s) "
                            f"(person={reimbs[0]['person_name']}), "
                            f"Excel ne signale pas"
                        ),
                    }
                )

    return issues


# ─── Totals ───────────────────────────────────────────────────────────────────

def compute_totals(excel_rows, conn):
    excel_depenses = sum(r["depense"] for r in excel_rows if r["depense"] is not None)
    excel_recettes = sum(r["recette"] for r in excel_rows if r["recette"] is not None)
    excel_net = excel_recettes - excel_depenses

    row = conn.execute(
        """SELECT
               COALESCE(SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END), 0) AS depenses,
               COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) AS recettes
           FROM transactions"""
    ).fetchone()
    db_depenses = row[0]
    db_recettes = row[1]
    db_net = db_recettes - db_depenses

    return {
        "excel_depenses": excel_depenses,
        "excel_recettes": excel_recettes,
        "excel_net": excel_net,
        "db_depenses": db_depenses,
        "db_recettes": db_recettes,
        "db_net": db_net,
        "diff_depenses": excel_depenses - db_depenses,
        "diff_recettes": excel_recettes - db_recettes,
        "diff_net": excel_net - db_net,
    }


# ─── Render report ───────────────────────────────────────────────────────────

def render_report(
    excel_rows,
    db_transactions,
    categories,
    contacts,
    matched,
    missing,
    orphan_ids,
    ambiguous_list,
    field_diffs,
    reimb_issues,
    totals,
):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = []

    lines.append("# Audit de cohérence — compta BDA.xlsx ↔ openflow.db\n")
    lines.append(f"**Généré le :** {now_str}\n")

    # ── Summary
    lines.append("## Résumé\n")
    lines.append(f"- Excel `Suivi` : {len(excel_rows)} transactions")
    lines.append(f"- DB `transactions` : {len(db_transactions)} transactions")
    lines.append(f"- Appariées : {len(matched)}")
    lines.append(f"- Excel → DB manquantes : {len(missing)}")
    lines.append(f"- DB → Excel orphelines : {len(orphan_ids)}")
    lines.append(f"- Ambiguïtés (multi-candidats, score < {FUZZY_THRESHOLD}) : {len(ambiguous_list)}")
    lines.append(f"- Écarts sur lignes appariées : {len(field_diffs)}")
    lines.append(f"- Écarts de remboursement : {len(reimb_issues)}")
    lines.append("")

    # ── Totals
    lines.append("## Totaux\n")
    lines.append("| Source | Dépenses | Recettes | Net |")
    lines.append("|---|---|---|---|")
    lines.append(
        f"| Excel Suivi | {fmt_amount(totals['excel_depenses'])} | "
        f"{fmt_amount(totals['excel_recettes'])} | {fmt_amount(totals['excel_net'])} |"
    )
    lines.append(
        f"| DB | {fmt_amount(totals['db_depenses'])} | "
        f"{fmt_amount(totals['db_recettes'])} | {fmt_amount(totals['db_net'])} |"
    )
    ecart_prefix = lambda v: ("+" if v > 0 else "") + fmt_amount(v)
    lines.append(
        f"| Écart (Excel−DB) | {ecart_prefix(totals['diff_depenses'])} | "
        f"{ecart_prefix(totals['diff_recettes'])} | {ecart_prefix(totals['diff_net'])} |"
    )
    lines.append("")

    # ── Missing
    lines.append("## Transactions manquantes (Excel → DB)\n")
    if missing:
        lines.append("| Date | Motif | Catégorie | Montant | Signe | Payeur |")
        lines.append("|---|---|---|---|---|---|")
        for idx in missing:
            ex = excel_rows[idx]
            sign_sym = "−" if ex["sign"] == "depense" else "+"
            lines.append(
                f"| {ex['date']} | {esc_md(ex['label'])} | "
                f"{esc_md(ex['category_raw'])} | "
                f"{sign_sym}{fmt_amount(ex['amount_abs'])} | "
                f"{ex['sign']} | {esc_md(ex['payer'])} |"
            )
    else:
        lines.append("_Aucune._")
    lines.append("")

    # ── Orphans
    db_by_id = {tx["id"]: tx for tx in db_transactions}
    lines.append("## Transactions orphelines (DB → Excel)\n")
    if orphan_ids:
        lines.append("| ID | Date | Label | Montant | Catégorie |")
        lines.append("|---|---|---|---|---|")
        for oid in orphan_ids:
            tx = db_by_id[oid]
            cat = categories.get(tx["category_id"], "")
            sign_sym = "−" if tx["amount"] < 0 else "+"
            lines.append(
                f"| {tx['id']} | {tx['date']} | {esc_md(tx['label'])} | "
                f"{sign_sym}{fmt_amount(abs(tx['amount']))} | {esc_md(cat)} |"
            )
    else:
        lines.append("_Aucune._")
    lines.append("")

    # ── Ambiguous
    if ambiguous_list:
        lines.append("## Appariements ambigus (multi-candidats, score < seuil)\n")
        lines.append("| Date | Motif Excel | Meilleur match DB | Score | Nb candidats |")
        lines.append("|---|---|---|---|---|")
        for ex_i, best_tx, ratio, n in ambiguous_list:
            ex = excel_rows[ex_i]
            lines.append(
                f"| {ex['date']} | {esc_md(ex['label'])} | "
                f"{esc_md(best_tx['label'])} | {ratio:.2f} | {n} |"
            )
        lines.append("")

    # ── Field diffs
    lines.append("## Écarts sur lignes appariées\n")
    if field_diffs:
        lines.append("| Date | Motif (Excel) | Motif (DB) | Champ | Valeur Excel | Valeur DB |")
        lines.append("|---|---|---|---|---|---|")
        for d in field_diffs:
            lines.append(
                f"| {d['date']} | {esc_md(d['excel_label'])} | "
                f"{esc_md(d['db_label'])} | {d['field']} | "
                f"{esc_md(d.get('excel_val', ''))} | {esc_md(d.get('db_val', ''))} |"
            )
    else:
        lines.append("_Aucun écart sur les lignes appariées._")
    lines.append("")

    # ── Reimbursement issues
    lines.append("## Écarts de remboursement\n")
    if reimb_issues:
        lines.append("| Code | Date | Motif | Détail |")
        lines.append("|---|---|---|---|")
        for iss in reimb_issues:
            lines.append(
                f"| {iss['code']} | {iss['date']} | "
                f"{esc_md(iss['label'])} | {esc_md(iss['detail'])} |"
            )
    else:
        lines.append("_Aucun écart de remboursement._")
    lines.append("")

    return "\n".join(lines)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    # Load data
    excel_rows = load_excel_rows()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    db_transactions, categories, contacts, reimb_by_tx = load_db(conn)

    # Match
    matched, missing, orphan_ids, ambiguous_list, field_diffs = match_rows(
        excel_rows, db_transactions, categories
    )

    # Totals
    totals = compute_totals(excel_rows, conn)

    # Reimbursements
    reimb_issues = check_reimbursements(excel_rows, matched, reimb_by_tx, contacts)

    conn.close()

    # Render
    report = render_report(
        excel_rows,
        db_transactions,
        categories,
        contacts,
        matched,
        missing,
        orphan_ids,
        ambiguous_list,
        field_diffs,
        reimb_issues,
        totals,
    )

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(report)

    print(
        f"Audit terminé — "
        f"{len(excel_rows)} Excel / {len(db_transactions)} DB / "
        f"{len(matched)} appariées / {len(missing)} manquantes / "
        f"{len(orphan_ids)} orphelines / "
        f"{len(field_diffs)} écarts champs / {len(reimb_issues)} écarts remb."
    )
    print(f"Rapport : {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
