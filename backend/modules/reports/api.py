"""Module Rapports — Compte de résultat et bilan simplifié pour l'AG.

Convention monétaire (C1+C2) :
  - amount en DB = entier de centimes, TOUJOURS POSITIF.
  - Sens porté par from_entity_id -> to_entity_id.
  - PRODUIT/RECETTE : to_entity INTERNE et from_entity EXTERNE.
  - CHARGE/DÉPENSE  : from_entity INTERNE et to_entity EXTERNE.
  - VIREMENT INTERNE (les deux internes) : ni produit ni charge.

Module en LECTURE SEULE — aucune table propre.
"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from backend.core.balance import compute_consolidated_balance
from backend.core.database import get_conn

router = APIRouter()


def _resolve_period(conn, fiscal_year_id: Optional[int],
                    start_date: Optional[str], end_date: Optional[str]):
    """Retourne (start, end) sous forme de chaînes ISO.

    Si fiscal_year_id fourni, lit les bornes depuis fiscal_years.
    Sinon, utilise start_date / end_date directement.
    Lève 400 si aucune borne n'est fournie, 404 si l'exercice est introuvable.
    """
    if fiscal_year_id is not None:
        row = conn.execute(
            "SELECT start_date, end_date FROM fiscal_years WHERE id = ?",
            (fiscal_year_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(404, f"Exercice fiscal {fiscal_year_id} introuvable")
        start = row["start_date"] if hasattr(row, "keys") else row[0]
        end = row["end_date"] if hasattr(row, "keys") else row[1]
        if not end:
            from datetime import date
            end = date.today().isoformat()
        return start, end

    if not start_date or not end_date:
        raise HTTPException(
            400,
            "Paramètres manquants : fournir fiscal_year_id ou start_date + end_date",
        )
    return start_date, end_date


def _get_internal_ids(conn) -> list:
    """Liste des identifiants d'entités internes."""
    rows = conn.execute("SELECT id FROM entities WHERE type = 'internal'").fetchall()
    return [(r["id"] if hasattr(r, "keys") else r[0]) for r in rows]


def _aggregate_compte_resultat(conn, start: str, end: str) -> dict:
    """Calcule produits et charges agrégés par catégorie sur la période.

    Produits : transactions dont to_entity est interne ET from_entity est externe.
    Charges  : transactions dont from_entity est interne ET to_entity est externe.
    Virements internes (from interne ET to interne) : ignorés.
    """
    internal_ids = _get_internal_ids(conn)
    if not internal_ids:
        return {
            "produits": [],
            "charges": [],
            "total_produits": 0,
            "total_charges": 0,
            "resultat": 0,
        }

    ph = ",".join("?" * len(internal_ids))

    # --- Produits : to interne, from externe ---
    produits_rows = conn.execute(
        f"""SELECT
                t.category_id,
                COALESCE(c.name, 'Sans catégorie') AS category_name,
                SUM(t.amount) AS montant
            FROM transactions t
            LEFT JOIN categories c ON c.id = t.category_id
            WHERE t.to_entity_id IN ({ph})
              AND t.from_entity_id NOT IN ({ph})
              AND t.date BETWEEN ? AND ?
            GROUP BY t.category_id, c.name
            ORDER BY c.name""",
        internal_ids + internal_ids + [start, end],
    ).fetchall()

    # --- Charges : from interne, to externe ---
    charges_rows = conn.execute(
        f"""SELECT
                t.category_id,
                COALESCE(c.name, 'Sans catégorie') AS category_name,
                SUM(t.amount) AS montant
            FROM transactions t
            LEFT JOIN categories c ON c.id = t.category_id
            WHERE t.from_entity_id IN ({ph})
              AND t.to_entity_id NOT IN ({ph})
              AND t.date BETWEEN ? AND ?
            GROUP BY t.category_id, c.name
            ORDER BY c.name""",
        internal_ids + internal_ids + [start, end],
    ).fetchall()

    def _row_to_dict(row):
        if hasattr(row, "keys"):
            return dict(row)
        return {"category_id": row[0], "category_name": row[1], "montant": row[2]}

    produits = [_row_to_dict(r) for r in produits_rows]
    charges = [_row_to_dict(r) for r in charges_rows]

    total_produits = sum(p["montant"] for p in produits)
    total_charges = sum(c["montant"] for c in charges)

    return {
        "produits": produits,
        "charges": charges,
        "total_produits": total_produits,
        "total_charges": total_charges,
        "resultat": total_produits - total_charges,
    }


@router.get("/compte-resultat")
def get_compte_resultat(
    fiscal_year_id: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    entity_id: Optional[int] = None,
):
    """Compte de résultat sur une période.

    Accepte soit fiscal_year_id, soit start_date + end_date.
    Renvoie produits/charges par catégorie, totaux et résultat (en centimes).
    """
    conn = get_conn()
    try:
        start, end = _resolve_period(conn, fiscal_year_id, start_date, end_date)
        result = _aggregate_compte_resultat(conn, start, end)
        result["periode"] = {"start": start, "end": end}
        return result
    finally:
        conn.close()


