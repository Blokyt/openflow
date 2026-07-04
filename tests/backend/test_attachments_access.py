"""Les pièces jointes ne sont servies que dans le périmètre du rôle."""
import io
import sqlite3

NOW = "2026-01-01T00:00:00+00:00"


def _seed(client, db_path):
    conn = sqlite3.connect(str(db_path))
    ids = {}
    def entity(name, parent=None, typ="internal"):
        cur = conn.execute(
            "INSERT INTO entities (name, type, parent_id, is_default, color, position, created_at, updated_at) "
            "VALUES (?, ?, ?, 0, '#000', 0, ?, ?)", (name, typ, parent, NOW, NOW))
        ids[name] = cur.lastrowid
    entity("Gastronomine"); entity("CCMP"); entity("Fournisseur", typ="external")
    conn.commit(); conn.close()
    tx = client.post("/api/transactions/", json={
        "date": "2026-01-15", "label": "achat ccmp", "amount": 1000,
        "from_entity_id": ids["CCMP"], "to_entity_id": ids["Fournisseur"],
    }).json()
    upload = client.post(
        f"/api/attachments/transaction/{tx['id']}",
        files={"file": ("facture.pdf", io.BytesIO(b"%PDF-1.4 test"), "application/pdf")},
    ).json()
    return ids, tx, upload


def test_attachment_blocked_outside_scope(client_and_db, login_as):
    client, db_path = client_and_db
    ids, tx, upload = _seed(client, db_path)
    tres = login_as("a1@t.fr", roles=[(ids["Gastronomine"], "treasurer")])
    assert tres.get(f"/api/attachments/transaction/{tx['id']}").status_code == 403
    assert tres.get(f"/api/attachments/{upload['id']}/preview").status_code == 403
    assert tres.get(f"/api/attachments/{upload['id']}/download").status_code == 403


def test_attachment_allowed_inside_scope(client_and_db, login_as):
    client, db_path = client_and_db
    ids, tx, upload = _seed(client, db_path)
    tres = login_as("a2@t.fr", roles=[(ids["CCMP"], "treasurer")])
    assert tres.get(f"/api/attachments/transaction/{tx['id']}").status_code == 200
    assert tres.get(f"/api/attachments/{upload['id']}/download").status_code == 200


def test_attachment_admin_unchanged(client_and_db):
    client, db_path = client_and_db
    _, tx, upload = _seed(client, db_path)
    assert client.get(f"/api/attachments/{upload['id']}/preview").status_code == 200
