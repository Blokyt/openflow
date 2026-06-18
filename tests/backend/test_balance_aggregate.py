"""Tests pour le mode de solde agrégé (Sujet 2.1).

Convention (refonte C1+C2) :
  - `amount` est un entier de centimes, TOUJOURS POSITIF.
  - Le sens vient de from_entity_id -> to_entity_id :
      recette  = from EXTERNE -> to INTERNE
      dépense  = from INTERNE -> to EXTERNE
      virement = INTERNE -> INTERNE
  - Solde propre = reference + SUM(amount où to=X) - SUM(amount où from=X).

Scénario :
  Root  (mode aggregate) — ref 2025-01-01 = 10000 centimes
  ├── A (mode own)        — ref 2025-01-01 = 4000 centimes
  └── B (mode own)        — ref 2025-01-01 = 3000 centimes

Transactions (après 2025-01-01, en centimes) :
  - 2025-02-01 : ext -> A   amount=500   (recette : entrée externe dans le sous-arbre)
  - 2025-02-15 : A   -> ext amount=200   (dépense : sortie externe du sous-arbre)
  - 2025-03-01 : A   -> B   amount=1000  (virement interne, montant positif)

Résultats attendus :
  A.own  = 4000 + 500 (to=A) - 200 (from=A, tx ext) - 1000 (from=A, tx B) = 3300
  B.own  = 3000 + 1000 (to=B, virement A→B) = 4000
  Root.consolidated (aggregate) = 10000 + 500 (entrée externe) - 200 (sortie externe) = 10300
    (le virement A→B est interne au sous-arbre → ignoré)
  Root.own = Root.consolidated - A.consolidated - B.consolidated
           = 10300 - 3300 - 4000 = 3000
"""
import sqlite3
import pytest
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent


# ---------------------------------------------------------------------------
# Helpers pour construire une DB autonome
# ---------------------------------------------------------------------------

