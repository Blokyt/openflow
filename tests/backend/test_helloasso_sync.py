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
    assert rows[0]["acknowledged_cents"] == 0
    assert rows[0]["pending_cents"] == 400000

    # Re-sync : pas de doublon (upsert sur fiscal_year_id + form).
    client.post(f"/api/helloasso/sync?fiscal_year_id={fy}")
    conn = sqlite3.connect(db_path)
    n = conn.execute("SELECT COUNT(*) FROM helloasso_campaigns").fetchone()[0]
    conn.close()
    assert n == 1


def test_sync_preserves_acknowledged(client_and_db, monkeypatch):
    """Pointer puis re-synchroniser avec un collecté plus élevé : le pointage est
    conservé et la campagne réapparaît avec uniquement le nouveau montant."""
    client, db_path = client_and_db
    fy = _make_fiscal_year(db_path)
    _config(client)

    monkeypatch.setattr(ha_api.HelloAssoClient, "fetch_campaign_totals", _totals(400000))
    client.post(f"/api/helloasso/sync?fiscal_year_id={fy}")
    client.post("/api/helloasso/acknowledge", json={
        "form_type": "Membership", "form_slug": "cotis", "fiscal_year_id": fy})

    # Nouvel encaissement : le collecté monte à 4500,00 €
    monkeypatch.setattr(ha_api.HelloAssoClient, "fetch_campaign_totals", _totals(450000))
    r = client.post(f"/api/helloasso/sync?fiscal_year_id={fy}")
    row = r.json()[0]
    assert row["collected_cents"] == 450000
    assert row["acknowledged_cents"] == 400000  # préservé par le re-sync
    assert row["pending_cents"] == 50000
