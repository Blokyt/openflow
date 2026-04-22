"""Tests for aggregate balance mode (Sujet 2.1).

Sign convention in OpenFlow:
  - amount > 0  → money flowing INTO to_entity_id
  - amount < 0  → money flowing OUT OF from_entity_id
    (when negative, the to_entity_id also sees the negative amount as incoming,
     reducing its balance — by design for internal allocations)

Scenario:
  Root  (aggregate mode) — ref 2025-01-01 = 10000 (consolidated bank statement)
  ├── A (own mode)        — ref 2025-01-01 = 4000
  └── B (own mode)        — ref 2025-01-01 = 3000

Transactions after 2025-01-01:
  - 2025-02-01: external → A   +500  (subtree external inflow)
  - 2025-02-15: A → external   -200  (subtree external outflow, from_entity=A, amount=-200)
  - 2025-03-01: A → B          -1000 (internal allocation, amount=-1000 per sign convention)

Expected results (per actual sign convention):
  A.own  = 4000 + 500 - 200 - 1000 = 3300
           (incoming SUM(amount WHERE to=A) = 500; outgoing SUM(ABS WHERE from=A,<0) = 200+1000)
  B.own  = 3000 + (-1000) = 2000
           (incoming SUM(amount WHERE to=B) = -1000)
  Root.consolidated (aggregate):
         = 10000 + 500 (external in, crosses subtree boundary) - 200 (external out) = 10300
         The A→B internal transfer does NOT cross the boundary → ignored ✓
  Root.own = Root.consolidated - A.consolidated - B.consolidated
           = 10300 - 3300 - 2000 = 5000
"""
import sqlite3
import pytest
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent


# ---------------------------------------------------------------------------
# Helpers to build a self-contained DB
# ---------------------------------------------------------------------------

