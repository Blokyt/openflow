"""Module DirENS — génération de l'Excel financier officiel pré-rempli.

Remplit de façon 100 % automatique et déterministe les DEUX premiers onglets du
template officiel DirENS (bundlé dans assets/template_direns.xlsx) à partir des
données de l'app :

  - Onglet 1 « Bilan financier {AAAA-AAAA} » : dépenses RÉALISÉES de l'exercice,
    une COLONNE par club (entité interne) et une LIGNE par CATÉGORIE OpenFlow
    (selon la catégorie de chaque transaction), plus la section financement
    (recettes par catégorie) et les soldes de trésorerie.
  - Onglet 2 « Budget prévisionnel {AAAA-AAAA} » : dépenses PRÉVISIONNELLES de
    l'exercice suivant, issues de budget_allocations (direction='expense'),
    mêmes lignes = catégories.
  - Onglet 3 « Demande subventions » : laissé vierge.

Il n'y a AUCUN mapping à configurer : les lignes sont exactement les catégories
définies dans l'app. Le bloc des dépenses (et celui des financements) est
redimensionné dynamiquement au nombre de catégories réellement utilisées.

Convention monétaire (comme tout OpenFlow) : amount = entier de centimes, positif.
Sens porté par from_entity_id -> to_entity_id :
  - DÉPENSE/CHARGE : from = club interne, to = tiers externe.
  - RECETTE/PRODUIT : to = club interne, from = tiers externe.

Le template est ouvert avec openpyxl (load_workbook) : styles, polices et cellules
oranges sont préservés ; on insère/supprime des lignes pour coller au nombre de
catégories, et on recalcule toutes les formules de totaux en conséquence.
"""
import io
import sqlite3
from copy import copy
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from backend.core.balance import compute_entity_balance
from backend.core.config import load_config
from backend.core.database import get_conn

router = APIRouter()

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
CONFIG_PATH = PROJECT_ROOT / "config.yaml"
ASSETS_DIR = Path(__file__).parent / "assets"
TEMPLATE_PATH = ASSETS_DIR / "template_direns.xlsx"

# Disposition du template (lignes Excel absolues du modèle d'origine).
EXP_FIRST = 7          # première ligne du bloc dépenses
EXP_SLOTS = 26         # lignes de saisie dépenses dans le modèle (7..32)
TOTAL_ROW = 33         # TOTAL DEPENSES (modèle)
FIN_FIRST = 35         # première ligne de financement (modèle)
FIN_SLOTS = 3          # lignes de saisie financement (35..37)
FIN_TOTAL = 38         # TOTAL FINANCEMENT RECU (modèle)
DEP_TOTAL = 39         # TOTAL DEPENSES REELLES (=total dépenses) (modèle)
SOLDE_PASS = 40        # SOLDE COMPTE BANCAIRE (Date passation)
SOLDE_TRES = 41        # SOLDE TRESORERIE (A date)
SOLDE_DATE = 42        # SOLDE COMPTE BANCAIRE (A date)
LABEL_NONE = "Non catégorisé"


# ───────────────────────── Accès aux données ──────────────────────────────

def _get_clubs(conn) -> list:
    """Entités internes (clubs), une par colonne, triées comme dans l'app."""
    rows = conn.execute(
        "SELECT id, name FROM entities WHERE type = 'internal' ORDER BY position ASC, id ASC"
    ).fetchall()
    return [dict(r) for r in rows]


