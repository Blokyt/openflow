import sqlite3


def _seed(db_path, fy_id, collected, recorded_tx):
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO helloasso_campaigns
           (fiscal_year_id, form_type, form_slug, title, state, collected_cents, currency, last_synced_at)
           VALUES (?, 'Membership', 'cotis', 'Cotisations', 'Public', ?, 'EUR', '2026-01-01T00:00:00')""",
        (fy_id, collected),
    )
    # transaction recette : to_entity 1 (club), categorie 20, dans l'exercice
    for amount in recorded_tx:
        conn.execute(
            """INSERT INTO transactions (date, label, description, amount, category_id, from_entity_id, to_entity_id, created_at, updated_at)
               VALUES ('2025-10-01', 'Cotis manuelle', '', ?, 20, 7, 1, '2025-10-01T00:00:00', '2025-10-01T00:00:00')""",
            (amount,),
        )
    conn.execute(
        "INSERT INTO fiscal_years (id, name, start_date, end_date, created_at, updated_at) VALUES (?, '2025-2026', '2025-09-01', NULL, '2025-09-01T00:00:00', '2025-09-01T00:00:00')",
        (fy_id,),
    )
    conn.commit()
    conn.close()


def test_campaign_gap_with_link(client_and_db):
    client, db_path = client_and_db
    fy = 1
    _seed(db_path, fy, collected=400000, recorded_tx=[382500])
    client.put("/api/helloasso/links", json={
        "form_type": "Membership", "form_slug": "cotis",
        "category_id": 20, "from_entity_id": 7, "to_entity_id": 1})

    rows = client.get(f"/api/helloasso/campaigns?fiscal_year_id={fy}").json()
    assert len(rows) == 1
    row = rows[0]
    assert row["collected_cents"] == 400000
    assert row["recorded_cents"] == 382500
    assert row["gap_cents"] == 17500
    assert row["link"] is not None


def test_campaign_without_link_has_null_gap(client_and_db):
    client, db_path = client_and_db
    fy = 1
    _seed(db_path, fy, collected=400000, recorded_tx=[])
    rows = client.get(f"/api/helloasso/campaigns?fiscal_year_id={fy}").json()
    assert rows[0]["link"] is None
    assert rows[0]["gap_cents"] is None
    assert rows[0]["recorded_cents"] is None
