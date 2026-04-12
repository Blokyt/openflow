# Sub-Entities Phase 1 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter un systeme de sous-entites hierarchiques a OpenFlow avec from/to sur chaque transaction, soldes dynamiques, et vue consolidee.

**Architecture:** Nouveau module `entities` avec arbre libre d'entites internes/externes. Balance centralisee dans `backend/core/balance.py` remplacant les 4 duplications. Chaque transaction a `from_entity_id` et `to_entity_id` (jamais null). Les modules existants recoivent un parametre `?entity_id=N` optionnel pour le scoping.

**Tech Stack:** Python 3, FastAPI, SQLite (raw sqlite3), React 18, Vite, Tailwind

---

### Task 1: Centraliser le calcul de balance dans `backend/core/balance.py`

**Files:**
- Create: `backend/core/balance.py`
- Test: `tests/backend/test_balance_core.py`

- [ ] **Step 1: Write the test file**

```python
"""Tests for the centralized balance computation."""
import sqlite3
import pytest
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent


def _make_db(tmp_path):
    """Create a minimal test DB with transactions table."""
    db = tmp_path / "test.db"
    conn = sqlite3.connect(str(db))
    conn.execute("""CREATE TABLE transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        label TEXT NOT NULL,
        amount REAL NOT NULL,
        from_entity_id INTEGER,
        to_entity_id INTEGER
    )""")
    conn.execute("""CREATE TABLE entity_balance_refs (
        entity_id INTEGER PRIMARY KEY,
        reference_date TEXT NOT NULL,
        reference_amount REAL NOT NULL DEFAULT 0.0,
        updated_at TEXT NOT NULL
    )""")
    conn.execute("""CREATE TABLE entities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        type TEXT NOT NULL DEFAULT 'internal',
        parent_id INTEGER
    )""")
    conn.commit()
    return conn


def test_legacy_balance_empty(tmp_path):
    from backend.core.balance import compute_legacy_balance
    conn = _make_db(tmp_path)
    result = compute_legacy_balance(conn, str(PROJECT_ROOT / "config.test.yaml"))
    conn.close()
    assert result["transactions_sum"] == pytest.approx(0.0)


def test_legacy_balance_with_transactions(tmp_path):
    from backend.core.balance import compute_legacy_balance
    conn = _make_db(tmp_path)
    conn.execute("INSERT INTO transactions (date, label, amount) VALUES ('2025-06-01', 'A', 500)")
    conn.execute("INSERT INTO transactions (date, label, amount) VALUES ('2025-06-02', 'B', -200)")
    conn.commit()
    result = compute_legacy_balance(conn, str(PROJECT_ROOT / "config.test.yaml"))
    conn.close()
    assert result["transactions_sum"] == pytest.approx(300.0)


def test_entity_balance_empty(tmp_path):
    from backend.core.balance import compute_entity_balance
    conn = _make_db(tmp_path)
    conn.execute("INSERT INTO entities (id, name, type) VALUES (1, 'BDA', 'internal')")
    conn.execute("INSERT INTO entity_balance_refs (entity_id, reference_date, reference_amount, updated_at) VALUES (1, '2025-01-01', 1000, '2025-01-01')")
    conn.commit()
    result = compute_entity_balance(conn, 1)
    conn.close()
    assert result["balance"] == pytest.approx(1000.0)
    assert result["reference_amount"] == pytest.approx(1000.0)
    assert result["transactions_sum"] == pytest.approx(0.0)


def test_entity_balance_with_transactions(tmp_path):
    from backend.core.balance import compute_entity_balance
    conn = _make_db(tmp_path)
    conn.execute("INSERT INTO entities (id, name, type) VALUES (1, 'BDA', 'internal')")
    conn.execute("INSERT INTO entities (id, name, type) VALUES (2, 'Fournisseur', 'external')")
    conn.execute("INSERT INTO entity_balance_refs (entity_id, reference_date, reference_amount, updated_at) VALUES (1, '2025-01-01', 1000, '2025-01-01')")
    # Incoming: Fournisseur → BDA, 500
    conn.execute("INSERT INTO transactions (date, label, amount, from_entity_id, to_entity_id) VALUES ('2025-06-01', 'Vente', 500, 2, 1)")
    # Outgoing: BDA → Fournisseur, -300
    conn.execute("INSERT INTO transactions (date, label, amount, from_entity_id, to_entity_id) VALUES ('2025-06-02', 'Achat', -300, 1, 2)")
    conn.commit()
    result = compute_entity_balance(conn, 1)
    conn.close()
    # Balance = 1000 + 500 (incoming) - 300 (outgoing) = 1200
    assert result["balance"] == pytest.approx(1200.0)


def test_entity_balance_ignores_unrelated(tmp_path):
    from backend.core.balance import compute_entity_balance
    conn = _make_db(tmp_path)
    conn.execute("INSERT INTO entities (id, name, type) VALUES (1, 'BDA', 'internal')")
    conn.execute("INSERT INTO entities (id, name, type) VALUES (2, 'Club', 'internal')")
    conn.execute("INSERT INTO entities (id, name, type) VALUES (3, 'Ext', 'external')")
    conn.execute("INSERT INTO entity_balance_refs (entity_id, reference_date, reference_amount, updated_at) VALUES (1, '2025-01-01', 0, '2025-01-01')")
    # Transaction between Club and Ext — should NOT affect BDA
    conn.execute("INSERT INTO transactions (date, label, amount, from_entity_id, to_entity_id) VALUES ('2025-06-01', 'X', -100, 2, 3)")
    conn.commit()
    result = compute_entity_balance(conn, 1)
    conn.close()
    assert result["balance"] == pytest.approx(0.0)


def test_consolidated_balance(tmp_path):
    from backend.core.balance import compute_consolidated_balance
    conn = _make_db(tmp_path)
    conn.execute("INSERT INTO entities (id, name, type, parent_id) VALUES (1, 'BDA', 'internal', NULL)")
    conn.execute("INSERT INTO entities (id, name, type, parent_id) VALUES (2, 'Gastro', 'internal', 1)")
    conn.execute("INSERT INTO entities (id, name, type) VALUES (3, 'Ext', 'external')")
    conn.execute("INSERT INTO entity_balance_refs (entity_id, reference_date, reference_amount, updated_at) VALUES (1, '2025-01-01', 1000, '2025-01-01')")
    conn.execute("INSERT INTO entity_balance_refs (entity_id, reference_date, reference_amount, updated_at) VALUES (2, '2025-01-01', 500, '2025-01-01')")
    # BDA gets 200 from Ext
    conn.execute("INSERT INTO transactions (date, label, amount, from_entity_id, to_entity_id) VALUES ('2025-06-01', 'Don', 200, 3, 1)")
    # Gastro spends 100 to Ext
    conn.execute("INSERT INTO transactions (date, label, amount, from_entity_id, to_entity_id) VALUES ('2025-06-02', 'Dep', -100, 2, 3)")
    conn.commit()
    result = compute_consolidated_balance(conn, 1)
    conn.close()
    # BDA own = 1000 + 200 = 1200
    assert result["own_balance"] == pytest.approx(1200.0)
    # Gastro own = 500 - 100 = 400
    # Consolidated = 1200 + 400 = 1600
    assert result["consolidated_balance"] == pytest.approx(1600.0)


def test_entity_balance_no_ref(tmp_path):
    """Entity with no balance reference: starts at 0."""
    from backend.core.balance import compute_entity_balance
    conn = _make_db(tmp_path)
    conn.execute("INSERT INTO entities (id, name, type) VALUES (1, 'BDA', 'internal')")
    conn.execute("INSERT INTO transactions (date, label, amount, from_entity_id, to_entity_id) VALUES ('2025-06-01', 'In', 300, 2, 1)")
    conn.commit()
    result = compute_entity_balance(conn, 1)
    conn.close()
    assert result["reference_amount"] == pytest.approx(0.0)
    assert result["balance"] == pytest.approx(300.0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/backend/test_balance_core.py -v`
