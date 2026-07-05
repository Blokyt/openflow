"""Module submissions : création et lectures scopées."""
import sqlite3

NOW = "2026-01-01T00:00:00+00:00"


def _entity(db_path, name, type="internal", parent_id=None):
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute(
            "INSERT INTO entities (name, type, parent_id, is_default, color, position, created_at, updated_at) "
            "VALUES (?, ?, ?, 0, '#000000', 0, ?, ?)",
            (name, type, parent_id, NOW, NOW),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def test_submissions_module_active(client):
    mods = client.get("/api/modules").json()
    assert any(m["id"] == "submissions" for m in mods)


def test_submissions_table_exists(client_and_db):
    _, db_path = client_and_db
    conn = sqlite3.connect(str(db_path))
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(transaction_submissions)").fetchall()}
    finally:
        conn.close()
    assert {
        "id", "date", "label", "description", "amount", "category_id",
        "entity_id", "counterparty_entity_id", "direction", "status",
        "submitted_by", "reviewed_by", "reviewed_at", "review_comment",
        "transaction_id", "created_at", "updated_at",
    } <= cols


def _payload(entity_id, counterparty_id, **over):
    p = {
        "date": "2026-05-10", "label": "Courses atelier", "description": "Farine et beurre",
        "amount": 4550, "category_id": None, "entity_id": entity_id,
        "counterparty_entity_id": counterparty_id, "direction": "expense",
    }
    p.update(over)
    return p


def _setup_tree(db_path):
    """BDA > Gastronomine > Cave ; CCMP à part ; un tiers externe."""
    bda = _entity(db_path, "BDA")
    gastro = _entity(db_path, "Gastronomine", parent_id=bda)
    cave = _entity(db_path, "Cave", parent_id=gastro)
    ccmp = _entity(db_path, "CCMP", parent_id=bda)
    fournisseur = _entity(db_path, "Boulangerie Martin", type="external")
    return bda, gastro, cave, ccmp, fournisseur


def test_treasurer_creates_submission_in_scope(client_and_db, login_as):
    _, db_path = client_and_db
    _, gastro, cave, _, fournisseur = _setup_tree(db_path)
    tres = login_as("tres@test.local", roles=[(gastro, "treasurer")])
    r = tres.post("/api/submissions/", json=_payload(cave, fournisseur))
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "pending"
    assert body["amount"] == 4550
    assert body["direction"] == "expense"
    assert body["entity_id"] == cave
    assert body["entity_name"] == "Cave"
    assert body["counterparty_name"] == "Boulangerie Martin"
    assert body["transaction_id"] is None
    assert body["submitted_by_email"] == "tres@test.local"


def test_admin_creates_submission_anywhere(client_and_db):
    client, db_path = client_and_db
    _, gastro, _, _, fournisseur = _setup_tree(db_path)
    r = client.post("/api/submissions/", json=_payload(gastro, fournisseur))
    assert r.status_code == 201


def test_treasurer_out_of_scope_403(client_and_db, login_as):
    _, db_path = client_and_db
    _, gastro, _, ccmp, fournisseur = _setup_tree(db_path)
    tres = login_as("tres2@test.local", roles=[(gastro, "treasurer")])
    r = tres.post("/api/submissions/", json=_payload(ccmp, fournisseur))
    assert r.status_code == 403


def test_viewer_cannot_submit(client_and_db, login_as):
    _, db_path = client_and_db
    _, gastro, _, _, fournisseur = _setup_tree(db_path)
    viewer = login_as("viewer@test.local", roles=[(gastro, "viewer")])
    r = viewer.post("/api/submissions/", json=_payload(gastro, fournisseur))
    assert r.status_code == 403


def test_create_validations(client_and_db, login_as):
    _, db_path = client_and_db
    _, gastro, _, _, fournisseur = _setup_tree(db_path)
    tres = login_as("tres3@test.local", roles=[(gastro, "treasurer")])
    # Montant non strictement positif.
    assert tres.post("/api/submissions/", json=_payload(gastro, fournisseur, amount=0)).status_code == 400
    assert tres.post("/api/submissions/", json=_payload(gastro, fournisseur, amount=-500)).status_code == 400
    # Entité == contrepartie.
    assert tres.post("/api/submissions/", json=_payload(gastro, gastro)).status_code == 400
    # Entité inexistante -> 403 (hors périmètre du rôle avant même l'existence),
    # contrepartie inexistante -> 400.
    assert tres.post("/api/submissions/", json=_payload(99999, fournisseur)).status_code in (400, 403)
    assert tres.post("/api/submissions/", json=_payload(gastro, 99999)).status_code == 400
    # Entité externe comme entity_id -> 400 (doit être interne).
    assert tres.post("/api/submissions/", json=_payload(fournisseur, gastro)).status_code in (400, 403)
    # Catégorie inexistante -> 400.
    assert tres.post("/api/submissions/", json=_payload(gastro, fournisseur, category_id=99999)).status_code == 400
    # Direction invalide -> 422 (validation pydantic Literal).
    assert tres.post("/api/submissions/", json=_payload(gastro, fournisseur, direction="transfer")).status_code == 422


def test_anonymous_401(client_and_db):
    from fastapi.testclient import TestClient
    client, _ = client_and_db
    anon = TestClient(client.app)
    assert anon.post("/api/submissions/", json={}).status_code == 401
