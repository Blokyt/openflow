"""Budget & Exercices API module for OpenFlow."""
import sqlite3
from datetime import datetime, timezone, date as _date, timedelta as _timedelta
from typing import Optional, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from backend.core.auth import get_allowed_entity_ids, get_current_user, require_entity_access
from backend.core.database import get_conn, row_to_dict
from backend.core.balance import compute_entity_balance

router = APIRouter()

# Message constant pour la garde « entité obligatoire pour un non-admin »,
# partagée avec dashboard/api.py et reports/api.py (même formulation exacte).
ENTITY_REQUIRED_MESSAGE = "Une entité est requise pour ce rôle"


def _require_scope(conn, user: dict, entity_id):
    """Non-admin : entity_id obligatoire (400 si absent) + dans le périmètre (403 sinon).
    Admin (`allowed is None`) : inchangé, aucune contrainte."""
    allowed = get_allowed_entity_ids(conn, user)
    if allowed is None:
        return
    if entity_id is None:
        raise HTTPException(status_code=400, detail=ENTITY_REQUIRED_MESSAGE)
    require_entity_access(conn, user, entity_id)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today() -> str:
    return _date.today().isoformat()


def _fy_end(fy) -> str:
    """Effective end date: today if the mandate is still open."""
    return fy["end_date"] if fy["end_date"] else _today()


# ─── Pydantic models ─────────────────────────────────────────────────────────

class FiscalYearCreate(BaseModel):
    name: str
    start_date: str
    notes: str = ""
    president_name: str = ""
    tresorier_name: str = ""


class FiscalYearUpdate(BaseModel):
    name: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None  # None = ne pas toucher ; "" ou null explicite = rouvrir
    notes: Optional[str] = None
    president_name: Optional[str] = None
    tresorier_name: Optional[str] = None


class FiscalYearClose(BaseModel):
    end_date: Optional[str] = None  # defaults to today


class OpeningBalanceUpsert(BaseModel):
    amount: int  # centimes, entier signé
    source: str = ""
    notes: str = ""


class AllocationCreate(BaseModel):
    entity_id: int
    category_id: Optional[int] = None
    direction: Literal["expense", "income"] = "expense"
    amount: int  # centimes entiers (cohérent avec le stockage budget_allocations)
    notes: str = ""
    # 'manual' = saisie utilisateur (affichée en doré) ; 'seeded' = pré-remplie depuis
    # un exercice précédent (copie), affichée en gris tant qu'elle n'a pas été modifiée.
    origin: Literal["manual", "seeded"] = "manual"


class AllocationUpdate(BaseModel):
    entity_id: Optional[int] = None
    category_id: Optional[int] = None
    amount: Optional[int] = None  # centimes entiers
    notes: Optional[str] = None


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _find_previous_fiscal_year(conn, current_start: str) -> Optional[int]:
    d = _date.fromisoformat(current_start)
    target = _date(d.year - 1, d.month, d.day).isoformat()
    window_low = (_date.fromisoformat(target) - _timedelta(days=31)).isoformat()
    window_high = (_date.fromisoformat(target) + _timedelta(days=31)).isoformat()
    row = conn.execute(
        """SELECT id FROM fiscal_years
           WHERE start_date BETWEEN ? AND ?
             AND start_date < ?
           ORDER BY ABS(julianday(start_date) - julianday(?)) ASC
           LIMIT 1""",
        (window_low, window_high, current_start, target),
    ).fetchone()
    return row["id"] if row else None


def _sum_realized(conn, entity_id: int, start: str, end: str, category_id: Optional[int]) -> float:
    if category_id is None:
        row = conn.execute(
            """SELECT COALESCE(SUM(CASE
                    WHEN to_entity_id = ? THEN amount
                    WHEN from_entity_id = ? THEN -amount
                    ELSE 0
                END), 0) AS net
               FROM transactions
               WHERE date BETWEEN ? AND ?
                 AND (from_entity_id = ? OR to_entity_id = ?)""",
            (entity_id, entity_id, start, end, entity_id, entity_id),
        ).fetchone()
    else:
        row = conn.execute(
            """SELECT COALESCE(SUM(CASE
                    WHEN to_entity_id = ? THEN amount
                    WHEN from_entity_id = ? THEN -amount
                    ELSE 0
                END), 0) AS net
               FROM transactions
               WHERE date BETWEEN ? AND ?
                 AND (from_entity_id = ? OR to_entity_id = ?)
                 AND category_id = ?""",
            (entity_id, entity_id, start, end, entity_id, entity_id, category_id),
        ).fetchone()
    return row["net"] if row else 0.0


# ─── Fiscal years CRUD ───────────────────────────────────────────────────────

