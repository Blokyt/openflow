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

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel

from backend.core.config import load_config

from backend.core.auth import get_allowed_entity_ids, get_current_user, require_entity_access
from backend.core.balance import (
    compute_consolidated_balance,
    compute_entity_balance,
    compute_entity_balance_for_period,
    get_subtree_ids,
)
from backend.core.database import get_conn
from backend.core.formatting import format_date_fr

router = APIRouter()

# Endpoints de vue financière globale : entity_id devient obligatoire pour un
# non-admin (même règle que le dashboard), et vérifié contre son périmètre.
ENTITY_REQUIRED_MESSAGE = "Une entité est requise pour ce rôle"
FISCAL_YEAR_REQUIRED_MESSAGE = "Un exercice est requis pour ce rôle"


def _require_scope(conn, user: dict, entity_id):
    allowed = get_allowed_entity_ids(conn, user)
    if allowed is None:
        return
    if entity_id is None:
        raise HTTPException(status_code=400, detail=ENTITY_REQUIRED_MESSAGE)
    require_entity_access(conn, user, entity_id)


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


def _entity_perimeter(conn, entity_id: Optional[int]) -> list:
    """Périmètre P (liste d'IDs internes) pour les calculs de flux.

    - entity_id None  : P = tous les internes (compte de résultat / bilan global).
    - entity_id fourni : P = {entity_id} ∪ descendants internes. Un flux entrant
      dans P depuis hors-P (ex: dotation BDA -> club) devient alors un produit du
      club ; les flux intra-P s'annulent.
    404 si l'entité n'existe pas, 400 si elle est externe.
    """
    if entity_id is None:
        return _get_internal_ids(conn)
    row = conn.execute("SELECT id, type FROM entities WHERE id = ?", (entity_id,)).fetchone()
    if row is None:
        raise HTTPException(404, f"Entité {entity_id} introuvable")
    if row["type"] != "internal":
        raise HTTPException(400, "entity_id doit référencer une entité interne")
    return get_subtree_ids(conn, entity_id)


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


# Heuristique nom de catégorie -> code de compte PCG (aide au pré-remplissage).
# L'ordre compte : la première liste de mots-clés trouvée dans le nom gagne.
# On inclut les variantes avec et sans accent pour matcher les deux graphies.
KEYWORD_ACCOUNT_MAP = [
    (["cotis"], "756"),
    (["don", "mécénat", "mecenat"], "754"),
    (["subvention", "subv"], "74"),
    (["vente", "buvette", "billet", "ticket", "prestation", "activité", "activite"], "70"),
    (["location", "loyer", "salle", "assurance", "entretien"], "61"),
    (["communication", "transport", "frais bancaire", "banque", "impression", "affranchiss", "site", "frais de port"], "62"),
    (["salaire", "personnel", "rémunération", "remuneration"], "64"),
    (["impôt", "impot", "taxe"], "63"),
    (["achat", "fourniture", "matériel", "materiel", "nourriture", "boisson", "alimentation", "goodies"], "60"),
    (["intérêt", "interet", "agios"], "66"),
]


def _suggest_code(name: str):
    low = (name or "").lower()
    for keywords, code in KEYWORD_ACCOUNT_MAP:
        if any(kw in low for kw in keywords):
            return code
    return None


@router.get("/mapping/suggestions")
def get_mapping_suggestions():
    """Propose un compte PCG par heuristique de nom, pour les catégories encore
    non mappées. L'utilisateur valide (et peut appliquer en masse)."""
    conn = get_conn()
    try:
        mapped_ids = set(_mapping_dict(conn).keys())
        accounts_by_code = {a["code"]: a for a in _account_list(conn)}
        cats = conn.execute("SELECT id, name FROM categories ORDER BY name").fetchall()
        suggestions = []
        for cat in cats:
            if cat["id"] in mapped_ids:
                continue
            code = _suggest_code(cat["name"])
            acc = accounts_by_code.get(code) if code else None
            if acc is None:
                continue
            suggestions.append({
                "category_id": cat["id"],
                "category_name": cat["name"],
                "suggested_account_id": acc["id"],
                "suggested_account_code": acc["code"],
                "suggested_account_label": acc["label"],
            })
        return {"suggestions": suggestions}
    finally:
        conn.close()


