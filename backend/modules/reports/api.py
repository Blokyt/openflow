"""Module Rapports — compte de résultat et bilan officiels (asso loi 1901).

Convention monétaire (C1+C2) :
  - amount en DB = entier de centimes, TOUJOURS POSITIF.
  - Sens porté par from_entity_id -> to_entity_id.
  - PRODUIT/RECETTE : to_entity INTERNE et from_entity EXTERNE.
  - CHARGE/DÉPENSE  : from_entity INTERNE et to_entity EXTERNE.
  - VIREMENT INTERNE (les deux internes) : ni produit ni charge.

Phase 1 (méthode trésorerie) :
  - Plan comptable associatif simplifié (table report_accounts, seedée).
  - Pont non destructif catégorie -> compte (table category_account_map). Le
    mapping ne fait que VENTILER les catégories en postes normalisés ; il ne
    change jamais les totaux (qui restent calculés par le sens from/to).
  - Bilan par exercice : actif = disponibilités de clôture ; passif = report à
    nouveau (trésorerie d'ouverture) + résultat de l'exercice. L'équilibre
    actif = passif est garanti par construction :
        somme_internes (ouverture + réalisé) = somme ouverture + (produits - charges)
    car les virements internes s'annulent dans la somme des réalisés.

La couche engagement (créances/dettes, extournes) arrive en Phase 2.
"""
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from backend.core.balance import (
    compute_consolidated_balance,
    compute_entity_balance,
    compute_entity_balance_for_period,
)
from backend.core.database import get_conn

router = APIRouter()


# ───────────────────────── Période & entités ──────────────────────────────