@router.get("/fiscal-years")
def list_fiscal_years():
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM fiscal_years ORDER BY start_date DESC"
        ).fetchall()
        return [row_to_dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/fiscal-years/current")
def get_current_fiscal_year():
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM fiscal_years WHERE end_date IS NULL ORDER BY start_date DESC LIMIT 1"
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Aucun mandat en cours")
        return row_to_dict(row)
    finally:
        conn.close()


@router.post("/fiscal-years", status_code=201)
def create_fiscal_year(body: FiscalYearCreate):
    conn = get_conn()
    try:
        open_fy = conn.execute(
            "SELECT id, name FROM fiscal_years WHERE end_date IS NULL LIMIT 1"
        ).fetchone()
        if open_fy:
            raise HTTPException(
                400,
                f"Le mandat « {open_fy['name']} » est encore ouvert. Clos-le avant d'en créer un nouveau."
            )
        if conn.execute("SELECT id FROM fiscal_years WHERE name = ?", (body.name,)).fetchone():
            raise HTTPException(409, f"Un exercice nommé « {body.name} » existe déjà")
        now = _now()
        # Trouve l'exercice précédent : le plus récent dont end_date < nouveau start_date.
        prev_row = conn.execute(
            """SELECT id FROM fiscal_years
               WHERE end_date IS NOT NULL AND end_date < ?
               ORDER BY end_date DESC LIMIT 1""",
            (body.start_date,),
        ).fetchone()
        prev_fy_id = prev_row["id"] if prev_row else None
        cur = conn.execute(
            """INSERT INTO fiscal_years
                 (name, start_date, end_date, notes, previous_fiscal_year_id, president_name, tresorier_name, created_at, updated_at)
               VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?)""",
            (body.name, body.start_date, body.notes, prev_fy_id, body.president_name, body.tresorier_name, now, now),
        )
        fy_id = cur.lastrowid
        row = conn.execute("SELECT * FROM fiscal_years WHERE id = ?", (fy_id,)).fetchone()
        new_data = row_to_dict(row)
        conn.commit()
        return new_data
    finally:
        conn.close()


@router.post("/fiscal-years/{fy_id}/close")
def close_fiscal_year(fy_id: int, body: FiscalYearClose):
    conn = get_conn()
    try:
        existing = conn.execute("SELECT * FROM fiscal_years WHERE id = ?", (fy_id,)).fetchone()
        if existing is None:
            raise HTTPException(404, f"Exercice {fy_id} introuvable")
        if existing["end_date"] is not None:
            raise HTTPException(400, "Ce mandat est déjà clos")
        end_date = body.end_date or _today()
        if end_date <= existing["start_date"]:
            raise HTTPException(400, "La date de clôture doit être postérieure à la date de début")
        now = _now()
        conn.execute(
            "UPDATE fiscal_years SET end_date = ?, updated_at = ? WHERE id = ?",
            (end_date, now, fy_id),
        )
        row = conn.execute("SELECT * FROM fiscal_years WHERE id = ?", (fy_id,)).fetchone()
        new_data = row_to_dict(row)
        conn.commit()
        return new_data
    finally:
        conn.close()


@router.put("/fiscal-years/{fy_id}")
def update_fiscal_year(fy_id: int, body: FiscalYearUpdate):
    now = _now()
    conn = get_conn()
    try:
        existing = conn.execute("SELECT * FROM fiscal_years WHERE id = ?", (fy_id,)).fetchone()
        if existing is None:
            raise HTTPException(404, f"Exercice {fy_id} introuvable")
        old_data = row_to_dict(existing)
        updates = body.model_dump(exclude_unset=True)
        if not updates:
            return old_data
        set_clause = ", ".join(f"{k} = ?" for k in updates) + ", updated_at = ?"
        conn.execute(f"UPDATE fiscal_years SET {set_clause} WHERE id = ?",
                     list(updates.values()) + [now, fy_id])
        row = conn.execute("SELECT * FROM fiscal_years WHERE id = ?", (fy_id,)).fetchone()
        new_data = row_to_dict(row)
        conn.commit()
        return new_data
    finally:
        conn.close()


@router.delete("/fiscal-years/{fy_id}")
def delete_fiscal_year(fy_id: int):
    conn = get_conn()
    try:
        existing = conn.execute("SELECT * FROM fiscal_years WHERE id = ?", (fy_id,)).fetchone()
        if existing is None:
            raise HTTPException(404, f"Exercice {fy_id} introuvable")
        conn.execute("DELETE FROM budget_allocations WHERE fiscal_year_id = ?", (fy_id,))
        conn.execute("DELETE FROM fiscal_year_opening_balances WHERE fiscal_year_id = ?", (fy_id,))
        # Ne pas laisser un exercice suivant pointer vers un exercice supprimé.
        conn.execute(
            "UPDATE fiscal_years SET previous_fiscal_year_id = NULL WHERE previous_fiscal_year_id = ?",
            (fy_id,),
        )
        # Cascade vers les modules optionnels (ignorée si le module est absent).
        for stmt in (
            "DELETE FROM helloasso_campaign_transactions WHERE campaign_id IN "
            "(SELECT id FROM helloasso_campaigns WHERE fiscal_year_id = ?)",
            "DELETE FROM helloasso_campaigns WHERE fiscal_year_id = ?",
            "DELETE FROM report_accruals WHERE fiscal_year_id = ?",
        ):
            try:
                conn.execute(stmt, (fy_id,))
            except sqlite3.OperationalError:
                pass
        conn.execute("DELETE FROM fiscal_years WHERE id = ?", (fy_id,))
        conn.commit()
        return {"deleted": fy_id}
    finally:
        conn.close()


# ─── Opening-balances ────────────────────────────────────────────────────────

@router.get("/fiscal-years/{fy_id}/opening-balances")
def list_opening_balances(fy_id: int, request: Request):
    """Liste les soldes d'ouverture saisis pour un exercice.

    Non-admin : lignes filtrées au périmètre du rôle (entity_id hors périmètre
    absentes de la réponse). Admin (`allowed is None`) : inchangé.
    """
    user = get_current_user(request)
    conn = get_conn()
    try:
        if conn.execute("SELECT id FROM fiscal_years WHERE id = ?", (fy_id,)).fetchone() is None:
            raise HTTPException(404, f"Exercice {fy_id} introuvable")
        allowed = get_allowed_entity_ids(conn, user)
        query = "SELECT * FROM fiscal_year_opening_balances WHERE fiscal_year_id = ?"
        params: list = [fy_id]
        if allowed is not None:
            if not allowed:
                query += " AND 0 = 1"
            else:
                ph = ",".join("?" * len(allowed))
                query += f" AND entity_id IN ({ph})"
                params.extend(list(allowed))
        query += " ORDER BY entity_id"
        rows = conn.execute(query, params).fetchall()
        return [row_to_dict(r) for r in rows]
    finally:
        conn.close()


@router.put("/fiscal-years/{fy_id}/opening-balances/{entity_id}")
def upsert_opening_balance(fy_id: int, entity_id: int, body: OpeningBalanceUpsert):
    """Upsert du solde d'ouverture pour (exercice, entité). Montant en centimes."""
    conn = get_conn()
    try:
        if conn.execute("SELECT id FROM fiscal_years WHERE id = ?", (fy_id,)).fetchone() is None:
            raise HTTPException(404, f"Exercice {fy_id} introuvable")
        if conn.execute("SELECT id FROM entities WHERE id = ?", (entity_id,)).fetchone() is None:
            raise HTTPException(400, f"Entité {entity_id} introuvable")
        now = _now()
        conn.execute(
            """INSERT INTO fiscal_year_opening_balances
               (fiscal_year_id, entity_id, amount, source, notes, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(fiscal_year_id, entity_id) DO UPDATE SET
                 amount = excluded.amount,
                 source = excluded.source,
                 notes = excluded.notes,
                 updated_at = excluded.updated_at""",
            (fy_id, entity_id, body.amount, body.source, body.notes, now, now),
        )
        row = conn.execute(
            "SELECT * FROM fiscal_year_opening_balances WHERE fiscal_year_id = ? AND entity_id = ?",
            (fy_id, entity_id),
        ).fetchone()
        conn.commit()
        return row_to_dict(row)
    finally:
        conn.close()


# ─── Allocations CRUD ────────────────────────────────────────────────────────

@router.get("/fiscal-years/{fy_id}/allocations")
def list_allocations(fy_id: int, request: Request):
    """Liste les allocations budgétaires d'un exercice.

    Non-admin : lignes filtrées au périmètre du rôle (entity_id hors périmètre
    absentes de la réponse). Admin (`allowed is None`) : inchangé.
    """
    user = get_current_user(request)
    conn = get_conn()
    try:
        allowed = get_allowed_entity_ids(conn, user)
        query = "SELECT * FROM budget_allocations WHERE fiscal_year_id = ?"
        params: list = [fy_id]
        if allowed is not None:
            if not allowed:
                query += " AND 0 = 1"
            else:
                ph = ",".join("?" * len(allowed))
                query += f" AND entity_id IN ({ph})"
                params.extend(list(allowed))
        query += " ORDER BY entity_id, category_id"
        rows = conn.execute(query, params).fetchall()
        return [row_to_dict(r) for r in rows]
    finally:
        conn.close()


@router.post("/fiscal-years/{fy_id}/allocations", status_code=201)
def create_allocation(fy_id: int, body: AllocationCreate):
    conn = get_conn()
    try:
        if body.amount <= 0:
            raise HTTPException(400, "Le montant budgété doit être strictement positif (en centimes).")
        if conn.execute("SELECT id FROM fiscal_years WHERE id = ?", (fy_id,)).fetchone() is None:
            raise HTTPException(404, f"Exercice {fy_id} introuvable")
        if conn.execute("SELECT id FROM entities WHERE id = ?", (body.entity_id,)).fetchone() is None:
            raise HTTPException(400, f"Entité {body.entity_id} introuvable")
        if body.category_id is not None:
            if conn.execute("SELECT id FROM categories WHERE id = ?", (body.category_id,)).fetchone() is None:
                raise HTTPException(400, f"Catégorie {body.category_id} introuvable")
        if body.category_id is None:
            dup = conn.execute(
                "SELECT id FROM budget_allocations WHERE fiscal_year_id=? AND entity_id=? AND category_id IS NULL AND direction=?",
                (fy_id, body.entity_id, body.direction),
            ).fetchone()
        else:
            dup = conn.execute(
                "SELECT id FROM budget_allocations WHERE fiscal_year_id=? AND entity_id=? AND category_id=? AND direction=?",
                (fy_id, body.entity_id, body.category_id, body.direction),
            ).fetchone()
        if dup:
            raise HTTPException(409, "Une allocation existe déjà pour ce triplet (entité, catégorie, sens)")
        now = _now()
        cur = conn.execute(
            """INSERT INTO budget_allocations
               (fiscal_year_id, entity_id, category_id, direction, amount, notes, origin, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (fy_id, body.entity_id, body.category_id, body.direction, body.amount, body.notes, body.origin, now, now),
        )
        new_id = cur.lastrowid
        row = conn.execute("SELECT * FROM budget_allocations WHERE id = ?", (new_id,)).fetchone()
        new_data = row_to_dict(row)
        conn.commit()
        return new_data
    finally:
        conn.close()


@router.put("/allocations/{alloc_id}")
def update_allocation(alloc_id: int, body: AllocationUpdate):
    conn = get_conn()
    try:
        existing = conn.execute("SELECT * FROM budget_allocations WHERE id = ?", (alloc_id,)).fetchone()
        if existing is None:
            raise HTTPException(404, f"Allocation {alloc_id} introuvable")
        old_data = row_to_dict(existing)
        updates = body.model_dump(exclude_unset=True)
        if not updates:
            return old_data
        # Modifier le montant d'une allocation = la valider ce mandat -> passe en 'manual' (doré).
        if "amount" in updates:
            updates["origin"] = "manual"
        now = _now()
        set_clause = ", ".join(f"{k} = ?" for k in updates) + ", updated_at = ?"
        conn.execute(f"UPDATE budget_allocations SET {set_clause} WHERE id = ?",
                     list(updates.values()) + [now, alloc_id])
        row = conn.execute("SELECT * FROM budget_allocations WHERE id = ?", (alloc_id,)).fetchone()
        new_data = row_to_dict(row)
        conn.commit()
        return new_data
    finally:
        conn.close()


@router.delete("/allocations/{alloc_id}")
def delete_allocation(alloc_id: int):
    conn = get_conn()
    try:
        existing = conn.execute("SELECT * FROM budget_allocations WHERE id = ?", (alloc_id,)).fetchone()
        if existing is None:
            raise HTTPException(404, f"Allocation {alloc_id} introuvable")
        conn.execute("DELETE FROM budget_allocations WHERE id = ?", (alloc_id,))
        conn.commit()
        return {"deleted": alloc_id}
    finally:
        conn.close()


@router.post("/fiscal-years/{fy_id}/seed-from-realized")
def seed_budget_from_realized(fy_id: int):
    """Pré-remplit le budget prévisionnel à partir du réel de l'exercice précédent.

    Pour chaque (entité interne, catégorie) ayant un réel sur l'exercice précédent,
    crée l'allocation dépense et/ou recette correspondante — au centime près — SANS
    écraser les allocations déjà saisies (« remplir les vides »). Les flux sans
    catégorie sont ignorés : pas d'enveloppe globale (qui masquerait le détail).
    """
    conn = get_conn()
    try:
        fy = conn.execute("SELECT * FROM fiscal_years WHERE id = ?", (fy_id,)).fetchone()
        if fy is None:
            raise HTTPException(404, f"Exercice {fy_id} introuvable")
        prev_id = (fy["previous_fiscal_year_id"] if "previous_fiscal_year_id" in fy.keys() else None) \
            or _find_previous_fiscal_year(conn, fy["start_date"])
        prev = conn.execute("SELECT * FROM fiscal_years WHERE id = ?", (prev_id,)).fetchone() if prev_id else None
        if prev is None:
            raise HTTPException(400, "Aucun exercice précédent pour récupérer le réel")

        entity_ids = [r["id"] for r in conn.execute(
            "SELECT id FROM entities WHERE type = 'internal'"
        ).fetchall()]
        lookup = _build_realized_split(conn, entity_ids, prev["start_date"], _fy_end(prev))

        # Allocations déjà présentes : « remplir les vides » -> on ne les écrase pas.
        existing = set()
        for a in conn.execute(
            "SELECT entity_id, category_id, direction FROM budget_allocations WHERE fiscal_year_id = ?",
            (fy_id,),
        ).fetchall():
            existing.add((a["entity_id"], a["category_id"], a["direction"]))

        now = _now()
        created = 0
        for (entity_id, category_id), split in lookup.items():
            if category_id is None:
                continue
            for direction in ("expense", "income"):
                amount = int(split[direction])
                if amount == 0:
                    continue
                if (entity_id, category_id, direction) in existing:
                    continue
                conn.execute(
                    """INSERT INTO budget_allocations
                       (fiscal_year_id, entity_id, category_id, direction, amount, notes, origin, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, 'seeded', ?, ?)""",
                    (fy_id, entity_id, category_id, direction, amount, "", now, now),
                )
                existing.add((entity_id, category_id, direction))
                created += 1
        conn.commit()
        return {
            "created": created,
            "source_fiscal_year_id": prev["id"],
            "source_name": prev["name"],
        }
    finally:
        conn.close()


# ─── Composite views ─────────────────────────────────────────────────────────

def _build_realized_lookup(conn, entity_ids: list, start: str, end: str) -> dict:
    """Construit un dictionnaire {(entity_id, category_id): net} en deux requêtes agrégées.

    Réalisé net = SUM(amount où to=entité) - SUM(amount où from=entité).
    category_id peut être None (transactions sans catégorie).
    Remplace les appels _sum_realized individuels : O(entités × catégories) -> O(1).
    """
    if not entity_ids:
        return {}

    ph = ",".join("?" * len(entity_ids))

    # Recettes par (entity_id, category_id) sur l'intervalle
    rows_in = conn.execute(
        f"""SELECT to_entity_id AS entity_id, category_id,
                   SUM(amount) AS s
            FROM transactions
            WHERE date BETWEEN ? AND ?
              AND to_entity_id IN ({ph})
            GROUP BY to_entity_id, category_id""",
        [start, end] + list(entity_ids),
    ).fetchall()

    # Dépenses par (entity_id, category_id) sur l'intervalle
    rows_out = conn.execute(
        f"""SELECT from_entity_id AS entity_id, category_id,
                   SUM(amount) AS s
            FROM transactions
            WHERE date BETWEEN ? AND ?
              AND from_entity_id IN ({ph})
            GROUP BY from_entity_id, category_id""",
        [start, end] + list(entity_ids),
    ).fetchall()

    lookup: dict = {}
    for r in rows_in:
        key = (r["entity_id"], r["category_id"])
        lookup[key] = lookup.get(key, 0) + r["s"]
    for r in rows_out:
        key = (r["entity_id"], r["category_id"])
        lookup[key] = lookup.get(key, 0) - r["s"]
    return lookup


def _realized_from_lookup(lookup: dict, entity_id: int, category_id) -> float:
    """Lecture dans le lookup. Lorsque category_id est None, agrège toutes les catégories."""
    if category_id is not None:
        return float(lookup.get((entity_id, category_id), 0))
    # Agrégation totale pour cette entité (toutes catégories confondues)
    total = 0.0
    for (eid, _cat), net in lookup.items():
        if eid == entity_id:
            total += net
    return total


def _build_realized_split(conn, entity_ids: list, start: str, end: str) -> dict:
    """{(entity_id, category_id): {"income": int, "expense": int}} en deux requêtes.

    Convention budget (vue trésorerie par entité) :
      income  = SUM(amount) des flux entrants (to_entity_id = entité)
      expense = SUM(amount) des flux sortants (from_entity_id = entité)
    Les virements internes comptent (une dotation reçue est une recette du club).
    """
    if not entity_ids:
        return {}
    ph = ",".join("?" * len(entity_ids))
    rows_in = conn.execute(
        f"""SELECT to_entity_id AS entity_id, category_id, SUM(amount) AS s
            FROM transactions
            WHERE date BETWEEN ? AND ? AND to_entity_id IN ({ph})
            GROUP BY to_entity_id, category_id""",
        [start, end] + list(entity_ids),
    ).fetchall()
    rows_out = conn.execute(
        f"""SELECT from_entity_id AS entity_id, category_id, SUM(amount) AS s
            FROM transactions
            WHERE date BETWEEN ? AND ? AND from_entity_id IN ({ph})
            GROUP BY from_entity_id, category_id""",
        [start, end] + list(entity_ids),
    ).fetchall()
    lookup: dict = {}
    for r in rows_in:
        key = (r["entity_id"], r["category_id"])
        lookup.setdefault(key, {"income": 0, "expense": 0})["income"] += r["s"]
    for r in rows_out:
        key = (r["entity_id"], r["category_id"])
        lookup.setdefault(key, {"income": 0, "expense": 0})["expense"] += r["s"]
    return lookup


def _split_from_lookup(lookup: dict, entity_id: int, category_id) -> dict:
    """{"income", "expense"} pour une (entité, catégorie). category_id None = total entité."""
    if category_id is not None:
        e = lookup.get((entity_id, category_id), {"income": 0, "expense": 0})
        return {"income": e["income"], "expense": e["expense"]}
    total = {"income": 0, "expense": 0}
    for (eid, _cat), e in lookup.items():
        if eid == entity_id:
            total["income"] += e["income"]
            total["expense"] += e["expense"]
    return total


@router.get("/view")
def get_budget_view(request: Request, fiscal_year_id: int):
    """Vue budgétaire hiérarchique Groupe > Club > Catégorie avec dépenses et
    recettes séparées (prévu et réalisé), N-1 et taux de couverture.

    Renvoie `groups` (arbre, totaux agrégés propre + descendants) ET `entities`
    (liste plate, champs historiques) + `totals` pour le widget dashboard.

    Non-admin : la liste `entities` de la réponse composite est restreinte au
    périmètre du rôle (les entités hors périmètre n'apparaissent pas).
    """
    user = get_current_user(request)
    conn = get_conn()
    try:
        fy = conn.execute("SELECT * FROM fiscal_years WHERE id = ?", (fiscal_year_id,)).fetchone()
        if fy is None:
            raise HTTPException(404, f"Exercice {fiscal_year_id} introuvable")

        end_date = _fy_end(fy)
        as_of = (_date.fromisoformat(fy["start_date"]) - _timedelta(days=1)).isoformat()
        explicit_prev_id = fy["previous_fiscal_year_id"] if "previous_fiscal_year_id" in fy.keys() else None
        prev_id = explicit_prev_id or _find_previous_fiscal_year(conn, fy["start_date"])
        prev = conn.execute("SELECT * FROM fiscal_years WHERE id = ?", (prev_id,)).fetchone() if prev_id else None

        # Méta catégories (nom + parent) pour reconstruire la hiérarchie d'affichage.
        cat_meta = {
            c["id"]: {"name": c["name"], "parent_id": c["parent_id"]}
            for c in conn.execute("SELECT id, name, parent_id FROM categories").fetchall()
        }

        # Entités internes + toute entité portant une allocation sur cet exercice.
        ent_by_id: dict = {}
        for r in conn.execute("SELECT id, name, parent_id, color FROM entities WHERE type = 'internal'").fetchall():
            ent_by_id[r["id"]] = {"id": r["id"], "name": r["name"], "parent_id": r["parent_id"], "color": r["color"]}
        for r in conn.execute(
            "SELECT DISTINCT entity_id FROM budget_allocations WHERE fiscal_year_id = ?", (fiscal_year_id,)
        ).fetchall():
            if r["entity_id"] not in ent_by_id:
                e = conn.execute("SELECT id, name, parent_id, color FROM entities WHERE id = ?", (r["entity_id"],)).fetchone()
                if e is not None:
                    ent_by_id[e["id"]] = {"id": e["id"], "name": e["name"], "parent_id": e["parent_id"], "color": e["color"]}

        entity_ids_list = sorted(ent_by_id.keys())
        lookup_n = _build_realized_split(conn, entity_ids_list, fy["start_date"], end_date)
        lookup_n1: dict = _build_realized_split(conn, entity_ids_list, prev["start_date"], _fy_end(prev)) if prev else {}

        # Allocations groupées par entité.
        allocs_by_entity: dict = {}
        for a in conn.execute(
            """SELECT a.id, a.entity_id, a.category_id, a.direction, a.amount, a.origin, c.name AS category_name
               FROM budget_allocations a
               LEFT JOIN categories c ON a.category_id = c.id
               WHERE a.fiscal_year_id = ?""",
            (fiscal_year_id,),
        ).fetchall():
            allocs_by_entity.setdefault(a["entity_id"], []).append(dict(a))

        # Index parent -> enfants ; racines = entités sans parent connu dans le périmètre.
        children_of: dict = {}
        roots: list = []
        for eid, ent in ent_by_id.items():
            pid = ent["parent_id"]
            if pid is not None and pid in ent_by_id:
                children_of.setdefault(pid, []).append(eid)
            else:
                roots.append(eid)

        def opening_for(eid):
            ob = conn.execute(
                "SELECT amount FROM fiscal_year_opening_balances WHERE fiscal_year_id = ? AND entity_id = ?",
                (fiscal_year_id, eid),
            ).fetchone()
            if ob is not None:
                return ob["amount"]
            # Solde en centimes entiers : pas de round(..., 2) qui le passerait en float.
            return int(compute_entity_balance(conn, eid, as_of_date=as_of)["balance"])

        def effective_alloc(allocs, direction):
            glob = sum(a["amount"] for a in allocs if a["direction"] == direction and a["category_id"] is None)
            det = sum(a["amount"] for a in allocs if a["direction"] == direction and a["category_id"] is not None)
            has_glob = any(a["direction"] == direction and a["category_id"] is None for a in allocs)
            return glob if has_glob else det

        def build_categories(eid, allocs):
            # Catégories « porteuses » : allocation, réel N ou réel N-1 sur cette entité.
            carrier_ids = {a["category_id"] for a in allocs if a["category_id"] is not None}
            carrier_ids |= {cat for (e, cat) in lookup_n if e == eid and cat is not None}
            if prev:
                carrier_ids |= {cat for (e, cat) in lookup_n1 if e == eid and cat is not None}

            # Montants propres (sans descendants) par catégorie porteuse.
            own: dict = {}
            for cid in carrier_ids:
                exp = next((a for a in allocs if a["category_id"] == cid and a["direction"] == "expense"), None)
                inc = next((a for a in allocs if a["category_id"] == cid and a["direction"] == "income"), None)
                sn = _split_from_lookup(lookup_n, eid, cid)
                sn1 = _split_from_lookup(lookup_n1, eid, cid) if prev else {"income": 0, "expense": 0}
                name = cat_meta.get(cid, {}).get("name")
                if not name:
                    name = next((a["category_name"] for a in allocs if a["category_id"] == cid and a["category_name"]), None) \
                        or "— Catégorie supprimée —"
                own[cid] = {
                    "name": name,
                    "allocation_id_expense": exp["id"] if exp else None,
                    "allocation_id_income": inc["id"] if inc else None,
                    "origin_expense": exp["origin"] if exp else None,
                    "origin_income": inc["origin"] if inc else None,
                    "allocated_expense": exp["amount"] if exp else 0,
                    "allocated_income": inc["amount"] if inc else 0,
                    "realized_expense": sn["expense"],
                    "realized_income": sn["income"],
                    "realized_expense_n1": sn1["expense"],
                    "realized_income_n1": sn1["income"],
                }

            # Matérialise les ancêtres pour le regroupement (montants propres nuls).
            node_ids = set(carrier_ids)
            for cid in carrier_ids:
                p = cat_meta.get(cid, {}).get("parent_id")
                while p is not None and p not in node_ids and p in cat_meta:
                    node_ids.add(p)
                    p = cat_meta.get(p, {}).get("parent_id")
            for cid in node_ids:
                if cid not in own:
                    own[cid] = {
                        "name": cat_meta.get(cid, {}).get("name") or "— Catégorie supprimée —",
                        "allocation_id_expense": None,
                        "allocation_id_income": None,
                        "origin_expense": None,
                        "origin_income": None,
                        "allocated_expense": 0,
                        "allocated_income": 0,
                        "realized_expense": 0,
                        "realized_income": 0,
                        "realized_expense_n1": 0,
                        "realized_income_n1": 0,
                    }

            # Index parent -> enfants ; racines = parent hors ensemble.
            children_of_cat: dict = {}
            cat_roots: list = []
            for cid in node_ids:
                pid = cat_meta.get(cid, {}).get("parent_id")
                if pid is not None and pid in node_ids:
                    children_of_cat.setdefault(pid, []).append(cid)
                else:
                    cat_roots.append(cid)

            def build_cat_node(cid):
                o = own[cid]
                kids = [build_cat_node(c) for c in children_of_cat.get(cid, [])]
                kids.sort(key=lambda c: c["category_name"])
                a_exp = o["allocated_expense"] + sum(k["allocated_expense"] for k in kids)
                a_inc = o["allocated_income"] + sum(k["allocated_income"] for k in kids)
                r_exp = o["realized_expense"] + sum(k["realized_expense"] for k in kids)
                r_inc = o["realized_income"] + sum(k["realized_income"] for k in kids)
                r_exp1 = o["realized_expense_n1"] + sum(k["realized_expense_n1"] for k in kids)
                r_inc1 = o["realized_income_n1"] + sum(k["realized_income_n1"] for k in kids)
                net = r_inc - r_exp
                net1 = r_inc1 - r_exp1
                base = a_exp if a_exp else a_inc
                pct = abs(net) / base * 100.0 if base else 0.0
                cov = r_inc / r_exp * 100.0 if r_exp else 0.0
                return {
                    "category_id": cid,
                    "category_name": o["name"],
                    "parent_id": cat_meta.get(cid, {}).get("parent_id"),
                    "is_leaf": len(kids) == 0,
                    "allocation_id": o["allocation_id_expense"] or o["allocation_id_income"],
                    "allocation_id_expense": o["allocation_id_expense"],
                    "allocation_id_income": o["allocation_id_income"],
                    # Origine du budget (feuilles uniquement) : 'seeded' -> gris, 'manual' -> doré.
                    "origin_expense": o["origin_expense"],
                    "origin_income": o["origin_income"],
                    "allocated": a_exp,            # legacy (dépense)
                    "allocated_expense": a_exp,
                    "allocated_income": a_inc,
                    "realized": net,               # legacy (net)
                    "realized_expense": r_exp,
                    "realized_income": r_inc,
                    "realized_n_minus_1": net1,    # legacy (net)
                    "realized_expense_n1": r_exp1,
                    "realized_income_n1": r_inc1,
                    "percent_consumed": round(pct, 1),
                    "coverage_pct": round(cov, 1),
                    "children": kids,
                }

            roots = [build_cat_node(cid) for cid in cat_roots]
            roots.sort(key=lambda c: c["category_name"])

            # Ligne « Sans catégorie » : réel non catégorisé (N et N-1) de l'entité,
            # pour que la somme des lignes réconcilie le total de l'entité (lecture seule).
            unc_n = lookup_n.get((eid, None), {"income": 0, "expense": 0})
            unc_n1 = lookup_n1.get((eid, None), {"income": 0, "expense": 0}) if prev else {"income": 0, "expense": 0}
            if unc_n["income"] or unc_n["expense"] or unc_n1["income"] or unc_n1["expense"]:
                net = unc_n["income"] - unc_n["expense"]
                net1 = unc_n1["income"] - unc_n1["expense"]
                cov = unc_n["income"] / unc_n["expense"] * 100.0 if unc_n["expense"] else 0.0
                roots.append({
                    "category_id": None,
                    "category_name": "Sans catégorie",
                    "parent_id": None,
                    "is_leaf": True,
                    "allocation_id": None,
                    "allocation_id_expense": None,
                    "allocation_id_income": None,
                    "allocated": 0,
                    "allocated_expense": 0,
                    "allocated_income": 0,
                    "realized": net,
                    "realized_expense": unc_n["expense"],
                    "realized_income": unc_n["income"],
                    "realized_n_minus_1": net1,
                    "realized_expense_n1": unc_n1["expense"],
                    "realized_income_n1": unc_n1["income"],
                    "percent_consumed": 0.0,
                    "coverage_pct": round(cov, 1),
                    "children": [],
                })
            return roots

        def build_node(eid):
            ent = ent_by_id[eid]
            allocs = allocs_by_entity.get(eid, [])
            own_alloc_exp = effective_alloc(allocs, "expense")
            own_alloc_inc = effective_alloc(allocs, "income")
            own_n = _split_from_lookup(lookup_n, eid, None)
            own_n1 = _split_from_lookup(lookup_n1, eid, None) if prev else {"income": 0, "expense": 0}
            cats = build_categories(eid, allocs)
            children = [build_node(c) for c in sorted(children_of.get(eid, []))]

            alloc_exp = own_alloc_exp + sum(ch["allocated_expense"] for ch in children)
            alloc_inc = own_alloc_inc + sum(ch["allocated_income"] for ch in children)
            real_exp = own_n["expense"] + sum(ch["realized_expense"] for ch in children)
            real_inc = own_n["income"] + sum(ch["realized_income"] for ch in children)
            real_exp1 = own_n1["expense"] + sum(ch["realized_expense_n1"] for ch in children)
            real_inc1 = own_n1["income"] + sum(ch["realized_income_n1"] for ch in children)
            net = real_inc - real_exp
            net1 = real_inc1 - real_exp1
            cov = real_inc / real_exp * 100.0 if real_exp else 0.0
            variation = round((net - net1) / abs(net1) * 100.0, 1) if net1 != 0 else None

            return {
                "entity_id": eid,
                "entity_name": ent["name"],
                "parent_id": ent["parent_id"],
                "color": ent["color"],
                "opening_balance": opening_for(eid),
                "allocated_expense": alloc_exp,
                "allocated_income": alloc_inc,
                "realized_expense": real_exp,
                "realized_income": real_inc,
                "realized_net": net,
                "realized_expense_n1": real_exp1,
                "realized_income_n1": real_inc1,
                "coverage_pct": round(cov, 1),
                "categories": cats,
                "children": children,
                # Champs historiques (widget dashboard + rétro-compatibilité).
                "allocated_total": alloc_exp,
                "realized_total": net,
                "realized_n_minus_1": net1,
                "variation_pct": variation,
            }

        groups = [build_node(r) for r in sorted(roots)]

        # Non-admin : élague l'arbre au périmètre du rôle avant tout calcul de
        # total. `allowed` est clos par sous-arbre (get_allowed_entity_ids) :
        # si un nœud est dans le périmètre, TOUS ses descendants le sont aussi
        # (la CTE remonte récursivement depuis les racines octroyées). Les
        # agrégats déjà calculés par build_node (propre + descendants) pour un
        # nœud conservé ne peuvent donc contenir aucune entité hors périmètre
        # -> aucun recalcul de valeur n'est nécessaire, seule la structure est
        # élaguée. Un nœud hors périmètre est supprimé et ses enfants conservés
        # (déjà élagués récursivement) sont remontés à son niveau, ce qui
        # recompose bien les racines de l'arbre affiché à partir de la liste
        # aplatie filtrée, sans jamais garder de total global.
        allowed = get_allowed_entity_ids(conn, user)

        def _prune_groups(nodes):
            result = []
            for node in nodes:
                pruned_children = _prune_groups(node["children"])
                if node["entity_id"] in allowed:
                    result.append({**node, "children": pruned_children})
                else:
                    result.extend(pruned_children)
            return result

        if allowed is not None:
            groups = _prune_groups(groups)

        flat: list = []

        def flatten(node):
            flat.append({k: v for k, v in node.items() if k != "children"})
            for ch in node["children"]:
                flatten(ch)
        for g in groups:
            flatten(g)

        # Recalculé APRÈS élagage : pour un non-admin, `groups` ne contient
        # plus que les racines (promues) du périmètre, donc ces totaux ne
        # portent que sur son sous-arbre (jamais le total global).
        totals = {
            "allocated_expense": sum(g["allocated_expense"] for g in groups),
            "allocated_income": sum(g["allocated_income"] for g in groups),
            "realized_expense": sum(g["realized_expense"] for g in groups),
            "realized_income": sum(g["realized_income"] for g in groups),
        }
        totals["realized_net"] = totals["realized_income"] - totals["realized_expense"]
        # Champs historiques : allocated = budget dépenses, realized = net.
        totals["allocated"] = totals["allocated_expense"]
        totals["realized"] = totals["realized_net"]
        totals["remaining"] = totals["allocated"] + totals["realized"]

        return {
            "fiscal_year": row_to_dict(fy),
            "previous_fiscal_year_id": prev["id"] if prev else None,
            "groups": groups,
            "entities": flat,
            "totals": totals,
        }
    finally:
        conn.close()


@router.get("/view/categories")
def get_budget_category_view(request: Request, fiscal_year_id: int, entity_id: Optional[int] = None):
    """Vue par catégorie parente — toutes entités internes confondues, ou
    limitée au sous-arbre d'une entité (focus global) quand entity_id est fourni.

    Non-admin : entity_id obligatoire (400 sinon) et vérifié contre le
    périmètre du rôle (403 hors périmètre). Admin (`allowed is None`) : inchangé.
    """
    user = get_current_user(request)
    conn = get_conn()
    try:
        _require_scope(conn, user, entity_id)
        fy = conn.execute("SELECT * FROM fiscal_years WHERE id = ?", (fiscal_year_id,)).fetchone()
        if fy is None:
            raise HTTPException(404, f"Exercice {fiscal_year_id} introuvable")

        end_date = _fy_end(fy)
        prev_id = _find_previous_fiscal_year(conn, fy["start_date"])
        prev = conn.execute("SELECT * FROM fiscal_years WHERE id = ?", (prev_id,)).fetchone() if prev_id else None

        all_cats = conn.execute("SELECT id, name, parent_id FROM categories ORDER BY name").fetchall()
        cat_by_id = {c["id"]: {"id": c["id"], "name": c["name"], "parent_id": c["parent_id"]}
                     for c in all_cats}

        def get_descendants(root_id: int) -> list:
            result, queue = {root_id}, [root_id]
            while queue:
                parent = queue.pop()
                for c in cat_by_id.values():
                    # `not in result` : garde anti-cycle (évite une boucle infinie
                    # si des données héritées contiennent un cycle parent_id).
                    if c["parent_id"] == parent and c["id"] not in result:
                        result.add(c["id"])
                        queue.append(c["id"])
            return list(result)

        root_cats = sorted(
            [c for c in cat_by_id.values() if c["parent_id"] is None],
            key=lambda c: c["name"],
        )

        if entity_id is not None:
            # Périmètre = sous-arbre interne de l'entité focalisée (mêmes
            # conventions que le dashboard : flux traversant la frontière).
            from backend.core.balance import get_subtree_ids
            internal_ids = get_subtree_ids(conn, entity_id)
        else:
            internal_ids = [r["id"] for r in conn.execute(
                "SELECT id FROM entities WHERE type = 'internal'"
            ).fetchall()]

        def sum_cat_realized(cat_ids: list, start: str, end: str) -> float:
            if not cat_ids or not internal_ids:
                return 0.0
            ph_e = ",".join("?" * len(internal_ids))
            ph_c = ",".join("?" * len(cat_ids))
            row = conn.execute(
                f"""SELECT COALESCE(SUM(CASE
                      WHEN to_entity_id IN ({ph_e}) AND (from_entity_id IS NULL OR from_entity_id NOT IN ({ph_e})) THEN amount
                      WHEN from_entity_id IN ({ph_e}) AND (to_entity_id IS NULL OR to_entity_id NOT IN ({ph_e})) THEN -amount
                      ELSE 0 END), 0) AS net
                    FROM transactions
                    WHERE date BETWEEN ? AND ? AND category_id IN ({ph_c})""",
                (*internal_ids, *internal_ids, *internal_ids, *internal_ids, start, end, *cat_ids),
            ).fetchone()
            return row["net"] if row else 0.0

        def sum_cat_allocated(cat_ids: list) -> float:
            if not cat_ids:
                return 0.0
            ph = ",".join("?" * len(cat_ids))
            sql = f"SELECT COALESCE(SUM(amount),0) AS t FROM budget_allocations WHERE fiscal_year_id=? AND category_id IN ({ph})"
            params = [fiscal_year_id, *cat_ids]
            if entity_id is not None:
                ph_e = ",".join("?" * len(internal_ids))
                sql += f" AND entity_id IN ({ph_e})"
                params.extend(internal_ids)
            row = conn.execute(sql, params).fetchone()
            return row["t"] if row else 0.0

        rows_out = []
        total_realized = total_allocated = 0.0

        for root in root_cats:
            desc = get_descendants(root["id"])
            realized = sum_cat_realized(desc, fy["start_date"], end_date)
            allocated = sum_cat_allocated(desc)
            realized_n1 = sum_cat_realized(desc, prev["start_date"], _fy_end(prev)) if prev else 0.0
            pct = abs(realized) / allocated * 100.0 if allocated != 0 else 0.0
            rows_out.append({
                "category_id": root["id"],
                "category_name": root["name"],
                "allocated": allocated,
                "realized": realized,
                "realized_n_minus_1": realized_n1,
                "percent_consumed": round(pct, 1),
            })
            total_realized += realized
            total_allocated += allocated

        if internal_ids:
            ph_e = ",".join("?" * len(internal_ids))
            row = conn.execute(
                f"""SELECT COALESCE(SUM(CASE
                      WHEN to_entity_id IN ({ph_e}) AND (from_entity_id IS NULL OR from_entity_id NOT IN ({ph_e})) THEN amount
                      WHEN from_entity_id IN ({ph_e}) AND (to_entity_id IS NULL OR to_entity_id NOT IN ({ph_e})) THEN -amount
                      ELSE 0 END), 0) AS net
                    FROM transactions
                    WHERE date BETWEEN ? AND ? AND category_id IS NULL""",
                (*internal_ids, *internal_ids, *internal_ids, *internal_ids, fy["start_date"], end_date),
            ).fetchone()
            uncategorized = row["net"] if row else 0.0
            if uncategorized != 0:
                rows_out.append({
                    "category_id": None,
                    "category_name": "— Sans catégorie —",
                    "allocated": 0.0,
                    "realized": uncategorized,
                    "realized_n_minus_1": 0.0,
                    "percent_consumed": 0.0,
                })
                total_realized += uncategorized

        return {
            "fiscal_year": row_to_dict(fy),
            "categories": rows_out,
            "totals": {"allocated": total_allocated, "realized": total_realized},
        }
    finally:
        conn.close()
