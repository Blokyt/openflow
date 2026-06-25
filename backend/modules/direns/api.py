"""Module DirENS — génération de l'Excel financier officiel pré-rempli.

Remplit de façon déterministe les DEUX premiers onglets du template officiel
DirENS (bundlé dans assets/template_direns.xlsx) à partir des données de l'app :

  - Onglet 1 « Bilan financier {AAAA-AAAA} » : dépenses RÉALISÉES de l'exercice
    clôturé, ventilées par club (une colonne par entité interne) et par ligne de
    nature (mapping catégorie -> ligne), plus la section financement (recettes)
    et les soldes de trésorerie.
  - Onglet 2 « Budget prévisionnel {AAAA-AAAA} » : dépenses PRÉVISIONNELLES de
    l'exercice suivant, issues de budget_allocations (direction='expense').
  - Onglet 3 « Demande subventions » : laissé vierge.

Convention monétaire (comme tout OpenFlow) : amount = entier de centimes, positif.
Sens porté par from_entity_id -> to_entity_id :
  - DÉPENSE/CHARGE : from = club interne, to = tiers externe.
  - RECETTE/PRODUIT : to = club interne, from = tiers externe.

Le template est ouvert avec openpyxl (load_workbook) : styles, fusions, polices et
cellules oranges sont préservés à l'identique. On n'écrit que des valeurs et des
formules de totaux ; on ne reconstruit jamais la mise en forme.
"""
import io
import sqlite3
from copy import copy
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from backend.core.balance import compute_entity_balance
from backend.core.config import load_config
from backend.core.database import get_conn

router = APIRouter()

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
CONFIG_PATH = PROJECT_ROOT / "config.yaml"
ASSETS_DIR = Path(__file__).parent / "assets"
TEMPLATE_PATH = ASSETS_DIR / "template_direns.xlsx"


# ───────────────────────── Structure du template ──────────────────────────
# Numéros de ligne Excel ABSOLUS, identiques sur les deux onglets remplis.
DIRENS_ROWS = {
    8: "Nourriture",
    9: "Boissons",
    10: "Fournitures",
    11: "Matériel",
    12: "Autres (achats)",
    15: "Location d'hébergement",
    16: "Location de salles",
    17: "Location de bus",
    18: "Location de voitures",
    19: "Location de matériels",
    20: "Déplacements (train…)",
    21: "Assurance",
    22: "Autres (services)",
    24: "Prestataire extérieur 1",
    25: "Prestataire extérieur 2",
    26: "Prestataire extérieur 3",
    27: "Prestataire extérieur 4",
    29: "Club à financer 1",
    30: "Club à financer 2",
    31: "Club à financer 3",
    32: "Club à financer 4",
    35: "Financement DirENS",
    36: "Financement N°2",
    37: "Financement N°…",
}
INCOME_ROWS = (35, 36, 37)
EXPENSE_ROWS = tuple(r for r in DIRENS_ROWS if r not in INCOME_ROWS)
TITLE_ROWS = (7, 14, 23, 28)
TOTAL_ROWS = (33, 38, 39, 40, 41, 42)

# Regroupement pour l'écran de correspondance (UI).
ROW_GROUPS = [
    ("Achats", "expense", (8, 9, 10, 11, 12)),
    ("Services extérieurs", "expense", (15, 16, 17, 18, 19, 20, 21, 22)),
    ("Prestataires extérieurs", "expense", (24, 25, 26, 27)),
    ("Clubs à financer", "expense", (29, 30, 31, 32)),
    ("Financements (recettes)", "income", (35, 36, 37)),
]


def _row_catalog() -> list:
    return [
        {
            "group": group,
            "section": section,
            "rows": [{"row": r, "label": DIRENS_ROWS[r]} for r in rows],
        }
        for group, section, rows in ROW_GROUPS
    ]


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


def _mapping(conn):
    """(category_id -> direns_row) pour les dépenses, et idem pour les recettes."""
    rows = conn.execute(
        "SELECT category_id, direns_row, section FROM direns_line_map"
    ).fetchall()
    expense = {r["category_id"]: r["direns_row"] for r in rows if r["section"] == "expense"}
    income = {r["category_id"]: r["direns_row"] for r in rows if r["section"] == "income"}
    return expense, income


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