class ApplyEntry(BaseModel):
    category_id: int
    account_id: int


class ApplySuggestionsIn(BaseModel):
    entries: list[ApplyEntry]


@router.post("/mapping/apply-suggestions")
def apply_mapping_suggestions(body: ApplySuggestionsIn):
    """Applique une liste de mappings catégorie -> compte en une fois.
    N'accepte que des comptes de produits ou de charges."""
    conn = get_conn()
    try:
        applied = 0
        for entry in body.entries:
            acc = conn.execute(
                "SELECT kind FROM report_accounts WHERE id = ?", (entry.account_id,)
            ).fetchone()
            if acc is None or acc["kind"] not in ("produit", "charge"):
                continue
            conn.execute(
                """INSERT INTO category_account_map (category_id, account_id) VALUES (?, ?)
                   ON CONFLICT(category_id) DO UPDATE SET account_id = excluded.account_id""",
                (entry.category_id, entry.account_id),
            )
            applied += 1
        conn.commit()
        return {"applied": applied}
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
              AND (t.{out_col} IS NULL OR t.{out_col} NOT IN ({ph}))
              AND t.date BETWEEN ? AND ?
            GROUP BY t.category_id, c.name
            ORDER BY c.name""",
        internal_ids + internal_ids + [start, end],
    ).fetchall()]


def _cr_category_rows(conn, start: str, end: str, perimeter: Optional[list] = None):
    """(produits, charges) par catégorie sur la période (méthode trésorerie).

    perimeter = liste d'IDs internes définissant le périmètre du rapport. None =
    tous les internes (rapport global). Pour un club, on passe son sous-arbre :
    un flux entrant depuis hors-périmètre est un produit, un flux sortant une charge.
    """
    internal_ids = perimeter if perimeter is not None else _get_internal_ids(conn)
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


def _aggregate_compte_resultat(conn, start: str, end: str, perimeter: Optional[list] = None) -> dict:
    """Compte de résultat trésorerie sur une période (par catégorie et par compte)."""
    produits, charges = _cr_category_rows(conn, start, end, perimeter)
    return _build_compte_resultat(conn, produits, charges, {"start": start, "end": end})


# ── Couche engagement : régularisations et extournes (Phase 2) ──

def _prev_fy_id(conn, fiscal_year_id: int) -> Optional[int]:
    row = conn.execute(
        "SELECT previous_fiscal_year_id, start_date FROM fiscal_years WHERE id = ?",
        (fiscal_year_id,),
    ).fetchone()
    if row is None:
        return None
    if row["previous_fiscal_year_id"] is not None:
        return row["previous_fiscal_year_id"]
    # Fallback par date (même fenêtre ±31 j que le module budget) quand le lien
    # explicite manque : sans cela les extournes N-1 sont perdues et les
    # créances/dettes de N sont comptées deux fois en N+1.
    start = row["start_date"]
    if not start:
        return None
    try:
        d = date.fromisoformat(str(start)[:10])
        target = date(d.year - 1, d.month, d.day)
    except Exception:
        return None
    low = (target - timedelta(days=31)).isoformat()
    high = (target + timedelta(days=31)).isoformat()
    prev = conn.execute(
        """SELECT id FROM fiscal_years
           WHERE start_date BETWEEN ? AND ? AND start_date < ?
           ORDER BY ABS(julianday(start_date) - julianday(?)) ASC LIMIT 1""",
        (low, high, start, target.isoformat()),
    ).fetchone()
    return prev["id"] if prev else None


def _accruals_rows(conn, fiscal_year_id: Optional[int], kind: str,
                   entity_filter: Optional[list] = None, include_global: bool = True) -> list:
    """Régularisations groupées par catégorie : [{category_id, category_name, montant}].

    Avec entity_filter (périmètre), ne retient que les régularisations de ces
    entités. include_global commande la prise en compte des régularisations sans
    entité (saisies au niveau global) : True en vue association, False en vue
    club. Sinon une régularisation globale serait additionnée dans le bilan de
    CHAQUE club et la somme des bilans de clubs dépasserait le bilan global."""
    if fiscal_year_id is None:
        return []
    sql = """SELECT a.category_id,
                    COALESCE(c.name, 'Sans catégorie') AS category_name,
                    SUM(a.amount) AS montant
             FROM report_accruals a
             LEFT JOIN categories c ON c.id = a.category_id
             WHERE a.fiscal_year_id = ? AND a.kind = ?"""
    params = [fiscal_year_id, kind]
    if entity_filter is not None:
        ph = ",".join("?" * len(entity_filter))
        if include_global:
            sql += f" AND (a.entity_id IN ({ph}) OR a.entity_id IS NULL)"
        else:
            sql += f" AND a.entity_id IN ({ph})"
        params.extend(entity_filter)
    sql += " GROUP BY a.category_id, c.name"
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


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


def _compte_resultat_for_fy(conn, fiscal_year_id: int, perimeter: Optional[list] = None,
                            include_global: bool = True) -> dict:
    """Compte de résultat en engagement pour un exercice.

    Produits(E) = produits trésorerie(E) + créances(E) - créances(E-1)
    Charges(E)  = charges trésorerie(E)  + dettes(E)   - dettes(E-1)
    L'extourne des régularisations de E-1 évite le double comptage lorsque la
    créance/dette se dénoue (encaissement/paiement) en E.

    perimeter restreint le calcul à un club (sous-arbre) ; None = asso entière.
    """
    fy = conn.execute(
        "SELECT start_date, end_date FROM fiscal_years WHERE id = ?", (fiscal_year_id,)
    ).fetchone()
    if fy is None:
        raise HTTPException(404, f"Exercice fiscal {fiscal_year_id} introuvable")
    start = fy["start_date"]
    end = fy["end_date"] or date.today().isoformat()
    prev = _prev_fy_id(conn, fiscal_year_id)

    base_produits, base_charges = _cr_category_rows(conn, start, end, perimeter)
    creances_e = _accruals_rows(conn, fiscal_year_id, "creance", perimeter, include_global)
    dettes_e = _accruals_rows(conn, fiscal_year_id, "dette", perimeter, include_global)
    creances_n1 = _accruals_rows(conn, prev, "creance", perimeter, include_global)
    dettes_n1 = _accruals_rows(conn, prev, "dette", perimeter, include_global)

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


def _resolve_cr_data(conn, fiscal_year_id, start_date, end_date,
                     entity_id: Optional[int] = None) -> dict:
    """Données du compte de résultat : engagement si fiscal_year_id, sinon
    trésorerie sur la période start/end. Source unique pour le JSON et le PDF.
    entity_id restreint au périmètre d'un club (None = asso entière)."""
    perimeter = _entity_perimeter(conn, entity_id) if entity_id is not None else None
    if fiscal_year_id is not None:
        return _compte_resultat_for_fy(conn, fiscal_year_id, perimeter=perimeter,
                                       include_global=(entity_id is None))
    start, end = _resolve_period(conn, None, start_date, end_date)
    return _aggregate_compte_resultat(conn, start, end, perimeter=perimeter)


