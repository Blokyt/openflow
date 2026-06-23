"""Tests du modèle « acquittement » HelloAsso : on pointe ce qui est pris en compte.

pending_cents = collected_cents - acknowledged_cents (montant restant à traiter).
Le pointage est préservé d'une synchro à l'autre ; une campagne réapparaît dès
que le collecté dépasse le montant pointé.
"""
import sqlite3


def _make_fiscal_year(db_path, fy_id=1):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO fiscal_years (id, name, start_date, end_date, created_at, updated_at) "
        "VALUES (?, '2025-2026', '2025-09-01', NULL, '2025-09-01T00:00:00', '2025-09-01T00:00:00')",
        (fy_id,),
    )
    conn.commit()
    conn.close()
    return fy_id


def _seed_campaign(db_path, fy_id, collected, acknowledged=0, slug="cotis"):
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO helloasso_campaigns
           (fiscal_year_id, form_type, form_slug, title, state, collected_cents, currency, last_synced_at, acknowledged_cents)
           VALUES (?, 'Membership', ?, 'Cotisations', 'Public', ?, 'EUR', '2026-01-01T00:00:00', ?)""",
        (fy_id, slug, collected, acknowledged),
    )
    conn.commit()
    conn.close()


def test_pending_equals_collected_minus_acknowledged(client_and_db):
    client, db_path = client_and_db
    fy = _make_fiscal_year(db_path)
    _seed_campaign(db_path, fy, collected=400000, acknowledged=0)
    rows = client.get(f"/api/helloasso/campaigns?fiscal_year_id={fy}").json()
    assert rows[0]["collected_cents"] == 400000
    assert rows[0]["acknowledged_cents"] == 0
    assert rows[0]["pending_cents"] == 400000


def test_acknowledge_zeroes_pending(client_and_db):
    client, db_path = client_and_db
    fy = _make_fiscal_year(db_path)
    _seed_campaign(db_path, fy, collected=400000)
    r = client.post("/api/helloasso/acknowledge", json={
        "form_type": "Membership", "form_slug": "cotis", "fiscal_year_id": fy})
    assert r.status_code == 200
    assert r.json()["acknowledged_cents"] == 400000
    assert r.json()["pending_cents"] == 0
    rows = client.get(f"/api/helloasso/campaigns?fiscal_year_id={fy}").json()
    assert rows[0]["pending_cents"] == 0


def test_reappears_when_collected_increases(client_and_db):
    """Après pointage, si le collecté augmente (nouvel encaissement), la campagne
    réapparaît avec UNIQUEMENT le nouveau montant à traiter."""
    client, db_path = client_and_db
    fy = _make_fiscal_year(db_path)
    _seed_campaign(db_path, fy, collected=400000)
    client.post("/api/helloasso/acknowledge", json={
        "form_type": "Membership", "form_slug": "cotis", "fiscal_year_id": fy})
    # nouvel encaissement : collecté passe à 4500,00 € (comme le ferait un re-sync)
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE helloasso_campaigns SET collected_cents = 450000 WHERE fiscal_year_id = ? AND form_slug = 'cotis'", (fy,))
    conn.commit()
    conn.close()
    rows = client.get(f"/api/helloasso/campaigns?fiscal_year_id={fy}").json()
    assert rows[0]["pending_cents"] == 50000  # 4500 - 4000 déjà pointés


def test_unacknowledge_restores_full_pending(client_and_db):
    client, db_path = client_and_db
    fy = _make_fiscal_year(db_path)
    _seed_campaign(db_path, fy, collected=400000, acknowledged=400000)
    r = client.post("/api/helloasso/unacknowledge", json={
        "form_type": "Membership", "form_slug": "cotis", "fiscal_year_id": fy})
    assert r.status_code == 200
    assert r.json()["pending_cents"] == 400000


def test_acknowledge_unknown_campaign_returns_404(client_and_db):
    client, db_path = client_and_db
    fy = _make_fiscal_year(db_path)
    r = client.post("/api/helloasso/acknowledge", json={
        "form_type": "Membership", "form_slug": "nexistepas", "fiscal_year_id": fy})
    assert r.status_code == 404