Expected: FAIL — `backend.core.balance` module not found

- [ ] **Step 3: Implement `backend/core/balance.py`**

```python
"""Centralized balance computation for OpenFlow entities."""
import sqlite3
from typing import Optional

from backend.core.config import load_config


def compute_legacy_balance(conn: sqlite3.Connection, config_path: str) -> dict:
    """Backward-compatible balance for modules not yet entity-aware."""
    try:
        config = load_config(config_path)
        reference_amount = config.balance.amount
        reference_date = config.balance.date
    except Exception:
        reference_amount = 0.0
        reference_date = None

    if reference_date:
        total = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE date >= ?",
            (reference_date,),
        ).fetchone()[0]
    else:
        total = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM transactions"
        ).fetchone()[0]

    return {
        "balance": reference_amount + total,
        "reference_amount": reference_amount,
        "reference_date": reference_date,
        "transactions_sum": total,
    }


def compute_entity_balance(
    conn: sqlite3.Connection,
    entity_id: int,
    as_of_date: Optional[str] = None,
) -> dict:
    """Compute balance for an internal entity: reference + incoming - outgoing."""
    ref = conn.execute(
        "SELECT reference_date, reference_amount FROM entity_balance_refs WHERE entity_id = ?",
        (entity_id,),
    ).fetchone()

    reference_amount = ref["reference_amount"] if ref else 0.0
    reference_date = ref["reference_date"] if ref else None

    # Build date filters
    conditions_in = ["to_entity_id = ?"]
    conditions_out = ["from_entity_id = ?", "amount < 0"]
    params_in = [entity_id]
    params_out = [entity_id]

    if reference_date:
        conditions_in.append("date >= ?")
        conditions_out.append("date >= ?")
        params_in.append(reference_date)
        params_out.append(reference_date)
    if as_of_date:
        conditions_in.append("date <= ?")
        conditions_out.append("date <= ?")
        params_in.append(as_of_date)
        params_out.append(as_of_date)

    where_in = " AND ".join(conditions_in)
    where_out = " AND ".join(conditions_out)

    incoming = conn.execute(
        f"SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE {where_in}",
        params_in,
    ).fetchone()[0]

    outgoing = conn.execute(
        f"SELECT COALESCE(SUM(ABS(amount)), 0) FROM transactions WHERE {where_out}",
        params_out,
    ).fetchone()[0]

    transactions_sum = incoming - outgoing

    return {
        "entity_id": entity_id,
        "balance": reference_amount + transactions_sum,
        "reference_amount": reference_amount,
        "reference_date": reference_date,
        "transactions_sum": transactions_sum,
    }


def compute_consolidated_balance(
    conn: sqlite3.Connection,
    entity_id: int,
    as_of_date: Optional[str] = None,
) -> dict:
    """Consolidated balance: own + all descendant entities (recursive)."""
    rows = conn.execute(
        """WITH RECURSIVE tree(id) AS (
            SELECT ? UNION ALL
            SELECT e.id FROM entities e JOIN tree t ON e.parent_id = t.id
            WHERE e.type = 'internal'
        ) SELECT id FROM tree""",
        (entity_id,),
    ).fetchall()

    own = compute_entity_balance(conn, entity_id, as_of_date)
    children = []
    consolidated = own["balance"]

    for row in rows:
        eid = row[0] if isinstance(row, tuple) else row["id"]
        if eid != entity_id:
            child_bal = compute_entity_balance(conn, eid, as_of_date)
            children.append(child_bal)
            consolidated += child_bal["balance"]

    return {
        "entity_id": entity_id,
        "own_balance": own["balance"],
        "consolidated_balance": consolidated,
        "children": children,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/backend/test_balance_core.py -v`
