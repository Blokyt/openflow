"""Justificatifs liés à une soumission : upload, accès, suppression."""
import io
import sqlite3

NOW = "2026-01-01T00:00:00+00:00"
PDF_BYTES = b"%PDF-1.4 test"


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


def _submission(tc, entity_id, counterparty_id, **over):
    p = {
        "date": "2026-05-10", "label": "Courses", "description": "",
        "amount": 4550, "category_id": None, "entity_id": entity_id,
        "counterparty_entity_id": counterparty_id, "direction": "expense",
    }
    p.update(over)
    r = tc.post("/api/submissions/", json=p)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _upload(tc, sid, name="facture.pdf"):
    return tc.post(
        f"/api/attachments/submission/{sid}",
        files={"file": (name, io.BytesIO(PDF_BYTES), "application/pdf")},
    )


def _env(db_path, login_as):
    gastro = _entity(db_path, "Gastronomine")
    ccmp = _entity(db_path, "CCMP")
    fournisseur = _entity(db_path, "Fournisseur", type="external")
    tres = login_as("tres-att@test.local", roles=[(gastro, "treasurer")])
    other = login_as("other-att@test.local", roles=[(ccmp, "treasurer")])
    return gastro, fournisseur, tres, other


def test_attachments_table_has_submission_id(client_and_db):
    _, db_path = client_and_db
    conn = sqlite3.connect(str(db_path))
    try:
        info = {r[1]: r for r in conn.execute("PRAGMA table_info(attachments)").fetchall()}
    finally:
        conn.close()
    assert "submission_id" in info
    # transaction_id est devenu nullable (notnull == 0).
    assert info["transaction_id"][3] == 0


def test_upload_and_list_on_submission(client_and_db, login_as):
    _, db_path = client_and_db
    gastro, fournisseur, tres, other = _env(db_path, login_as)
    sid = _submission(tres, gastro, fournisseur)
    r = _upload(tres, sid)
    assert r.status_code == 201
    att = r.json()
    assert att["submission_id"] == sid
    assert att["transaction_id"] is None
    # Liste : auteur et admin OK, autre treasurer 403.
    assert len(tres.get(f"/api/attachments/submission/{sid}").json()) == 1
    client, _ = client_and_db
    assert len(client.get(f"/api/attachments/submission/{sid}").json()) == 1
    assert other.get(f"/api/attachments/submission/{sid}").status_code == 403
    # 404 sur soumission inconnue.
    assert _upload(tres, 99999).status_code == 404
    assert tres.get("/api/attachments/submission/99999").status_code == 404


def test_upload_forbidden_for_non_owner_and_non_pending(client_and_db, login_as):
    client, db_path = client_and_db
    gastro, fournisseur, tres, other = _env(db_path, login_as)
    sid = _submission(tres, gastro, fournisseur)
    assert _upload(other, sid).status_code == 403
    tres.post(f"/api/submissions/{sid}/cancel")
    assert _upload(tres, sid).status_code == 409


def test_preview_download_access(client_and_db, login_as):
    client, db_path = client_and_db
    gastro, fournisseur, tres, other = _env(db_path, login_as)
    sid = _submission(tres, gastro, fournisseur)
    att_id = _upload(tres, sid).json()["id"]
    assert tres.get(f"/api/attachments/{att_id}/preview").status_code == 200
    assert tres.get(f"/api/attachments/{att_id}/download").status_code == 200
    assert client.get(f"/api/attachments/{att_id}/preview").status_code == 200
    assert other.get(f"/api/attachments/{att_id}/preview").status_code == 403
    assert other.get(f"/api/attachments/{att_id}/download").status_code == 403


def test_delete_own_pending_submission_attachment(client_and_db, login_as):
    client, db_path = client_and_db
    gastro, fournisseur, tres, other = _env(db_path, login_as)
    sid = _submission(tres, gastro, fournisseur)
    att_id = _upload(tres, sid).json()["id"]
    # Un autre treasurer ne peut pas supprimer.
    assert other.delete(f"/api/attachments/{att_id}").status_code == 403
    # L'auteur peut supprimer tant que la soumission est pending.
    assert tres.delete(f"/api/attachments/{att_id}").status_code == 200
    # Une pièce liée à une transaction reste inaccessible au treasurer.
    tx = client.post("/api/transactions/", json={
        "date": "2026-05-01", "label": "Tx admin", "amount": 1000,
        "from_entity_id": gastro, "to_entity_id": fournisseur,
    }).json()
    r = client.post(
        f"/api/attachments/transaction/{tx['id']}",
        files={"file": ("f.pdf", io.BytesIO(PDF_BYTES), "application/pdf")},
    )
    tx_att = r.json()["id"]
    assert tres.delete(f"/api/attachments/{tx_att}").status_code == 403
    # L'admin garde tous les droits.
    assert client.delete(f"/api/attachments/{tx_att}").status_code == 200
