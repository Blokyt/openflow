"""Tests for the centralized balance computation."""
import sqlite3
import pytest
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent


def _make_db(tmp_path):
    """Create a minimal test DB with required tables."""
    db = tmp_path / "test.db"
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
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
    # Montants toujours positifs ; le sens vient de from/to.
    conn.execute("INSERT INTO transactions (date, label, amount, from_entity_id, to_entity_id) VALUES ('2025-06-01', 'Vente', 500, 2, 1)")
    conn.execute("INSERT INTO transactions (date, label, amount, from_entity_id, to_entity_id) VALUES ('2025-06-02', 'Achat', 300, 1, 2)")
    conn.commit()
    result = compute_entity_balance(conn, 1)
    conn.close()
    assert result["balance"] == pytest.approx(1200.0)


def test_entity_balance_ignores_unrelated(tmp_path):
    from backend.core.balance import compute_entity_balance
    conn = _make_db(tmp_path)
    conn.execute("INSERT INTO entities (id, name, type) VALUES (1, 'BDA', 'internal')")
    conn.execute("INSERT INTO entities (id, name, type) VALUES (2, 'Club', 'internal')")
    conn.execute("INSERT INTO entities (id, name, type) VALUES (3, 'Ext', 'external')")
    conn.execute("INSERT INTO entity_balance_refs (entity_id, reference_date, reference_amount, updated_at) VALUES (1, '2025-01-01', 0, '2025-01-01')")
    conn.execute("INSERT INTO transactions (date, label, amount, from_entity_id, to_entity_id) VALUES ('2025-06-01', 'X', 100, 2, 3)")
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
    conn.execute("INSERT INTO transactions (date, label, amount, from_entity_id, to_entity_id) VALUES ('2025-06-01', 'Don', 200, 3, 1)")
    conn.execute("INSERT INTO transactions (date, label, amount, from_entity_id, to_entity_id) VALUES ('2025-06-02', 'Dep', 100, 2, 3)")
    conn.commit()
    result = compute_consolidated_balance(conn, 1)
    conn.close()
    assert result["own_balance"] == pytest.approx(1200.0)
    assert result["consolidated_balance"] == pytest.approx(1600.0)


def test_internal_transfer_conserves_total(tmp_path):
    """Un virement interne (entité interne -> entité interne) débite la source,
    crédite la cible, et laisse le consolidé inchangé. Cassé par l'ancien
    modèle de signe ; correct avec la convention from/to."""
    from backend.core.balance import compute_entity_balance, compute_consolidated_balance
    conn = _make_db(tmp_path)
    conn.execute("INSERT INTO entities (id, name, type, parent_id) VALUES (1, 'BDA', 'internal', NULL)")
    conn.execute("INSERT INTO entities (id, name, type, parent_id) VALUES (2, 'Cine', 'internal', 1)")
    conn.execute("INSERT INTO entity_balance_refs (entity_id, reference_date, reference_amount, updated_at) VALUES (1, '2025-01-01', 1000, '2025-01-01')")
    conn.execute("INSERT INTO entity_balance_refs (entity_id, reference_date, reference_amount, updated_at) VALUES (2, '2025-01-01', 500, '2025-01-01')")
    # Dotation interne : BDA (1) vire 100 a Cine (2), montant positif.
    conn.execute("INSERT INTO transactions (date, label, amount, from_entity_id, to_entity_id) VALUES ('2025-06-01', 'Dotation Cine', 100, 1, 2)")
    conn.commit()
    bda = compute_entity_balance(conn, 1)
    cine = compute_entity_balance(conn, 2)
    cons = compute_consolidated_balance(conn, 1)
    conn.close()
    assert bda["balance"] == pytest.approx(900.0)            # 1000 - 100
    assert cine["balance"] == pytest.approx(600.0)           # 500 + 100
    assert cons["consolidated_balance"] == pytest.approx(1500.0)  # inchangé


