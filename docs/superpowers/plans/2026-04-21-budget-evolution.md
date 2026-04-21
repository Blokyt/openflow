# Budget & Exercices — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the `budget` module so the BDA treasurer can define fiscal years with real bank opening balances, allocate budgets per entity × category, follow realized vs allocated live, and compare realized to the previous fiscal year.

**Architecture:** Three new SQL tables (`fiscal_years`, `fiscal_year_opening_balances`, `budget_allocations`) replacing the legacy `budgets` table. Balance calculation extended in `backend/core/balance.py` (new `compute_entity_balance_for_period`). Refounded `/budget` page with 3 tabs + fiscal year wizard. Dashboard widget + sidebar badge. Fiscal year state threaded through a new React context.

**Tech Stack:** Python 3.11 + FastAPI + sqlite3 (no SQLAlchemy), React 18 + TypeScript + Vite + Tailwind. TDD on backend, build-passes + manual Firefox-MCP validation on frontend.

**Spec:** `docs/superpowers/specs/2026-04-21-budget-evolution-design.md`

---

## File Structure

**Backend (modified):**
- `backend/modules/budget/models.py` — migration 1.2.0: drop `budgets`, create 3 new tables
- `backend/modules/budget/manifest.json` — version 1.2.0, updated name/help/widgets
- `backend/modules/budget/api.py` — full rewrite: 6 endpoint groups
- `backend/core/balance.py` — add `compute_entity_balance_for_period()`
- `backend/modules/entities/api.py` — extend DELETE handler to cascade-delete opening balances + allocations

**Backend (new):**
- `tests/backend/test_budget.py` — module-level tests
- `tests/backend/test_coherence_budget.py` — cross-module consistency tests

**Frontend (modified):**
- `frontend/src/modules/budget/BudgetManager.tsx` — full rewrite as shell with tabs
- `frontend/src/core/Sidebar.tsx` — badge when overspending on current year
- `frontend/src/modules/entities/EntityTree.tsx` — swap "Solde de référence" for "Solde d'ouverture (exercice N)"

**Frontend (new):**
- `frontend/src/core/FiscalYearContext.tsx` — shared state for the active fiscal year
- `frontend/src/modules/budget/tabs/OverviewTab.tsx` — tab 1 (read-only view with N-1)
- `frontend/src/modules/budget/tabs/AllocationTab.tsx` — tab 2 (editable allocations)
- `frontend/src/modules/budget/tabs/FiscalYearsTab.tsx` — tab 3 (list + wizard trigger)
- `frontend/src/modules/budget/FiscalYearWizard.tsx` — 3-step modal
- `frontend/src/modules/budget/widgets/BudgetOverview.tsx` — dashboard widget

---

## Task 1 — Migration 1.2.0: new tables, drop legacy

**Files:**
- Modify: `backend/modules/budget/models.py`
- Modify: `backend/modules/budget/manifest.json`
- Test: `tests/backend/test_budget.py`

- [ ] **Step 1.1: Write the failing test for the migration**

Create `tests/backend/test_budget.py` with:

```python
"""Tests for the Budget & Exercices module (1.2.0)."""
import os, sys
import sqlite3
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


def test_budget_tables_exist(client_and_db):
    """After migration 1.2.0, the three new tables exist and legacy `budgets` is gone."""
    _, db_path = client_and_db
    conn = sqlite3.connect(str(db_path))
    try:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
    finally:
        conn.close()
    assert "fiscal_years" in tables
    assert "fiscal_year_opening_balances" in tables
    assert "budget_allocations" in tables
    assert "budgets" not in tables  # legacy dropped
```

- [ ] **Step 1.2: Run test to verify it fails**

```
cd openflow
python -m pytest tests/backend/test_budget.py::test_budget_tables_exist -v
```

