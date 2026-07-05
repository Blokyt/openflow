"""Workflow complet : approbation (transaction créée, justificatifs re-liés) et refus."""
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
        "date": "2026-05-10", "label": "Courses atelier", "description": "Farine",
        "amount": 4550, "category_id": None, "entity_id": entity_id,
        "counterparty_entity_id": counterparty_id, "direction": "expense",
    }
    p.update(over)
    r = tc.post("/api/submissions/", json=p)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _env(db_path, login_as):
    gastro = _entity(db_path, "Gastronomine")
    fournisseur = _entity(db_path, "Fournisseur", type="external")
    tres = login_as("tres-wf@test.local", roles=[(gastro, "treasurer")])
    return gastro, fournisseur, tres


def test_approve_expense_creates_transaction(client_and_db, login_as):
    client, db_path = client_and_db
    gastro, fournisseur, tres = _env(db_path, login_as)
    sid = _submission(tres, gastro, fournisseur)
    r = client.post(f"/api/submissions/{sid}/approve")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "approved"
    assert body["transaction_id"] is not None
    assert body["reviewed_by_name"] == "Admin Test"
    tx = client.get(f"/api/transactions/{body['transaction_id']}").json()
    # Dépense : l'argent sort de l'entité vers la contrepartie.
    assert tx["from_entity_id"] == gastro
    assert tx["to_entity_id"] == fournisseur
    assert tx["amount"] == 4550
    assert tx["label"] == "Courses atelier"
    assert tx["created_by"] == "tres-wf@test.local"


def test_approve_income_swaps_from_to(client_and_db, login_as):
    client, db_path = client_and_db
    gastro, fournisseur, tres = _env(db_path, login_as)
    sid = _submission(tres, gastro, fournisseur, direction="income", label="Subvention")
    tx_id = client.post(f"/api/submissions/{sid}/approve").json()["transaction_id"]
    tx = client.get(f"/api/transactions/{tx_id}").json()
    # Recette : l'argent vient de la contrepartie vers l'entité.
    assert tx["from_entity_id"] == fournisseur
    assert tx["to_entity_id"] == gastro


def test_approve_relinks_attachments(client_and_db, login_as):
    client, db_path = client_and_db
    gastro, fournisseur, tres = _env(db_path, login_as)
    sid = _submission(tres, gastro, fournisseur)
    att = tres.post(
        f"/api/attachments/submission/{sid}",
        files={"file": ("facture.pdf", io.BytesIO(PDF_BYTES), "application/pdf")},
    ).json()
    tx_id = client.post(f"/api/submissions/{sid}/approve").json()["transaction_id"]
    # Le justificatif est maintenant lié à la transaction ET garde son submission_id.
    linked = client.get(f"/api/attachments/transaction/{tx_id}").json()
    assert [a["id"] for a in linked] == [att["id"]]
    assert linked[0]["submission_id"] == sid


def test_approve_guards(client_and_db, login_as):
    client, db_path = client_and_db
    gastro, fournisseur, tres = _env(db_path, login_as)
    sid = _submission(tres, gastro, fournisseur)
    # Un treasurer ne peut pas approuver (garde centrale).
    assert tres.post(f"/api/submissions/{sid}/approve").status_code == 403
    # 404 sur id inconnu.
    assert client.post("/api/submissions/99999/approve").status_code == 404
    # Double approbation -> 409.
    assert client.post(f"/api/submissions/{sid}/approve").status_code == 200
    assert client.post(f"/api/submissions/{sid}/approve").status_code == 409
    # Une soumission annulée ne s'approuve pas.
    sid2 = _submission(tres, gastro, fournisseur)
    tres.post(f"/api/submissions/{sid2}/cancel")
    assert client.post(f"/api/submissions/{sid2}/approve").status_code == 409


def test_approve_closed_fiscal_year_needs_force(client_and_db, login_as):
    client, db_path = client_and_db
    gastro, fournisseur, tres = _env(db_path, login_as)
    # Exercice clôturé couvrant la date de la soumission.
    client.post("/api/budget/fiscal-years", json={"name": "Ex 2026", "start_date": "2026-01-01"})
    fy = client.get("/api/budget/fiscal-years").json()[0]
    client.post(f"/api/budget/fiscal-years/{fy['id']}/close", json={"end_date": "2026-12-31"})
    sid = _submission(tres, gastro, fournisseur)  # date 2026-05-10, dans l'exercice clos
    assert client.post(f"/api/submissions/{sid}/approve").status_code == 409
    r = client.post(f"/api/submissions/{sid}/approve?force=true")
    assert r.status_code == 200


def test_approve_fails_when_entity_deleted(client_and_db, login_as):
    client, db_path = client_and_db
    gastro, fournisseur, tres = _env(db_path, login_as)
    sid = _submission(tres, gastro, fournisseur)
    # L'entité interne disparaît après la soumission (FK OFF, pas de cascade).
    conn = sqlite3.connect(str(db_path))
    try:
        tx_count_before = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        conn.execute("DELETE FROM entities WHERE id = ?", (gastro,))
        conn.commit()
    finally:
        conn.close()
    r = client.post(f"/api/submissions/{sid}/approve")
    assert r.status_code == 400
    # La soumission reste en attente et aucune transaction n'a été créée.
    assert client.get(f"/api/submissions/{sid}").json()["status"] == "pending"
    conn = sqlite3.connect(str(db_path))
    try:
        tx_count_after = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    finally:
        conn.close()
    assert tx_count_after == tx_count_before


def test_approve_rejected_submission_409(client_and_db, login_as):
    client, db_path = client_and_db
    gastro, fournisseur, tres = _env(db_path, login_as)
    sid = _submission(tres, gastro, fournisseur)
    r = client.post(f"/api/submissions/{sid}/reject", json={"comment": "Montant incohérent"})
    assert r.status_code == 200
    assert client.post(f"/api/submissions/{sid}/approve").status_code == 409


def test_reject_requires_comment(client_and_db, login_as):
    client, db_path = client_and_db
    gastro, fournisseur, tres = _env(db_path, login_as)
    sid = _submission(tres, gastro, fournisseur)
    assert client.post(f"/api/submissions/{sid}/reject", json={"comment": ""}).status_code == 400
    assert client.post(f"/api/submissions/{sid}/reject", json={"comment": "   "}).status_code == 400
    r = client.post(f"/api/submissions/{sid}/reject", json={"comment": "Justificatif illisible"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "rejected"
    assert body["review_comment"] == "Justificatif illisible"
    assert body["transaction_id"] is None
    # Double refus -> 409 ; refus après approbation -> 409 ; 404 sur inconnu.
    assert client.post(f"/api/submissions/{sid}/reject", json={"comment": "encore"}).status_code == 409
    assert client.post("/api/submissions/99999/reject", json={"comment": "x"}).status_code == 404
    # Treasurer -> 403 (garde centrale).
    assert tres.post(f"/api/submissions/{sid}/reject", json={"comment": "x"}).status_code == 403