def _resolve_period(conn, fiscal_year_id: Optional[int],
                    start_date: Optional[str], end_date: Optional[str]):
    """Retourne (start, end) ISO. Soit depuis fiscal_years, soit direct."""
    if fiscal_year_id is not None:
        row = conn.execute(
            "SELECT start_date, end_date FROM fiscal_years WHERE id = ?",
            (fiscal_year_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(404, f"Exercice fiscal {fiscal_year_id} introuvable")
        start = row["start_date"]
        end = row["end_date"]
        if not end:
            end = date.today().isoformat()
        return start, end

    if not start_date or not end_date:
        raise HTTPException(
            400,
            "Paramètres manquants : fournir fiscal_year_id ou start_date + end_date",
        )
    return start_date, end_date


def _get_internal_ids(conn) -> list:
    rows = conn.execute("SELECT id FROM entities WHERE type = 'internal'").fetchall()
    return [r["id"] for r in rows]


# ───────────────────────── Plan comptable & mapping ───────────────────────

def _account_list(conn) -> list:
    rows = conn.execute(
        "SELECT id, code, label, kind, pcg_class, is_default, position "
        "FROM report_accounts ORDER BY position, code"
    ).fetchall()
    return [dict(r) for r in rows]


def _default_account(conn, kind: str) -> Optional[dict]:
    row = conn.execute(
        "SELECT id, code, label, kind FROM report_accounts "
        "WHERE kind = ? AND is_default = 1 ORDER BY position LIMIT 1",
        (kind,),
    ).fetchone()
    return dict(row) if row else None


def _mapping_dict(conn) -> dict:
    """category_id -> {account_id, account_code, account_label, account_kind}."""
    rows = conn.execute(
        """SELECT m.category_id,
                  a.id    AS account_id,
                  a.code  AS account_code,
                  a.label AS account_label,
                  a.kind  AS account_kind
           FROM category_account_map m
           JOIN report_accounts a ON a.id = m.account_id"""
    ).fetchall()
    return {r["category_id"]: dict(r) for r in rows}


def _account_context(conn) -> dict:
    """Charge le plan comptable une seule fois pour la ventilation par compte :
    mapping catégorie->compte, comptes « Autres » par défaut, et positions."""
    accounts = _account_list(conn)
    defaults: dict = {}
    for a in accounts:
        if a["is_default"] and a["kind"] not in defaults:
            defaults[a["kind"]] = a
    return {
        "mapping": _mapping_dict(conn),
        "defaults": defaults,
        "positions": {a["id"]: a["position"] for a in accounts},
    }


def _group_by_account(rows: list, kind: str, ctx: dict) -> list:
    """Regroupe des lignes {category_id, category_name, montant} par compte.

    Une catégorie mappée vers un compte du bon sens va dans ce compte ; sinon
    elle tombe dans le compte « Autres » du sens (is_default). Les totaux par
    compte somment exactement les montants d'entrée (le mapping ne crée ni ne
    détruit de montant). `ctx` vient de `_account_context` (chargé une fois).
    """
    mapping = ctx["mapping"]
    default_acc = ctx["defaults"].get(kind)
    positions = ctx["positions"]

    buckets: dict = {}
    for r in rows:
        cat_id = r["category_id"]
        m = mapping.get(cat_id)
        if m and m["account_kind"] == kind:
            acc_id, code, label = m["account_id"], m["account_code"], m["account_label"]
        elif default_acc is not None:
            acc_id, code, label = default_acc["id"], default_acc["code"], default_acc["label"]
        else:  # garde-fou : aucun compte par défaut (ne devrait pas arriver)
            acc_id, code, label = None, "-", "Non classé"
        b = buckets.setdefault(
            acc_id,
            {"account_id": acc_id, "code": code, "label": label, "montant": 0, "categories": []},
        )
        b["montant"] += r["montant"]
        b["categories"].append({
            "category_id": cat_id,
            "category_name": r["category_name"],
            "montant": r["montant"],
        })
    return sorted(buckets.values(), key=lambda x: positions.get(x["account_id"], 9999))


@router.get("/accounts")
def get_accounts():
    """Plan comptable associatif simplifié (comptes de classes 6/7 et postes de bilan)."""
    conn = get_conn()
    try:
        return {"accounts": _account_list(conn)}
    finally:
        conn.close()


@router.get("/mapping")
def get_mapping():
    """Correspondance catégorie -> compte, et catégories encore non mappées."""
    conn = get_conn()
    try:
        mapped = conn.execute(
            """SELECT m.category_id, c.name AS category_name,
                      a.id AS account_id, a.code AS account_code, a.label AS account_label
               FROM category_account_map m
               JOIN categories c ON c.id = m.category_id
               JOIN report_accounts a ON a.id = m.account_id
               ORDER BY c.name"""
        ).fetchall()
        mapped_ids = {r["category_id"] for r in mapped}
        all_cats = conn.execute(
            "SELECT id AS category_id, name AS category_name FROM categories ORDER BY name"
        ).fetchall()
        unmapped = [dict(c) for c in all_cats if c["category_id"] not in mapped_ids]
        return {"mapping": [dict(r) for r in mapped], "unmapped": unmapped}
    finally:
        conn.close()


class MappingIn(BaseModel):
    category_id: int
    account_id: Optional[int] = None  # None => dissocier la catégorie


@router.put("/mapping")
def put_mapping(body: MappingIn):
    """Associe (ou dissocie si account_id est nul) une catégorie à un compte 6/7."""
    conn = get_conn()
    try:
        if conn.execute("SELECT 1 FROM categories WHERE id = ?", (body.category_id,)).fetchone() is None:
            raise HTTPException(404, f"Catégorie {body.category_id} introuvable")

        if body.account_id is None:
            conn.execute("DELETE FROM category_account_map WHERE category_id = ?", (body.category_id,))
            conn.commit()
            return {"category_id": body.category_id, "account_id": None}

        acc = conn.execute(
            "SELECT kind FROM report_accounts WHERE id = ?", (body.account_id,)
        ).fetchone()
        if acc is None:
            raise HTTPException(404, f"Compte {body.account_id} introuvable")
        if acc["kind"] not in ("produit", "charge"):
            raise HTTPException(400, "Seuls les comptes de produits ou de charges peuvent être mappés")

        conn.execute(
            """INSERT INTO category_account_map (category_id, account_id) VALUES (?, ?)
               ON CONFLICT(category_id) DO UPDATE SET account_id = excluded.account_id""",
            (body.category_id, body.account_id),
        )
        conn.commit()
        return {"category_id": body.category_id, "account_id": body.account_id}
    finally:
        conn.close()


# ───────────────────────── Compte de résultat ─────────────────────────────

def _category_rows(conn, internal_ids, ph, start, end, in_col, out_col) -> list:
    """Montants par catégorie d'un sens de flux (in_col interne, out_col externe)."""
    return [dict(r) for r in conn.execute(
        f"""SELECT t.category_id,
                   COALESCE(c.name, 'Sans catégorie') AS category_name,
                   SUM(t.amount) AS montant
            FROM transactions t
            LEFT JOIN categories c ON c.id = t.category_id
            WHERE t.{in_col} IN ({ph})
              AND t.{out_col} NOT IN ({ph})
              AND t.date BETWEEN ? AND ?
            GROUP BY t.category_id, c.name
            ORDER BY c.name""",
        internal_ids + internal_ids + [start, end],
    ).fetchall()]


def _cr_category_rows(conn, start: str, end: str):
    """(produits, charges) par catégorie sur la période (méthode trésorerie)."""
    internal_ids = _get_internal_ids(conn)
    if not internal_ids:
        return [], []
    ph = ",".join("?" * len(internal_ids))
    produits = _category_rows(conn, internal_ids, ph, start, end, "to_entity_id", "from_entity_id")
    charges = _category_rows(conn, internal_ids, ph, start, end, "from_entity_id", "to_entity_id")
    return produits, charges


def _build_compte_resultat(conn, produits: list, charges: list, periode: dict,
                           engagement: Optional[dict] = None) -> dict:
    """Assemble la réponse : ventilation par compte (groupée une seule fois),
    totaux, résultat. `produits`/`charges` sont des lignes nettes par catégorie."""
    ctx = _account_context(conn)
    total_produits = sum(p["montant"] for p in produits)
    total_charges = sum(c["montant"] for c in charges)
    result = {
        "produits": produits,
        "charges": charges,
        "produits_par_compte": _group_by_account(produits, "produit", ctx),
        "charges_par_compte": _group_by_account(charges, "charge", ctx),
        "total_produits": total_produits,
        "total_charges": total_charges,
        "resultat": total_produits - total_charges,
        "periode": periode,
    }
    if engagement is not None:
        result["engagement"] = engagement
    return result


def _aggregate_compte_resultat(conn, start: str, end: str) -> dict:
    """Compte de résultat trésorerie sur une période (par catégorie et par compte)."""
    produits, charges = _cr_category_rows(conn, start, end)
    return _build_compte_resultat(conn, produits, charges, {"start": start, "end": end})


# ── Couche engagement : régularisations et extournes (Phase 2) ──

def _prev_fy_id(conn, fiscal_year_id: int) -> Optional[int]:
    row = conn.execute(
        "SELECT previous_fiscal_year_id FROM fiscal_years WHERE id = ?", (fiscal_year_id,)
    ).fetchone()
    return row[0] if row and row[0] is not None else None


def _accruals_rows(conn, fiscal_year_id: Optional[int], kind: str) -> list:
    """Régularisations groupées par catégorie : [{category_id, category_name, montant}]."""
    if fiscal_year_id is None:
        return []
    rows = conn.execute(
        """SELECT a.category_id,
                  COALESCE(c.name, 'Sans catégorie') AS category_name,
                  SUM(a.amount) AS montant
           FROM report_accruals a
           LEFT JOIN categories c ON c.id = a.category_id
           WHERE a.fiscal_year_id = ? AND a.kind = ?
           GROUP BY a.category_id, c.name""",
        (fiscal_year_id, kind),
    ).fetchall()
    return [dict(r) for r in rows]


def _merge_by_category(*groups) -> list:
    """Combine des groupes (rows, signe) en montants nets par catégorie.

    Chaque groupe = (rows, sign) où rows = [{category_id, category_name, montant}].
    Les catégories de montant net nul sont retirées.
    """
    acc: dict = {}
    for rows, sign in groups:
        for r in rows:
            cid = r["category_id"]
            if cid not in acc:
                acc[cid] = {"category_id": cid, "category_name": r["category_name"], "montant": 0}
            acc[cid]["montant"] += sign * r["montant"]
    return [v for v in acc.values() if v["montant"] != 0]


def _compte_resultat_for_fy(conn, fiscal_year_id: int) -> dict:
    """Compte de résultat en engagement pour un exercice.

    Produits(E) = produits trésorerie(E) + créances(E) - créances(E-1)
    Charges(E)  = charges trésorerie(E)  + dettes(E)   - dettes(E-1)
    L'extourne des régularisations de E-1 évite le double comptage lorsque la
    créance/dette se dénoue (encaissement/paiement) en E.
    """
    fy = conn.execute(
        "SELECT start_date, end_date FROM fiscal_years WHERE id = ?", (fiscal_year_id,)
    ).fetchone()
    if fy is None:
        raise HTTPException(404, f"Exercice fiscal {fiscal_year_id} introuvable")
    start = fy["start_date"]
    end = fy["end_date"] or date.today().isoformat()
    prev = _prev_fy_id(conn, fiscal_year_id)

    base_produits, base_charges = _cr_category_rows(conn, start, end)
    creances_e = _accruals_rows(conn, fiscal_year_id, "creance")
    dettes_e = _accruals_rows(conn, fiscal_year_id, "dette")
    creances_n1 = _accruals_rows(conn, prev, "creance")
    dettes_n1 = _accruals_rows(conn, prev, "dette")

    produits = _merge_by_category((base_produits, 1), (creances_e, 1), (creances_n1, -1))
    charges = _merge_by_category((base_charges, 1), (dettes_e, 1), (dettes_n1, -1))

    def _sum(rows):
        return sum(r["montant"] for r in rows)

    engagement = {
        "creances": _sum(creances_e),
        "dettes": _sum(dettes_e),
        "creances_n1": _sum(creances_n1),
        "dettes_n1": _sum(dettes_n1),
    }
    return _build_compte_resultat(
        conn, produits, charges, {"start": start, "end": end}, engagement
    )


def _resolve_cr_data(conn, fiscal_year_id, start_date, end_date) -> dict:
    """Données du compte de résultat : engagement si fiscal_year_id, sinon
    trésorerie sur la période start/end. Source unique pour le JSON et le PDF."""
    if fiscal_year_id is not None:
        return _compte_resultat_for_fy(conn, fiscal_year_id)
    start, end = _resolve_period(conn, None, start_date, end_date)
    return _aggregate_compte_resultat(conn, start, end)


@router.get("/compte-resultat")
def get_compte_resultat(
    fiscal_year_id: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    entity_id: Optional[int] = None,
):
    """Compte de résultat (centimes).

    Avec fiscal_year_id : méthode d'engagement (créances/dettes + extournes).
    Avec start_date/end_date seulement : trésorerie pure sur la période.
    Dans les deux cas : produits/charges par catégorie ET par compte, totaux,
    résultat.
    """
    conn = get_conn()
    try:
        return _resolve_cr_data(conn, fiscal_year_id, start_date, end_date)
    finally:
        conn.close()


# ───────────────────────── Bilan ──────────────────────────────────────────

def _opening_balance(conn, fiscal_year_id: int, entity_id: int, start: str) -> int:
    """Solde d'ouverture (centimes) d'une entité pour l'exercice.

    Priorité au solde saisi dans fiscal_year_opening_balances ; sinon calcul du
    solde propre à la veille du début d'exercice (même logique que budget /view).
    """
    row = conn.execute(
        "SELECT amount FROM fiscal_year_opening_balances WHERE fiscal_year_id = ? AND entity_id = ?",
        (fiscal_year_id, entity_id),
    ).fetchone()
    if row is not None:
        return row["amount"]
    as_of = (date.fromisoformat(start) - timedelta(days=1)).isoformat()
    return compute_entity_balance(conn, entity_id, as_of_date=as_of)["balance"]


def _bilan_instantane(conn) -> dict:
    """Bilan de trésorerie instantané (comportement historique sans exercice)."""
    rows = conn.execute(
        "SELECT id, name FROM entities WHERE type = 'internal' AND parent_id IS NULL"
    ).fetchall()
    tresorerie = []
    total_actif = 0
    for row in rows:
        eid = row["id"]
        ename = row["name"]
        bal = compute_consolidated_balance(conn, eid)
        solde = bal.get("consolidated_balance", bal.get("balance", 0))
        tresorerie.append({"entity_id": eid, "name": ename, "solde": solde})
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


def _bilan_exercice(conn, fiscal_year_id: int) -> dict:
    """Bilan de fin d'exercice (méthode trésorerie, Phase 1).

    Actif  = disponibilités de clôture (ouverture + réalisé sur la période),
             ventilées par entité interne.
    Passif = report à nouveau (trésorerie consolidée d'ouverture) + résultat.
    Équilibre garanti : somme clôture = somme ouverture + (produits - charges).
    """
    fy = conn.execute(
        "SELECT id, start_date, end_date FROM fiscal_years WHERE id = ?",
        (fiscal_year_id,),
    ).fetchone()
    if fy is None:
        raise HTTPException(404, f"Exercice fiscal {fiscal_year_id} introuvable")
    start = fy["start_date"]
    end = fy["end_date"] or date.today().isoformat()

    internal = conn.execute(
        "SELECT id, name FROM entities WHERE type = 'internal' ORDER BY name"
    ).fetchall()

    disponibilites = []
    total_disponibilites = 0
    tresorerie_ouverture = 0
    for e in internal:
        eid = e["id"]
        opening = _opening_balance(conn, fiscal_year_id, eid, start)
        per = compute_entity_balance_for_period(conn, eid, start, end, opening=opening)
        closing = per["closing"]
        disponibilites.append({"entity_id": eid, "name": e["name"], "montant": closing})
        total_disponibilites += closing
        tresorerie_ouverture += opening

    # Couche engagement : un seul calcul du compte de résultat fournit le
    # résultat ET les totaux de créances/dettes (N et N-1).
    cr = _compte_resultat_for_fy(conn, fiscal_year_id)
    resultat = cr["resultat"]
    eng = cr["engagement"]
    creances, dettes = eng["creances"], eng["dettes"]

    # Report à nouveau = actif net d'ouverture (trésorerie + créances N-1 - dettes N-1).
    report_a_nouveau = tresorerie_ouverture + eng["creances_n1"] - eng["dettes_n1"]

    total_actif = total_disponibilites + creances
    total_passif = report_a_nouveau + resultat + dettes

    return {
        "fiscal_year_id": fiscal_year_id,
        "arrete_le": end,
        "periode": {"start": start, "end": end},
        "actif": {
            "disponibilites": disponibilites,
            "total_disponibilites": total_disponibilites,
            "total_creances": creances,
            "total": total_actif,
        },
        "passif": {
            "report_a_nouveau": report_a_nouveau,
            "resultat_exercice": resultat,
            "total_dettes": dettes,
            "total": total_passif,
        },
        "equilibre": total_actif == total_passif,
        # Rétro-compatibilité avec l'ancien format de bilan.
        "tresorerie_par_entite": [
            {"entity_id": d["entity_id"], "name": d["name"], "solde": d["montant"]}
            for d in disponibilites
        ],
        "total_actif": total_actif,
    }


@router.get("/bilan")
def get_bilan(fiscal_year_id: Optional[int] = None, entity_id: Optional[int] = None):
    """Bilan : par exercice (fiscal_year_id) avec actif/passif équilibrés, ou
    trésorerie instantanée si aucun exercice n'est fourni."""
    conn = get_conn()
    try:
        if fiscal_year_id is None:
            return _bilan_instantane(conn)
        return _bilan_exercice(conn, fiscal_year_id)
    finally:
        conn.close()


# ───────────────────────── Régularisations (engagement) ───────────────────

ACCRUAL_KINDS = ("creance", "dette")


class AccrualIn(BaseModel):
    fiscal_year_id: int
    kind: str
    amount: int
    label: str
    category_id: Optional[int] = None
    entity_id: Optional[int] = None
    description: str = ""


class AccrualUpdate(BaseModel):
    kind: Optional[str] = None
    amount: Optional[int] = None
    label: Optional[str] = None
    category_id: Optional[int] = None
    entity_id: Optional[int] = None
    description: Optional[str] = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_accrual(conn, kind, amount, fiscal_year_id):
    if kind not in ACCRUAL_KINDS:
        raise HTTPException(400, "kind doit être 'creance' (produit à recevoir) ou 'dette' (charge à payer)")
    if amount is None or amount <= 0:
        raise HTTPException(400, "Le montant doit être un entier de centimes positif")
    if conn.execute("SELECT 1 FROM fiscal_years WHERE id = ?", (fiscal_year_id,)).fetchone() is None:
        raise HTTPException(404, f"Exercice fiscal {fiscal_year_id} introuvable")


@router.get("/accruals")
def list_accruals(fiscal_year_id: int):
    """Liste les régularisations (créances/dettes) d'un exercice."""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT a.*, c.name AS category_name, e.name AS entity_name
               FROM report_accruals a
               LEFT JOIN categories c ON c.id = a.category_id
               LEFT JOIN entities e ON e.id = a.entity_id
               WHERE a.fiscal_year_id = ?
               ORDER BY a.kind, a.id""",
            (fiscal_year_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.post("/accruals", status_code=201)
def create_accrual(body: AccrualIn):
    """Crée une créance (produit à recevoir) ou une dette (charge à payer)."""
    conn = get_conn()
    try:
        _validate_accrual(conn, body.kind, body.amount, body.fiscal_year_id)
        now = _now_iso()
        cur = conn.execute(
            """INSERT INTO report_accruals
               (fiscal_year_id, kind, amount, category_id, entity_id, label, description, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (body.fiscal_year_id, body.kind, body.amount, body.category_id,
             body.entity_id, body.label, body.description, now, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM report_accruals WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(row)
    finally:
        conn.close()


@router.put("/accruals/{accrual_id}")
def update_accrual(accrual_id: int, body: AccrualUpdate):
    conn = get_conn()
    try:
        existing = conn.execute("SELECT * FROM report_accruals WHERE id = ?", (accrual_id,)).fetchone()
        if existing is None:
            raise HTTPException(404, f"Régularisation {accrual_id} introuvable")
        merged_kind = body.kind if body.kind is not None else existing["kind"]
        merged_amount = body.amount if body.amount is not None else existing["amount"]
        _validate_accrual(conn, merged_kind, merged_amount, existing["fiscal_year_id"])
        conn.execute(
            """UPDATE report_accruals
               SET kind=?, amount=?, label=?, category_id=?, entity_id=?, description=?, updated_at=?
               WHERE id=?""",
            (
                merged_kind,
                merged_amount,
                body.label if body.label is not None else existing["label"],
                body.category_id if body.category_id is not None else existing["category_id"],
                body.entity_id if body.entity_id is not None else existing["entity_id"],
                body.description if body.description is not None else existing["description"],
                _now_iso(),
                accrual_id,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM report_accruals WHERE id = ?", (accrual_id,)).fetchone()
        return dict(row)
    finally:
        conn.close()


@router.delete("/accruals/{accrual_id}")
def delete_accrual(accrual_id: int):
    conn = get_conn()
    try:
        if conn.execute("SELECT 1 FROM report_accruals WHERE id = ?", (accrual_id,)).fetchone() is None:
            raise HTTPException(404, f"Régularisation {accrual_id} introuvable")
        conn.execute("DELETE FROM report_accruals WHERE id = ?", (accrual_id,))
        conn.commit()
        return {"deleted": accrual_id}
    finally:
        conn.close()


# ───────────────────────── Export PDF ─────────────────────────────────────

FONT_DIR = Path(__file__).parent / "assets" / "fonts"


def _fmt_eur(cents: int, symbol: str = "€") -> str:
    """Formate des centimes en montant français : « 1 234,56 € »."""
    s = f"{abs(int(cents)) / 100:,.2f}".replace(",", " ").replace(".", ",")
    sign = "-" if cents < 0 else ""
    return f"{sign}{s} {symbol}"


def _new_pdf():
    """FPDF avec la police Unicode DejaVu si disponible (accents + €), sinon
    repli sur Helvetica (latin-1, € remplacé par EUR)."""
    from fpdf import FPDF
    pdf = FPDF()
    font, symbol = "Helvetica", "EUR"
    try:
        if (FONT_DIR / "DejaVuSans.ttf").exists():
            pdf.add_font("DejaVu", "", str(FONT_DIR / "DejaVuSans.ttf"))
            pdf.add_font("DejaVu", "B", str(FONT_DIR / "DejaVuSans-Bold.ttf"))
            font, symbol = "DejaVu", "€"
    except Exception:
        font, symbol = "Helvetica", "EUR"
    return pdf, font, symbol


def _pdf_response(pdf, filename: str) -> Response:
    return Response(
        content=bytes(pdf.output()),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/compte-resultat/pdf")
def get_compte_resultat_pdf(
    fiscal_year_id: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    entity_id: Optional[int] = None,
):
    """Export PDF du compte de résultat (postes par compte, accents et €)."""
    conn = get_conn()
    try:
        data = _resolve_cr_data(conn, fiscal_year_id, start_date, end_date)
        start = data["periode"]["start"]
        end = data["periode"]["end"]
    finally:
        conn.close()

    try:
        pdf, font, eur = _new_pdf()
    except ImportError:
        raise HTTPException(500, "fpdf2 non installé — impossible de générer le PDF")

    pdf.add_page()
    pdf.set_font(font, "B", 16)
    pdf.cell(0, 12, "Compte de résultat", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font(font, "", 10)
    pdf.cell(0, 6, f"Période : {start} au {end}", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(6)

    def _section(titre, postes, total, total_label, fill):
        pdf.set_font(font, "B", 12)
        pdf.cell(0, 8, titre, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font(font, "B", 9)
        pdf.set_fill_color(*fill)
        pdf.cell(130, 7, "Poste", border=1, fill=True)
        pdf.cell(50, 7, f"Montant ({eur})", border=1, fill=True, align="R",
                 new_x="LMARGIN", new_y="NEXT")
        pdf.set_font(font, "", 9)
        for poste in postes:
            libelle = f"{poste['code']}  {poste['label']}"
            pdf.cell(130, 6, libelle[:70], border=1)
            pdf.cell(50, 6, _fmt_eur(poste["montant"], eur), border=1, align="R",
                     new_x="LMARGIN", new_y="NEXT")
        pdf.set_font(font, "B", 10)
        pdf.cell(130, 7, total_label, border=1)
        pdf.cell(50, 7, _fmt_eur(total, eur), border=1, align="R",
                 new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)

    _section("PRODUITS", data["produits_par_compte"], data["total_produits"],
             "TOTAL DES PRODUITS", (235, 245, 235))
    _section("CHARGES", data["charges_par_compte"], data["total_charges"],
             "TOTAL DES CHARGES", (250, 235, 235))

    resultat = data["resultat"]
    libelle = "Excédent de l'exercice" if resultat >= 0 else "Déficit de l'exercice"
    pdf.set_font(font, "B", 12)
    pdf.set_fill_color(225, 225, 250)
    pdf.cell(130, 9, libelle, border=1, fill=True)
    pdf.cell(50, 9, _fmt_eur(resultat, eur), border=1, fill=True, align="R",
             new_x="LMARGIN", new_y="NEXT")

    pdf.ln(8)
    pdf.set_font(font, "", 8)
    pdf.multi_cell(0, 5,
        "Méthode : comptabilité de trésorerie. Produits = encaissements depuis "
        "l'extérieur vers l'association ; charges = décaissements vers l'extérieur ; "
        "virements internes neutralisés.")

    return _pdf_response(pdf, f"compte-resultat_{start}_{end}.pdf")


@router.get("/bilan/pdf")
def get_bilan_pdf(fiscal_year_id: Optional[int] = None, entity_id: Optional[int] = None):
    """Export PDF du bilan d'un exercice (actif / passif équilibrés)."""
    if fiscal_year_id is None:
        raise HTTPException(400, "Le bilan PDF nécessite un fiscal_year_id")
    conn = get_conn()
    try:
        data = _bilan_exercice(conn, fiscal_year_id)
    finally:
        conn.close()

    try:
        pdf, font, eur = _new_pdf()
    except ImportError:
        raise HTTPException(500, "fpdf2 non installé — impossible de générer le PDF")

    actif = data["actif"]
    passif = data["passif"]

    pdf.add_page()
    pdf.set_font(font, "B", 16)
    pdf.cell(0, 12, "Bilan", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font(font, "", 10)
    pdf.cell(0, 6, f"Arrêté au {data['arrete_le']}", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(6)

    def _line(libelle, montant, bold=False):
        pdf.set_font(font, "B" if bold else "", 10 if bold else 9)
        pdf.cell(130, 7 if bold else 6, libelle[:70], border=1)
        pdf.cell(50, 7 if bold else 6, _fmt_eur(montant, eur), border=1, align="R",
                 new_x="LMARGIN", new_y="NEXT")

    pdf.set_font(font, "B", 12)
    pdf.cell(0, 8, "ACTIF", new_x="LMARGIN", new_y="NEXT")
    for d in actif["disponibilites"]:
        _line(f"Disponibilités  {d['name']}", d["montant"])
    if actif["total_creances"]:
        _line("Créances (produits à recevoir)", actif["total_creances"])
    _line("TOTAL DE L'ACTIF", actif["total"], bold=True)
    pdf.ln(4)

    pdf.set_font(font, "B", 12)
    pdf.cell(0, 8, "PASSIF", new_x="LMARGIN", new_y="NEXT")
    _line("Fonds associatifs et report à nouveau", passif["report_a_nouveau"])
    _line("Résultat de l'exercice", passif["resultat_exercice"])
    if passif["total_dettes"]:
        _line("Dettes (charges à payer)", passif["total_dettes"])
    _line("TOTAL DU PASSIF", passif["total"], bold=True)
    pdf.ln(6)

    pdf.set_font(font, "", 8)
    equ = "équilibré" if data["equilibre"] else "DÉSÉQUILIBRÉ"
    pdf.multi_cell(0, 5,
        f"Bilan {equ} (actif = passif). Méthode trésorerie : l'actif se résume aux "
        "disponibilités ; le passif aux fonds associatifs et au résultat de l'exercice.")

    return _pdf_response(pdf, f"bilan_{data['arrete_le']}.pdf")