Expected: FAIL (tables don't exist or `budgets` still exists).

- [ ] **Step 1.3: Add migration 1.2.0 in models.py**

Replace the entire content of `backend/modules/budget/models.py` with:

```python
migrations = {
    "1.0.0": [
        """CREATE TABLE budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER,
            division_id INTEGER,
            period_start TEXT NOT NULL,
            period_end TEXT NOT NULL,
            amount REAL NOT NULL,
            label TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY (category_id) REFERENCES categories(id),
            FOREIGN KEY (division_id) REFERENCES divisions(id)
        )""",
    ],
    "1.1.0": [
        "ALTER TABLE budgets ADD COLUMN entity_id INTEGER",
    ],
    "1.2.0": [
        # Legacy `budgets` table is empty in every known install — drop it.
        "DROP TABLE IF EXISTS budgets",
        """CREATE TABLE fiscal_years (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            is_current INTEGER NOT NULL DEFAULT 0,
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""",
        """CREATE TABLE fiscal_year_opening_balances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fiscal_year_id INTEGER NOT NULL,
            entity_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            source TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (fiscal_year_id, entity_id)
        )""",
        """CREATE TABLE budget_allocations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fiscal_year_id INTEGER NOT NULL,
            entity_id INTEGER NOT NULL,
            category_id INTEGER,
            amount REAL NOT NULL,
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (fiscal_year_id, entity_id, category_id)
        )""",
    ],
}
```

- [ ] **Step 1.4: Bump manifest version to 1.2.0**

In `backend/modules/budget/manifest.json`, set `"version": "1.2.0"` and update name/help/example/dashboard_widgets:

```json
{
  "id": "budget",
  "name": "Budget & Exercices",
  "description": "Allocations budgétaires par entité et catégorie, suivi du réalisé et comparaison inter-exercices",
  "help": "Définis des exercices budgétaires (ex: année universitaire), alloue un budget par pôle/club et par catégorie, suis le réalisé en temps réel et compare à l'exercice précédent.",
  "version": "1.2.0",
  "origin": "builtin",
  "category": "standard",
  "dependencies": ["entities", "categories", "transactions"],
  "menu": { "label": "Budget", "icon": "piggy-bank", "position": 15 },
  "api_routes": ["api.py"],
  "db_models": ["models.py"],
  "dashboard_widgets": [
    {
      "id": "budget_overview",
      "name": "Budget en cours",
      "component": "widgets/BudgetOverview.tsx",
      "default_visible": true,
      "size": "half"
    }
  ],
  "settings_schema": {},
  "example": "Je définis l'exercice 2025-2026 (sept→août), j'alloue 2 000 € à Gastronomine dont 1 500 € Nourriture, et je vois en temps réel que 40 % a été consommé vs 55 % l'an dernier à la même date."
}
```

- [ ] **Step 1.5: Run test to verify it passes**

```
python tools/check.py
python -m pytest tests/backend/test_budget.py::test_budget_tables_exist -v
```

Expected: check PASS, test PASS.

- [ ] **Step 1.6: Commit**

```bash
git add backend/modules/budget/models.py backend/modules/budget/manifest.json tests/backend/test_budget.py
git commit -m "feat(budget): migration 1.2.0 - fiscal_years + opening_balances + allocations tables"
```

---

## Task 2 — Core balance: compute_entity_balance_for_period

**Files:**
- Modify: `backend/core/balance.py`
- Test: `tests/backend/test_budget.py`

- [ ] **Step 2.1: Write the failing test**

Add to `tests/backend/test_budget.py`:

```python
def test_compute_entity_balance_for_period_basic(client_and_db):
    """Balance for an entity over a period = opening + net signed flow in [start, end]."""
    client, db_path = client_and_db
    from backend.core.balance import compute_entity_balance_for_period

    src = client.post("/api/entities/", json={"name": "Src", "type": "external"}).json()
    dst = client.post("/api/entities/", json={"name": "Dst", "type": "internal"}).json()

    # 3 tx: one before period, one inside, one after
    for date, amount in [("2025-05-15", 100.0), ("2025-09-15", 200.0), ("2025-11-15", 300.0)]:
        client.post("/api/transactions/", json={
            "date": date, "label": "tx", "amount": amount,
            "from_entity_id": src["id"], "to_entity_id": dst["id"],
        })

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        # Period = all of September
        result = compute_entity_balance_for_period(conn, dst["id"], "2025-09-01", "2025-09-30", opening=500.0)
        assert result["opening"] == 500.0
        assert result["realized"] == 200.0  # only the September tx
        assert result["closing"] == 700.0
    finally:
        conn.close()


def test_compute_entity_balance_for_period_expense(client_and_db):
    """Expense (from=entity, amount<0) counts negatively in realized."""
    client, db_path = client_and_db
    from backend.core.balance import compute_entity_balance_for_period

    ext = client.post("/api/entities/", json={"name": "Ext", "type": "external"}).json()
    me = client.post("/api/entities/", json={"name": "Me", "type": "internal"}).json()

    client.post("/api/transactions/", json={
        "date": "2025-09-10", "label": "buy", "amount": -50.0,
        "from_entity_id": me["id"], "to_entity_id": ext["id"],
    })

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        result = compute_entity_balance_for_period(conn, me["id"], "2025-09-01", "2025-09-30", opening=1000.0)
        assert result["realized"] == -50.0
        assert result["closing"] == 950.0
    finally:
        conn.close()
```

- [ ] **Step 2.2: Run tests to verify they fail**

```
python -m pytest tests/backend/test_budget.py::test_compute_entity_balance_for_period_basic tests/backend/test_budget.py::test_compute_entity_balance_for_period_expense -v
```

Expected: FAIL with `ImportError: cannot import name 'compute_entity_balance_for_period'`.

- [ ] **Step 2.3: Add the function to balance.py**

Append to `backend/core/balance.py`:

```python
def compute_entity_balance_for_period(
    conn: sqlite3.Connection,
    entity_id: int,
    start_date: str,
    end_date: str,
    opening: float = 0.0,
) -> dict:
    """Realized flow and closing balance for an entity on a date interval.

    Uses the same sign convention as compute_entity_balance:
        net = SUM(amount when to_entity=entity) + SUM(amount when from_entity=entity AND amount<0)

    Returns {opening, realized, closing}.
    """
    row = conn.execute(
        """SELECT COALESCE(SUM(CASE
                WHEN to_entity_id = ? THEN amount
                WHEN from_entity_id = ? AND amount < 0 THEN amount
                ELSE 0
            END), 0) AS realized
           FROM transactions
           WHERE date BETWEEN ? AND ?
             AND (from_entity_id = ? OR to_entity_id = ?)""",
        (entity_id, entity_id, start_date, end_date, entity_id, entity_id),
    ).fetchone()
    realized = row[0] if not hasattr(row, "keys") else row["realized"]
    return {
        "opening": opening,
        "realized": realized,
        "closing": opening + realized,
    }
```

- [ ] **Step 2.4: Run tests to verify they pass**

```
python -m pytest tests/backend/test_budget.py::test_compute_entity_balance_for_period_basic tests/backend/test_budget.py::test_compute_entity_balance_for_period_expense -v
```

Expected: 2 PASS.

- [ ] **Step 2.5: Commit**

```bash
git add backend/core/balance.py tests/backend/test_budget.py
git commit -m "feat(balance): compute_entity_balance_for_period for budget views"
```

---

## Task 3 — API: fiscal_years CRUD

**Files:**
- Modify: `backend/modules/budget/api.py`
- Test: `tests/backend/test_budget.py`

- [ ] **Step 3.1: Write failing tests for fiscal_years CRUD**

Add to `tests/backend/test_budget.py`:

```python
def test_fiscal_year_crud(client):
    # Empty
    r = client.get("/api/budget/fiscal-years")
    assert r.status_code == 200 and r.json() == []

    # Create
    r = client.post("/api/budget/fiscal-years", json={
        "name": "2025-2026", "start_date": "2025-09-01", "end_date": "2026-08-31",
        "is_current": True, "notes": "rentrée",
    })
    assert r.status_code == 201
    fy = r.json()
    assert fy["name"] == "2025-2026"
    assert fy["is_current"] == 1

    # Update
    r = client.put(f"/api/budget/fiscal-years/{fy['id']}", json={"notes": "rentrée universitaire"})
    assert r.status_code == 200
    assert r.json()["notes"] == "rentrée universitaire"

    # List (1 entry)
    r = client.get("/api/budget/fiscal-years")
    assert len(r.json()) == 1

    # Delete
    r = client.delete(f"/api/budget/fiscal-years/{fy['id']}")
    assert r.status_code == 200

    r = client.get("/api/budget/fiscal-years")
    assert r.json() == []


def test_fiscal_year_is_current_unique(client):
    a = client.post("/api/budget/fiscal-years", json={
        "name": "2024-2025", "start_date": "2024-09-01", "end_date": "2025-08-31",
        "is_current": True,
    }).json()
    b = client.post("/api/budget/fiscal-years", json={
        "name": "2025-2026", "start_date": "2025-09-01", "end_date": "2026-08-31",
        "is_current": True,
    }).json()

    rows = client.get("/api/budget/fiscal-years").json()
    currents = [r for r in rows if r["is_current"] == 1]
    assert len(currents) == 1
    assert currents[0]["id"] == b["id"]


def test_fiscal_year_current_endpoint(client):
    assert client.get("/api/budget/fiscal-years/current").status_code == 404
    client.post("/api/budget/fiscal-years", json={
        "name": "2025-2026", "start_date": "2025-09-01", "end_date": "2026-08-31",
        "is_current": True,
    })
    r = client.get("/api/budget/fiscal-years/current")
    assert r.status_code == 200
    assert r.json()["name"] == "2025-2026"


def test_fiscal_year_name_unique(client):
    client.post("/api/budget/fiscal-years", json={
        "name": "2025-2026", "start_date": "2025-09-01", "end_date": "2026-08-31",
    })
    r = client.post("/api/budget/fiscal-years", json={
        "name": "2025-2026", "start_date": "2025-09-01", "end_date": "2026-08-31",
    })
    assert r.status_code in (400, 409)


def test_fiscal_year_dates_validated(client):
    r = client.post("/api/budget/fiscal-years", json={
        "name": "broken", "start_date": "2026-09-01", "end_date": "2025-08-31",
    })
    assert r.status_code == 400
```

- [ ] **Step 3.2: Run tests to verify they fail**

```
python -m pytest tests/backend/test_budget.py::test_fiscal_year_crud -v
```

Expected: FAIL (endpoints don't exist, probably 404).

- [ ] **Step 3.3: Rewrite budget/api.py with fiscal_years endpoints**

Replace entire `backend/modules/budget/api.py` with:

```python
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
```

- [ ] **Step 3.4: Run tests to verify they pass**

```
python -m pytest tests/backend/test_budget.py -v -k fiscal_year
```

Expected: 5 PASS.

- [ ] **Step 3.5: Commit**

```bash
git add backend/modules/budget/api.py tests/backend/test_budget.py
git commit -m "feat(budget): fiscal_years CRUD endpoints with uniqueness + current flag"
```

---

## Task 4 — API: opening_balances (upsert + suggested)

**Files:**
- Modify: `backend/modules/budget/api.py`
- Test: `tests/backend/test_budget.py`

- [ ] **Step 4.1: Write failing tests**

Add to `tests/backend/test_budget.py`:

```python
def test_opening_balance_upsert(client):
    fy = client.post("/api/budget/fiscal-years", json={
        "name": "2025-2026", "start_date": "2025-09-01", "end_date": "2026-08-31",
    }).json()
    e1 = client.post("/api/entities/", json={"name": "Club1", "type": "internal"}).json()
    e2 = client.post("/api/entities/", json={"name": "Club2", "type": "internal"}).json()

    # Upsert two rows
    r = client.put(f"/api/budget/fiscal-years/{fy['id']}/opening-balances", json=[
        {"entity_id": e1["id"], "amount": 1000.0, "source": "CE IDF"},
        {"entity_id": e2["id"], "amount": 500.0, "source": ""},
    ])
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    assert sum(o["amount"] for o in data) == 1500.0

    # Re-upsert with an updated value (replaces)
    r = client.put(f"/api/budget/fiscal-years/{fy['id']}/opening-balances", json=[
        {"entity_id": e1["id"], "amount": 1200.0, "source": "CE IDF au 31/08"},
    ])
    assert r.status_code == 200
    ob = client.get(f"/api/budget/fiscal-years/{fy['id']}/opening-balances").json()
    assert len(ob) == 1  # e2 removed
    assert ob[0]["amount"] == 1200.0


def test_opening_balance_rejects_external_entity(client):
    fy = client.post("/api/budget/fiscal-years", json={
        "name": "2025-2026", "start_date": "2025-09-01", "end_date": "2026-08-31",
    }).json()
    ext = client.post("/api/entities/", json={"name": "Bank", "type": "external"}).json()

    r = client.put(f"/api/budget/fiscal-years/{fy['id']}/opening-balances", json=[
        {"entity_id": ext["id"], "amount": 1000.0},
    ])
    assert r.status_code == 400


def test_suggested_opening(client):
    # Internal entity with some history
    ext = client.post("/api/entities/", json={"name": "Ext", "type": "external"}).json()
    me = client.post("/api/entities/", json={"name": "Me", "type": "internal"}).json()
    # Adjust its reference so we have a known baseline
    client.put(f"/api/entities/{me['id']}/balance-ref", json={
        "reference_date": "2025-01-01", "reference_amount": 1000.0,
    })
    # One tx before the fiscal year start
    client.post("/api/transactions/", json={
        "date": "2025-06-15", "label": "paid", "amount": 200.0,
        "from_entity_id": ext["id"], "to_entity_id": me["id"],
    })

    fy = client.post("/api/budget/fiscal-years", json={
        "name": "2025-2026", "start_date": "2025-09-01", "end_date": "2026-08-31",
    }).json()

    r = client.get(f"/api/budget/fiscal-years/{fy['id']}/suggested-opening")
    assert r.status_code == 200
    data = r.json()
    me_row = next(x for x in data if x["entity_id"] == me["id"])
    assert me_row["suggested_amount"] == 1200.0  # 1000 ref + 200 flow
```

- [ ] **Step 4.2: Run tests to verify they fail**

```
python -m pytest tests/backend/test_budget.py -v -k opening
```

Expected: FAIL with 404 on missing endpoints.

- [ ] **Step 4.3: Add opening balance endpoints to api.py**

Append to `backend/modules/budget/api.py`:

```python
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
```

- [ ] **Step 4.4: Run tests to verify they pass**

```
python -m pytest tests/backend/test_budget.py -v -k opening
```

Expected: 3 PASS.

- [ ] **Step 4.5: Commit**

```bash
git add backend/modules/budget/api.py tests/backend/test_budget.py
git commit -m "feat(budget): opening balances upsert + suggested endpoint"
```

---

## Task 5 — API: budget_allocations CRUD

**Files:**
- Modify: `backend/modules/budget/api.py`
- Test: `tests/backend/test_budget.py`

- [ ] **Step 5.1: Write failing tests**

Add to `tests/backend/test_budget.py`:

```python
def test_allocation_crud(client):
    fy = client.post("/api/budget/fiscal-years", json={
        "name": "2025-2026", "start_date": "2025-09-01", "end_date": "2026-08-31",
    }).json()
    e = client.post("/api/entities/", json={"name": "Club", "type": "internal"}).json()
    c = client.post("/api/categories/", json={"name": "Food"}).json()

    # Create global (no category)
    r = client.post(f"/api/budget/fiscal-years/{fy['id']}/allocations", json={
        "entity_id": e["id"], "amount": 2000.0, "notes": "enveloppe globale",
    })
    assert r.status_code == 201
    global_alloc = r.json()
    assert global_alloc["category_id"] is None

    # Create categorized
    r = client.post(f"/api/budget/fiscal-years/{fy['id']}/allocations", json={
        "entity_id": e["id"], "category_id": c["id"], "amount": 1500.0,
    })
    assert r.status_code == 201

    # List
    rows = client.get(f"/api/budget/fiscal-years/{fy['id']}/allocations").json()
    assert len(rows) == 2

    # Update
    r = client.put(f"/api/budget/allocations/{global_alloc['id']}", json={"amount": 2500.0})
    assert r.status_code == 200
    assert r.json()["amount"] == 2500.0

    # Delete
    r = client.delete(f"/api/budget/allocations/{global_alloc['id']}")
    assert r.status_code == 200
    rows = client.get(f"/api/budget/fiscal-years/{fy['id']}/allocations").json()
    assert len(rows) == 1


def test_allocation_unique_triplet(client):
    fy = client.post("/api/budget/fiscal-years", json={
        "name": "2025-2026", "start_date": "2025-09-01", "end_date": "2026-08-31",
    }).json()
    e = client.post("/api/entities/", json={"name": "Club", "type": "internal"}).json()
    c = client.post("/api/categories/", json={"name": "Food"}).json()

    client.post(f"/api/budget/fiscal-years/{fy['id']}/allocations", json={
        "entity_id": e["id"], "category_id": c["id"], "amount": 100.0,
    })
    r = client.post(f"/api/budget/fiscal-years/{fy['id']}/allocations", json={
        "entity_id": e["id"], "category_id": c["id"], "amount": 200.0,
    })
    assert r.status_code in (400, 409)
```

- [ ] **Step 5.2: Run tests to verify they fail**

```
python -m pytest tests/backend/test_budget.py -v -k allocation
```

Expected: FAIL.

- [ ] **Step 5.3: Add allocation endpoints to api.py**

Append to `backend/modules/budget/api.py`:

```python
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

        # Check unique triplet (SQL UNIQUE handles NULL quirkly — do it at the app layer too)
        dup = conn.execute(
            """SELECT id FROM budget_allocations
               WHERE fiscal_year_id = ? AND entity_id = ?
                 AND (category_id IS ? OR category_id = ?)""",
            (fy_id, body.entity_id, body.category_id, body.category_id),
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
```

- [ ] **Step 5.4: Run tests to verify they pass**

```
python -m pytest tests/backend/test_budget.py -v -k allocation
```

Expected: 2 PASS.

- [ ] **Step 5.5: Commit**

```bash
git add backend/modules/budget/api.py tests/backend/test_budget.py
git commit -m "feat(budget): allocations CRUD with unique triplet constraint"
```

---

## Task 6 — API: composite view endpoint with N-1 comparison

**Files:**
- Modify: `backend/modules/budget/api.py`
- Test: `tests/backend/test_budget.py`

- [ ] **Step 6.1: Write failing test for the view endpoint**

Add to `tests/backend/test_budget.py`:

```python
def test_view_realized_and_categories(client):
    fy = client.post("/api/budget/fiscal-years", json={
        "name": "2025-2026", "start_date": "2025-09-01", "end_date": "2026-08-31",
        "is_current": True,
    }).json()
    e = client.post("/api/entities/", json={"name": "Club", "type": "internal"}).json()
    ext = client.post("/api/entities/", json={"name": "Ext", "type": "external"}).json()
    cat = client.post("/api/categories/", json={"name": "Food"}).json()

    client.put(f"/api/budget/fiscal-years/{fy['id']}/opening-balances", json=[
        {"entity_id": e["id"], "amount": 1000.0},
    ])
    client.post(f"/api/budget/fiscal-years/{fy['id']}/allocations", json={
        "entity_id": e["id"], "amount": 500.0,  # global
    })
    client.post(f"/api/budget/fiscal-years/{fy['id']}/allocations", json={
        "entity_id": e["id"], "category_id": cat["id"], "amount": 300.0,
    })
    # Two tx inside the year (one categorized, one not)
    client.post("/api/transactions/", json={
        "date": "2025-10-15", "label": "buy food", "amount": -120.0,
        "from_entity_id": e["id"], "to_entity_id": ext["id"],
        "category_id": cat["id"],
    })
    client.post("/api/transactions/", json={
        "date": "2025-11-05", "label": "cash in", "amount": 50.0,
        "from_entity_id": ext["id"], "to_entity_id": e["id"],
    })
    # tx outside the year (ignored)
    client.post("/api/transactions/", json={
        "date": "2024-08-15", "label": "old", "amount": -200.0,
        "from_entity_id": e["id"], "to_entity_id": ext["id"],
    })

    r = client.get(f"/api/budget/view?fiscal_year_id={fy['id']}")
    assert r.status_code == 200
    data = r.json()
    assert data["fiscal_year"]["id"] == fy["id"]
    assert data["previous_fiscal_year_id"] is None  # no N-1
    club = next(x for x in data["entities"] if x["entity_id"] == e["id"])
    assert club["opening_balance"] == 1000.0
    assert club["allocated_total"] == 500.0
    # realized = -120 + 50 = -70
    assert round(club["realized_total"], 2) == -70.0
    # Category breakdown
    food = next(c for c in club["categories"] if c["category_id"] == cat["id"])
    assert food["allocated"] == 300.0
    assert round(food["realized"], 2) == -120.0


def test_view_with_previous_year(client):
    """With a prior fiscal year, realized_n_minus_1 is populated."""
    # N-1
    fy_prev = client.post("/api/budget/fiscal-years", json={
        "name": "2024-2025", "start_date": "2024-09-01", "end_date": "2025-08-31",
    }).json()
    fy = client.post("/api/budget/fiscal-years", json={
        "name": "2025-2026", "start_date": "2025-09-01", "end_date": "2026-08-31",
    }).json()
    e = client.post("/api/entities/", json={"name": "Club", "type": "internal"}).json()
    ext = client.post("/api/entities/", json={"name": "Ext", "type": "external"}).json()

    client.post("/api/transactions/", json={
        "date": "2024-10-15", "label": "prev year buy", "amount": -100.0,
        "from_entity_id": e["id"], "to_entity_id": ext["id"],
    })
    client.post("/api/transactions/", json={
        "date": "2025-10-15", "label": "this year buy", "amount": -140.0,
        "from_entity_id": e["id"], "to_entity_id": ext["id"],
    })

    data = client.get(f"/api/budget/view?fiscal_year_id={fy['id']}").json()
    assert data["previous_fiscal_year_id"] == fy_prev["id"]
    club = next(x for x in data["entities"] if x["entity_id"] == e["id"])
    assert round(club["realized_total"], 2) == -140.0
    assert round(club["realized_n_minus_1"], 2) == -100.0


def test_view_no_fiscal_year(client):
    r = client.get("/api/budget/view?fiscal_year_id=999")
    assert r.status_code == 404
```

- [ ] **Step 6.2: Run tests to verify they fail**

```
python -m pytest tests/backend/test_budget.py -v -k view
```

Expected: FAIL (endpoint missing).

- [ ] **Step 6.3: Add the view endpoint**

Append to `backend/modules/budget/api.py`:

```python
from datetime import date as _date, timedelta

def _find_previous_fiscal_year(conn, current_start: str) -> Optional[int]:
    """Find the previous fiscal year: the one whose start_date is closest to
    (current_start - 1 year), within a ±31 day tolerance.
    """
    d = _date.fromisoformat(current_start)
    target = _date(d.year - 1, d.month, d.day).isoformat()
    window_low = (_date.fromisoformat(target) - timedelta(days=31)).isoformat()
    window_high = (_date.fromisoformat(target) + timedelta(days=31)).isoformat()
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
                "allocated_total": allocated_global,
                "realized_total": realized_total,
                "realized_n_minus_1": realized_n1_total,
                "variation_pct": (
                    round((realized_total - realized_n1_total) / abs(realized_n1_total) * 100.0, 1)
                    if realized_n1_total != 0 else None
                ),
                "categories": cats_out,
            })
            total_allocated += allocated_global
            total_realized += realized_total

        return {
            "fiscal_year": row_to_dict(fy),
            "previous_fiscal_year_id": prev["id"] if prev else None,
            "entities": result_entities,
            "totals": {
                "allocated": total_allocated,
                "realized": total_realized,
                "remaining": total_allocated - abs(total_realized),
            },
        }
    finally:
        conn.close()
```

- [ ] **Step 6.4: Run tests to verify they pass**

```
python -m pytest tests/backend/test_budget.py -v -k view
```

Expected: 3 PASS.

- [ ] **Step 6.5: Commit**

```bash
git add backend/modules/budget/api.py tests/backend/test_budget.py
git commit -m "feat(budget): /view composite endpoint with N-1 comparison"
```

---

## Task 7 — Entity delete: cascade applicative

**Files:**
- Modify: `backend/modules/entities/api.py`
- Test: `tests/backend/test_budget.py`

- [ ] **Step 7.1: Write failing test**

Add to `tests/backend/test_budget.py`:

```python
def test_entity_delete_cascades_budget(client):
    fy = client.post("/api/budget/fiscal-years", json={
        "name": "2025-2026", "start_date": "2025-09-01", "end_date": "2026-08-31",
    }).json()
    e = client.post("/api/entities/", json={"name": "Doomed", "type": "internal"}).json()
    client.put(f"/api/budget/fiscal-years/{fy['id']}/opening-balances", json=[
        {"entity_id": e["id"], "amount": 100.0},
    ])
    client.post(f"/api/budget/fiscal-years/{fy['id']}/allocations", json={
        "entity_id": e["id"], "amount": 50.0,
    })

    # Precondition
    assert len(client.get(f"/api/budget/fiscal-years/{fy['id']}/opening-balances").json()) == 1
    assert len(client.get(f"/api/budget/fiscal-years/{fy['id']}/allocations").json()) == 1

    r = client.delete(f"/api/entities/{e['id']}")
    assert r.status_code == 200

    # Cascade removed the budget rows
    assert len(client.get(f"/api/budget/fiscal-years/{fy['id']}/opening-balances").json()) == 0
    assert len(client.get(f"/api/budget/fiscal-years/{fy['id']}/allocations").json()) == 0
```

- [ ] **Step 7.2: Run test to verify it fails**

```
python -m pytest tests/backend/test_budget.py::test_entity_delete_cascades_budget -v
```

Expected: FAIL (orphan rows remain).

- [ ] **Step 7.3: Extend the DELETE entity handler**

Open `backend/modules/entities/api.py`, find the DELETE handler (it already deletes `entity_balance_refs`). Add two more deletes right before removing the entity itself. Look for the block around line 195-200 that starts with `conn.execute("DELETE FROM entity_balance_refs WHERE entity_id = ?", (entity_id,))` and add, immediately after it:

```python
        # Cascade to budget module (PRAGMA foreign_keys OFF)
        conn.execute("DELETE FROM fiscal_year_opening_balances WHERE entity_id = ?", (entity_id,))
        conn.execute("DELETE FROM budget_allocations WHERE entity_id = ?", (entity_id,))
```

- [ ] **Step 7.4: Run test to verify it passes**

```
python -m pytest tests/backend/test_budget.py::test_entity_delete_cascades_budget -v
```

Expected: PASS.

- [ ] **Step 7.5: Commit**

```bash
git add backend/modules/entities/api.py tests/backend/test_budget.py
git commit -m "feat(entities): cascade delete to budget opening_balances + allocations"
```

---

## Task 8 — Cross-module coherence tests

**Files:**
- Test: `tests/backend/test_coherence_budget.py`

- [ ] **Step 8.1: Create the coherence test file**

Create `tests/backend/test_coherence_budget.py`:

```python
"""Cross-module coherence: budget view ↔ balance calculation ↔ transactions."""
import os, sys
import sqlite3
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


def test_budget_view_matches_entity_balance_for_period(client_and_db):
    """opening + realized_total from /view == compute_entity_balance_for_period closing."""
    client, db_path = client_and_db
    from backend.core.balance import compute_entity_balance_for_period

    fy = client.post("/api/budget/fiscal-years", json={
        "name": "2025-2026", "start_date": "2025-09-01", "end_date": "2026-08-31",
        "is_current": True,
    }).json()
    e = client.post("/api/entities/", json={"name": "Club", "type": "internal"}).json()
    ext = client.post("/api/entities/", json={"name": "Ext", "type": "external"}).json()

    client.put(f"/api/budget/fiscal-years/{fy['id']}/opening-balances", json=[
        {"entity_id": e["id"], "amount": 2000.0},
    ])
    client.post("/api/transactions/", json={
        "date": "2025-10-01", "label": "x", "amount": -150.0,
        "from_entity_id": e["id"], "to_entity_id": ext["id"],
    })
    client.post("/api/transactions/", json={
        "date": "2026-02-01", "label": "y", "amount": 75.0,
        "from_entity_id": ext["id"], "to_entity_id": e["id"],
    })

    view = client.get(f"/api/budget/view?fiscal_year_id={fy['id']}").json()
    club = next(x for x in view["entities"] if x["entity_id"] == e["id"])

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        direct = compute_entity_balance_for_period(conn, e["id"], "2025-09-01", "2026-08-31", opening=2000.0)
    finally:
        conn.close()

    assert round(club["opening_balance"] + club["realized_total"], 2) == round(direct["closing"], 2)


def test_view_ignores_transactions_outside_period(client):
    fy = client.post("/api/budget/fiscal-years", json={
        "name": "2025-2026", "start_date": "2025-09-01", "end_date": "2026-08-31",
    }).json()
    e = client.post("/api/entities/", json={"name": "Club", "type": "internal"}).json()
    ext = client.post("/api/entities/", json={"name": "Ext", "type": "external"}).json()

    # Before period
    client.post("/api/transactions/", json={
        "date": "2025-06-15", "label": "pre", "amount": 1000.0,
        "from_entity_id": ext["id"], "to_entity_id": e["id"],
    })
    # After period
    client.post("/api/transactions/", json={
        "date": "2026-10-15", "label": "post", "amount": 1000.0,
        "from_entity_id": ext["id"], "to_entity_id": e["id"],
    })

    view = client.get(f"/api/budget/view?fiscal_year_id={fy['id']}").json()
    club = next(x for x in view["entities"] if x["entity_id"] == e["id"])
    assert club["realized_total"] == 0.0
```

- [ ] **Step 8.2: Run tests**

```
python -m pytest tests/backend/test_coherence_budget.py -v
```

Expected: 2 PASS.

- [ ] **Step 8.3: Run full backend suite to confirm no regression**

```
python tools/check.py
python -m pytest tests/backend/ -q
```

Expected: check PASS, all tests pass (~300+).

- [ ] **Step 8.4: Commit**

```bash
git add tests/backend/test_coherence_budget.py
git commit -m "test(budget): cross-module coherence with balance core and tx filters"
```

---

## Task 9 — Frontend: FiscalYearContext

**Files:**
- Create: `frontend/src/core/FiscalYearContext.tsx`

- [ ] **Step 9.1: Create the context file**

Create `frontend/src/core/FiscalYearContext.tsx`:

```tsx
import { createContext, useContext, useEffect, useState, ReactNode, useCallback } from "react";

export interface FiscalYear {
  id: number;
  name: string;
  start_date: string;
  end_date: string;
  is_current: number;
  notes: string;
}

interface FiscalYearContextType {
  years: FiscalYear[];
  currentYear: FiscalYear | null;
  selectedYear: FiscalYear | null;
  setSelectedYearId: (id: number | null) => void;
  reload: () => Promise<void>;
}

const FiscalYearContext = createContext<FiscalYearContextType>({
  years: [],
  currentYear: null,
  selectedYear: null,
  setSelectedYearId: () => {},
  reload: async () => {},
});

export function useFiscalYear() {
  return useContext(FiscalYearContext);
}

export function FiscalYearProvider({ children }: { children: ReactNode }) {
  const [years, setYears] = useState<FiscalYear[]>([]);
  const [selectedYearId, setSelectedYearIdState] = useState<number | null>(() => {
    const stored = localStorage.getItem("openflow_fiscal_year_id");
    return stored ? parseInt(stored, 10) : null;
  });

  const reload = useCallback(async () => {
    try {
      const r = await fetch("/api/budget/fiscal-years");
      if (!r.ok) {
        setYears([]);
        return;
      }
      const data: FiscalYear[] = await r.json();
      setYears(data);
    } catch {
      setYears([]);
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const setSelectedYearId = useCallback((id: number | null) => {
    setSelectedYearIdState(id);
    if (id === null) localStorage.removeItem("openflow_fiscal_year_id");
    else localStorage.setItem("openflow_fiscal_year_id", String(id));
  }, []);

  const currentYear = years.find((y) => y.is_current === 1) ?? null;
  const selectedYear =
    (selectedYearId ? years.find((y) => y.id === selectedYearId) : null) ?? currentYear;

  return (
    <FiscalYearContext.Provider
      value={{ years, currentYear, selectedYear, setSelectedYearId, reload }}
    >
      {children}
    </FiscalYearContext.Provider>
  );
}
```

- [ ] **Step 9.2: Wrap the app tree with the provider**

Edit `frontend/src/App.tsx`, find `<EntityProvider>` opening and closing tags, wrap them inside a `<FiscalYearProvider>`. Replace the block:

```tsx
      <EntityProvider>
```

With:

```tsx
      <FiscalYearProvider>
        <EntityProvider>
```

And closing:

```tsx
        </EntityProvider>
      </FiscalYearProvider>
```

Add the import at the top:

```tsx
import { FiscalYearProvider } from "./core/FiscalYearContext";
```

- [ ] **Step 9.3: Verify frontend still builds**

```
cd frontend && npm run build
```

Expected: build passes without TypeScript errors.

- [ ] **Step 9.4: Commit**

```bash
git add frontend/src/core/FiscalYearContext.tsx frontend/src/App.tsx
git commit -m "feat(frontend): FiscalYearContext provider wired into App shell"
```

---

## Task 10 — Frontend API client: budget endpoints

**Files:**
- Modify: `frontend/src/api.ts`

- [ ] **Step 10.1: Add budget helpers to api.ts**

Edit `frontend/src/api.ts`, locate the `api` object literal (look for `getEntities`). Add the following block inside the same object:

```ts
  // Budget & Exercices
  listFiscalYears: () => request<any[]>("/budget/fiscal-years"),
  getCurrentFiscalYear: () => request<any>("/budget/fiscal-years/current"),
  createFiscalYear: (fy: any) =>
    request<any>("/budget/fiscal-years", { method: "POST", body: JSON.stringify(fy) }),
  updateFiscalYear: (id: number, fy: any) =>
    request<any>(`/budget/fiscal-years/${id}`, { method: "PUT", body: JSON.stringify(fy) }),
  deleteFiscalYear: (id: number) =>
    request<any>(`/budget/fiscal-years/${id}`, { method: "DELETE" }),
  listOpeningBalances: (id: number) =>
    request<any[]>(`/budget/fiscal-years/${id}/opening-balances`),
  upsertOpeningBalances: (id: number, entries: any[]) =>
    request<any[]>(`/budget/fiscal-years/${id}/opening-balances`, {
      method: "PUT",
      body: JSON.stringify(entries),
    }),
  getSuggestedOpening: (id: number) =>
    request<any[]>(`/budget/fiscal-years/${id}/suggested-opening`),
  listAllocations: (fyId: number) =>
    request<any[]>(`/budget/fiscal-years/${fyId}/allocations`),
  createAllocation: (fyId: number, a: any) =>
    request<any>(`/budget/fiscal-years/${fyId}/allocations`, {
      method: "POST",
      body: JSON.stringify(a),
    }),
  updateAllocation: (id: number, a: any) =>
    request<any>(`/budget/allocations/${id}`, {
      method: "PUT",
      body: JSON.stringify(a),
    }),
  deleteAllocation: (id: number) =>
    request<any>(`/budget/allocations/${id}`, { method: "DELETE" }),
  getBudgetView: (fyId: number) =>
    request<any>(`/budget/view?fiscal_year_id=${fyId}`),
```

- [ ] **Step 10.2: Verify build**

```
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 10.3: Commit**

```bash
git add frontend/src/api.ts
git commit -m "feat(frontend): budget API helpers"
```

---

## Task 11 — Frontend: BudgetManager shell with 3 tabs

**Files:**
- Modify: `frontend/src/modules/budget/BudgetManager.tsx`

- [ ] **Step 11.1: Replace BudgetManager.tsx with the shell**

Overwrite `frontend/src/modules/budget/BudgetManager.tsx`:

```tsx
import { useState } from "react";
import { useFiscalYear } from "../../core/FiscalYearContext";
import OverviewTab from "./tabs/OverviewTab";
import AllocationTab from "./tabs/AllocationTab";
import FiscalYearsTab from "./tabs/FiscalYearsTab";

type TabId = "overview" | "allocation" | "years";

const TABS: { id: TabId; label: string }[] = [
  { id: "overview", label: "Vue d'ensemble" },
  { id: "allocation", label: "Allocation" },
  { id: "years", label: "Exercices" },
];

export default function BudgetManager() {
  const { years, selectedYear, setSelectedYearId, reload } = useFiscalYear();
  const [tab, setTab] = useState<TabId>("overview");

  return (
    <div className="p-8 space-y-6">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white" style={{ letterSpacing: "-0.02em" }}>
            Budget
          </h1>
          <p className="text-sm text-[#999] mt-1">
            Allocations, suivi du réalisé, comparaison à l'exercice précédent.
          </p>
        </div>
        {years.length > 0 && (
          <select
            value={selectedYear?.id ?? ""}
            onChange={(e) => setSelectedYearId(parseInt(e.target.value, 10))}
            className="bg-[#111] border border-[#222] rounded-xl px-3 py-2.5 text-sm text-white"
          >
            {years.map((y) => (
              <option key={y.id} value={y.id}>
                {y.name} {y.is_current === 1 ? "(actif)" : ""}
              </option>
            ))}
          </select>
        )}
      </div>

      <div className="flex gap-1 border-b border-[#222]">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
              tab === t.id
                ? "border-[#F2C48D] text-white"
                : "border-transparent text-[#666] hover:text-white"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "overview" && <OverviewTab year={selectedYear} />}
      {tab === "allocation" && <AllocationTab year={selectedYear} onChange={reload} />}
      {tab === "years" && <FiscalYearsTab />}
    </div>
  );
}
```

- [ ] **Step 11.2: Commit (placeholder tabs will be added in tasks 12/13/14)**

Skip commit until tab files exist — otherwise build fails. Move to Task 12.

---

## Task 12 — Frontend: FiscalYearsTab + FiscalYearWizard

**Files:**
- Create: `frontend/src/modules/budget/tabs/FiscalYearsTab.tsx`
- Create: `frontend/src/modules/budget/FiscalYearWizard.tsx`

- [ ] **Step 12.1: Create FiscalYearWizard.tsx**

Create `frontend/src/modules/budget/FiscalYearWizard.tsx`:

```tsx
import { useEffect, useState } from "react";
import { api } from "../../api";
import { X, ArrowRight } from "lucide-react";

interface WizardProps {
  previousYearId: number | null;
  onClose: () => void;
  onCreated: () => void;
}

export default function FiscalYearWizard({ previousYearId, onClose, onCreated }: WizardProps) {
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const today = new Date();
  const defaultStart = `${today.getFullYear()}-09-01`;
  const defaultEnd = `${today.getFullYear() + 1}-08-31`;

  const [name, setName] = useState(`${today.getFullYear()}-${today.getFullYear() + 1}`);
  const [startDate, setStartDate] = useState(defaultStart);
  const [endDate, setEndDate] = useState(defaultEnd);
  const [isCurrent, setIsCurrent] = useState(true);

  const [suggestions, setSuggestions] = useState<any[]>([]);
  const [openings, setOpenings] = useState<Record<number, { amount: string; source: string }>>({});
  const [createdFyId, setCreatedFyId] = useState<number | null>(null);

  const [copyAllocations, setCopyAllocations] = useState(previousYearId !== null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function goToStep2() {
    setError(null);
    setSubmitting(true);
    try {
      const fy = await api.createFiscalYear({
        name, start_date: startDate, end_date: endDate, is_current: isCurrent,
      });
      setCreatedFyId(fy.id);
      const sugg = await api.getSuggestedOpening(fy.id);
      setSuggestions(sugg);
      setOpenings(Object.fromEntries(sugg.map((s) => [s.entity_id, { amount: "", source: "" }])));
      setStep(2);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  }

  async function goToStep3() {
    setError(null);
    setSubmitting(true);
    if (!createdFyId) return;
    try {
      const entries = suggestions.map((s) => ({
        entity_id: s.entity_id,
        amount: parseFloat(openings[s.entity_id]?.amount || String(s.suggested_amount)),
        source: openings[s.entity_id]?.source || "",
      }));
      await api.upsertOpeningBalances(createdFyId, entries);
      setStep(3);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  }

  async function finish() {
    setError(null);
    setSubmitting(true);
    if (!createdFyId) return;
    try {
      if (copyAllocations && previousYearId !== null) {
        const prevAllocs = await api.listAllocations(previousYearId);
        for (const a of prevAllocs) {
          await api.createAllocation(createdFyId, {
            entity_id: a.entity_id,
            category_id: a.category_id,
            amount: a.amount,
            notes: a.notes,
          });
        }
      }
      onCreated();
      onClose();
    } catch (e: any) {
      setError(e.message);
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div
        className="bg-[#0a0a0a] border border-[#222] rounded-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-5 border-b border-[#222]">
          <h2 className="text-base font-semibold text-white">
            Nouvel exercice — étape {step}/3
          </h2>
          <button onClick={onClose} className="text-[#666] hover:text-white"><X size={18} /></button>
        </div>

        <div className="p-5 space-y-4">
          {error && (
            <div className="bg-[#1a0a0a] border border-[#FF5252]/30 text-[#FF5252] rounded-xl p-3 text-sm">
              {error}
            </div>
          )}

          {step === 1 && (
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-[#B0B0B0] mb-1.5">Nom</label>
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full bg-[#0a0a0a] border border-[#222] rounded-xl px-3 py-2.5 text-sm text-white"
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-[#B0B0B0] mb-1.5">Début</label>
                  <input
                    type="date"
                    value={startDate}
                    onChange={(e) => setStartDate(e.target.value)}
                    className="w-full bg-[#0a0a0a] border border-[#222] rounded-xl px-3 py-2.5 text-sm text-white [color-scheme:dark]"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-[#B0B0B0] mb-1.5">Fin</label>
                  <input
                    type="date"
                    value={endDate}
                    onChange={(e) => setEndDate(e.target.value)}
                    className="w-full bg-[#0a0a0a] border border-[#222] rounded-xl px-3 py-2.5 text-sm text-white [color-scheme:dark]"
                  />
                </div>
              </div>
              <label className="flex items-center gap-2 text-sm text-[#B0B0B0]">
                <input type="checkbox" checked={isCurrent} onChange={(e) => setIsCurrent(e.target.checked)} />
                Définir comme exercice actif
              </label>
            </div>
          )}

          {step === 2 && (
            <div className="space-y-2">
              <p className="text-sm text-[#B0B0B0]">
                Saisis le vrai solde bancaire de chaque entité au {startDate}.
                Utilise les valeurs suggérées comme point de départ ou saisis tes relevés réels.
              </p>
              <div className="space-y-2">
                {suggestions.map((s) => (
                  <div key={s.entity_id} className="flex items-center gap-3 bg-[#111] border border-[#222] rounded-xl p-3">
                    <div className="flex-1">
                      <p className="text-sm text-white font-medium">{s.entity_name}</p>
                      <p className="text-xs text-[#666]">Suggéré : {s.suggested_amount.toFixed(2)} €</p>
                    </div>
                    <input
                      type="number"
                      step="0.01"
                      placeholder={String(s.suggested_amount)}
                      value={openings[s.entity_id]?.amount ?? ""}
                      onChange={(e) =>
                        setOpenings((p) => ({
                          ...p,
                          [s.entity_id]: { ...(p[s.entity_id] ?? { amount: "", source: "" }), amount: e.target.value },
                        }))
                      }
                      className="w-28 bg-[#0a0a0a] border border-[#333] rounded-lg px-2 py-1.5 text-sm text-white text-right"
                    />
                    <input
                      type="text"
                      placeholder="source (optionnel)"
                      value={openings[s.entity_id]?.source ?? ""}
                      onChange={(e) =>
                        setOpenings((p) => ({
                          ...p,
                          [s.entity_id]: { ...(p[s.entity_id] ?? { amount: "", source: "" }), source: e.target.value },
                        }))
                      }
                      className="w-40 bg-[#0a0a0a] border border-[#333] rounded-lg px-2 py-1.5 text-sm text-white"
                    />
                  </div>
                ))}
              </div>
            </div>
          )}

          {step === 3 && (
            <div className="space-y-3">
              {previousYearId !== null && (
                <label className="flex items-center gap-2 text-sm text-[#B0B0B0]">
                  <input type="checkbox" checked={copyAllocations} onChange={(e) => setCopyAllocations(e.target.checked)} />
                  Copier les allocations de l'exercice précédent
                </label>
              )}
              <p className="text-sm text-[#666]">
                L'exercice est prêt à être créé. Tu pourras affiner allocations et soldes à tout moment.
              </p>
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-3 p-5 border-t border-[#222]">
          {step > 1 && (
            <button
              onClick={() => setStep((s) => (s - 1) as any)}
              className="px-4 py-2 text-sm text-[#B0B0B0] hover:text-white"
            >
              Retour
            </button>
          )}
          {step === 1 && (
            <button
              onClick={goToStep2}
              disabled={submitting || !name || !startDate || !endDate}
              className="px-5 py-2.5 text-sm font-semibold text-black bg-[#F2C48D] rounded-full hover:bg-[#e8b87a] disabled:opacity-50 inline-flex items-center gap-1"
            >
              Suivant <ArrowRight size={14} />
            </button>
          )}
          {step === 2 && (
            <button
              onClick={goToStep3}
              disabled={submitting}
              className="px-5 py-2.5 text-sm font-semibold text-black bg-[#F2C48D] rounded-full hover:bg-[#e8b87a] disabled:opacity-50"
            >
              Suivant
            </button>
          )}
          {step === 3 && (
            <button
              onClick={finish}
              disabled={submitting}
              className="px-5 py-2.5 text-sm font-semibold text-black bg-[#F2C48D] rounded-full hover:bg-[#e8b87a] disabled:opacity-50"
            >
              Créer l'exercice
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 12.2: Create FiscalYearsTab.tsx**

Create `frontend/src/modules/budget/tabs/FiscalYearsTab.tsx`:

```tsx
import { useState } from "react";
import { useFiscalYear, FiscalYear } from "../../../core/FiscalYearContext";
import { api } from "../../../api";
import FiscalYearWizard from "../FiscalYearWizard";
import { Plus, Trash2, CheckCircle } from "lucide-react";

export default function FiscalYearsTab() {
  const { years, reload } = useFiscalYear();
  const [showWizard, setShowWizard] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);
  const previousYearId = years.length > 0 ? years[0].id : null;

  async function setActive(y: FiscalYear) {
    await api.updateFiscalYear(y.id, { is_current: true });
    await reload();
  }

  async function doDelete(id: number) {
    await api.deleteFiscalYear(id);
    setConfirmDelete(null);
    await reload();
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-[#B0B0B0]">
          {years.length} exercice(s). Un seul peut être actif à la fois.
        </p>
        <button
          onClick={() => setShowWizard(true)}
          className="flex items-center gap-2 px-5 py-2.5 text-sm font-semibold text-black bg-[#F2C48D] rounded-full hover:bg-[#e8b87a]"
        >
          <Plus size={14} /> Nouvel exercice
        </button>
      </div>

      <div className="bg-[#111] border border-[#222] rounded-2xl overflow-hidden">
        {years.length === 0 ? (
          <div className="py-8 text-center text-sm text-[#666]">
            Aucun exercice. Crée le premier pour activer le suivi budgétaire.
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#1a1a1a]">
                <th className="px-4 py-3 text-left text-xs font-medium text-[#666] uppercase">Nom</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-[#666] uppercase">Début</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-[#666] uppercase">Fin</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-[#666] uppercase">Actions</th>
              </tr>
            </thead>
            <tbody>
              {years.map((y, idx) => (
                <tr key={y.id} className={idx > 0 ? "border-t border-[#1a1a1a]" : ""}>
                  <td className="px-4 py-3 text-white font-medium">
                    {y.name}
                    {y.is_current === 1 && (
                      <span className="ml-2 text-xs text-[#F2C48D] inline-flex items-center gap-1">
                        <CheckCircle size={11} /> actif
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-[#B0B0B0]">{y.start_date}</td>
                  <td className="px-4 py-3 text-[#B0B0B0]">{y.end_date}</td>
                  <td className="px-4 py-3 text-right">
                    {y.is_current !== 1 && (
                      <button
                        onClick={() => setActive(y)}
                        className="text-xs text-[#F2C48D] hover:underline mr-3"
                      >
                        Définir actif
                      </button>
                    )}
                    {confirmDelete === y.id ? (
                      <span className="inline-flex items-center gap-2 text-xs">
                        <span className="text-[#666]">Supprimer ?</span>
                        <button onClick={() => doDelete(y.id)} className="text-[#FF5252] font-semibold">Oui</button>
                        <button onClick={() => setConfirmDelete(null)} className="text-[#666]">Non</button>
                      </span>
                    ) : (
                      <button
                        onClick={() => setConfirmDelete(y.id)}
                        className="p-1.5 text-[#666] hover:text-[#FF5252]"
                        title="Supprimer"
                      >
                        <Trash2 size={14} strokeWidth={1.5} />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {showWizard && (
        <FiscalYearWizard
          previousYearId={previousYearId}
          onClose={() => setShowWizard(false)}
          onCreated={reload}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 12.3: Verify build (wizard + tab should resolve; overview/allocation tabs still missing → will fail)**

```
cd frontend && npm run build
```

Expected: FAIL with missing imports for OverviewTab / AllocationTab. Proceed to Task 13.

---

## Task 13 — Frontend: OverviewTab (read-only with N-1)

**Files:**
- Create: `frontend/src/modules/budget/tabs/OverviewTab.tsx`

- [ ] **Step 13.1: Create OverviewTab.tsx**

Create `frontend/src/modules/budget/tabs/OverviewTab.tsx`:

```tsx
import { useEffect, useState } from "react";
import { api } from "../../../api";
import { FiscalYear } from "../../../core/FiscalYearContext";
import { ChevronDown, ChevronRight } from "lucide-react";

const eur = new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" });

interface Props { year: FiscalYear | null }

export default function OverviewTab({ year }: Props) {
  const [data, setData] = useState<any | null>(null);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  useEffect(() => {
    if (!year) return;
    setLoading(true);
    api.getBudgetView(year.id).then(setData).finally(() => setLoading(false));
  }, [year?.id]);

  if (!year) return <p className="text-sm text-[#666]">Crée un exercice pour voir le suivi.</p>;
  if (loading) return <p className="text-sm text-[#666]">Chargement…</p>;
  if (!data) return null;

  const hasNMinus1 = data.previous_fiscal_year_id !== null;

  function toggle(id: number) {
    setExpanded((prev) => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id); else n.add(id);
      return n;
    });
  }

  function color(pct: number): string {
    if (pct < 70) return "#00C853";
    if (pct < 95) return "#F2C48D";
    return "#FF5252";
  }

  return (
    <div className="bg-[#111] border border-[#222] rounded-2xl overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-[#1a1a1a] text-[#666]">
            <th className="px-4 py-3 text-left text-xs font-medium uppercase"></th>
            <th className="px-4 py-3 text-left text-xs font-medium uppercase">Entité</th>
            <th className="px-4 py-3 text-right text-xs font-medium uppercase">Ouverture</th>
            <th className="px-4 py-3 text-right text-xs font-medium uppercase">Alloué</th>
            <th className="px-4 py-3 text-right text-xs font-medium uppercase">Réalisé</th>
            <th className="px-4 py-3 text-right text-xs font-medium uppercase">% consommé</th>
            {hasNMinus1 && <th className="px-4 py-3 text-right text-xs font-medium uppercase">N-1</th>}
            {hasNMinus1 && <th className="px-4 py-3 text-right text-xs font-medium uppercase">Variation</th>}
          </tr>
        </thead>
        <tbody>
          {data.entities.map((ent: any, idx: number) => {
            const pct = ent.allocated_total > 0
              ? Math.abs(ent.realized_total) / ent.allocated_total * 100
              : 0;
            return (
              <>
                <tr key={ent.entity_id} className={idx > 0 ? "border-t border-[#1a1a1a]" : ""}>
                  <td className="px-4 py-3">
                    {ent.categories.length > 0 && (
                      <button onClick={() => toggle(ent.entity_id)} className="text-[#666] hover:text-white">
                        {expanded.has(ent.entity_id) ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                      </button>
                    )}
                  </td>
                  <td className="px-4 py-3 text-white font-medium">{ent.entity_name}</td>
                  <td className="px-4 py-3 text-right text-[#B0B0B0]">{eur.format(ent.opening_balance)}</td>
                  <td className="px-4 py-3 text-right text-[#B0B0B0]">{eur.format(ent.allocated_total)}</td>
                  <td className={`px-4 py-3 text-right font-semibold ${ent.realized_total >= 0 ? "text-[#00C853]" : "text-[#FF5252]"}`}>
                    {eur.format(ent.realized_total)}
                  </td>
                  <td className="px-4 py-3 text-right" style={{ color: color(pct) }}>
                    {ent.allocated_total > 0 ? `${pct.toFixed(1)} %` : "—"}
                  </td>
                  {hasNMinus1 && (
                    <td className="px-4 py-3 text-right text-[#B0B0B0]">{eur.format(ent.realized_n_minus_1)}</td>
                  )}
                  {hasNMinus1 && (
                    <td className="px-4 py-3 text-right text-xs">
                      {ent.variation_pct !== null ? (
                        <span className={ent.variation_pct < 0 ? "text-[#00C853]" : "text-[#FF5252]"}>
                          {ent.variation_pct > 0 ? "+" : ""}{ent.variation_pct} %
                        </span>
                      ) : "—"}
                    </td>
                  )}
                </tr>
                {expanded.has(ent.entity_id) && ent.categories.map((c: any) => (
                  <tr key={`${ent.entity_id}-${c.allocation_id}`} className="bg-[#0a0a0a] text-xs">
                    <td className="px-4 py-2"></td>
                    <td className="px-8 py-2 text-[#B0B0B0]">↳ {c.category_name}</td>
                    <td className="px-4 py-2 text-right text-[#555]">—</td>
                    <td className="px-4 py-2 text-right text-[#B0B0B0]">{eur.format(c.allocated)}</td>
                    <td className="px-4 py-2 text-right">{eur.format(c.realized)}</td>
                    <td className="px-4 py-2 text-right" style={{ color: color(c.percent_consumed) }}>
                      {c.percent_consumed.toFixed(1)} %
                    </td>
                    {hasNMinus1 && <td className="px-4 py-2 text-right text-[#B0B0B0]">{eur.format(c.realized_n_minus_1)}</td>}
                    {hasNMinus1 && <td className="px-4 py-2 text-right">—</td>}
                  </tr>
                ))}
              </>
            );
          })}
        </tbody>
        <tfoot>
          <tr className="border-t-2 border-[#222] bg-[#0a0a0a]">
            <td></td>
            <td className="px-4 py-3 text-white font-semibold">Total</td>
            <td></td>
            <td className="px-4 py-3 text-right text-white font-semibold">{eur.format(data.totals.allocated)}</td>
            <td className="px-4 py-3 text-right text-white font-semibold">{eur.format(data.totals.realized)}</td>
            <td colSpan={hasNMinus1 ? 3 : 1}></td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}
```

- [ ] **Step 13.2: Commit after AllocationTab exists (Task 14)**

Move to Task 14.

---

## Task 14 — Frontend: AllocationTab (editable)

**Files:**
- Create: `frontend/src/modules/budget/tabs/AllocationTab.tsx`

- [ ] **Step 14.1: Create AllocationTab.tsx**

Create `frontend/src/modules/budget/tabs/AllocationTab.tsx`:

```tsx
import { useEffect, useState } from "react";
import { api } from "../../../api";
import { FiscalYear } from "../../../core/FiscalYearContext";
import { Entity, Category } from "../../../types";
import { Plus, Trash2, Copy } from "lucide-react";

const eur = new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" });

interface Props {
  year: FiscalYear | null;
  onChange: () => void;
}

export default function AllocationTab({ year, onChange }: Props) {
  const [allocations, setAllocations] = useState<any[]>([]);
  const [entities, setEntities] = useState<Entity[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [adding, setAdding] = useState(false);
  const [newEntity, setNewEntity] = useState("");
  const [newCategory, setNewCategory] = useState("");
  const [newAmount, setNewAmount] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function reload() {
    if (!year) return;
    const [a, e, c] = await Promise.all([
      api.listAllocations(year.id),
      api.getEntities(),
      api.getCategories(),
    ]);
    setAllocations(a);
    setEntities(e as any);
    setCategories(c as any);
  }

  useEffect(() => { reload(); }, [year?.id]);

  if (!year) return <p className="text-sm text-[#666]">Crée un exercice d'abord.</p>;

  async function addRow() {
    setError(null);
    if (!newEntity || !newAmount) { setError("Entité et montant obligatoires."); return; }
    try {
      await api.createAllocation(year!.id, {
        entity_id: parseInt(newEntity, 10),
        category_id: newCategory ? parseInt(newCategory, 10) : null,
        amount: parseFloat(newAmount),
      });
      setNewEntity(""); setNewCategory(""); setNewAmount("");
      setAdding(false);
      await reload();
      onChange();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function remove(id: number) {
    await api.deleteAllocation(id);
    await reload();
    onChange();
  }

  const internalEntities = entities.filter((e: any) => e.type === "internal");

  return (
    <div className="space-y-4">
      {error && (
        <div className="bg-[#1a0a0a] border border-[#FF5252]/30 text-[#FF5252] rounded-xl p-3 text-sm">
          {error}
        </div>
      )}

      <div className="flex items-center justify-between">
        <p className="text-sm text-[#B0B0B0]">
          {allocations.length} allocation(s). Laisse la catégorie vide pour une enveloppe globale de l'entité.
        </p>
        <button
          onClick={() => setAdding(true)}
          className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-[#F2C48D] border border-[#F2C48D]/40 rounded-full hover:bg-[#F2C48D]/10"
        >
          <Plus size={14} /> Ajouter
        </button>
      </div>

      {adding && (
        <div className="bg-[#111] border border-[#222] rounded-xl p-4 flex items-end gap-3">
          <div className="flex-1">
            <label className="block text-xs text-[#666] mb-1">Entité</label>
            <select
              value={newEntity}
              onChange={(e) => setNewEntity(e.target.value)}
              className="w-full bg-[#0a0a0a] border border-[#333] rounded-lg px-2 py-1.5 text-sm text-white"
            >
              <option value="">— Choisir —</option>
              {internalEntities.map((e: any) => (
                <option key={e.id} value={e.id}>{e.name}</option>
              ))}
            </select>
          </div>
          <div className="flex-1">
            <label className="block text-xs text-[#666] mb-1">Catégorie (facultatif)</label>
            <select
              value={newCategory}
              onChange={(e) => setNewCategory(e.target.value)}
              className="w-full bg-[#0a0a0a] border border-[#333] rounded-lg px-2 py-1.5 text-sm text-white"
            >
              <option value="">— Globale —</option>
              {categories.map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs text-[#666] mb-1">Montant</label>
            <input
              type="number"
              step="0.01"
              value={newAmount}
              onChange={(e) => setNewAmount(e.target.value)}
              className="w-28 bg-[#0a0a0a] border border-[#333] rounded-lg px-2 py-1.5 text-sm text-white text-right"
            />
          </div>
          <button onClick={addRow} className="px-4 py-2 text-sm font-semibold text-black bg-[#F2C48D] rounded-full">
            OK
          </button>
          <button onClick={() => setAdding(false)} className="px-4 py-2 text-sm text-[#666]">
            Annuler
          </button>
        </div>
      )}

      <div className="bg-[#111] border border-[#222] rounded-2xl overflow-hidden">
        {allocations.length === 0 ? (
          <div className="py-8 text-center text-sm text-[#666]">Aucune allocation.</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#1a1a1a]">
                <th className="px-4 py-3 text-left text-xs font-medium text-[#666] uppercase">Entité</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-[#666] uppercase">Catégorie</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-[#666] uppercase">Montant</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-[#666] uppercase">Actions</th>
              </tr>
            </thead>
            <tbody>
              {allocations.map((a, idx) => {
                const ent = entities.find((e: any) => e.id === a.entity_id);
                const cat = a.category_id ? categories.find((c) => c.id === a.category_id) : null;
                return (
                  <tr key={a.id} className={idx > 0 ? "border-t border-[#1a1a1a]" : ""}>
                    <td className="px-4 py-3 text-white">{(ent as any)?.name ?? `#${a.entity_id}`}</td>
                    <td className="px-4 py-3 text-[#B0B0B0]">
                      {cat ? cat.name : <span className="text-[#666] italic">Globale</span>}
                    </td>
                    <td className="px-4 py-3 text-right font-medium text-white">{eur.format(a.amount)}</td>
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={() => remove(a.id)}
                        className="p-1.5 text-[#666] hover:text-[#FF5252]"
                        title="Supprimer"
                      >
                        <Trash2 size={14} strokeWidth={1.5} />
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 14.2: Verify build**

```
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 14.3: Commit (bundles tasks 11+12+13+14)**

```bash
git add frontend/src/modules/budget/BudgetManager.tsx \
        frontend/src/modules/budget/FiscalYearWizard.tsx \
        frontend/src/modules/budget/tabs/
git commit -m "feat(budget): /budget page with Overview, Allocation, FiscalYears tabs + wizard"
```

---

## Task 15 — Frontend: BudgetOverview dashboard widget

**Files:**
- Create: `frontend/src/modules/budget/widgets/BudgetOverview.tsx`
- Modify: `frontend/src/core/Dashboard.tsx`

- [ ] **Step 15.1: Create the widget**

Create `frontend/src/modules/budget/widgets/BudgetOverview.tsx`:

```tsx
import { useEffect, useState } from "react";
import { useFiscalYear } from "../../../core/FiscalYearContext";
import { api } from "../../../api";
import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";

const eur = new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" });

export default function BudgetOverview() {
  const { selectedYear } = useFiscalYear();
  const [view, setView] = useState<any | null>(null);

  useEffect(() => {
    if (!selectedYear) { setView(null); return; }
    api.getBudgetView(selectedYear.id).then(setView).catch(() => setView(null));
  }, [selectedYear?.id]);

  if (!selectedYear) {
    return (
      <div className="bg-[#111] border border-[#222] rounded-2xl p-6">
        <p className="text-xs font-medium text-[#666] uppercase tracking-wider mb-3">Budget</p>
        <p className="text-sm text-[#666]">
          <Link to="/budget" className="text-[#F2C48D] hover:underline">Crée un exercice</Link> pour activer le suivi.
        </p>
      </div>
    );
  }
  if (!view) return null;

  const allocated = view.totals.allocated as number;
  const realized = Math.abs(view.totals.realized as number);
  const pct = allocated > 0 ? (realized / allocated) * 100 : 0;
  const barColor = pct < 70 ? "#00C853" : pct < 95 ? "#F2C48D" : "#FF5252";

  const overspending = view.entities
    .filter((e: any) => e.allocated_total > 0 && Math.abs(e.realized_total) / e.allocated_total >= 0.95)
    .slice(0, 3);

  return (
    <div className="bg-[#111] border border-[#222] rounded-2xl p-6">
      <div className="flex items-center justify-between mb-3">
        <p className="text-xs font-medium text-[#666] uppercase tracking-wider">Budget — {selectedYear.name}</p>
        <Link to="/budget" className="text-xs text-[#F2C48D] hover:underline inline-flex items-center gap-0.5">
          Détail <ArrowRight size={11} />
        </Link>
      </div>
      <p className="text-sm text-white mb-2">
        {eur.format(realized)} consommés / {eur.format(allocated)} alloués
      </p>
      <div className="h-2 bg-[#1a1a1a] rounded-full overflow-hidden mb-3">
        <div className="h-full rounded-full" style={{ width: `${Math.min(pct, 100)}%`, backgroundColor: barColor }} />
      </div>
      <p className="text-xs text-[#666] mb-3">Reste {eur.format(allocated - realized)}</p>
      {overspending.length > 0 && (
        <div className="mt-2 pt-3 border-t border-[#1a1a1a]">
          <p className="text-xs text-[#666] uppercase tracking-wider mb-1.5">Top dépassements</p>
          <div className="space-y-1">
            {overspending.map((e: any) => (
              <div key={e.entity_id} className="flex items-center justify-between text-xs">
                <span className="text-white">{e.entity_name}</span>
                <span className="text-[#FF5252] font-medium">
                  {((Math.abs(e.realized_total) / e.allocated_total) * 100).toFixed(0)} %
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 15.2: Embed widget in Dashboard.tsx**

Open `frontend/src/core/Dashboard.tsx`, add the import at the top:

```tsx
import BudgetOverview from "../modules/budget/widgets/BudgetOverview";
```

Find the existing `<div className="grid grid-cols-1 lg:grid-cols-2 gap-4">` block that contains `<TopCategories cats={cats} />` and `<RecentTransactions txs={recent} />`. Change it to 3-column grid and prepend BudgetOverview:

```tsx
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <BudgetOverview />
        <TopCategories cats={cats} />
        <RecentTransactions txs={recent} />
      </div>
```

- [ ] **Step 15.3: Verify build**

```
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 15.4: Commit**

```bash
git add frontend/src/modules/budget/widgets/BudgetOverview.tsx frontend/src/core/Dashboard.tsx
git commit -m "feat(budget): BudgetOverview dashboard widget"
```

---

## Task 16 — Frontend: sidebar badge for overspending

**Files:**
- Modify: `frontend/src/core/Sidebar.tsx`

- [ ] **Step 16.1: Add a fetch for budget view and compute badge**

Open `frontend/src/core/Sidebar.tsx`. Locate the block that fetches `/api/reimbursements/?status=pending`. Add a similar block for budget overspending. Insert after the existing reimbursement effect:

```tsx
  const [budgetBadge, setBudgetBadge] = useState(0);
  useEffect(() => {
    const budgetActive = activeModules.some((m) => m.id === "budget");
    if (!budgetActive) return;
    let cancelled = false;
    (async () => {
      try {
        const r = await fetch("/api/budget/fiscal-years/current");
        if (!r.ok) return;
        const fy = await r.json();
        const v = await fetch(`/api/budget/view?fiscal_year_id=${fy.id}`);
        if (!v.ok) return;
        const data = await v.json();
        const count = (data.entities as any[]).filter(
          (e) => e.allocated_total > 0 && Math.abs(e.realized_total) / e.allocated_total >= 0.95
        ).length;
        if (!cancelled) setBudgetBadge(count);
      } catch {}
    })();
    return () => { cancelled = true; };
  }, [activeModules]);
```

Then locate the `optionalItems` array (the `.map((m: any) => ({ ... }))` block). Extend the badge computation to include budget:

```tsx
  const optionalItems = optionalModules.map((m: any) => ({
    id: m.id,
    to: MODULE_PATH_MAP[m.id] || `/${m.id}`,
    label: m.menu?.label || m.name,
    icon: ICON_MAP[m.menu?.icon] || LayoutDashboard,
    badge:
      m.id === "reimbursements" ? pendingReimbursements :
      m.id === "budget" ? budgetBadge :
      undefined,
  }));
```

- [ ] **Step 16.2: Verify build**

```
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 16.3: Commit**

```bash
git add frontend/src/core/Sidebar.tsx
git commit -m "feat(sidebar): budget overspending badge from current fiscal year"
```

---

## Task 17 — Entities panel: surface opening balance of current year

**Files:**
- Modify: `frontend/src/modules/entities/EntityTree.tsx`

- [ ] **Step 17.1: Add opening balance display in EntityBalancePanel**

Open `frontend/src/modules/entities/EntityTree.tsx`. Locate `EntityBalancePanel`. Add imports at top of the file:

```tsx
import { useFiscalYear } from "../../core/FiscalYearContext";
```

Inside `EntityBalancePanel`, add a new piece of state and fetch:

```tsx
  const { currentYear } = useFiscalYear();
  const [opening, setOpening] = useState<{ amount: number; source: string } | null>(null);

  useEffect(() => {
    if (!currentYear) { setOpening(null); return; }
    fetch(`/api/budget/fiscal-years/${currentYear.id}/opening-balances`)
      .then((r) => (r.ok ? r.json() : []))
      .then((rows: any[]) => {
        const row = rows.find((r) => r.entity_id === entityId);
        setOpening(row ? { amount: row.amount, source: row.source || "" } : null);
      })
      .catch(() => setOpening(null));
  }, [entityId, currentYear?.id]);
```

Locate the block rendering `balance.reference_date` (the "Solde propre" card section) and replace the sub-line that renders `Réf. {balance.reference_date}`. Replace:

```tsx
              {balance.reference_date && (
                <p className="text-xs text-[#555] mt-1">
                  Réf. {balance.reference_date} : {eurFormatter.format(balance.reference_amount)}
                </p>
              )}
```

With:

```tsx
              {opening ? (
                <p className="text-xs text-[#555] mt-1">
                  Ouverture {currentYear?.name} : {eurFormatter.format(opening.amount)}
                  {opening.source && <span className="text-[#444]"> ({opening.source})</span>}
                </p>
              ) : balance.reference_date && (
                <p className="text-xs text-[#555] mt-1">
                  Réf. {balance.reference_date} : {eurFormatter.format(balance.reference_amount)}
                </p>
              )}
```

- [ ] **Step 17.2: Verify build**

```
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 17.3: Commit**

```bash
git add frontend/src/modules/entities/EntityTree.tsx
git commit -m "feat(entities): show current fiscal-year opening balance in panel"
```

---

## Task 18 — E2E validation + documentation

**Files:**
- Modify: `openflow/CLAUDE.md`

- [ ] **Step 18.1: Run full backend + integrity checks**

```
cd openflow
python tools/check.py
python -m pytest tests/backend/ -q
```

Expected: check PASS, all tests green (~300+ including the new ones).

- [ ] **Step 18.2: Manual browser validation via Firefox-MCP**

Start the app if needed: `python start.py`.

Checklist (each item: open the page, confirm the result):
- `/budget` page loads with 3 tabs
- Clicking "Nouvel exercice" opens wizard; complete 3 steps with dummy data
- Overview tab shows the created exercise with entity rows; expanding a row shows categories if any allocation has `category_id`
- Allocation tab: add, then delete a row
- Fiscal Years tab: toggle "Définir actif" switches the indicator
- `/dashboard`: widget "Budget — YYYY-YYYY" visible with progress bar
- `/entities`: open panel, opening balance of current year appears if set
- Sidebar shows "Budget" entry; badge appears when an entity is ≥95 % consumed

Log any regression found and fix before committing.

- [ ] **Step 18.3: Update CLAUDE.md with the new concept**

Open `openflow/CLAUDE.md`, locate the "Convention modules" section. Add a new subsection at the same level titled "Budget & Exercices":

```markdown
## Budget & Exercices

Le module `budget` (1.2.0) introduit trois tables :
- `fiscal_years` : tranches d'affichage libres (pas de verrou sur les tx)
- `fiscal_year_opening_balances` : solde bancaire réel par entité interne à l'ouverture
- `budget_allocations` : allocation (entité, catégorie optionnelle) = montant

`backend/core/balance.py::compute_entity_balance_for_period` calcule le réalisé
sur un intervalle de dates pour une entité (± catégorie), utilisant la même
convention de signe que `compute_entity_balance`.

L'endpoint composite `/api/budget/view?fiscal_year_id=X` renvoie la vue
complète (entités + catégories + N-1) consommée par la page `/budget` et le
widget dashboard.

Le contexte React `FiscalYearContext` expose `currentYear` et `selectedYear`
(persisté dans `localStorage`).
```

- [ ] **Step 18.4: Commit docs**

```bash
git add openflow/CLAUDE.md
git commit -m "docs(claude): budget & exercices concept"
```

- [ ] **Step 18.5: Final sanity commit if Firefox tests surfaced fixes**

Only if step 18.2 required inline fixes, commit them separately with a descriptive message. Otherwise skip.

---

## Plan Summary

**18 tasks. ~18 commits. Each task self-contained and testable.**

- Tasks 1-8 = backend (migration + balance extension + 4 endpoint groups + cascade + coherence). All TDD.
- Task 9 = React context provider
- Task 10 = frontend API client helpers
- Tasks 11-14 = `/budget` page refoundation (shell + 3 tabs + wizard)
- Task 15 = dashboard widget
- Task 16 = sidebar badge
- Task 17 = entities panel surfaces opening balance
- Task 18 = E2E validation + docs update

**Verification strategy:**
- Backend: `pytest tests/backend/test_budget.py -v` and `pytest tests/backend/test_coherence_budget.py -v` after every backend task; full suite `pytest tests/backend/ -q` at task 8 and 18
- Frontend: `npm run build` after every task that touches TypeScript; manual Firefox-MCP validation at task 18
- Integrity: `python tools/check.py` at task 1 and 18 (on every manifest edit)

**Invariants maintained through the plan:**
- `from_entity_id` / `to_entity_id` never null (unchanged; bug #1 regression guard)
- Solde calculation stays centralized in `backend/core/balance.py`
- Manifest.json is the source of truth for module metadata
- PRAGMA foreign_keys remains OFF; cascades are implemented at the API layer
- `entity_balance_refs` is not touched (legacy fallback for installs without a fiscal year)
