import sqlite3

import backend.modules.helloasso.api as ha_api


def _make_fiscal_year(db_path, start="2025-09-01", end=None):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO fiscal_years (name, start_date, end_date, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        ("2025-2026", start, end, "2025-09-01T00:00:00", "2025-09-01T00:00:00"),
    )
    conn.commit()
    fy_id = conn.execute("SELECT id FROM fiscal_years WHERE name = '2025-2026'").fetchone()[0]
    conn.close()
    return fy_id


def _config(client):
    client.put("/api/helloasso/config", json={
        "client_id": "id", "client_secret": "sec", "organization_slug": "bda-ens"})


def _totals(collected):
    return lambda self, s, e: [
        {"form_type": "Membership", "form_slug": "cotis", "title": "Cotisations",
         "state": "Public", "collected_cents": collected, "currency": "EUR"},
    ]


def test_sync_requires_config(client_and_db):
    client, db_path = client_and_db
    fy = _make_fiscal_year(db_path)
    r = client.post(f"/api/helloasso/sync?fiscal_year_id={fy}")
    assert r.status_code == 400  # config absente


def test_sync_populates_cache(client_and_db, monkeypatch):
    client, db_path = client_and_db
    fy = _make_fiscal_year(db_path)
    _config(client)
    monkeypatch.setattr(ha_api.HelloAssoClient, "fetch_campaign_totals", _totals(400000))

    r = client.post(f"/api/helloasso/sync?fiscal_year_id={fy}")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["collected_cents"] == 400000
    assert rows[0]["linked_cents"] == 0
    assert rows[0]["pending_cents"] == 400000

    # Re-sync : pas de doublon (upsert sur fiscal_year_id + form).
    client.post(f"/api/helloasso/sync?fiscal_year_id={fy}")
    conn = sqlite3.connect(db_path)
    n = conn.execute("SELECT COUNT(*) FROM helloasso_campaigns").fetchone()[0]
    conn.close()
    assert n == 1


def test_sync_preserves_links(client_and_db, monkeypatch):
    """Associer une transaction puis re-synchroniser avec un collecté plus élevé :
    le lien est conservé (l'id de campagne est stable) et la campagne réapparaît
    avec uniquement le nouveau montant restant."""
    client, db_path = client_and_db
    fy = _make_fiscal_year(db_path)
    _config(client)

    monkeypatch.setattr(ha_api.HelloAssoClient, "fetch_campaign_totals", _totals(400000))
    cid = client.post(f"/api/helloasso/sync?fiscal_year_id={fy}").json()[0]["id"]

    # Une recette enregistrée en compta, associée à la campagne.
    interne = client.post("/api/entities/", json={"name": "Asso", "type": "internal"}).json()["id"]
    externe = client.post("/api/entities/", json={"name": "Adhérents", "type": "external"}).json()["id"]
    tx = client.post("/api/transactions/", json={
        "date": "2025-10-15", "label": "cotis", "amount": 400000,
        "from_entity_id": externe, "to_entity_id": interne,
    }).json()["id"]
    client.post(f"/api/helloasso/campaigns/{cid}/links", json={"transaction_id": tx})

    # Nouvel encaissement : le collecté monte à 4500,00 €
    monkeypatch.setattr(ha_api.HelloAssoClient, "fetch_campaign_totals", _totals(450000))
    r = client.post(f"/api/helloasso/sync?fiscal_year_id={fy}")
    row = r.json()[0]
    assert row["collected_cents"] == 450000
    assert row["linked_cents"] == 400000  # lien préservé par le re-sync
    assert row["pending_cents"] == 50000