def _make_db(tmp_path):
    """Create a minimal test DB with balance_mode column."""
    db = tmp_path / "agg_test.db"
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE entities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        type TEXT NOT NULL DEFAULT 'internal',
        parent_id INTEGER,
        balance_mode TEXT NOT NULL DEFAULT 'own'
    )""")
    conn.execute("""CREATE TABLE entity_balance_refs (
        entity_id INTEGER PRIMARY KEY,
        reference_date TEXT NOT NULL,
        reference_amount REAL NOT NULL DEFAULT 0.0,
        updated_at TEXT NOT NULL
    )""")
    conn.execute("""CREATE TABLE transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        label TEXT NOT NULL,
        amount REAL NOT NULL,
        from_entity_id INTEGER,
        to_entity_id INTEGER
    )""")
    conn.commit()
    return conn


def _seed(conn):
    """Seed the scenario described in the module docstring."""
    # Entities: root=1 (aggregate), A=2 (own, child of root), B=3 (own, child of root)
    # external=99 used as the external counterpart
    conn.execute(
        "INSERT INTO entities (id, name, type, parent_id, balance_mode) VALUES (1, 'Root', 'internal', NULL, 'aggregate')"
    )
    conn.execute(
        "INSERT INTO entities (id, name, type, parent_id, balance_mode) VALUES (2, 'A', 'internal', 1, 'own')"
    )
    conn.execute(
        "INSERT INTO entities (id, name, type, parent_id, balance_mode) VALUES (3, 'B', 'internal', 1, 'own')"
    )
    conn.execute(
        "INSERT INTO entities (id, name, type, parent_id, balance_mode) VALUES (99, 'External', 'external', NULL, 'own')"
    )

    # Balance refs
    conn.execute(
        "INSERT INTO entity_balance_refs (entity_id, reference_date, reference_amount, updated_at) VALUES (1, '2025-01-01', 10000, '2025-01-01')"
    )
    conn.execute(
        "INSERT INTO entity_balance_refs (entity_id, reference_date, reference_amount, updated_at) VALUES (2, '2025-01-01', 4000, '2025-01-01')"
    )
    conn.execute(
        "INSERT INTO entity_balance_refs (entity_id, reference_date, reference_amount, updated_at) VALUES (3, '2025-01-01', 3000, '2025-01-01')"
    )

    # Transactions
    # external → A +500 (external inflow)
    conn.execute(
        "INSERT INTO transactions (date, label, amount, from_entity_id, to_entity_id) VALUES ('2025-02-01', 'ext-A', 500, 99, 2)"
    )
    # A → external -200 (external outflow; from_entity=A, amount<0)
    conn.execute(
        "INSERT INTO transactions (date, label, amount, from_entity_id, to_entity_id) VALUES ('2025-02-15', 'A-ext', -200, 2, 99)"
    )
    # A → B -1000 (internal allocation; amount=-1000 per sign convention)
    conn.execute(
        "INSERT INTO transactions (date, label, amount, from_entity_id, to_entity_id) VALUES ('2025-03-01', 'A-B', -1000, 2, 3)"
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Direct balance.py function tests
# ---------------------------------------------------------------------------

class TestAggregateDirect:
    """Test balance functions directly against a seeded connection."""

    def setup_method(self, method):
        import tempfile
        self.tmp = tempfile.mkdtemp()
        self.conn = _make_db(Path(self.tmp))
        _seed(self.conn)

    def teardown_method(self, method):
        self.conn.close()

    def test_child_A_own_balance(self):
        from backend.core.balance import compute_entity_balance
        result = compute_entity_balance(self.conn, 2)
        # A: ref=4000
        # incoming: SUM(amount WHERE to_entity=A) = 500 (ext→A)
        # outgoing: SUM(ABS WHERE from_entity=A AND amount<0) = 200 (A→ext) + 1000 (A→B) = 1200
        # balance = 4000 + 500 - 1200 = 3300
        assert result["balance"] == pytest.approx(3300.0)
        assert result["mode"] == "own"

    def test_child_B_own_balance(self):
        from backend.core.balance import compute_entity_balance
        result = compute_entity_balance(self.conn, 3)
        # B: ref=3000
        # incoming: SUM(amount WHERE to_entity=B) = -1000 (A→B, amount=-1000)
        # outgoing: SUM(ABS WHERE from_entity=B AND amount<0) = 0
        # balance = 3000 + (-1000) = 2000
        assert result["balance"] == pytest.approx(2000.0)
        assert result["mode"] == "own"

    def test_root_consolidated_balance(self):
        from backend.core.balance import compute_consolidated_balance
        result = compute_consolidated_balance(self.conn, 1)
        # Root aggregate: ref=10000
        # External inflow: amount=500, to_entity=A (in subtree), from_entity=99 (NOT in subtree) → +500
        # External outflow: amount=-200, from_entity=A (in subtree), to_entity=99 (NOT in subtree) → -200
        # A→B: both A and B are in subtree → NOT an external crossing → ignored
        # consolidated = 10000 + 500 - 200 = 10300
        assert result["consolidated_balance"] == pytest.approx(10300.0)
        assert result["mode"] == "aggregate"

    def test_root_own_balance_derived(self):
        from backend.core.balance import compute_entity_balance
        result = compute_entity_balance(self.conn, 1)
        # Root.own = Root.consolidated - A.consolidated - B.consolidated
        # A.consolidated = 3300, B.consolidated = 2000
        # Root.own = 10300 - 3300 - 2000 = 5000
        assert result["balance"] == pytest.approx(5000.0)
        assert result["mode"] == "aggregate"

    def test_root_consolidated_children_detail(self):
        from backend.core.balance import compute_consolidated_balance
        result = compute_consolidated_balance(self.conn, 1)
        children_by_id = {c["entity_id"]: c for c in result["children"]}
        assert children_by_id[2]["consolidated_balance"] == pytest.approx(3300.0)
        assert children_by_id[3]["consolidated_balance"] == pytest.approx(2000.0)

    def test_root_own_balance_in_consolidated(self):
        from backend.core.balance import compute_consolidated_balance
        result = compute_consolidated_balance(self.conn, 1)
        assert result["own_balance"] == pytest.approx(5000.0)

    def test_internal_transfer_no_aggregate_impact(self):
        """A→B transfer should not move Root.consolidated (both sides in subtree)."""
        from backend.core.balance import compute_consolidated_balance
        # Without the internal transfer, consolidated would be:
        # 10000 + 500 (ext in) - 200 (ext out) = 10300
        # With A→B (-1000): still 10300 — internal boundary not crossed
        result = compute_consolidated_balance(self.conn, 1)
        assert result["consolidated_balance"] == pytest.approx(10300.0)

    def test_as_of_date_before_any_tx(self):
        from backend.core.balance import compute_consolidated_balance
        # As of 2025-01-01 (reference date itself) — all tx are strictly after
        result = compute_consolidated_balance(self.conn, 1, as_of_date="2025-01-15")
        # No tx before 2025-01-15 (all tx are 2025-02-01+) but ref date 2025-01-01 means >= 2025-01-01
        # So as_of=2025-01-15 filters tx <= 2025-01-15, but tx are all 2025-02+, none pass
        assert result["consolidated_balance"] == pytest.approx(10000.0)

    def test_as_of_date_partial(self):
        from backend.core.balance import compute_consolidated_balance
        # As of 2025-02-10: only +500 (ext→A, 2025-02-01) has happened; A→ext (-200) is 2025-02-15
        result = compute_consolidated_balance(self.conn, 1, as_of_date="2025-02-10")
        assert result["consolidated_balance"] == pytest.approx(10500.0)

    def test_no_ref_defaults_zero(self):
        """An aggregate entity with no ref defaults to external_delta only."""
        from backend.core.balance import compute_consolidated_balance
        # Remove root's ref
        self.conn.execute("DELETE FROM entity_balance_refs WHERE entity_id = 1")
        self.conn.commit()
        result = compute_consolidated_balance(self.conn, 1)
        # ref=0, external_delta = +500 - 200 = 300
        assert result["consolidated_balance"] == pytest.approx(300.0)


# ---------------------------------------------------------------------------
# API endpoint tests (via TestClient)
# ---------------------------------------------------------------------------

class TestAggregateAPI:
    """Test the /api/entities/{id}/balance and /consolidated endpoints."""

    @pytest.fixture(autouse=True)
    def setup_client(self, client_and_db):
        import sqlite3 as _sq
        self.client, self.db_path = client_and_db
        conn = _sq.connect(str(self.db_path))
        conn.row_factory = _sq.Row
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()

        # Create root (aggregate)
        cur = conn.execute(
            "INSERT INTO entities (name, type, parent_id, is_default, is_divers, color, position, balance_mode, created_at, updated_at) "
            "VALUES ('TestRoot', 'internal', NULL, 0, 0, '#6B7280', 10, 'aggregate', ?, ?)",
            (now, now),
        )
        self.root_id = cur.lastrowid

        # Create child A (own)
        cur = conn.execute(
            "INSERT INTO entities (name, type, parent_id, is_default, is_divers, color, position, balance_mode, created_at, updated_at) "
            "VALUES ('TestA', 'internal', ?, 0, 0, '#6B7280', 11, 'own', ?, ?)",
            (self.root_id, now, now),
        )
        self.a_id = cur.lastrowid

        # Create child B (own)
        cur = conn.execute(
            "INSERT INTO entities (name, type, parent_id, is_default, is_divers, color, position, balance_mode, created_at, updated_at) "
            "VALUES ('TestB', 'internal', ?, 0, 0, '#6B7280', 12, 'own', ?, ?)",
            (self.root_id, now, now),
        )
        self.b_id = cur.lastrowid

        # Create external entity
        cur = conn.execute(
            "INSERT INTO entities (name, type, parent_id, is_default, is_divers, color, position, balance_mode, created_at, updated_at) "
            "VALUES ('TestExt', 'external', NULL, 0, 0, '#6B7280', 13, 'own', ?, ?)",
            (now, now),
        )
        self.ext_id = cur.lastrowid

        # Balance refs
        conn.execute(
            "INSERT INTO entity_balance_refs (entity_id, reference_date, reference_amount, updated_at) VALUES (?, '2025-01-01', 10000, ?)",
            (self.root_id, now),
        )
        conn.execute(
            "INSERT INTO entity_balance_refs (entity_id, reference_date, reference_amount, updated_at) VALUES (?, '2025-01-01', 4000, ?)",
            (self.a_id, now),
        )
        conn.execute(
            "INSERT INTO entity_balance_refs (entity_id, reference_date, reference_amount, updated_at) VALUES (?, '2025-01-01', 3000, ?)",
            (self.b_id, now),
        )

        # Transactions — full schema requires created_at and updated_at
        conn.execute(
            "INSERT INTO transactions (date, label, amount, from_entity_id, to_entity_id, created_at, updated_at) VALUES ('2025-02-01', 'ext-A', 500, ?, ?, ?, ?)",
            (self.ext_id, self.a_id, now, now),
        )
        conn.execute(
            "INSERT INTO transactions (date, label, amount, from_entity_id, to_entity_id, created_at, updated_at) VALUES ('2025-02-15', 'A-ext', -200, ?, ?, ?, ?)",
            (self.a_id, self.ext_id, now, now),
        )
        conn.execute(
            "INSERT INTO transactions (date, label, amount, from_entity_id, to_entity_id, created_at, updated_at) VALUES ('2025-03-01', 'A-B', -1000, ?, ?, ?, ?)",
            (self.a_id, self.b_id, now, now),
        )
        conn.commit()
        conn.close()

    def test_api_child_a_balance(self):
        r = self.client.get(f"/api/entities/{self.a_id}/balance")
        assert r.status_code == 200
        data = r.json()
        assert pytest.approx(data["balance"], abs=0.01) == 3300.0

    def test_api_child_b_balance(self):
        r = self.client.get(f"/api/entities/{self.b_id}/balance")
        assert r.status_code == 200
        data = r.json()
        assert pytest.approx(data["balance"], abs=0.01) == 2000.0

    def test_api_root_consolidated(self):
        r = self.client.get(f"/api/entities/{self.root_id}/consolidated")
        assert r.status_code == 200
        data = r.json()
        assert pytest.approx(data["consolidated_balance"], abs=0.01) == 10300.0
        assert data.get("mode") == "aggregate"

    def test_api_root_balance_own_derived(self):
        r = self.client.get(f"/api/entities/{self.root_id}/balance")
        assert r.status_code == 200
        data = r.json()
        assert pytest.approx(data["balance"], abs=0.01) == 5000.0
        assert data.get("mode") == "aggregate"

    def test_api_root_consolidated_own_balance(self):
        r = self.client.get(f"/api/entities/{self.root_id}/consolidated")
        assert r.status_code == 200
        data = r.json()
        assert pytest.approx(data["own_balance"], abs=0.01) == 5000.0

    def test_api_create_aggregate_root(self):
        """Creating a root entity with balance_mode='aggregate' should succeed."""
        r = self.client.post("/api/entities/", json={
            "name": "AnotherRoot",
            "type": "internal",
            "balance_mode": "aggregate",
        })
        assert r.status_code == 201
        assert r.json()["balance_mode"] == "aggregate"

    def test_api_create_aggregate_child_rejected(self):
        """Creating a child entity with balance_mode='aggregate' should fail."""
        r = self.client.post("/api/entities/", json={
            "name": "ChildAggregate",
            "type": "internal",
            "parent_id": self.root_id,
            "balance_mode": "aggregate",
        })
        assert r.status_code == 400

    def test_api_list_entities_includes_balance_mode(self):
        r = self.client.get("/api/entities/")
        assert r.status_code == 200
        entities = r.json()
        root_entities = [e for e in entities if e["id"] == self.root_id]
        assert len(root_entities) == 1
        assert root_entities[0]["balance_mode"] == "aggregate"

    def test_api_get_entity_includes_balance_mode(self):
        r = self.client.get(f"/api/entities/{self.root_id}")
        assert r.status_code == 200
        assert r.json()["balance_mode"] == "aggregate"

    def test_api_update_balance_mode_to_aggregate(self):
        """Updating a root entity's balance_mode to aggregate should succeed."""
        r = self.client.post("/api/entities/", json={
            "name": "UpdateTestRoot",
            "type": "internal",
        })
        assert r.status_code == 201
        new_id = r.json()["id"]
        r = self.client.put(f"/api/entities/{new_id}", json={"balance_mode": "aggregate"})
        assert r.status_code == 200
        assert r.json()["balance_mode"] == "aggregate"

    def test_api_update_child_to_aggregate_rejected(self):
        """Updating a child entity's balance_mode to aggregate should fail."""
        r = self.client.put(f"/api/entities/{self.a_id}", json={"balance_mode": "aggregate"})
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# Regression: own-mode behaviour unchanged
# ---------------------------------------------------------------------------