def _make_db(tmp_path):
    """Crée une DB de test minimale avec la colonne balance_mode."""
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
        amount INTEGER NOT NULL,
        from_entity_id INTEGER,
        to_entity_id INTEGER
    )""")
    conn.commit()
    return conn


def _seed(conn):
    """Insère le scénario décrit dans la docstring du module.

    Tous les montants sont positifs. Le sens est encodé via from/to.
    ext=99 est l'entité externe de référence.
    """
    # Entités : root=1 (aggregate), A=2 (own, enfant de root), B=3 (own, enfant de root)
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

    # Références de solde (en centimes)
    conn.execute(
        "INSERT INTO entity_balance_refs (entity_id, reference_date, reference_amount, updated_at) VALUES (1, '2025-01-01', 10000, '2025-01-01')"
    )
    conn.execute(
        "INSERT INTO entity_balance_refs (entity_id, reference_date, reference_amount, updated_at) VALUES (2, '2025-01-01', 4000, '2025-01-01')"
    )
    conn.execute(
        "INSERT INTO entity_balance_refs (entity_id, reference_date, reference_amount, updated_at) VALUES (3, '2025-01-01', 3000, '2025-01-01')"
    )

    # Transactions (montants positifs, sens via from/to)
    # ext -> A : recette 500 centimes
    conn.execute(
        "INSERT INTO transactions (date, label, amount, from_entity_id, to_entity_id) VALUES ('2025-02-01', 'ext-A', 500, 99, 2)"
    )
    # A -> ext : dépense 200 centimes
    conn.execute(
        "INSERT INTO transactions (date, label, amount, from_entity_id, to_entity_id) VALUES ('2025-02-15', 'A-ext', 200, 2, 99)"
    )
    # A -> B : virement interne 1000 centimes
    conn.execute(
        "INSERT INTO transactions (date, label, amount, from_entity_id, to_entity_id) VALUES ('2025-03-01', 'A-B', 1000, 2, 3)"
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Tests directs sur les fonctions de balance.py
# ---------------------------------------------------------------------------

class TestAggregateDirect:
    """Tests des fonctions balance.py sur une connexion seedée."""

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
        # A : ref=4000
        # entrées  (to=A)   : 500 (ext→A)
        # sorties  (from=A) : 200 (A→ext) + 1000 (A→B) = 1200
        # solde = 4000 + 500 - 1200 = 3300
        assert result["balance"] == pytest.approx(3300.0)
        assert result["mode"] == "own"

    def test_child_B_own_balance(self):
        from backend.core.balance import compute_entity_balance
        result = compute_entity_balance(self.conn, 3)
        # B : ref=3000
        # entrées  (to=B)   : 1000 (A→B, montant positif)
        # sorties  (from=B) : 0
        # solde = 3000 + 1000 = 4000
        assert result["balance"] == pytest.approx(4000.0)
        assert result["mode"] == "own"

    def test_root_consolidated_balance(self):
        from backend.core.balance import compute_consolidated_balance
        result = compute_consolidated_balance(self.conn, 1)
        # Root aggregate : ref=10000
        # Entrée externe : amount=500, to=A (dans sous-arbre), from=99 (hors sous-arbre) -> +500
        # Sortie externe : amount=200, from=A (dans sous-arbre), to=99 (hors sous-arbre) -> -200
        # A->B : les deux sont dans le sous-arbre -> ignoré
        # consolidé = 10000 + 500 - 200 = 10300
        assert result["consolidated_balance"] == pytest.approx(10300.0)
        assert result["mode"] == "aggregate"

    def test_root_own_balance_derived(self):
        from backend.core.balance import compute_entity_balance
        result = compute_entity_balance(self.conn, 1)
        # Root.own = Root.consolidated - A.consolidated - B.consolidated
        # = 10300 - 3300 - 4000 = 3000
        assert result["balance"] == pytest.approx(3000.0)
        assert result["mode"] == "aggregate"

    def test_root_consolidated_children_detail(self):
        from backend.core.balance import compute_consolidated_balance
        result = compute_consolidated_balance(self.conn, 1)
        children_by_id = {c["entity_id"]: c for c in result["children"]}
        assert children_by_id[2]["consolidated_balance"] == pytest.approx(3300.0)
        assert children_by_id[3]["consolidated_balance"] == pytest.approx(4000.0)

    def test_root_own_balance_in_consolidated(self):
        from backend.core.balance import compute_consolidated_balance
        result = compute_consolidated_balance(self.conn, 1)
        assert result["own_balance"] == pytest.approx(3000.0)

    def test_internal_transfer_no_aggregate_impact(self):
        """Le virement A->B ne doit pas modifier Root.consolidated (les deux côtés sont dans le sous-arbre)."""
        from backend.core.balance import compute_consolidated_balance
        # Sans le virement : 10000 + 500 - 200 = 10300
        # Avec le virement A->B (interne) : toujours 10300
        result = compute_consolidated_balance(self.conn, 1)
        assert result["consolidated_balance"] == pytest.approx(10300.0)

    def test_as_of_date_before_any_tx(self):
        from backend.core.balance import compute_consolidated_balance
        # Au 2025-01-15 : aucune tx (toutes sont 2025-02+), consolidé = ref seul = 10000
        result = compute_consolidated_balance(self.conn, 1, as_of_date="2025-01-15")
        assert result["consolidated_balance"] == pytest.approx(10000.0)

    def test_as_of_date_partial(self):
        from backend.core.balance import compute_consolidated_balance
        # Au 2025-02-10 : seule ext→A (500, 2025-02-01) a eu lieu ; A→ext (2025-02-15) pas encore
        result = compute_consolidated_balance(self.conn, 1, as_of_date="2025-02-10")
        assert result["consolidated_balance"] == pytest.approx(10500.0)

    def test_no_ref_defaults_zero(self):
        """Une entité aggregate sans référence utilise ref=0 (delta externe uniquement)."""
        from backend.core.balance import compute_consolidated_balance
        self.conn.execute("DELETE FROM entity_balance_refs WHERE entity_id = 1")
        self.conn.commit()
        result = compute_consolidated_balance(self.conn, 1)
        # ref=0, external_delta = +500 - 200 = 300
        assert result["consolidated_balance"] == pytest.approx(300.0)


# ---------------------------------------------------------------------------
# Tests via l'API (TestClient)
# ---------------------------------------------------------------------------

class TestAggregateAPI:
    """Tests des endpoints /api/entities/{id}/balance et /consolidated."""

    @pytest.fixture(autouse=True)
    def setup_client(self, client_and_db):
        import sqlite3 as _sq
        self.client, self.db_path = client_and_db
        conn = _sq.connect(str(self.db_path))
        conn.row_factory = _sq.Row
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()

        # Root (aggregate)
        cur = conn.execute(
            "INSERT INTO entities (name, type, parent_id, is_default, is_divers, color, position, balance_mode, created_at, updated_at) "
            "VALUES ('TestRoot', 'internal', NULL, 0, 0, '#6B7280', 10, 'aggregate', ?, ?)",
            (now, now),
        )
        self.root_id = cur.lastrowid

        # Enfant A (own)
        cur = conn.execute(
            "INSERT INTO entities (name, type, parent_id, is_default, is_divers, color, position, balance_mode, created_at, updated_at) "
            "VALUES ('TestA', 'internal', ?, 0, 0, '#6B7280', 11, 'own', ?, ?)",
            (self.root_id, now, now),
        )
        self.a_id = cur.lastrowid

        # Enfant B (own)
        cur = conn.execute(
            "INSERT INTO entities (name, type, parent_id, is_default, is_divers, color, position, balance_mode, created_at, updated_at) "
            "VALUES ('TestB', 'internal', ?, 0, 0, '#6B7280', 12, 'own', ?, ?)",
            (self.root_id, now, now),
        )
        self.b_id = cur.lastrowid

        # Entité externe
        cur = conn.execute(
            "INSERT INTO entities (name, type, parent_id, is_default, is_divers, color, position, balance_mode, created_at, updated_at) "
            "VALUES ('TestExt', 'external', NULL, 0, 0, '#6B7280', 13, 'own', ?, ?)",
            (now, now),
        )
        self.ext_id = cur.lastrowid

        # Références de solde (centimes)
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

        # Transactions (montants positifs, sens via from/to)
        # ext -> A : recette 500 centimes
        conn.execute(
            "INSERT INTO transactions (date, label, amount, from_entity_id, to_entity_id, created_at, updated_at) VALUES ('2025-02-01', 'ext-A', 500, ?, ?, ?, ?)",
            (self.ext_id, self.a_id, now, now),
        )
        # A -> ext : dépense 200 centimes
        conn.execute(
            "INSERT INTO transactions (date, label, amount, from_entity_id, to_entity_id, created_at, updated_at) VALUES ('2025-02-15', 'A-ext', 200, ?, ?, ?, ?)",
            (self.a_id, self.ext_id, now, now),
        )
        # A -> B : virement interne 1000 centimes
        conn.execute(
            "INSERT INTO transactions (date, label, amount, from_entity_id, to_entity_id, created_at, updated_at) VALUES ('2025-03-01', 'A-B', 1000, ?, ?, ?, ?)",
            (self.a_id, self.b_id, now, now),
        )
        conn.commit()
        conn.close()

    def test_api_child_a_balance(self):
        r = self.client.get(f"/api/entities/{self.a_id}/balance")
        assert r.status_code == 200
        data = r.json()
        # A : 4000 + 500 - 1200 = 3300
        assert pytest.approx(data["balance"], abs=0.01) == 3300.0

    def test_api_child_b_balance(self):
        r = self.client.get(f"/api/entities/{self.b_id}/balance")
        assert r.status_code == 200
        data = r.json()
        # B : 3000 + 1000 = 4000
        assert pytest.approx(data["balance"], abs=0.01) == 4000.0

    def test_api_root_consolidated(self):
        r = self.client.get(f"/api/entities/{self.root_id}/consolidated")
        assert r.status_code == 200
        data = r.json()
        # Root aggregate : 10000 + 500 - 200 = 10300
        assert pytest.approx(data["consolidated_balance"], abs=0.01) == 10300.0
        assert data.get("mode") == "aggregate"

    def test_api_root_balance_own_derived(self):
        r = self.client.get(f"/api/entities/{self.root_id}/balance")
        assert r.status_code == 200
        data = r.json()
        # Root.own = 10300 - 3300 - 4000 = 3000
        assert pytest.approx(data["balance"], abs=0.01) == 3000.0
        assert data.get("mode") == "aggregate"

    def test_api_root_consolidated_own_balance(self):
        r = self.client.get(f"/api/entities/{self.root_id}/consolidated")
        assert r.status_code == 200
        data = r.json()
        assert pytest.approx(data["own_balance"], abs=0.01) == 3000.0

    def test_api_create_aggregate_root(self):
        """Créer une entité racine en balance_mode='aggregate' doit réussir."""
        r = self.client.post("/api/entities/", json={
            "name": "AnotherRoot",
            "type": "internal",
            "balance_mode": "aggregate",
        })
        assert r.status_code == 201
        assert r.json()["balance_mode"] == "aggregate"

    def test_api_create_aggregate_child_rejected(self):
        """Créer un enfant en balance_mode='aggregate' doit échouer (400)."""
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
        """Mettre à jour le balance_mode d'une entité racine en 'aggregate' doit réussir."""
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
        """Mettre à jour le balance_mode d'un enfant en 'aggregate' doit échouer (400)."""
        r = self.client.put(f"/api/entities/{self.a_id}", json={"balance_mode": "aggregate"})
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# Régression : mode 'own' inchangé
# ---------------------------------------------------------------------------