Expected: 8 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/core/balance.py tests/backend/test_balance_core.py
git commit -m "feat: centralized balance computation in backend/core/balance.py"
```

---

### Task 2: Rewire les 4 modules qui dupliquent le calcul de balance

**Files:**
- Modify: `backend/modules/transactions/api.py`
- Modify: `backend/modules/dashboard/api.py`
- Modify: `backend/modules/alerts/api.py`
- Modify: `backend/modules/forecasting/api.py`

- [ ] **Step 1: Replace balance in transactions/api.py**

Replace the `get_balance()` endpoint (lines 107-135) to use `compute_legacy_balance`:

```python
from backend.core.balance import compute_legacy_balance

@router.get("/balance")
def get_balance():
    conn = get_conn()
    try:
        return compute_legacy_balance(conn, str(CONFIG_PATH))
    finally:
        conn.close()
```

Remove the manual config loading and SUM query that was there before.

- [ ] **Step 2: Replace balance in dashboard/api.py**

Replace the balance section of `get_summary()` (lines 97-131) to use `compute_legacy_balance`:

```python
from backend.core.balance import compute_legacy_balance

@router.get("/summary")
def get_summary():
    conn = get_conn()
    try:
        # Check transactions table exists
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='transactions'")
        if cur.fetchone() is None:
            return {"balance": 0.0, "total_income": 0.0, "total_expenses": 0.0, "transaction_count": 0}

        bal = compute_legacy_balance(conn, str(CONFIG_PATH))

        total_income = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE amount > 0"
        ).fetchone()[0]
        total_expenses = abs(conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE amount < 0"
        ).fetchone()[0])
        transaction_count = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]

        return {
            "balance": bal["balance"],
            "total_income": total_income,
            "total_expenses": total_expenses,
            "transaction_count": transaction_count,
        }
    finally:
        conn.close()
