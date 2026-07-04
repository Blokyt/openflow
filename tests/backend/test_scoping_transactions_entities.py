"""Scoping des lectures : transactions et entités limitées au sous-arbre du rôle."""
import sqlite3

NOW = "2026-01-01T00:00:00+00:00"


def _seed_tree(db_path):
    """BDA -> (Gastronomine -> Cave, CCMP) + un externe + 3 transactions."""
    conn = sqlite3.connect(str(db_path))
    ids = {}
    def entity(name, typ="internal", parent=None):
        cur = conn.execute(
            "INSERT INTO entities (name, type, parent_id, is_default, color, position, created_at, updated_at) "
            "VALUES (?, ?, ?, 0, '#000', 0, ?, ?)", (name, typ, parent, NOW, NOW))
        ids[name] = cur.lastrowid
        return cur.lastrowid
    bda = entity("BDA")
    gastro = entity("Gastronomine", parent=bda)
    entity("Cave", parent=gastro)
    entity("CCMP", parent=bda)
    ext = entity("Fournisseur", typ="external")
    def tx(label, frm, to, amount=1000):
        conn.execute(
            "INSERT INTO transactions (date, label, description, amount, category_id, contact_id, "
            "created_by, created_at, updated_at, from_entity_id, to_entity_id) "
            "VALUES ('2026-01-15', ?, '', ?, NULL, NULL, '', ?, ?, ?, ?)",
            (label, amount, NOW, NOW, frm, to))
    tx("achat gastro", ids["Gastronomine"], ext)
    tx("achat cave", ids["Cave"], ext)
    tx("achat ccmp", ids["CCMP"], ext)
    conn.commit(); conn.close()
    return ids


def test_treasurer_sees_only_subtree_transactions(client_and_db, login_as):
    _, db_path = client_and_db
    ids = _seed_tree(db_path)
    tres = login_as("tres@gastro.fr", roles=[(ids["Gastronomine"], "treasurer")])
    items = tres.get("/api/transactions/").json()["items"]
    labels = {t["label"] for t in items}
    assert labels == {"achat gastro", "achat cave"}


def test_treasurer_cannot_focus_outside(client_and_db, login_as):
    _, db_path = client_and_db
    ids = _seed_tree(db_path)
    tres = login_as("tres2@gastro.fr", roles=[(ids["Gastronomine"], "treasurer")])
    r = tres.get(f"/api/transactions/?entity_id={ids['CCMP']}")
    assert r.status_code == 403
    r = tres.get(f"/api/transactions/?entity_id={ids['Gastronomine']}&include_children=true")
    assert r.status_code == 200


def test_transaction_detail_scoped(client_and_db, login_as):
    client, db_path = client_and_db
    ids = _seed_tree(db_path)
    all_tx = client.get("/api/transactions/").json()["items"]
    ccmp_tx = next(t for t in all_tx if t["label"] == "achat ccmp")
    gastro_tx = next(t for t in all_tx if t["label"] == "achat gastro")
    tres = login_as("tres3@gastro.fr", roles=[(ids["Gastronomine"], "treasurer")])
    assert tres.get(f"/api/transactions/{gastro_tx['id']}").status_code == 200
    assert tres.get(f"/api/transactions/{ccmp_tx['id']}").status_code == 403


def test_entities_list_scoped(client_and_db, login_as):
    _, db_path = client_and_db
    ids = _seed_tree(db_path)
    tres = login_as("tres4@gastro.fr", roles=[(ids["Gastronomine"], "treasurer")])
    r = tres.get("/api/entities/")
    assert r.status_code == 200
    names = {e["name"] for e in r.json()}
    assert "Gastronomine" in names and "Cave" in names
    assert "CCMP" not in names and "BDA" not in names
    assert "Fournisseur" in names   # les externes restent visibles (contreparties)


def test_entity_balance_scoped(client_and_db, login_as):
    _, db_path = client_and_db
    ids = _seed_tree(db_path)
    tres = login_as("tres5@gastro.fr", roles=[(ids["Gastronomine"], "treasurer")])
    assert tres.get(f"/api/entities/{ids['Gastronomine']}/balance").status_code == 200
    assert tres.get(f"/api/entities/{ids['CCMP']}/balance").status_code == 403


def test_no_role_sees_nothing(client_and_db, login_as):
    _, db_path = client_and_db
    _seed_tree(db_path)
    nobody = login_as("personne@test.local")
    assert nobody.get("/api/transactions/").json()["items"] == []