class TestOwnModeRegression:
    """Vérifie que le mode 'own' est inchangé quand aucune entité n'utilise aggregate."""

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
        # Recette pour Parent : ext(99) -> Parent(1), 200 centimes
        conn.execute(
            "INSERT INTO transactions (date, label, amount, from_entity_id, to_entity_id) VALUES ('2025-06-01', 'Don', 200, 99, 1)"
        )
        # Dépense pour Child : Child(2) -> ext(99), 100 centimes
        conn.execute(
            "INSERT INTO transactions (date, label, amount, from_entity_id, to_entity_id) VALUES ('2025-06-02', 'Dep', 100, 2, 99)"
        )
        conn.commit()
        return conn

    def test_own_entity_balance(self, tmp_path):
        from backend.core.balance import compute_entity_balance
        conn = self._make_own_db(tmp_path)
        result = compute_entity_balance(conn, 1)
        conn.close()
        # Parent : 1000 + 200 (entrée) - 0 (aucune sortie de 1) = 1200
        assert result["balance"] == pytest.approx(1200.0)
        assert result["mode"] == "own"

    def test_own_consolidated_balance(self, tmp_path):
        from backend.core.balance import compute_consolidated_balance
        conn = self._make_own_db(tmp_path)
        result = compute_consolidated_balance(conn, 1)
        conn.close()
        # Parent propre : 1200
        # Child propre  : 500 + 0 - 100 = 400
        # Consolidé     : 1200 + 400 = 1600
        assert result["own_balance"] == pytest.approx(1200.0)
        assert result["consolidated_balance"] == pytest.approx(1600.0)