def _aggregate_income(conn, start: str, end: str, club_ids: list, cat_to_income_row: dict) -> dict:
    """{direns_row: euros} des recettes réelles (entrantes depuis l'externe)."""
    if not club_ids:
        return {}
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
    by_row: dict = {}
    for r in rows:
        row = cat_to_income_row.get(r["cid"])
        if row is None:
            continue
        by_row[row] = by_row.get(row, 0) + r["total"]
    return {row: round(cents / 100, 2) for row, cents in by_row.items()}


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
    # Repli : solde consolidé la veille de l'ouverture.
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
    # Ré-étend les fusions de titre (lignes 1 et 3) sur toute la largeur.
    tcl = get_column_letter(total_col)
    for row in (1, 3):
        existing = [str(m) for m in ws.merged_cells.ranges if m.min_row == row and m.max_row == row]
        for m in existing:
            ws.unmerge_cells(m)
        ws.merge_cells(f"A{row}:{tcl}{row}")


def _fill_sheet_expenses(ws, clubs, last_club_col, total_col, amounts, cat_to_row):
    """Écrit en-têtes clubs, montants de dépense (euros) et formules de totaux."""
    from openpyxl.utils import get_column_letter

    id_to_idx = {c["id"]: i for i, c in enumerate(clubs)}
    for i, club in enumerate(clubs):
        ws.cell(row=5, column=2 + i).value = club["name"]

    matrix: dict = {}
    for (club_id, cat_id), cents in amounts.items():
        row = cat_to_row.get(cat_id)
        if row is None:
            continue
        idx = id_to_idx.get(club_id)
        if idx is None:
            continue
        matrix[(row, idx)] = matrix.get((row, idx), 0) + cents
    for (row, idx), cents in matrix.items():
        if cents:
            ws.cell(row=row, column=2 + idx).value = round(cents / 100, 2)

    first = get_column_letter(2)               # B
    last = get_column_letter(last_club_col)    # E (ou plus si >4 clubs)
    # Total par ligne de nature (colonne TOTAL).
    for row in EXPENSE_ROWS:
        ws.cell(row=row, column=total_col).value = f"=SUM({first}{row}:{last}{row})"
    # Ligne 33 (TOTAL DEPENSES) par club, puis total général.
    for i in range(len(clubs)):
        cl = get_column_letter(2 + i)
        ws.cell(row=33, column=2 + i).value = f"=SUM({cl}8:{cl}32)"
    ws.cell(row=33, column=total_col).value = f"=SUM({first}33:{last}33)"