def test_entity_balance_no_ref(tmp_path):
    from backend.core.balance import compute_entity_balance
    conn = _make_db(tmp_path)
    conn.execute("INSERT INTO entities (id, name, type) VALUES (1, 'BDA', 'internal')")
    conn.execute("INSERT INTO transactions (date, label, amount, from_entity_id, to_entity_id) VALUES ('2025-06-01', 'In', 300, 2, 1)")
    conn.commit()
    result = compute_entity_balance(conn, 1)
    conn.close()
    assert result["reference_amount"] == pytest.approx(0.0)
    assert result["balance"] == pytest.approx(300.0)


def test_entity_balance_as_of_before_reference_date(client_and_db):
    """as_of antérieur à la date de référence : on remonte le temps depuis la
    référence en retranchant les flux intermédiaires (pas de double comptage).

    Régression : le bilan d'un exercice utilisait le solde à la veille de
    l'ouverture ; avec une référence posée en cours d'exercice, il renvoyait
    la référence brute puis ré-additionnait le réalisé -> disponibilités fausses.
    """
    import sqlite3
    from backend.core.balance import compute_entity_balance

    client, db_path = client_and_db
    ent = client.post("/api/entities/", json={"name": "Club", "type": "internal"}).json()
    ext = client.post("/api/entities/", json={"name": "Ext", "type": "external"}).json()

    # Flux : +10000 le 10/05, -3000 le 20/05. Référence posée le 26/06 : 93836.
    client.post("/api/transactions/", json={
        "date": "2026-05-10", "label": "in", "amount": 10000,
        "from_entity_id": ext["id"], "to_entity_id": ent["id"],
    })
    client.post("/api/transactions/", json={
        "date": "2026-05-20", "label": "out", "amount": 3000,
        "from_entity_id": ent["id"], "to_entity_id": ext["id"],
    })
    client.put(f"/api/entities/{ent['id']}/balance-ref", json={
        "reference_date": "2026-06-26", "reference_amount": 93836
    })

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        # Au 30/06 (>= ref) : référence seule, aucun flux depuis.
        assert compute_entity_balance(conn, ent["id"], as_of_date="2026-06-30")["balance"] == 93836
        # Au 30/04 (< ref, avant les flux) : ref - (+10000 - 3000) = 86836.
        assert compute_entity_balance(conn, ent["id"], as_of_date="2026-04-30")["balance"] == 86836
        # Au 15/05 (< ref, entre les deux flux) : ref - (-3000) = 96836.
        assert compute_entity_balance(conn, ent["id"], as_of_date="2026-05-15")["balance"] == 96836
    finally:
        conn.close()


def test_subtree_ids_guards_against_parent_cycle(tmp_path):
    """Un cycle parent_id (A.parent=B, B.parent=A) créé par erreur en base ne doit
    jamais faire boucler indéfiniment le calcul de solde consolidé (FIX 3 :
    garde anti-cycle `e.id NOT IN (SELECT id FROM tree)` dans la CTE récursive)."""
    from backend.core.balance import get_subtree_ids, compute_consolidated_balance

    conn = _make_db(tmp_path)
    conn.execute("INSERT INTO entities (id, name, type, parent_id) VALUES (1, 'A', 'internal', 2)")
    conn.execute("INSERT INTO entities (id, name, type, parent_id) VALUES (2, 'B', 'internal', 1)")
    conn.execute("INSERT INTO entity_balance_refs (entity_id, reference_date, reference_amount, updated_at) VALUES (1, '2025-01-01', 100, '2025-01-01')")
    conn.execute("INSERT INTO entity_balance_refs (entity_id, reference_date, reference_amount, updated_at) VALUES (2, '2025-01-01', 200, '2025-01-01')")
    conn.commit()

    # Termine sans boucle infinie et ne renvoie chaque id qu'une seule fois.
    ids = get_subtree_ids(conn, 1)
    assert sorted(ids) == [1, 2]

    result = compute_consolidated_balance(conn, 1)
    conn.close()
    assert result["consolidated_balance"] == pytest.approx(300.0)