```

- [ ] **Step 3: Replace `_compute_balance` in alerts/api.py**

Replace the `_compute_balance` private function (lines 67-85):

```python
from backend.core.balance import compute_legacy_balance

def _compute_balance(conn: sqlite3.Connection) -> float:
    return compute_legacy_balance(conn, str(CONFIG_PATH))["balance"]
```

- [ ] **Step 4: Replace balance in forecasting/api.py**

Replace the balance section of `get_projection()` (lines 25-47):

```python
from backend.core.balance import compute_legacy_balance

# Inside get_projection():
bal = compute_legacy_balance(conn, str(CONFIG_PATH))
current_balance = bal["balance"]
# ... rest of the function stays the same (averages computation, projection loop)
```

Remove the manual config loading and SUM query.

- [ ] **Step 5: Run the existing coherence tests**

Run: `python -m pytest tests/backend/test_coherence_balance.py -v`
Expected: all 15 tests PASS (same behavior, different implementation)

- [ ] **Step 6: Run full test suite**

Run: `python -m pytest tests/ -q`
Expected: 361+ passed

- [ ] **Step 7: Commit**

```bash
git add backend/modules/transactions/api.py backend/modules/dashboard/api.py backend/modules/alerts/api.py backend/modules/forecasting/api.py
git commit -m "refactor: 4 modules now use centralized balance from core/balance.py"
```

---

### Task 3: Creer le module `entities` — schema + manifest + CRUD API

**Files:**
- Create: `backend/modules/entities/manifest.json`
- Create: `backend/modules/entities/__init__.py`
- Create: `backend/modules/entities/models.py`
- Create: `backend/modules/entities/api.py`
- Test: `tests/backend/test_entities_api.py`

- [ ] **Step 1: Create manifest.json**

```json
{
  "id": "entities",
  "name": "Entites",
  "description": "Arbre d'entites internes et externes",
  "help": "Gerez votre structure organisationnelle : entite racine, sous-clubs, fournisseurs, clients. Chaque transaction trace qui paie qui. Consultez le solde propre et consolide de chaque entite.",
  "version": "1.0.0",
  "origin": "builtin",
  "category": "core",
  "dependencies": ["transactions"],
  "menu": {"label": "Entites", "icon": "git-branch", "position": 1},
  "api_routes": ["api.py"],
  "db_models": ["models.py"],
  "dashboard_widgets": [],
  "settings_schema": {}
}
```

- [ ] **Step 2: Create `__init__.py`** (empty file)

- [ ] **Step 3: Create models.py**

```python
migrations = {
    "1.0.0": [
        """CREATE TABLE entities (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT    NOT NULL,
            description  TEXT    DEFAULT '',
            type         TEXT    NOT NULL DEFAULT 'internal',
            parent_id    INTEGER,
            is_default   INTEGER NOT NULL DEFAULT 0,
            is_divers    INTEGER NOT NULL DEFAULT 0,
            color        TEXT    DEFAULT '#6B7280',
            position     INTEGER DEFAULT 0,
            created_at   TEXT    NOT NULL,
            updated_at   TEXT    NOT NULL
        )""",
        """CREATE TABLE entity_balance_refs (
            entity_id        INTEGER PRIMARY KEY,
            reference_date   TEXT    NOT NULL,
            reference_amount REAL    NOT NULL DEFAULT 0.0,
            updated_at       TEXT    NOT NULL
        )""",
    ],
}
```

- [ ] **Step 4: Create api.py with CRUD + tree + balance endpoints**

Full API with endpoints:
- `GET /` — list entities (filter by `?type=internal|external`)
- `POST /` — create entity
- `GET /tree` — recursive tree of internal entities
- `GET /{id}` — get single entity
- `PUT /{id}` — update entity
- `DELETE /{id}` — delete (reject if has children or transactions)
- `GET /{id}/balance` — entity balance (from `core/balance.py`)
- `GET /{id}/consolidated` — consolidated balance with children
- `GET /{id}/balance-ref` — get/set reference balance
- `PUT /{id}/balance-ref` — update reference balance

- [ ] **Step 5: Write tests**

`tests/backend/test_entities_api.py` — CRUD + tree + constraints:
- Create internal root entity
- Create internal child entity
- Create external entity
- Create divers entity (only one allowed)
- Reject second divers entity
- Reject external entity with parent_id
- Get tree structure (parent → children)
- Delete entity (reject if has children)
- Balance endpoint returns correct value
- Consolidated balance sums children

- [ ] **Step 6: Add entities to config.example.yaml**

Add `entities: true` to the modules section.

- [ ] **Step 7: Run check.py + tests**

Run: `python tools/check.py && python -m pytest tests/backend/test_entities_api.py -v`

- [ ] **Step 8: Commit**

```bash
git add backend/modules/entities/ config.example.yaml
git commit -m "feat: add entities module with hierarchy, balance, and CRUD"
```

---

### Task 4: Ajouter from_entity_id / to_entity_id sur transactions

**Files:**
- Modify: `backend/modules/transactions/models.py` — migration v1.1.0
- Modify: `backend/modules/transactions/api.py` — validation + entity_id filter
- Create: `backend/modules/entities/migration_helper.py` — backfill data
- Test: `tests/backend/test_transaction_entities.py`

- [ ] **Step 1: Add migration v1.1.0 to transactions/models.py**

```python
migrations = {
    "1.0.0": [ ... existing ... ],
    "1.1.0": [
        "ALTER TABLE transactions ADD COLUMN from_entity_id INTEGER",
        "ALTER TABLE transactions ADD COLUMN to_entity_id INTEGER",
    ],
}
```

- [ ] **Step 2: Write migration_helper.py for data backfill**

Script that reads config.yaml, creates root + divers entities, and backfills all existing transactions with from/to entity IDs based on amount sign and contact_id.

- [ ] **Step 3: Update transactions/api.py**

- Add `from_entity_id` and `to_entity_id` to `TransactionCreate` (required int fields)
- Add optional `entity_id` query param to list endpoint
- Add `include_children` bool query param
- On create: validate both entity IDs exist, at least one is internal
- On create: if to_entity is the "divers" entity, description must be non-empty

- [ ] **Step 4: Write tests**

`tests/backend/test_transaction_entities.py`:
- Create transaction with from/to entity IDs
- Reject transaction without from_entity_id
- Reject transaction without to_entity_id
- Filter transactions by entity_id
- Filter with include_children=true
- Divers entity requires description

- [ ] **Step 5: Run all tests**

Run: `python -m pytest tests/ -q`
Expected: all pass (old tests use nullable from/to, new tests enforce non-null)

- [ ] **Step 6: Commit**

```bash
git add backend/modules/transactions/ backend/modules/entities/migration_helper.py tests/
git commit -m "feat: from_entity_id/to_entity_id on transactions with validation"
```

---

### Task 5: Scoper les modules existants avec entity_id

**Files:**
- Modify: `backend/modules/dashboard/api.py`
- Modify: `backend/modules/budget/models.py` + `api.py`
- Modify: `backend/modules/export/api.py`
- Modify: `backend/modules/forecasting/api.py`
- Modify: `backend/modules/alerts/api.py`
- Test: `tests/backend/test_coherence_entities.py`

- [ ] **Step 1: Dashboard — add entity_id param**

`GET /summary?entity_id=N` — if provided, use `compute_entity_balance` instead of legacy. Income/expenses also filtered by entity.

- [ ] **Step 2: Budget — add entity_id column + filter**

Migration v1.1.0 adds `entity_id` to budgets table. Status endpoint filters transactions by entity when budget has one.

- [ ] **Step 3: Export — pass entity_id to queries**

`GET /export/transactions/csv?entity_id=N` and `/summary/csv?entity_id=N` — filter transactions by from/to entity.

- [ ] **Step 4: Forecasting — entity-aware projection**

`GET /projection?entity_id=N` — uses `compute_entity_balance` and filters averages window by entity.

- [ ] **Step 5: Alerts — entity-scoped rules**

Alert rules can optionally have `entity_id`. `_compute_balance` checks if rule has entity_id and uses the right function.

- [ ] **Step 6: Write coherence tests**

`tests/backend/test_coherence_entities.py`:
- Dashboard summary with entity_id == entity balance
- Forecasting with entity_id == entity balance
- Internal transfer: parent consolidated unchanged
- Budget scoped to entity: only counts entity's transactions
- Export with entity_id: only entity's data

- [ ] **Step 7: Run all tests**

Run: `python -m pytest tests/ -q`

- [ ] **Step 8: Commit**

```bash
git add backend/modules/ tests/
git commit -m "feat: scope dashboard, budget, export, forecasting, alerts by entity_id"
```

---

### Task 6: Frontend — EntityContext + selecteur + page entities

**Files:**
- Create: `frontend/src/core/EntityContext.tsx`
- Create: `frontend/src/modules/entities/EntityTree.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/core/Sidebar.tsx`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/types.ts`