class TestOwnModeRegression:
    """Verify 'own' mode is unaffected when no entity uses aggregate mode."""

    def _make_own_db(self, tmp_path):
        conn = _make_db(tmp_path)
        conn.execute(
            "INSERT INTO entities (id, name, type, parent_id, balance_mode) VALUES (1, 'Parent', 'internal', NULL, 'own')"
        )
        conn.execute(
            "INSERT INTO entities (id, name, type, parent_id, balance_mode) VALUES (2, 'Child', 'internal', 1, 'own')"
        )
        conn.execute(
            "INSERT INTO entities (id, name, type, parent_id, balance_mode) VALUES (99, 'Ext', 'external', NULL, 'own')"
        )
        conn.execute(
            "INSERT INTO entity_balance_refs (entity_id, reference_date, reference_amount, updated_at) VALUES (1, '2025-01-01', 1000, '2025-01-01')"
        )
        conn.execute(
            "INSERT INTO entity_balance_refs (entity_id, reference_date, reference_amount, updated_at) VALUES (2, '2025-01-01', 500, '2025-01-01')"
        )
        conn.execute(
            "INSERT INTO transactions (date, label, amount, from_entity_id, to_entity_id) VALUES ('2025-06-01', 'Don', 200, 99, 1)"
        )
        conn.execute(
            "INSERT INTO transactions (date, label, amount, from_entity_id, to_entity_id) VALUES ('2025-06-02', 'Dep', -100, 2, 99)"
        )
        conn.commit()
        return conn

    def test_own_entity_balance(self, tmp_path):
        from backend.core.balance import compute_entity_balance
        conn = self._make_own_db(tmp_path)
        result = compute_entity_balance(conn, 1)
        conn.close()
        assert result["balance"] == pytest.approx(1200.0)
        assert result["mode"] == "own"

    def test_own_consolidated_balance(self, tmp_path):
        from backend.core.balance import compute_consolidated_balance
        conn = self._make_own_db(tmp_path)
        result = compute_consolidated_balance(conn, 1)
        conn.close()
        assert result["own_balance"] == pytest.approx(1200.0)
        assert result["consolidated_balance"] == pytest.approx(1600.0)
