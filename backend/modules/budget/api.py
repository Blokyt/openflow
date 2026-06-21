"""Budget & Exercices API module for OpenFlow."""
from datetime import datetime, timezone, date as _date, timedelta as _timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core.database import get_conn, row_to_dict
from backend.core.balance import compute_entity_balance

router = APIRouter()


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
    amount: int  # centimes entiers (cohérent avec le stockage budget_allocations)
    notes: str = ""


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
        conn.execute("DELETE FROM fiscal_years WHERE id = ?", (fy_id,))
        conn.commit()
        return {"deleted": fy_id}
    finally:
        conn.close()


# ─── Opening-balances ────────────────────────────────────────────────────────

@router.get("/fiscal-years/{fy_id}/opening-balances")
def list_opening_balances(fy_id: int):
    """Liste les soldes d'ouverture saisis pour un exercice."""
    conn = get_conn()
    try:
        if conn.execute("SELECT id FROM fiscal_years WHERE id = ?", (fy_id,)).fetchone() is None:
            raise HTTPException(404, f"Exercice {fy_id} introuvable")
        rows = conn.execute(
            "SELECT * FROM fiscal_year_opening_balances WHERE fiscal_year_id = ? ORDER BY entity_id",
            (fy_id,),
        ).fetchall()
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
def list_allocations(fy_id: int):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM budget_allocations WHERE fiscal_year_id = ? ORDER BY entity_id, category_id",
            (fy_id,),
        ).fetchall()
        return [row_to_dict(r) for r in rows]
    finally:
        conn.close()


