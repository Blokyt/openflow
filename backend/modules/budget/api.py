"""Budget & Exercices API module for OpenFlow."""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core.database import get_conn, row_to_dict

router = APIRouter()


# ─── Pydantic models ─────────────────────────────────────────────────────────

class FiscalYearCreate(BaseModel):
    name: str
    start_date: str
    end_date: str
    is_current: bool = False
    notes: str = ""


class FiscalYearUpdate(BaseModel):
    name: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    is_current: Optional[bool] = None
    notes: Optional[str] = None


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _set_single_current(conn, fiscal_year_id: int) -> None:
    """Atomically flip is_current so only the given year is marked current."""
    conn.execute("UPDATE fiscal_years SET is_current = 0 WHERE id != ?", (fiscal_year_id,))
    conn.execute("UPDATE fiscal_years SET is_current = 1 WHERE id = ?", (fiscal_year_id,))


# ─── Fiscal years CRUD ──────────────────────────────────────────────────────

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
            "SELECT * FROM fiscal_years WHERE is_current = 1 LIMIT 1"
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Aucun exercice marqué actif")
        return row_to_dict(row)
    finally:
        conn.close()


@router.post("/fiscal-years", status_code=201)
def create_fiscal_year(body: FiscalYearCreate):
    if body.start_date >= body.end_date:
        raise HTTPException(400, "start_date doit être antérieur à end_date")
    now = _now()
    conn = get_conn()
    try:
        dup = conn.execute("SELECT id FROM fiscal_years WHERE name = ?", (body.name,)).fetchone()
        if dup is not None:
            raise HTTPException(409, f"Un exercice nommé '{body.name}' existe déjà")
        cur = conn.execute(
            """INSERT INTO fiscal_years
               (name, start_date, end_date, is_current, notes, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (body.name, body.start_date, body.end_date,
             1 if body.is_current else 0, body.notes, now, now),
        )
        fy_id = cur.lastrowid
        if body.is_current:
            _set_single_current(conn, fy_id)
        conn.commit()
        row = conn.execute("SELECT * FROM fiscal_years WHERE id = ?", (fy_id,)).fetchone()
        return row_to_dict(row)
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

        updates = body.model_dump(exclude_unset=True)
        if not updates:
            return row_to_dict(existing)

        new_start = updates.get("start_date", existing["start_date"])
        new_end = updates.get("end_date", existing["end_date"])
        if new_start >= new_end:
            raise HTTPException(400, "start_date doit être antérieur à end_date")

        if "is_current" in updates:
            updates["is_current"] = 1 if updates["is_current"] else 0

        set_clause = ", ".join(f"{k} = ?" for k in updates) + ", updated_at = ?"
        values = list(updates.values()) + [now, fy_id]
        conn.execute(f"UPDATE fiscal_years SET {set_clause} WHERE id = ?", values)
        if updates.get("is_current") == 1:
            _set_single_current(conn, fy_id)
        conn.commit()
        row = conn.execute("SELECT * FROM fiscal_years WHERE id = ?", (fy_id,)).fetchone()
        return row_to_dict(row)
    finally:
        conn.close()


@router.delete("/fiscal-years/{fy_id}")
def delete_fiscal_year(fy_id: int):
    conn = get_conn()
    try:
        existing = conn.execute("SELECT * FROM fiscal_years WHERE id = ?", (fy_id,)).fetchone()
        if existing is None:
            raise HTTPException(404, f"Exercice {fy_id} introuvable")
        # Applicative cascade (PRAGMA foreign_keys OFF in this project)
        conn.execute("DELETE FROM budget_allocations WHERE fiscal_year_id = ?", (fy_id,))
        conn.execute("DELETE FROM fiscal_year_opening_balances WHERE fiscal_year_id = ?", (fy_id,))
        conn.execute("DELETE FROM fiscal_years WHERE id = ?", (fy_id,))
        conn.commit()
        return {"deleted": fy_id}
    finally:
        conn.close()


class OpeningBalanceEntry(BaseModel):
    entity_id: int
    amount: float
    source: str = ""
    notes: str = ""


@router.get("/fiscal-years/{fy_id}/opening-balances")
def list_opening_balances(fy_id: int):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM fiscal_year_opening_balances WHERE fiscal_year_id = ? ORDER BY entity_id",
            (fy_id,),
        ).fetchall()
        return [row_to_dict(r) for r in rows]
    finally:
        conn.close()


@router.put("/fiscal-years/{fy_id}/opening-balances")
def upsert_opening_balances(fy_id: int, entries: list[OpeningBalanceEntry]):
    conn = get_conn()
    try:
        fy = conn.execute("SELECT id FROM fiscal_years WHERE id = ?", (fy_id,)).fetchone()
        if fy is None:
            raise HTTPException(404, f"Exercice {fy_id} introuvable")

        # Validate each entity is internal
        for entry in entries:
            ent = conn.execute(
                "SELECT type FROM entities WHERE id = ?", (entry.entity_id,)
            ).fetchone()
            if ent is None:
                raise HTTPException(400, f"Entité {entry.entity_id} introuvable")
            if ent["type"] != "internal":
                raise HTTPException(
                    400, f"Entité {entry.entity_id} est externe: pas de solde d'ouverture"
                )

        now = _now()
        conn.execute("DELETE FROM fiscal_year_opening_balances WHERE fiscal_year_id = ?", (fy_id,))
        for entry in entries:
            conn.execute(
                """INSERT INTO fiscal_year_opening_balances
                   (fiscal_year_id, entity_id, amount, source, notes, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (fy_id, entry.entity_id, entry.amount, entry.source, entry.notes, now, now),
            )
        conn.commit()
        rows = conn.execute(
            "SELECT * FROM fiscal_year_opening_balances WHERE fiscal_year_id = ? ORDER BY entity_id",
            (fy_id,),
        ).fetchall()
        return [row_to_dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/fiscal-years/{fy_id}/suggested-opening")
def suggested_opening(fy_id: int):
    """For each internal entity, suggest the balance as of start_date - 1 day."""
    from datetime import date as _date, timedelta
    from backend.core.balance import compute_entity_balance

    conn = get_conn()
    try:
        fy = conn.execute(
            "SELECT id, start_date FROM fiscal_years WHERE id = ?", (fy_id,)
        ).fetchone()
        if fy is None:
            raise HTTPException(404, f"Exercice {fy_id} introuvable")

        d = _date.fromisoformat(fy["start_date"]) - timedelta(days=1)
        as_of = d.isoformat()

        internals = conn.execute(
            "SELECT id, name FROM entities WHERE type = 'internal' ORDER BY position, id"
        ).fetchall()

        result = []
        for ent in internals:
            bal = compute_entity_balance(conn, ent["id"], as_of_date=as_of)
            result.append({
                "entity_id": ent["id"],
                "entity_name": ent["name"],
                "suggested_amount": round(bal["balance"], 2),
                "as_of_date": as_of,
            })
        return result
    finally:
        conn.close()


# ─── Budget allocations CRUD ─────────────────────────────────────────────────

class AllocationCreate(BaseModel):
    entity_id: int
    category_id: Optional[int] = None
    amount: float
    notes: str = ""


class AllocationUpdate(BaseModel):
    entity_id: Optional[int] = None
    category_id: Optional[int] = None
    amount: Optional[float] = None
    notes: Optional[str] = None


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
        fy = conn.execute("SELECT id FROM fiscal_years WHERE id = ?", (fy_id,)).fetchone()
        if fy is None:
            raise HTTPException(404, f"Exercice {fy_id} introuvable")
        ent = conn.execute("SELECT id FROM entities WHERE id = ?", (body.entity_id,)).fetchone()
        if ent is None:
            raise HTTPException(400, f"Entité {body.entity_id} introuvable")
        if body.category_id is not None:
            cat = conn.execute("SELECT id FROM categories WHERE id = ?", (body.category_id,)).fetchone()
            if cat is None:
                raise HTTPException(400, f"Catégorie {body.category_id} introuvable")

        # Check unique triplet at app layer (SQLite UNIQUE treats NULLs as distinct)
        if body.category_id is None:
            dup = conn.execute(
                """SELECT id FROM budget_allocations
                   WHERE fiscal_year_id = ? AND entity_id = ? AND category_id IS NULL""",
                (fy_id, body.entity_id),
            ).fetchone()
        else:
            dup = conn.execute(
                """SELECT id FROM budget_allocations
                   WHERE fiscal_year_id = ? AND entity_id = ? AND category_id = ?""",
                (fy_id, body.entity_id, body.category_id),
            ).fetchone()
        if dup is not None:
            raise HTTPException(409, "Une allocation existe déjà pour ce triplet")

        now = _now()
        cur = conn.execute(
            """INSERT INTO budget_allocations
               (fiscal_year_id, entity_id, category_id, amount, notes, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (fy_id, body.entity_id, body.category_id, body.amount, body.notes, now, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM budget_allocations WHERE id = ?", (cur.lastrowid,)).fetchone()
        return row_to_dict(row)
    finally:
        conn.close()


@router.put("/allocations/{alloc_id}")
def update_allocation(alloc_id: int, body: AllocationUpdate):
    conn = get_conn()
    try:
        existing = conn.execute("SELECT * FROM budget_allocations WHERE id = ?", (alloc_id,)).fetchone()
        if existing is None:
            raise HTTPException(404, f"Allocation {alloc_id} introuvable")
        updates = body.model_dump(exclude_unset=True)
        if not updates:
            return row_to_dict(existing)
        now = _now()
        set_clause = ", ".join(f"{k} = ?" for k in updates) + ", updated_at = ?"
        values = list(updates.values()) + [now, alloc_id]
        conn.execute(f"UPDATE budget_allocations SET {set_clause} WHERE id = ?", values)
        conn.commit()
        row = conn.execute("SELECT * FROM budget_allocations WHERE id = ?", (alloc_id,)).fetchone()
        return row_to_dict(row)
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


# ─── Composite view endpoint ─────────────────────────────────────────────────

from datetime import date as _date, timedelta as _timedelta


def _find_previous_fiscal_year(conn, current_start: str) -> Optional[int]:
    """Find the previous fiscal year: the one whose start_date is closest to
    (current_start - 1 year), within a ±31 day tolerance.
    """
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


@router.get("/view")
def get_budget_view(fiscal_year_id: int):
    conn = get_conn()
    try:
        fy = conn.execute("SELECT * FROM fiscal_years WHERE id = ?", (fiscal_year_id,)).fetchone()
        if fy is None:
            raise HTTPException(404, f"Exercice {fiscal_year_id} introuvable")

        prev_id = _find_previous_fiscal_year(conn, fy["start_date"])
        prev = None
        if prev_id is not None:
            prev = conn.execute("SELECT * FROM fiscal_years WHERE id = ?", (prev_id,)).fetchone()

        # Entities to report: all internal + any that have an allocation/opening in this FY
        entity_ids = {r["id"] for r in conn.execute(
            "SELECT id FROM entities WHERE type = 'internal'"
        ).fetchall()}
        for tbl in ("fiscal_year_opening_balances", "budget_allocations"):
            extras = conn.execute(
                f"SELECT DISTINCT entity_id FROM {tbl} WHERE fiscal_year_id = ?",
                (fiscal_year_id,),
            ).fetchall()
            entity_ids.update(r["entity_id"] for r in extras)

        result_entities = []
        total_allocated = 0.0
        total_realized = 0.0

        def _sum_realized(entity_id: int, start: str, end: str, category_id: Optional[int]):
            if category_id is None:
                row = conn.execute(
                    """SELECT COALESCE(SUM(CASE
                            WHEN to_entity_id = ? THEN amount
                            WHEN from_entity_id = ? AND amount < 0 THEN amount
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
                            WHEN from_entity_id = ? AND amount < 0 THEN amount
                            ELSE 0
                        END), 0) AS net
                       FROM transactions
                       WHERE date BETWEEN ? AND ?
                         AND (from_entity_id = ? OR to_entity_id = ?)
                         AND category_id = ?""",
                    (entity_id, entity_id, start, end, entity_id, entity_id, category_id),
                ).fetchone()
            return row["net"] if row else 0.0

        for eid in sorted(entity_ids):
            ent = conn.execute("SELECT id, name FROM entities WHERE id = ?", (eid,)).fetchone()
            if ent is None:
                continue

            ob = conn.execute(
                "SELECT amount FROM fiscal_year_opening_balances WHERE fiscal_year_id = ? AND entity_id = ?",
                (fiscal_year_id, eid),
            ).fetchone()
            opening = ob["amount"] if ob else 0.0

            allocs = conn.execute(
                """SELECT a.*, c.name AS category_name
                   FROM budget_allocations a
                   LEFT JOIN categories c ON a.category_id = c.id
                   WHERE a.fiscal_year_id = ? AND a.entity_id = ?""",
                (fiscal_year_id, eid),
            ).fetchall()

            allocated_global = sum(a["amount"] for a in allocs if a["category_id"] is None)
            allocated_detailed = sum(a["amount"] for a in allocs if a["category_id"] is not None)
            # Effective envelope = global if defined, else sum of category allocations.
            # When both exist, keep the global (it acts as the umbrella) but surface both for UI warnings.
            allocated_effective = allocated_global if allocated_global > 0 else allocated_detailed
            cats_out = []
            for a in allocs:
                if a["category_id"] is None:
                    continue
                realized = _sum_realized(eid, fy["start_date"], fy["end_date"], a["category_id"])
                realized_n1 = 0.0
                if prev:
                    realized_n1 = _sum_realized(eid, prev["start_date"], prev["end_date"], a["category_id"])
                pct_consumed = (
                    abs(realized) / a["amount"] * 100.0 if a["amount"] != 0 else 0.0
                )
                cats_out.append({
                    "category_id": a["category_id"],
                    "category_name": a["category_name"] or "— Catégorie supprimée —",
                    "allocation_id": a["id"],
                    "allocated": a["amount"],
                    "realized": realized,
                    "realized_n_minus_1": realized_n1,
                    "percent_consumed": round(pct_consumed, 1),
                })

            realized_total = _sum_realized(eid, fy["start_date"], fy["end_date"], None)
            realized_n1_total = 0.0
            if prev:
                realized_n1_total = _sum_realized(eid, prev["start_date"], prev["end_date"], None)

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
