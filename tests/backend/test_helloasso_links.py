"""Tests du modèle « liaison transactions » HelloAsso.

linked_cents = somme des transactions associées à la campagne.
pending_cents = collected_cents - linked_cents (montant restant à prendre en compte).
Une campagne disparaît de « à traiter » quand pending atteint 0.
"""
import sqlite3


def _make_fiscal_year(db_path, fy_id=1, start="2025-09-01", end=None):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO fiscal_years (id, name, start_date, end_date, created_at, updated_at) "
        "VALUES (?, '2025-2026', ?, ?, '2025-09-01T00:00:00', '2025-09-01T00:00:00')",
        (fy_id, start, end),
    )
    conn.commit()
    conn.close()
    return fy_id


def _seed_campaign(db_path, fy_id, collected, slug="cotis"):
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO helloasso_campaigns
           (fiscal_year_id, form_type, form_slug, title, state, collected_cents, currency, last_synced_at, acknowledged_cents)
           VALUES (?, 'Membership', ?, 'Cotisations', 'Public', ?, 'EUR', '2026-01-01T00:00:00', 0)""",
        (fy_id, slug, collected),
    )
    conn.commit()
    cid = conn.execute(
        "SELECT id FROM helloasso_campaigns WHERE fiscal_year_id = ? AND form_slug = ?", (fy_id, slug)
    ).fetchone()[0]
    conn.close()
    return cid


def _entities(client):
    """Crée une entité interne (asso) et une externe (adhérents)."""
    interne = client.post("/api/entities/", json={"name": "Asso", "type": "internal"}).json()["id"]
    externe = client.post("/api/entities/", json={"name": "Adhérents", "type": "external"}).json()["id"]
    return interne, externe


def _recette(client, interne, externe, amount, date="2026-01-15", label="cotis"):
    """Crée une recette (externe -> interne) et renvoie son id."""
    return client.post("/api/transactions/", json={
        "date": date, "label": label, "amount": amount,
        "from_entity_id": externe, "to_entity_id": interne,
    }).json()["id"]


# ─── Calcul lié / restant ────────────────────────────────────────────────────

def test_links_empty_initially(client_and_db):
    client, db_path = client_and_db
    fy = _make_fiscal_year(db_path)
    cid = _seed_campaign(db_path, fy, collected=400000)
    r = client.get(f"/api/helloasso/campaigns/{cid}/links")
    assert r.status_code == 200
    body = r.json()
    assert body["linked_cents"] == 0
    assert body["pending_cents"] == 400000
    assert body["links"] == []


def test_link_reduces_pending_cotisations_example(client_and_db):
    """Exemple cotisations : 4000 collectés, on associe 3700 -> 300 restant."""
    client, db_path = client_and_db
    fy = _make_fiscal_year(db_path)
    cid = _seed_campaign(db_path, fy, collected=400000)
    interne, externe = _entities(client)
    tx = _recette(client, interne, externe, 370000)

    r = client.post(f"/api/helloasso/campaigns/{cid}/links", json={"transaction_id": tx})
    assert r.status_code == 201
    body = r.json()
    assert body["linked_cents"] == 370000
    assert body["pending_cents"] == 30000
    assert len(body["links"]) == 1

    # La campagne reflète le pending dans la liste générale.
    rows = client.get(f"/api/helloasso/campaigns?fiscal_year_id={fy}").json()
    assert rows[0]["linked_cents"] == 370000
    assert rows[0]["pending_cents"] == 30000


def test_full_coverage_zeroes_pending(client_and_db):
    client, db_path = client_and_db
    fy = _make_fiscal_year(db_path)
    cid = _seed_campaign(db_path, fy, collected=400000)
    interne, externe = _entities(client)
    tx1 = _recette(client, interne, externe, 370000)
    tx2 = _recette(client, interne, externe, 30000)

    client.post(f"/api/helloasso/campaigns/{cid}/links", json={"transaction_id": tx1})
    r = client.post(f"/api/helloasso/campaigns/{cid}/links", json={"transaction_id": tx2})
    assert r.json()["pending_cents"] == 0


def test_unlink_restores_pending(client_and_db):
    client, db_path = client_and_db
    fy = _make_fiscal_year(db_path)
    cid = _seed_campaign(db_path, fy, collected=400000)
    interne, externe = _entities(client)
    tx = _recette(client, interne, externe, 370000)
    client.post(f"/api/helloasso/campaigns/{cid}/links", json={"transaction_id": tx})

    r = client.delete(f"/api/helloasso/campaigns/{cid}/links/{tx}")
    assert r.status_code == 200
    assert r.json()["pending_cents"] == 400000
    assert r.json()["links"] == []


def test_transaction_splits_across_campaigns(client_and_db):
    """Régularisation : une transaction est répartie (many-to-many) sur plusieurs
    campagnes, chaque lien n'imputant qu'une partie du montant."""
    client, db_path = client_and_db
    fy = _make_fiscal_year(db_path)
    cid1 = _seed_campaign(db_path, fy, collected=30000, slug="cotis")   # 300 €
    cid2 = _seed_campaign(db_path, fy, collected=418000, slug="dons")   # 4180 €
    interne, externe = _entities(client)
    tx = _recette(client, interne, externe, 448000)                     # régul 4480 €

    # Impute auto sur cid1 : min(restant campagne 300 €, restant tx 4480 €) = 300 €.
    r1 = client.post(f"/api/helloasso/campaigns/{cid1}/links", json={"transaction_id": tx})
    assert r1.status_code == 201
    assert r1.json()["linked_cents"] == 30000
    assert r1.json()["pending_cents"] == 0

    # La MÊME transaction s'impute sur cid2 : il lui reste 4180 €.
    r2 = client.post(f"/api/helloasso/campaigns/{cid2}/links", json={"transaction_id": tx})
    assert r2.status_code == 201
    assert r2.json()["linked_cents"] == 418000
    assert r2.json()["pending_cents"] == 0


def test_link_amount_override_and_fully_allocated_guard(client_and_db):
    client, db_path = client_and_db
    fy = _make_fiscal_year(db_path)
    cid = _seed_campaign(db_path, fy, collected=100000, slug="cotis")
    interne, externe = _entities(client)
    tx = _recette(client, interne, externe, 60000)
    # Impute explicitement 25 000 sur la campagne.
    r = client.post(f"/api/helloasso/campaigns/{cid}/links", json={"transaction_id": tx, "amount_cents": 25000})
    assert r.json()["linked_cents"] == 25000
    # Trop imputer (au-delà du restant de la transaction) -> 400.
    cid2 = _seed_campaign(db_path, fy, collected=100000, slug="dons")
    r = client.post(f"/api/helloasso/campaigns/{cid2}/links", json={"transaction_id": tx, "amount_cents": 40000})
    assert r.status_code == 400  # il ne reste que 35 000


def test_link_same_campaign_twice_conflict(client_and_db):
    client, db_path = client_and_db
    fy = _make_fiscal_year(db_path)
    cid = _seed_campaign(db_path, fy, collected=400000)
    interne, externe = _entities(client)
    tx = _recette(client, interne, externe, 100000)
    client.post(f"/api/helloasso/campaigns/{cid}/links", json={"transaction_id": tx})
    r = client.post(f"/api/helloasso/campaigns/{cid}/links", json={"transaction_id": tx})
    assert r.status_code == 409


def test_link_unknown_campaign_404(client_and_db):
    client, db_path = client_and_db
    _make_fiscal_year(db_path)
    r = client.post("/api/helloasso/campaigns/99999/links", json={"transaction_id": 1})
    assert r.status_code == 404


def test_link_unknown_transaction_404(client_and_db):
    client, db_path = client_and_db
    fy = _make_fiscal_year(db_path)
    cid = _seed_campaign(db_path, fy, collected=400000)
    r = client.post(f"/api/helloasso/campaigns/{cid}/links", json={"transaction_id": 99999})
    assert r.status_code == 404


def test_unlink_unknown_link_404(client_and_db):
    client, db_path = client_and_db
    fy = _make_fiscal_year(db_path)
    cid = _seed_campaign(db_path, fy, collected=400000)
    r = client.delete(f"/api/helloasso/campaigns/{cid}/links/99999")
    assert r.status_code == 404


# ─── Suggestions ─────────────────────────────────────────────────────────────

def test_suggestions_are_mandate_receipts_sorted_closest_below(client_and_db):
    """Suggestions = recettes du mandat triées « la plus proche inférieurement »."""
    client, db_path = client_and_db
    fy = _make_fiscal_year(db_path)
    cid = _seed_campaign(db_path, fy, collected=400000)
    interne, externe = _entities(client)
    _recette(client, interne, externe, 370000, label="r370")
    _recette(client, interne, externe, 50000, label="r50")
    _recette(client, interne, externe, 410000, label="r410")
    _recette(client, interne, externe, 200000, label="r200")

    s = client.get(f"/api/helloasso/campaigns/{cid}/suggestions").json()
    amounts = [x["amount"] for x in s["suggestions"]]
    # reste = 400000 : inférieurs du plus proche (370000, 200000, 50000) puis supérieur (410000)
    assert amounts == [370000, 200000, 50000, 410000]


def test_suggestions_exclude_linked_and_track_remaining(client_and_db):
    client, db_path = client_and_db
    fy = _make_fiscal_year(db_path)
    cid = _seed_campaign(db_path, fy, collected=400000)
    interne, externe = _entities(client)
    tx370 = _recette(client, interne, externe, 370000)
    _recette(client, interne, externe, 50000)
    _recette(client, interne, externe, 200000)

    client.post(f"/api/helloasso/campaigns/{cid}/links", json={"transaction_id": tx370})
    s = client.get(f"/api/helloasso/campaigns/{cid}/suggestions").json()
    amounts = [x["amount"] for x in s["suggestions"]]
    assert 370000 not in amounts          # déjà liée, exclue
    assert s["pending_cents"] == 30000    # reste après le lien
    # reste = 30000 : tout est au-dessus, le plus proche d'abord -> 50000 puis 200000
    assert amounts == [50000, 200000]


def test_suggestions_exclude_expenses_and_out_of_period(client_and_db):
    client, db_path = client_and_db
    # Mandat ouvert (start 2025-09-01) : les transactions y sont éditables.
    fy = _make_fiscal_year(db_path, start="2025-09-01", end=None)
    cid = _seed_campaign(db_path, fy, collected=400000)
    interne, externe = _entities(client)
    # Dépense (interne -> externe) dans la période : exclue car c'est une dépense.
    client.post("/api/transactions/", json={
        "date": "2026-01-15", "label": "depense", "amount": 100000,
        "from_entity_id": interne, "to_entity_id": externe,
    })
    # Recette avant le début d'exercice : hors période, donc exclue.
    _recette(client, interne, externe, 120000, date="2025-01-01", label="hors")
    # Recette valide dans la période.
    valide = _recette(client, interne, externe, 90000, date="2026-02-01", label="ok")

    s = client.get(f"/api/helloasso/campaigns/{cid}/suggestions").json()
    ids = [x["transaction_id"] for x in s["suggestions"]]
    assert ids == [valide]