def _build_excel(conn, bilan_fy: dict, budget_fy: Optional[dict], assoc_name: str) -> bytes:
    from openpyxl import load_workbook
    from openpyxl.utils import get_column_letter

    wb = load_workbook(str(TEMPLATE_PATH))
    clubs = _get_clubs(conn)
    club_ids = [c["id"] for c in clubs]
    n = len(clubs)
    cat_to_row, cat_to_income_row = _mapping(conn)

    if n <= 4:
        last_club_col, total_col, extra = 5, 6, 0
    else:
        extra = n - 4
        last_club_col, total_col = n + 1, n + 2

    # ── Onglet 1 : bilan financier (réalisé) ──
    ws1 = wb.worksheets[0]
    if extra:
        _widen_sheet(ws1, extra, total_col)
    _fill_sheet_expenses(
        ws1, clubs, last_club_col, total_col,
        _get_expenses(conn, bilan_fy["start"], bilan_fy["end"], club_ids), cat_to_row,
    )
    ws1["A1"] = f"BILAN FINANCIER {bilan_fy['name']}"
    ws1["A3"] = assoc_name
    ws1["A38"] = f"TOTAL FINANCEMENT RECU {bilan_fy['name']}"
    ws1["A39"] = f"TOTAL DEPENSES REELLES {bilan_fy['name']} (cf tableau ci-dessus)"

    # Section financement (recettes), colonne B + soldes.
    for row, amount in _aggregate_income(
        conn, bilan_fy["start"], bilan_fy["end"], club_ids, cat_to_income_row
    ).items():
        ws1.cell(row=row, column=2).value = amount
    tcl = get_column_letter(total_col)
    ws1["B38"] = "=SUM(B35:B37)"
    ws1["B39"] = f"={tcl}33"
    ws1["B40"] = _get_opening_total(conn, bilan_fy["id"], club_ids, bilan_fy["start"])
    ws1["B41"] = "=B38-B39+B40"
    ws1["B42"] = _get_current_total(conn, club_ids)
    try:
        ws1.title = _safe_title(f"Bilan financier {bilan_fy['name']}")
    except Exception:
        pass

    # ── Onglet 2 : budget prévisionnel ──
    if budget_fy:
        ws2 = wb.worksheets[1]
        if extra:
            _widen_sheet(ws2, extra, total_col)
        _fill_sheet_expenses(
            ws2, clubs, last_club_col, total_col,
            _get_budget_expenses(conn, budget_fy["id"], club_ids), cat_to_row,
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


# ───────────────────────── Endpoints ──────────────────────────────────────

class LineMapIn(BaseModel):
    category_id: int
    direns_row: int
    section: str = "expense"
    notes: str = ""


@router.get("/line-map")
def get_line_map():
    """Mapping actuel + catégories non mappées + catalogue des lignes DirENS."""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT m.category_id, c.name AS category_name, m.direns_row, m.section, m.notes
               FROM direns_line_map m
               JOIN categories c ON c.id = m.category_id
               ORDER BY m.section, m.direns_row, c.name"""
        ).fetchall()
        unmapped = conn.execute(
            """SELECT id AS category_id, name AS category_name FROM categories
               WHERE id NOT IN (SELECT category_id FROM direns_line_map)
               ORDER BY name"""
        ).fetchall()
        return {
            "mapping": [dict(r) for r in rows],
            "unmapped": [dict(r) for r in unmapped],
            "rows": _row_catalog(),
        }
    finally:
        conn.close()


@router.put("/line-map")
def put_line_map(body: LineMapIn):
    """Associe (ou réassocie) une catégorie à une ligne DirENS."""
    if body.direns_row not in DIRENS_ROWS:
        raise HTTPException(400, f"Ligne DirENS {body.direns_row} inconnue ou non saisissable")
    if body.section not in ("expense", "income"):
        raise HTTPException(400, "section doit être 'expense' ou 'income'")
    expected = "income" if body.direns_row in INCOME_ROWS else "expense"
    if expected != body.section:
        raise HTTPException(400, f"La ligne {body.direns_row} relève de la section '{expected}'")
    conn = get_conn()
    try:
        if conn.execute("SELECT 1 FROM categories WHERE id = ?", (body.category_id,)).fetchone() is None:
            raise HTTPException(404, f"Catégorie {body.category_id} introuvable")
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """INSERT INTO direns_line_map (category_id, direns_row, section, notes, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(category_id) DO UPDATE SET
                 direns_row = excluded.direns_row,
                 section = excluded.section,
                 notes = excluded.notes,
                 updated_at = excluded.updated_at""",
            (body.category_id, body.direns_row, body.section, body.notes, now, now),
        )
        conn.commit()
        return {"category_id": body.category_id, "direns_row": body.direns_row, "section": body.section}
    finally:
        conn.close()


@router.delete("/line-map/{category_id}")
def delete_line_map(category_id: int):
    conn = get_conn()
    try:
        conn.execute("DELETE FROM direns_line_map WHERE category_id = ?", (category_id,))
        conn.commit()
        return {"deleted": category_id}
    finally:
        conn.close()


@router.get("/export")
def export_direns(
    bilan_fiscal_year_id: int,
    budget_fiscal_year_id: Optional[int] = None,
    assoc_name: str = "",
):
    """Génère le fichier Excel DirENS pré-rempli (onglets 1 et 2)."""
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
