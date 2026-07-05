"""Cohérence : une soumission pending/rejected/cancelled n'affecte JAMAIS un
solde, un budget, un rapport ni une liste de transactions. Seule l'approbation
fait entrer le montant en comptabilité."""
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


def _payload(entity_id, counterparty_id, **over):
    p = {
        "date": "2026-05-10", "label": "Soumission test", "description": "",
        "amount": 12345, "category_id": None, "entity_id": entity_id,
        "counterparty_entity_id": counterparty_id, "direction": "expense",
    }
    p.update(over)
    return p


def _snapshot(client, entity_id, fy_id):
    """Photographie tous les agrégats financiers exposés par l'API."""
    return {
        "balance": client.get(f"/api/entities/{entity_id}/balance").json(),
        "consolidated": client.get(f"/api/entities/{entity_id}/consolidated").json(),
        "summary": client.get("/api/dashboard/summary").json(),
        "tx_total": client.get("/api/transactions/").json()["total"],
        "budget_view": client.get(f"/api/budget/view?fiscal_year_id={fy_id}").json(),
        "compte_resultat": client.get(
            f"/api/reports/compte-resultat?fiscal_year_id={fy_id}"
        ).json(),
    }


def test_non_approved_submissions_never_affect_balances(client_and_db, login_as):
    client, db_path = client_and_db
    gastro = _entity(db_path, "Gastronomine")
    fournisseur = _entity(db_path, "Fournisseur", type="external")
    tres = login_as("tres-coh@test.local", roles=[(gastro, "treasurer")])

    # Un exercice ouvert pour donner un cadre au budget et aux rapports.
    client.post("/api/budget/fiscal-years", json={"name": "Exercice test", "start_date": "2026-01-01"})
    fy_id = client.get("/api/budget/fiscal-years").json()[0]["id"]

    # Une transaction réelle de référence pour que le baseline soit non trivial.
    client.post("/api/transactions/", json={
        "date": "2026-02-01", "label": "Référence", "amount": 5000,
        "from_entity_id": gastro, "to_entity_id": fournisseur,
    })

    before = _snapshot(client, gastro, fy_id)

    # 1. Une soumission pending.
    sid_pending = tres.post("/api/submissions/", json=_payload(gastro, fournisseur)).json()["id"]
    # 2. Une soumission refusée.
    sid_rejected = tres.post("/api/submissions/", json=_payload(gastro, fournisseur)).json()["id"]
    client.post(f"/api/submissions/{sid_rejected}/reject", json={"comment": "Non conforme"})
    # 3. Une soumission annulée.
    sid_cancelled = tres.post("/api/submissions/", json=_payload(gastro, fournisseur)).json()["id"]
    tres.post(f"/api/submissions/{sid_cancelled}/cancel")

    after = _snapshot(client, gastro, fy_id)
    assert after == before, "Une soumission non approuvée a modifié un agrégat financier"

    # L'approbation, elle, fait bouger le solde du montant exact.
    client.post(f"/api/submissions/{sid_pending}/approve")
    final = _snapshot(client, gastro, fy_id)
    assert final != before
    assert final["balance"]["balance"] == before["balance"]["balance"] - 12345
    assert final["tx_total"] == before["tx_total"] + 1


def test_submissions_table_never_read_by_balance_queries(client_and_db):
    """Garde-fou statique : balance.py ne référence jamais la table des soumissions."""
    from pathlib import Path
    balance_src = (Path(__file__).parent.parent.parent / "backend" / "core" / "balance.py").read_text(encoding="utf-8")
    assert "transaction_submissions" not in balance_src