def _resolve_fy(conn, fy_id: int) -> dict:
    row = conn.execute(
        "SELECT id, name, start_date, end_date FROM fiscal_years WHERE id = ?", (fy_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, f"Exercice {fy_id} introuvable")
    end = row["end_date"] or date.today().isoformat()
    return {"id": row["id"], "name": row["name"], "start": row["start_date"], "end": end}


def _category_names(conn) -> dict:
    return {r["id"]: r["name"] for r in conn.execute("SELECT id, name FROM categories").fetchall()}


def _get_expenses(conn, start: str, end: str, club_ids: list) -> dict:
    """{(club_id, category_id): cents} des dépenses réelles (sortantes vers l'externe)."""
    if not club_ids:
        return {}
    ph = ",".join("?" * len(club_ids))
    rows = conn.execute(
        f"""SELECT from_entity_id AS eid, category_id AS cid, SUM(amount) AS total
            FROM transactions
            WHERE date BETWEEN ? AND ?
              AND from_entity_id IN ({ph})
              AND to_entity_id NOT IN ({ph})
            GROUP BY from_entity_id, category_id""",
        [start, end] + club_ids + club_ids,
    ).fetchall()
    return {(r["eid"], r["cid"]): r["total"] for r in rows}


def _get_budget_expenses(conn, fy_id: int, club_ids: list) -> dict:
    """{(club_id, category_id): cents} des dépenses prévisionnelles (budget_allocations)."""
    if not club_ids:
        return {}
    ph = ",".join("?" * len(club_ids))
    try:
        rows = conn.execute(
            f"""SELECT entity_id AS eid, category_id AS cid, SUM(amount) AS total
                FROM budget_allocations
                WHERE fiscal_year_id = ? AND direction = 'expense' AND entity_id IN ({ph})
                GROUP BY entity_id, category_id""",
            [fy_id] + club_ids,
        ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {(r["eid"], r["cid"]): r["total"] for r in rows}


def _category_rows(conn, amounts: dict, clubs: list) -> list:
    """Transforme {(club_id, cat_id): cents} en lignes [(label, {club_idx: euros})].

    Une ligne par catégorie ayant un montant non nul, triée par nom (« Non
    catégorisé » en dernier). Les montants sont en euros.
    """
    names = _category_names(conn)
    id_to_idx = {c["id"]: i for i, c in enumerate(clubs)}
    per_cat: dict = {}
    for (club_id, cat_id), cents in amounts.items():
        idx = id_to_idx.get(club_id)
        if idx is None:
            continue
        per_cat.setdefault(cat_id, {})[idx] = per_cat.get(cat_id, {}).get(idx, 0) + cents
    rows = []
    for cat_id, per_club in per_cat.items():
        if sum(per_club.values()) == 0:
            continue
        label = names.get(cat_id) or LABEL_NONE
        euros = {idx: round(c / 100, 2) for idx, c in per_club.items() if c}
        rows.append((label, euros))
    rows.sort(key=lambda r: (r[0] == LABEL_NONE, r[0].lower()))
    return rows


def _income_rows(conn, start: str, end: str, club_ids: list) -> list:
    """Lignes de financement [(label, euros)] : recettes réelles par catégorie."""
    if not club_ids:
        return []
    ph = ",".join("?" * len(club_ids))
    rows = conn.execute(
        f"""SELECT category_id AS cid, SUM(amount) AS total
            FROM transactions
            WHERE date BETWEEN ? AND ?
              AND to_entity_id IN ({ph})
              AND from_entity_id NOT IN ({ph})
            GROUP BY category_id""",
        [start, end] + club_ids + club_ids,
    ).fetchall()
    names = _category_names(conn)
    out = []
    for r in rows:
        if not r["total"]:
            continue
        out.append((names.get(r["cid"]) or LABEL_NONE, round(r["total"] / 100, 2)))
    out.sort(key=lambda x: (x[0] == LABEL_NONE, x[0].lower()))
    return out


def _get_opening_total(conn, fy_id: int, club_ids: list, start: str) -> float:
    """Solde bancaire à l'ouverture de l'exercice (somme des clubs), en euros."""
    if not club_ids:
        return 0.0
    ph = ",".join("?" * len(club_ids))
    try:
        rows = conn.execute(
            f"SELECT entity_id, amount FROM fiscal_year_opening_balances "
            f"WHERE fiscal_year_id = ? AND entity_id IN ({ph})",
            [fy_id] + club_ids,
        ).fetchall()
    except sqlite3.OperationalError:
        rows = []
    if rows:
        return round(sum(r["amount"] for r in rows) / 100, 2)
    try:
        prev = (datetime.fromisoformat(start) - timedelta(days=1)).date().isoformat()
    except Exception:
        prev = None
    total = sum(compute_entity_balance(conn, eid, as_of_date=prev)["balance"] for eid in club_ids)
    return round(total / 100, 2)


def _get_current_total(conn, club_ids: list) -> float:
    """Solde bancaire courant (somme des clubs), en euros."""
    total = sum(compute_entity_balance(conn, eid)["balance"] for eid in club_ids)
    return round(total / 100, 2)


def _resolve_assoc_name(provided: str) -> str:
    if provided and provided.strip():
        return provided.strip()
    try:
        cfg = load_config(str(CONFIG_PATH))
        return cfg.entity.name or "Association"
    except Exception:
        return "Association"


# ───────────────────────── Génération du fichier ──────────────────────────

def _safe_title(title: str) -> str:
    for ch in "[]:*?/\\":
        title = title.replace(ch, "-")
    return title[:31]


def _capture_row_style(ws, row: int, total_col: int) -> dict:
    out = {}
    for c in range(1, total_col + 1):
        cell = ws.cell(row=row, column=c)
        if cell.has_style:
            out[c] = copy(cell._style)
    return out


def _apply_row_style(ws, row: int, styles: dict):
    for c, style in styles.items():
        ws.cell(row=row, column=c)._style = copy(style)


def _widen_sheet(ws, extra: int, total_col: int):
    """Insère `extra` colonnes (clubs > 4) en recopiant le style de la colonne E."""
    from openpyxl.utils import get_column_letter

    ws.insert_cols(6, extra)
    for r in range(1, 43):
        src = ws.cell(row=r, column=5)  # colonne E (modèle)
        for c in range(6, 6 + extra):
            dst = ws.cell(row=r, column=c)
            if src.has_style:
                dst._style = copy(src._style)
    e_width = ws.column_dimensions["E"].width
    if e_width:
        for c in range(6, 6 + extra):
            ws.column_dimensions[get_column_letter(c)].width = e_width
    tcl = get_column_letter(total_col)
    for row in (1, 3):
        existing = [str(m) for m in ws.merged_cells.ranges if m.min_row == row and m.max_row == row]
        for m in existing:
            ws.unmerge_cells(m)
        ws.merge_cells(f"A{row}:{tcl}{row}")


def _fill_sheet(ws, clubs, last_club_col, total_col, expense_rows, income_rows,
                with_financing, total_label, opening=None, current=None, fin_year_name=""):
    """Écrit en-têtes clubs, lignes catégories (dépenses), totaux et, si demandé,
    la section financement + soldes. Redimensionne les blocs au nombre de lignes."""
    from openpyxl.utils import get_column_letter

    # Styles de référence capturés AVANT toute insertion/suppression de lignes.
    data_style = _capture_row_style(ws, 8, total_col)              # ligne de saisie type
    fin_style = _capture_row_style(ws, FIN_FIRST, total_col) if with_financing else {}

    n = len(clubs)
    for i, club in enumerate(clubs):
        ws.cell(row=5, column=2 + i).value = club["name"]

    # ── Redimensionnement du bloc dépenses ──
    e = len(expense_rows)
    if e < EXP_SLOTS:
        ws.delete_rows(EXP_FIRST + e, EXP_SLOTS - e)
    elif e > EXP_SLOTS:
        ws.insert_rows(TOTAL_ROW, e - EXP_SLOTS)
    delta_exp = e - EXP_SLOTS
    total_row = TOTAL_ROW + delta_exp

    # Positions de la section financement après décalage du bloc dépenses.
    fin_first = FIN_FIRST + delta_exp
    fin_total = FIN_TOTAL + delta_exp
    dep_total = DEP_TOTAL + delta_exp
    solde_pass = SOLDE_PASS + delta_exp
    solde_tres = SOLDE_TRES + delta_exp
    solde_date = SOLDE_DATE + delta_exp

    if with_financing:
        i_count = len(income_rows)
        if i_count < FIN_SLOTS:
            ws.delete_rows(fin_first + i_count, FIN_SLOTS - i_count)
        elif i_count > FIN_SLOTS:
            ws.insert_rows(fin_total, i_count - FIN_SLOTS)
        delta_fin = i_count - FIN_SLOTS
        fin_total += delta_fin
        dep_total += delta_fin
        solde_pass += delta_fin
        solde_tres += delta_fin
        solde_date += delta_fin

    first_cl = get_column_letter(2)
    last_cl = get_column_letter(last_club_col)
    total_cl = get_column_letter(total_col)

    # ── Écriture des lignes catégories (dépenses) ──
    for k, (label, euros) in enumerate(expense_rows):
        r = EXP_FIRST + k
        _apply_row_style(ws, r, data_style)
        ws.cell(row=r, column=1).value = label
        for idx, val in euros.items():
            ws.cell(row=r, column=2 + idx).value = val
        ws.cell(row=r, column=total_col).value = f"=SUM({first_cl}{r}:{last_cl}{r})"

    # ── Ligne TOTAL dépenses ──
    ws.cell(row=total_row, column=1).value = total_label
    if e > 0:
        for i in range(n):
            cl = get_column_letter(2 + i)
            ws.cell(row=total_row, column=2 + i).value = f"=SUM({cl}{EXP_FIRST}:{cl}{total_row - 1})"
        ws.cell(row=total_row, column=total_col).value = f"=SUM({first_cl}{total_row}:{last_cl}{total_row})"
    else:
        ws.cell(row=total_row, column=total_col).value = 0

    # ── Section financement (bilan uniquement) ──
    if with_financing:
        i_count = len(income_rows)
        for k, (label, val) in enumerate(income_rows):
            r = fin_first + k
            _apply_row_style(ws, r, fin_style)
            ws.cell(row=r, column=1).value = label
            ws.cell(row=r, column=2).value = val
        ws.cell(row=fin_total, column=1).value = f"TOTAL FINANCEMENT RECU {fin_year_name}"
        ws.cell(row=fin_total, column=2).value = (
            f"=SUM(B{fin_first}:B{fin_first + i_count - 1})" if i_count > 0 else 0
        )
        ws.cell(row=dep_total, column=1).value = (
            f"TOTAL DEPENSES REELLES {fin_year_name} (cf tableau ci-dessus)"
        )
        ws.cell(row=dep_total, column=2).value = f"={total_cl}{total_row}"
        ws.cell(row=solde_pass, column=2).value = opening
        ws.cell(row=solde_tres, column=2).value = f"=B{fin_total}-B{dep_total}+B{solde_pass}"
        ws.cell(row=solde_date, column=2).value = current


def _build_excel(conn, bilan_fy: dict, budget_fy: Optional[dict], assoc_name: str) -> bytes:
    from openpyxl import load_workbook

    wb = load_workbook(str(TEMPLATE_PATH))
    clubs = _get_clubs(conn)
    club_ids = [c["id"] for c in clubs]
    n = len(clubs)
    if n <= 4:
        last_club_col, total_col, extra = 5, 6, 0
    else:
        extra = n - 4
        last_club_col, total_col = n + 1, n + 2

    # ── Onglet 1 : bilan financier (réalisé) ──
    ws1 = wb.worksheets[0]
    if extra:
        _widen_sheet(ws1, extra, total_col)
    exp_rows = _category_rows(conn, _get_expenses(conn, bilan_fy["start"], bilan_fy["end"], club_ids), clubs)
    inc_rows = _income_rows(conn, bilan_fy["start"], bilan_fy["end"], club_ids)
    _fill_sheet(
        ws1, clubs, last_club_col, total_col, exp_rows, inc_rows,
        with_financing=True, total_label="TOTAL DEPENSES REELLES",
        opening=_get_opening_total(conn, bilan_fy["id"], club_ids, bilan_fy["start"]),
        current=_get_current_total(conn, club_ids),
        fin_year_name=bilan_fy["name"],
    )
    ws1["A1"] = f"BILAN FINANCIER {bilan_fy['name']}"
    ws1["A3"] = assoc_name
    try:
        ws1.title = _safe_title(f"Bilan financier {bilan_fy['name']}")
    except Exception:
        pass

    # ── Onglet 2 : budget prévisionnel ──
    if budget_fy:
        ws2 = wb.worksheets[1]
        if extra:
            _widen_sheet(ws2, extra, total_col)
        bexp = _category_rows(conn, _get_budget_expenses(conn, budget_fy["id"], club_ids), clubs)
        _fill_sheet(
            ws2, clubs, last_club_col, total_col, bexp, [],
            with_financing=False, total_label="TOTAL DEPENSES PREVISONNELLES (E)",
        )
        ws2["A1"] = f"BUDGET PREVISIONNEL {budget_fy['name']}"
        ws2["A3"] = assoc_name
        try:
            ws2.title = _safe_title(f"Budget previsionnel {budget_fy['name']}")
        except Exception:
            pass

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


# ───────────────────────── Endpoint ────────────────────────────────────────

@router.get("/export")
def export_direns(
    bilan_fiscal_year_id: int,
    budget_fiscal_year_id: Optional[int] = None,
    assoc_name: str = "",
):
    """Génère le fichier Excel DirENS pré-rempli (onglets 1 et 2), lignes = catégories."""
    if not TEMPLATE_PATH.exists():
        raise HTTPException(500, "Template DirENS introuvable dans le module (assets/template_direns.xlsx).")
    try:
        import openpyxl  # noqa: F401
    except ImportError:
        raise HTTPException(500, "openpyxl non installé : impossible de générer le fichier Excel.")

    conn = get_conn()
    try:
        bilan_fy = _resolve_fy(conn, bilan_fiscal_year_id)
        budget_fy = _resolve_fy(conn, budget_fiscal_year_id) if budget_fiscal_year_id else None
        name = _resolve_assoc_name(assoc_name)
        data = _build_excel(conn, bilan_fy, budget_fy, name)
    finally:
        conn.close()

    safe = bilan_fy["name"].replace(" ", "_").replace("/", "-")
    filename = f"DirENS_{safe}.xlsx"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