@router.get("/compte-resultat/pdf")
def get_compte_resultat_pdf(
    fiscal_year_id: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    entity_id: Optional[int] = None,
):
    """Export PDF du compte de résultat.

    Même paramètres que GET /compte-resultat.
    Utilise fpdf2.
    """
    conn = get_conn()
    try:
        start, end = _resolve_period(conn, fiscal_year_id, start_date, end_date)
        data = _aggregate_compte_resultat(conn, start, end)
    finally:
        conn.close()

    try:
        from fpdf import FPDF
    except ImportError:
        raise HTTPException(500, "fpdf2 non installé — impossible de générer le PDF")

    pdf = FPDF()
    pdf.add_page()

    # Titre
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 12, "Compte de resultat", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"Periode : {start} au {end}", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(6)

    # Section Produits
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "PRODUITS", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_fill_color(240, 248, 240)
    pdf.cell(130, 7, "Categorie", border=1, fill=True)
    pdf.cell(50, 7, "Montant (EUR)", border=1, fill=True, align="R",
             new_x="LMARGIN", new_y="NEXT")
    for p in data["produits"]:
        eur = p["montant"] / 100
        pdf.cell(130, 6, str(p["category_name"])[:50], border=1)
        pdf.cell(50, 6, f"{eur:.2f}", border=1, align="R",
                 new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(130, 7, "TOTAL PRODUITS", border=1)
    pdf.cell(50, 7, f"{data['total_produits'] / 100:.2f}", border=1, align="R",
             new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # Section Charges
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "CHARGES", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_fill_color(255, 240, 240)
    pdf.cell(130, 7, "Categorie", border=1, fill=True)
    pdf.cell(50, 7, "Montant (EUR)", border=1, fill=True, align="R",
             new_x="LMARGIN", new_y="NEXT")
    for c in data["charges"]:
        eur = c["montant"] / 100
        pdf.cell(130, 6, str(c["category_name"])[:50], border=1)
        pdf.cell(50, 6, f"{eur:.2f}", border=1, align="R",
                 new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(130, 7, "TOTAL CHARGES", border=1)
    pdf.cell(50, 7, f"{data['total_charges'] / 100:.2f}", border=1, align="R",
             new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)

    # Resultat
    resultat = data["resultat"]
    label = "Excedent" if resultat >= 0 else "Deficit"
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_fill_color(220, 220, 255)
    pdf.cell(130, 9, f"{label} de l'exercice", border=1, fill=True)
    pdf.cell(50, 9, f"{abs(resultat) / 100:.2f}", border=1, fill=True, align="R",
             new_x="LMARGIN", new_y="NEXT")

    pdf.ln(8)
    pdf.set_font("Helvetica", "I", 8)
    pdf.multi_cell(0, 5, "Hypotheses : montants en EUR (centimes / 100). "
                         "Produits = flux entrant depuis l'exterieur vers une entite interne. "
                         "Charges = flux sortant d'une entite interne vers l'exterieur. "
                         "Virements internes exclus.")

    pdf_bytes = bytes(pdf.output())
    filename = f"compte-resultat_{start}_{end}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/bilan")
def get_bilan(
    entity_id: Optional[int] = None,
):
    """Bilan simplifié de trésorerie.

    Hypothèses :
    - Actif = somme des soldes consolidés des entités internes racines (parent_id IS NULL).
    - Chaque ligne = (entity_id, name, solde consolidé en centimes).
    - Entités racines à solde nul incluses pour la complétude.
    - Les entités enfants sont incluses dans le solde consolidé de leur racine.
    """
    conn = get_conn()
    try:
        # Entités internes racines
        rows = conn.execute(
            "SELECT id, name FROM entities WHERE type = 'internal' AND parent_id IS NULL"
        ).fetchall()

        tresorerie = []
        total_actif = 0

        for row in rows:
            eid = row["id"] if hasattr(row, "keys") else row[0]
            ename = row["name"] if hasattr(row, "keys") else row[1]
            bal = compute_consolidated_balance(conn, eid)
            solde = bal.get("consolidated_balance", bal.get("balance", 0))
            tresorerie.append({
                "entity_id": eid,
                "name": ename,
                "solde": solde,
            })
            if solde > 0:
                total_actif += solde

        return {
            "tresorerie_par_entite": tresorerie,
            "total_actif": total_actif,
            "hypotheses": (
                "Actif = soldes consolidés positifs des entités internes racines. "
                "Montants en centimes. Virements internes neutralisés dans le consolidé."
            ),
        }
    finally:
        conn.close()
