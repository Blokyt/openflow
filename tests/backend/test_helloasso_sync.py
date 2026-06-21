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


def test_sync_requires_config(client_and_db):
    client, db_path = client_and_db
    fy = _make_fiscal_year(db_path)
    r = client.post(f"/api/helloasso/sync?fiscal_year_id={fy}")
    assert r.status_code == 400  # config absente


def test_sync_populates_cache(client_and_db, monkeypatch):
    client, db_path = client_and_db
    fy = _make_fiscal_year(db_path)
    client.put("/api/helloasso/config", json={
        "client_id": "id", "client_secret": "sec", "organization_slug": "bda-ens"})

    monkeypatch.setattr(
        ha_api.HelloAssoClient, "fetch_campaign_totals",
        lambda self, s, e: [
            {"form_type": "Membership", "form_slug": "cotis", "title": "Cotisations",
             "state": "Public", "collected_cents": 400000, "currency": "EUR"},
        ],
    )

    r = client.post(f"/api/helloasso/sync?fiscal_year_id={fy}")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["collected_cents"] == 400000

    # Re-sync : pas de doublon (upsert sur fiscal_year_id + form).
    client.post(f"/api/helloasso/sync?fiscal_year_id={fy}")
    conn = sqlite3.connect(db_path)
    n = conn.execute("SELECT COUNT(*) FROM helloasso_campaigns").fetchone()[0]
    conn.close()
    assert n == 1