@router.get("/compte-resultat")
def get_compte_resultat(
    request: Request,
    fiscal_year_id: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    entity_id: Optional[int] = None,
):
    """Compte de résultat (centimes).

    Avec fiscal_year_id : méthode d'engagement (créances/dettes + extournes).
    Avec start_date/end_date seulement : trésorerie pure sur la période.
    Dans les deux cas : produits/charges par catégorie ET par compte, totaux,
    résultat. Avec entity_id : périmètre restreint à ce club (sous-arbre).

    Non-admin : entity_id obligatoire (vue globale sinon) et vérifié contre
    le périmètre du rôle.
    """
    user = get_current_user(request)
    conn = get_conn()
    try:
        _require_scope(conn, user, entity_id)
        return _resolve_cr_data(conn, fiscal_year_id, start_date, end_date, entity_id)
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
        total_actif += solde
    return {
        "tresorerie_par_entite": tresorerie,
        "total_actif": total_actif,
        "hypotheses": (
            "Actif = somme des soldes consolidés des entités internes racines (découverts inclus, comptés négativement). "
            "Montants en centimes. Virements internes neutralisés dans le consolidé."
        ),
    }


def _bilan_exercice(conn, fiscal_year_id: int, entity_id: Optional[int] = None) -> dict:
    """Bilan de fin d'exercice (méthode trésorerie, Phase 1).

    Actif  = disponibilités de clôture (ouverture + réalisé sur la période),
             ventilées par entité interne.
    Passif = report à nouveau (trésorerie consolidée d'ouverture) + résultat.
    Équilibre garanti : somme clôture = somme ouverture + (produits - charges).

    Avec entity_id, on restreint au périmètre du club (sous-arbre). L'équilibre
    tient toujours : clôture(P) = ouverture(P) + produits_club - charges_club,
    car les flux intra-P s'annulent et les flux P<->hors-P sont comptés au CR.
    """
    fy = conn.execute(
        "SELECT id, start_date, end_date FROM fiscal_years WHERE id = ?",
        (fiscal_year_id,),
    ).fetchone()
    if fy is None:
        raise HTTPException(404, f"Exercice fiscal {fiscal_year_id} introuvable")
    start = fy["start_date"]
    end = fy["end_date"] or date.today().isoformat()

    perimeter = _entity_perimeter(conn, entity_id)
    if not perimeter:
        internal = []
    else:
        ph = ",".join("?" * len(perimeter))
        internal = conn.execute(
            f"SELECT id, name FROM entities WHERE type = 'internal' AND id IN ({ph}) ORDER BY name",
            perimeter,
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

    # Vue association (entity_id None) : les régularisations globales comptent.
    # Vue club : elles sont exclues (sinon doublées entre clubs, cf _accruals_rows).
    include_global = entity_id is None

    # Couche engagement : un seul calcul du compte de résultat fournit le
    # résultat ET les totaux de créances/dettes (N et N-1).
    cr = _compte_resultat_for_fy(conn, fiscal_year_id, perimeter=perimeter,
                                 include_global=include_global)
    resultat = cr["resultat"]
    eng = cr["engagement"]
    creances, dettes = eng["creances"], eng["dettes"]

    # Détail par catégorie des créances/dettes de l'exercice (mêmes lignes que
    # celles dont la somme constitue les totaux ci-dessus) -> rapport lisible.
    creances_detail = sorted(
        _accruals_rows(conn, fiscal_year_id, "creance", perimeter, include_global),
        key=lambda r: r["category_name"],
    )
    dettes_detail = sorted(
        _accruals_rows(conn, fiscal_year_id, "dette", perimeter, include_global),
        key=lambda r: r["category_name"],
    )

    # Report à nouveau = actif net d'ouverture (trésorerie + créances N-1 - dettes N-1).
    report_a_nouveau = tresorerie_ouverture + eng["creances_n1"] - eng["dettes_n1"]

    total_actif = total_disponibilites + creances
    total_passif = report_a_nouveau + resultat + dettes

    return {
        "fiscal_year_id": fiscal_year_id,
        "entity_id": entity_id,
        "arrete_le": end,
        "periode": {"start": start, "end": end},
        "actif": {
            "disponibilites": disponibilites,
            "total_disponibilites": total_disponibilites,
            "total_creances": creances,
            "creances_detail": creances_detail,
            "total": total_actif,
        },
        "passif": {
            "report_a_nouveau": report_a_nouveau,
            "resultat_exercice": resultat,
            "total_dettes": dettes,
            "dettes_detail": dettes_detail,
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
def get_bilan(request: Request, fiscal_year_id: Optional[int] = None, entity_id: Optional[int] = None):
    """Bilan : par exercice (fiscal_year_id) avec actif/passif équilibrés, ou
    trésorerie instantanée si aucun exercice n'est fourni.

    Non-admin : entity_id obligatoire et vérifié contre le périmètre. Le bilan
    instantané (_bilan_instantane) agrège tous les internes sans notion
    d'entity_id : il reste donc réservé à un fiscal_year_id explicite pour un
    non-admin (sinon entity_id serait ignoré et la vue redeviendrait globale).
    """
    user = get_current_user(request)
    conn = get_conn()
    try:
        _require_scope(conn, user, entity_id)
        allowed = get_allowed_entity_ids(conn, user)
        if allowed is not None and fiscal_year_id is None:
            raise HTTPException(status_code=400, detail=FISCAL_YEAR_REQUIRED_MESSAGE)
        if fiscal_year_id is None:
            return _bilan_instantane(conn)
        return _bilan_exercice(conn, fiscal_year_id, entity_id=entity_id)
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


def _validate_accrual(conn, kind, amount, fiscal_year_id, entity_id=None):
    if kind not in ACCRUAL_KINDS:
        raise HTTPException(400, "kind doit être 'creance' (produit à recevoir) ou 'dette' (charge à payer)")
    if amount is None or amount <= 0:
        raise HTTPException(400, "Le montant doit être un entier de centimes positif")
    if conn.execute("SELECT 1 FROM fiscal_years WHERE id = ?", (fiscal_year_id,)).fetchone() is None:
        raise HTTPException(404, f"Exercice fiscal {fiscal_year_id} introuvable")
    # Une régularisation rattachée à une entité externe serait comptée dans le
    # compte de résultat mais exclue du bilan (déséquilibre). On l'interdit.
    if entity_id is not None:
        ent = conn.execute("SELECT type FROM entities WHERE id = ?", (entity_id,)).fetchone()
        if ent is None or ent["type"] != "internal":
            raise HTTPException(400, "entity_id doit référencer une entité interne (ou être absent pour le niveau global)")


@router.get("/accruals")
def list_accruals(request: Request, fiscal_year_id: int, entity_id: Optional[int] = None):
    """Liste les régularisations (créances/dettes) d'un exercice.

    Non-admin : entity_id obligatoire (400 sinon, même règle que compte-résultat
    / bilan) et vérifié contre le périmètre du rôle (403 hors périmètre). Les
    lignes sont alors filtrées au sous-arbre demandé (`_entity_perimeter`). Les
    régularisations sans entity_id (saisies au niveau global) sont EXCLUES pour
    un non-admin : sans entité de rattachement vérifiable, on refuse par défaut
    (deny-by-default) plutôt que de risquer une fuite de données globales.
    Admin (`allowed is None`) : inchangé, toutes les lignes remontent comme
    avant (y compris entity_id NULL), sans filtre.
    """
    user = get_current_user(request)
    conn = get_conn()
    try:
        _require_scope(conn, user, entity_id)
        allowed = get_allowed_entity_ids(conn, user)
        sql = """SELECT a.*, c.name AS category_name, e.name AS entity_name
                 FROM report_accruals a
                 LEFT JOIN categories c ON c.id = a.category_id
                 LEFT JOIN entities e ON e.id = a.entity_id
                 WHERE a.fiscal_year_id = ?"""
        params: list = [fiscal_year_id]
        if allowed is not None:
            perimeter = _entity_perimeter(conn, entity_id)
            if not perimeter:
                sql += " AND 0 = 1"
            else:
                ph = ",".join("?" * len(perimeter))
                # entity_id NULL exclu explicitement (deny-by-default ci-dessus).
                sql += f" AND a.entity_id IN ({ph})"
                params.extend(perimeter)
        sql += " ORDER BY a.kind, a.id"
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.post("/accruals", status_code=201)
def create_accrual(body: AccrualIn):
    """Crée une créance (produit à recevoir) ou une dette (charge à payer)."""
    conn = get_conn()
    try:
        _validate_accrual(conn, body.kind, body.amount, body.fiscal_year_id, body.entity_id)
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
        merged_entity_id = body.entity_id if body.entity_id is not None else existing["entity_id"]
        _validate_accrual(conn, merged_kind, merged_amount, existing["fiscal_year_id"], merged_entity_id)
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
_CONFIG_PATH = Path(__file__).parent.parent.parent.parent / "config.yaml"


def _fmt_eur(cents: int, symbol: str = "€") -> str:
    """Formate des centimes en montant français : « 1 234,56 € »."""
    # Espace fine insécable (typographie FR) en mode Unicode ; espace normale en
    # repli Helvetica (latin-1) qui ne sait pas afficher U+202F.
    thin = " " if symbol == "€" else " "
    s = f"{abs(int(round(cents))) / 100:,.2f}".replace(",", thin).replace(".", ",")
    sign = "-" if cents < 0 else ""
    return f"{sign}{s}{thin}{symbol}"


def _fmt_date(iso) -> str:
    """ISO (YYYY-MM-DD) -> format français JJ/MM/AAAA."""
    return format_date_fr(str(iso)[:10])


def _fit(pdf, text: str, max_w: float) -> str:
    """Tronque `text` avec une ellipse pour qu'il tienne dans `max_w` mm (police courante)."""
    if pdf.get_string_width(text) <= max_w:
        return text
    ell = "..."
    while text and pdf.get_string_width(text + ell) > max_w:
        text = text[:-1]
    return text + ell


def _assoc_name():
    """Nom de l'association depuis la config (None si absent ou valeur par défaut)."""
    try:
        name = (load_config(str(_CONFIG_PATH)).entity.name or "").strip()
        return name or None
    except Exception:
        return None


def _new_pdf():
    """FPDF avec la police Unicode DejaVu si disponible (accents + €), sinon
    repli sur Helvetica (latin-1, € remplacé par EUR). Pied de page : date de
    génération + numérotation des pages."""
    from fpdf import FPDF

    gen_label = "Généré le " + datetime.now().strftime("%d/%m/%Y")

    class _ReportPDF(FPDF):
        font_name = "Helvetica"

        def footer(self):
            self.set_y(-12)
            try:
                self.set_font(self.font_name, "", 7)
            except Exception:
                return
            self.set_text_color(130, 130, 130)
            self.cell(95, 5, gen_label, align="L")
            self.cell(95, 5, f"Page {self.page_no()}/{{nb}}", align="R")
            self.set_text_color(0, 0, 0)

    pdf = _ReportPDF()
    pdf.alias_nb_pages()
    font, symbol = "Helvetica", "EUR"
    try:
        if (FONT_DIR / "DejaVuSans.ttf").exists():
            pdf.add_font("DejaVu", "", str(FONT_DIR / "DejaVuSans.ttf"))
            pdf.add_font("DejaVu", "B", str(FONT_DIR / "DejaVuSans-Bold.ttf"))
            font, symbol = "DejaVu", "€"
    except Exception:
        font, symbol = "Helvetica", "EUR"
    pdf.font_name = font
    return pdf, font, symbol


def _pdf_response(pdf, filename: str) -> Response:
    return Response(
        content=bytes(pdf.output()),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/compte-resultat/pdf")
def get_compte_resultat_pdf(
    request: Request,
    fiscal_year_id: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    entity_id: Optional[int] = None,
):
    """Export PDF du compte de résultat (postes par compte, accents et €).

    Même règle de périmètre que /compte-resultat (export = lecture)."""
    user = get_current_user(request)
    conn = get_conn()
    try:
        _require_scope(conn, user, entity_id)
        data = _resolve_cr_data(conn, fiscal_year_id, start_date, end_date, entity_id)
        start = data["periode"]["start"]
        end = data["periode"]["end"]
        entity_name = None
        if entity_id:
            row = conn.execute("SELECT name FROM entities WHERE id = ?", (entity_id,)).fetchone()
            entity_name = row["name"] if row else None
    finally:
        conn.close()

    try:
        pdf, font, eur = _new_pdf()
    except ImportError:
        raise HTTPException(500, "fpdf2 non installé — impossible de générer le PDF")

    pdf.add_page()
    assoc = _assoc_name()
    if assoc:
        pdf.set_font(font, "B", 11)
        pdf.cell(0, 6, assoc, new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font(font, "B", 16)
    pdf.cell(0, 12, "Compte de résultat", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font(font, "", 10)
    if entity_name:
        pdf.cell(0, 6, f"Club : {entity_name}", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.cell(0, 6, f"Période : {_fmt_date(start)} au {_fmt_date(end)}", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(6)

    def _section(titre, postes, total, total_label, fill):
        pdf.set_font(font, "B", 12)
        pdf.cell(0, 8, titre, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font(font, "B", 9)
        pdf.set_fill_color(*fill)
        pdf.cell(130, 7, "Poste", border=1, fill=True)
        pdf.cell(50, 7, f"Montant ({eur})", border=1, fill=True, align="R",
                 new_x="LMARGIN", new_y="NEXT")
        for poste in postes:
            # Ligne du compte (poste), en gras.
            pdf.set_font(font, "B", 9)
            libelle = f"{poste['code']}  {poste['label']}"
            pdf.cell(130, 6, _fit(pdf, libelle, 128), border=1)
            pdf.cell(50, 6, _fmt_eur(poste["montant"], eur), border=1, align="R",
                     new_x="LMARGIN", new_y="NEXT")
            # Détail des contributions par catégorie, sous le compte, en plus clair.
            pdf.set_font(font, "", 8)
            pdf.set_text_color(110, 110, 110)
            for cat in poste.get("categories", []):
                nom = f"        {cat['category_name']}"
                pdf.cell(130, 5, _fit(pdf, nom, 128), border="LR")
                pdf.cell(50, 5, _fmt_eur(cat["montant"], eur), border="LR", align="R",
                         new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0, 0, 0)
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

    engagement = data.get("engagement")
    has_regularisations = bool(engagement) and any(
        engagement.get(k) for k in ("creances", "dettes", "creances_n1", "dettes_n1")
    )

    pdf.ln(8)
    pdf.set_font(font, "", 8)
    if has_regularisations:
        pdf.multi_cell(0, 5,
            "Méthode : comptabilité d'engagement (créances et dettes). Produits et "
            "charges de trésorerie sont corrigés des créances et dettes de l'exercice, "
            "avec extourne de celles de l'exercice précédent ; virements internes neutralisés.")
    else:
        pdf.multi_cell(0, 5,
            "Méthode : comptabilité de trésorerie. Produits = encaissements depuis "
            "l'extérieur vers l'association ; charges = décaissements vers l'extérieur ; "
            "virements internes neutralisés.")

    return _pdf_response(pdf, f"compte-resultat_{start}_{end}.pdf")


@router.get("/bilan/pdf")
def get_bilan_pdf(request: Request, fiscal_year_id: Optional[int] = None, entity_id: Optional[int] = None):
    """Export PDF du bilan d'un exercice (actif / passif équilibrés).

    Même règle de périmètre que /bilan (export = lecture) ; fiscal_year_id est
    déjà obligatoire pour tout le monde ici, donc pas de piège "bilan
    instantané" possible pour un non-admin."""
    if fiscal_year_id is None:
        raise HTTPException(400, "Le bilan PDF nécessite un fiscal_year_id")
    user = get_current_user(request)
    conn = get_conn()
    try:
        _require_scope(conn, user, entity_id)
        data = _bilan_exercice(conn, fiscal_year_id, entity_id=entity_id)
        entity_name = None
        if entity_id:
            row = conn.execute("SELECT name FROM entities WHERE id = ?", (entity_id,)).fetchone()
            entity_name = row["name"] if row else None
    finally:
        conn.close()

    try:
        pdf, font, eur = _new_pdf()
    except ImportError:
        raise HTTPException(500, "fpdf2 non installé — impossible de générer le PDF")

    actif = data["actif"]
    passif = data["passif"]

    pdf.add_page()
    assoc = _assoc_name()
    if assoc:
        pdf.set_font(font, "B", 11)
        pdf.cell(0, 6, assoc, new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font(font, "B", 16)
    pdf.cell(0, 12, "Bilan", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font(font, "", 10)
    if entity_name:
        pdf.cell(0, 6, f"Club : {entity_name}", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.cell(0, 6, f"Arrêté au {_fmt_date(data['arrete_le'])}", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(6)

    def _line(libelle, montant, bold=False):
        pdf.set_font(font, "B" if bold else "", 10 if bold else 9)
        pdf.cell(130, 7 if bold else 6, _fit(pdf, libelle, 128), border=1)
        pdf.cell(50, 7 if bold else 6, _fmt_eur(montant, eur), border=1, align="R",
                 new_x="LMARGIN", new_y="NEXT")

    def _detail(rows):
        # Sous-lignes par catégorie (contributions), en plus clair.
        pdf.set_font(font, "", 8)
        pdf.set_text_color(110, 110, 110)
        for r in rows:
            nom = f"        {r['category_name']}"
            pdf.cell(130, 5, _fit(pdf, nom, 128), border="LR")
            pdf.cell(50, 5, _fmt_eur(r["montant"], eur), border="LR", align="R",
                     new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)

    pdf.set_font(font, "B", 12)
    pdf.cell(0, 8, "ACTIF", new_x="LMARGIN", new_y="NEXT")
    for d in actif["disponibilites"]:
        _line(f"Disponibilités  {d['name']}", d["montant"])
    if actif["total_creances"]:
        _line("Créances (produits à recevoir)", actif["total_creances"])
        _detail(actif.get("creances_detail", []))
    _line("TOTAL DE L'ACTIF", actif["total"], bold=True)
    pdf.ln(4)

    pdf.set_font(font, "B", 12)
    pdf.cell(0, 8, "PASSIF", new_x="LMARGIN", new_y="NEXT")
    _line("Fonds associatifs et report à nouveau", passif["report_a_nouveau"])
    _line("Résultat de l'exercice", passif["resultat_exercice"])
    if passif["total_dettes"]:
        _line("Dettes (charges à payer)", passif["total_dettes"])
        _detail(passif.get("dettes_detail", []))
    _line("TOTAL DU PASSIF", passif["total"], bold=True)
    pdf.ln(6)

    pdf.set_font(font, "", 8)
    equ = "équilibré" if data["equilibre"] else "DÉSÉQUILIBRÉ"
    has_regularisations = bool(actif["total_creances"]) or bool(passif["total_dettes"])
    if has_regularisations:
        methode = (
            "Méthode trésorerie avec régularisations d'engagement : l'actif comprend "
            "les disponibilités et les créances (produits à recevoir) ; le passif "
            "comprend les fonds associatifs, le résultat de l'exercice et les dettes "
            "(charges à payer)."
        )
    else:
        methode = (
            "Méthode trésorerie : l'actif se résume aux disponibilités ; le passif "
            "aux fonds associatifs et au résultat de l'exercice."
        )
    pdf.multi_cell(0, 5, f"Bilan {equ} (actif = passif). {methode}")

    return _pdf_response(pdf, f"bilan_{data['arrete_le']}.pdf")
