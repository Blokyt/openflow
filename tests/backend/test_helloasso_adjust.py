import sqlite3


def _seed(db_path, fy_id, collected, recorded_tx):
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO helloasso_campaigns
           (fiscal_year_id, form_type, form_slug, title, state, collected_cents, currency, last_synced_at)
           VALUES (?, 'Membership', 'cotis', 'Cotisations', 'Public', ?, 'EUR', '2026-01-01T00:00:00')""",
        (fy_id, collected),
    )
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


def test_adjust_creates_transaction_and_zeroes_gap(client_and_db):
    client, db_path = client_and_db
    fy = 1
    _seed(db_path, fy, collected=400000, recorded_tx=[382500])
    client.put("/api/helloasso/links", json={
        "form_type": "Membership", "form_slug": "cotis",
        "category_id": 20, "from_entity_id": 7, "to_entity_id": 1})

    r = client.post("/api/helloasso/adjust", json={
        "form_type": "Membership", "form_slug": "cotis", "fiscal_year_id": fy})
    assert r.status_code == 201
    tx = r.json()
    assert tx["amount"] == 17500
    assert tx["to_entity_id"] == 1     # recette : entre dans le club
    assert tx["from_entity_id"] == 7
    assert tx["category_id"] == 20
    assert "HelloAsso" in tx["label"]

    rows = client.get(f"/api/helloasso/campaigns?fiscal_year_id={fy}").json()
    assert rows[0]["gap_cents"] == 0   # l'écart est résorbé


def test_adjust_negative_gap_inverts_direction(client_and_db):
    client, db_path = client_and_db
    fy = 1
    _seed(db_path, fy, collected=380000, recorded_tx=[400000])  # enregistré > collecté
    client.put("/api/helloasso/links", json={
        "form_type": "Membership", "form_slug": "cotis",
        "category_id": 20, "from_entity_id": 7, "to_entity_id": 1})

    r = client.post("/api/helloasso/adjust", json={
        "form_type": "Membership", "form_slug": "cotis", "fiscal_year_id": fy})
    assert r.status_code == 201
    tx = r.json()
    assert tx["amount"] == 20000
    assert tx["from_entity_id"] == 1   # sortie du club (régularisation inverse)
    assert tx["to_entity_id"] == 7


def test_adjust_requires_link(client_and_db):
    client, db_path = client_and_db
    fy = 1
    _seed(db_path, fy, collected=400000, recorded_tx=[])
    r = client.post("/api/helloasso/adjust", json={
        "form_type": "Membership", "form_slug": "cotis", "fiscal_year_id": fy})
    assert r.status_code == 400


def test_adjust_zero_gap_refused(client_and_db):
    client, db_path = client_and_db
    fy = 1
    _seed(db_path, fy, collected=382500, recorded_tx=[382500])
    client.put("/api/helloasso/links", json={
        "form_type": "Membership", "form_slug": "cotis",
        "category_id": 20, "from_entity_id": 7, "to_entity_id": 1})
    r = client.post("/api/helloasso/adjust", json={
        "form_type": "Membership", "form_slug": "cotis", "fiscal_year_id": fy})
    assert r.status_code == 400  # aucun écart à ajuster