- [ ] **Step 1: Create EntityContext.tsx**

React context with `selectedEntityId` + `setSelectedEntityId`, persisted in localStorage.

- [ ] **Step 2: Add entity API endpoints to api.ts**

`getEntities`, `getEntityTree`, `createEntity`, `updateEntity`, `deleteEntity`, `getEntityBalance`, `getConsolidatedBalance`

- [ ] **Step 3: Add Entity types to types.ts**

`Entity`, `EntityBalance`, `ConsolidatedBalance` interfaces.

- [ ] **Step 4: Create EntityTree.tsx**

Page showing internal entity tree with CRUD, balance display, and reference balance editing.

- [ ] **Step 5: Wrap App.tsx in EntityContext.Provider**

Add entity route to MODULE_ROUTES. EntityContext.Provider wraps all routes.

- [ ] **Step 6: Add entity selector to Sidebar.tsx**

Dropdown above nav items showing internal entity tree. Selection changes EntityContext.

- [ ] **Step 7: Build frontend**

Run: `cd frontend && npm run build`

- [ ] **Step 8: Commit**

```bash
git add frontend/
git commit -m "feat: frontend entity context, tree page, sidebar selector"
```

---

### Task 7: Verification finale

- [ ] **Step 1: check.py**

Run: `python tools/check.py`
Expected: PASS, 22 modules (21 + entities)

- [ ] **Step 2: Full test suite**

Run: `python -m pytest tests/ -v`
Expected: all pass

- [ ] **Step 3: App start**

Run: `python start.py`
Verify: app starts, entities page accessible, entity selector works

- [ ] **Step 4: Frontend build**

Run: `cd frontend && npm run build`
Expected: build succeeds