@router.post("/fiscal-years/{fy_id}/allocations", status_code=201)
def create_allocation(fy_id: int, body: AllocationCreate):
    conn = get_conn()
    try:
        if conn.execute("SELECT id FROM fiscal_years WHERE id = ?", (fy_id,)).fetchone() is None:
            raise HTTPException(404, f"Exercice {fy_id} introuvable")
        if conn.execute("SELECT id FROM entities WHERE id = ?", (body.entity_id,)).fetchone() is None:
            raise HTTPException(400, f"Entité {body.entity_id} introuvable")
        if body.category_id is not None:
            if conn.execute("SELECT id FROM categories WHERE id = ?", (body.category_id,)).fetchone() is None:
                raise HTTPException(400, f"Catégorie {body.category_id} introuvable")
        if body.category_id is None:
            dup = conn.execute(
                "SELECT id FROM budget_allocations WHERE fiscal_year_id=? AND entity_id=? AND category_id IS NULL",
                (fy_id, body.entity_id),
            ).fetchone()
        else:
            dup = conn.execute(
                "SELECT id FROM budget_allocations WHERE fiscal_year_id=? AND entity_id=? AND category_id=?",
                (fy_id, body.entity_id, body.category_id),
            ).fetchone()
        if dup:
            raise HTTPException(409, "Une allocation existe déjà pour ce triplet")
        now = _now()
        cur = conn.execute(
            """INSERT INTO budget_allocations
               (fiscal_year_id, entity_id, category_id, amount, notes, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (fy_id, body.entity_id, body.category_id, body.amount, body.notes, now, now),
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


@router.get("/view")
def get_budget_view(fiscal_year_id: int):
    conn = get_conn()
    try:
        fy = conn.execute("SELECT * FROM fiscal_years WHERE id = ?", (fiscal_year_id,)).fetchone()
        if fy is None:
            raise HTTPException(404, f"Exercice {fiscal_year_id} introuvable")

        end_date = _fy_end(fy)
        as_of = (_date.fromisoformat(fy["start_date"]) - _timedelta(days=1)).isoformat()
        # Utilise le lien explicite s'il est renseigné, sinon heuristique.
        explicit_prev_id = fy["previous_fiscal_year_id"] if "previous_fiscal_year_id" in fy.keys() else None
        prev_id = explicit_prev_id or _find_previous_fiscal_year(conn, fy["start_date"])
        prev = conn.execute("SELECT * FROM fiscal_years WHERE id = ?", (prev_id,)).fetchone() if prev_id else None

        entity_ids = {r["id"] for r in conn.execute(
            "SELECT id FROM entities WHERE type = 'internal'"
        ).fetchall()}
        entity_ids.update(
            r["entity_id"] for r in conn.execute(
                "SELECT DISTINCT entity_id FROM budget_allocations WHERE fiscal_year_id = ?",
                (fiscal_year_id,),
            ).fetchall()
        )

        entity_ids_list = sorted(entity_ids)

        # Deux requêtes agrégées pour N et N-1 : remplace O(entités × catégories) appels _sum_realized.
        lookup_n = _build_realized_lookup(conn, entity_ids_list, fy["start_date"], end_date)
        lookup_n1: dict = {}
        if prev:
            lookup_n1 = _build_realized_lookup(conn, entity_ids_list, prev["start_date"], _fy_end(prev))

        result_entities = []
        total_allocated = total_realized = 0.0

        for eid in entity_ids_list:
            ent = conn.execute("SELECT id, name FROM entities WHERE id = ?", (eid,)).fetchone()
            if ent is None:
                continue

            # Priorité au solde d'ouverture saisi manuellement.
            ob_row = conn.execute(
                "SELECT amount FROM fiscal_year_opening_balances WHERE fiscal_year_id = ? AND entity_id = ?",
                (fiscal_year_id, eid),
            ).fetchone()
            if ob_row is not None:
                opening = ob_row["amount"]
            else:
                opening = round(compute_entity_balance(conn, eid, as_of_date=as_of)["balance"], 2)

            allocs = conn.execute(
                """SELECT a.*, c.name AS category_name
                   FROM budget_allocations a
                   LEFT JOIN categories c ON a.category_id = c.id
                   WHERE a.fiscal_year_id = ? AND a.entity_id = ?""",
                (fiscal_year_id, eid),
            ).fetchall()

            allocated_global = sum(a["amount"] for a in allocs if a["category_id"] is None)
            allocated_detailed = sum(a["amount"] for a in allocs if a["category_id"] is not None)
            has_global = any(a["category_id"] is None for a in allocs)
            allocated_effective = allocated_global if has_global else allocated_detailed

            cats_out = []
            for a in allocs:
                if a["category_id"] is None:
                    continue
                realized = _realized_from_lookup(lookup_n, eid, a["category_id"])
                realized_n1 = _realized_from_lookup(lookup_n1, eid, a["category_id"]) if prev else 0.0
                pct = abs(realized) / a["amount"] * 100.0 if a["amount"] != 0 else 0.0
                cats_out.append({
                    "category_id": a["category_id"],
                    "category_name": a["category_name"] or "— Catégorie supprimée —",
                    "allocation_id": a["id"],
                    "allocated": a["amount"],
                    "realized": realized,
                    "realized_n_minus_1": realized_n1,
                    "percent_consumed": round(pct, 1),
                })

            realized_total = _realized_from_lookup(lookup_n, eid, None)
            realized_n1_total = _realized_from_lookup(lookup_n1, eid, None) if prev else 0.0

            result_entities.append({
                "entity_id": eid,
                "entity_name": ent["name"],
                "opening_balance": opening,
                "allocated_total": allocated_effective,
                "realized_total": realized_total,
                "realized_n_minus_1": realized_n1_total,
                "variation_pct": (
                    round((realized_total - realized_n1_total) / abs(realized_n1_total) * 100.0, 1)
                    if realized_n1_total != 0 else None
                ),
                "categories": cats_out,
            })
            total_allocated += allocated_effective
            total_realized += realized_total

        return {
            "fiscal_year": row_to_dict(fy),
            "previous_fiscal_year_id": prev["id"] if prev else None,
            "entities": result_entities,
            "totals": {
                "allocated": total_allocated,
                "realized": total_realized,
                "remaining": total_allocated + total_realized,
            },
        }
    finally:
        conn.close()


@router.get("/view/categories")
def get_budget_category_view(fiscal_year_id: int):
    """Vue par catégorie parente — toutes entités internes confondues."""
    conn = get_conn()
    try:
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
                    if c["parent_id"] == parent:
                        result.add(c["id"])
                        queue.append(c["id"])
            return list(result)

        root_cats = sorted(
            [c for c in cat_by_id.values() if c["parent_id"] is None],
            key=lambda c: c["name"],
        )

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
                      WHEN to_entity_id IN ({ph_e}) AND from_entity_id NOT IN ({ph_e}) THEN amount
                      WHEN from_entity_id IN ({ph_e}) AND to_entity_id NOT IN ({ph_e}) THEN -amount
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
            row = conn.execute(
                f"SELECT COALESCE(SUM(amount),0) AS t FROM budget_allocations WHERE fiscal_year_id=? AND category_id IN ({ph})",
                (fiscal_year_id, *cat_ids),
            ).fetchone()
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
                      WHEN to_entity_id IN ({ph_e}) AND from_entity_id NOT IN ({ph_e}) THEN amount
                      WHEN from_entity_id IN ({ph_e}) AND to_entity_id NOT IN ({ph_e}) THEN -amount
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
