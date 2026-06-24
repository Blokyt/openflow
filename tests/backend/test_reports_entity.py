"""Tests du compte de résultat et du bilan PAR CLUB (paramètre entity_id).

Périmètre P = {entité + descendants internes}. Un flux entrant dans P depuis
hors-P (ex: dotation BDA -> club) est un produit du club ; un flux sortant est
une charge ; les flux intra-P s'annulent. Sans entity_id : comportement global
inchangé.
"""


def _make_entity(client, name, entity_type, parent_id=None):
    payload = {"name": name, "type": entity_type}
    if parent_id is not None:
        payload["parent_id"] = parent_id
    r = client.post("/api/entities/", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _make_tx(client, *, date, label, amount, from_entity_id, to_entity_id, category_id=None):
    payload = {"date": date, "label": label, "amount": amount,
               "from_entity_id": from_entity_id, "to_entity_id": to_entity_id}
    if category_id is not None:
        payload["category_id"] = category_id
    r = client.post("/api/transactions/", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _make_fy(client, name="2025", start="2025-01-01", end="2025-12-31"):
    r = client.post("/api/budget/fiscal-years", json={"name": name, "start_date": start, "notes": ""})
    assert r.status_code == 201, r.text
    fy = r.json()
    if end:
        r2 = client.post(f"/api/budget/fiscal-years/{fy['id']}/close", json={"end_date": end})
        assert r2.status_code == 200, r2.text
        fy = r2.json()
    return fy


def _set_opening(client, fy_id, entity_id, amount):
    r = client.put(f"/api/budget/fiscal-years/{fy_id}/opening-balances/{entity_id}",
                   json={"amount": amount, "source": "test", "notes": ""})
    assert r.status_code in (200, 201), r.text
    return r.json()


# ─── Compte de résultat par club ─────────────────────────────────────────────

def test_cr_global_inchange_sans_entity_id(client):
    """Sans entity_id, seuls les flux avec l'extérieur de l'asso comptent."""
    bda = _make_entity(client, "BDA", "internal")
    club = _make_entity(client, "Club", "internal", parent_id=bda["id"])
    ext = _make_entity(client, "Ext", "external")
    _make_tx(client, date="2025-03-01", label="Recette", amount=5000,
             from_entity_id=ext["id"], to_entity_id=bda["id"])
    _make_tx(client, date="2025-04-01", label="Dotation", amount=10000,
             from_entity_id=bda["id"], to_entity_id=club["id"])  # interne -> neutre au global
    fy = _make_fy(client)

    cr = client.get("/api/reports/compte-resultat", params={"fiscal_year_id": fy["id"]}).json()
    assert cr["total_produits"] == 5000
    assert cr["total_charges"] == 0
    assert cr["resultat"] == 5000


def test_cr_club_dotation_interne_est_produit(client):
    """La dotation reçue d'un autre interne (BDA) est un produit du club."""
    bda = _make_entity(client, "BDA", "internal")
    club = _make_entity(client, "Club", "internal", parent_id=bda["id"])
    ext = _make_entity(client, "Ext", "external")
    _make_tx(client, date="2025-03-01", label="Recette BDA", amount=5000,
             from_entity_id=ext["id"], to_entity_id=bda["id"])
    _make_tx(client, date="2025-04-01", label="Dotation", amount=10000,
             from_entity_id=bda["id"], to_entity_id=club["id"])
    fy = _make_fy(client)

    cr = client.get("/api/reports/compte-resultat",
                    params={"fiscal_year_id": fy["id"], "entity_id": club["id"]}).json()
    assert cr["total_produits"] == 10000   # dotation reçue
    assert cr["total_charges"] == 0
    assert cr["resultat"] == 10000


def test_cr_club_charge_vers_externe(client):
    bda = _make_entity(client, "BDA", "internal")
    club = _make_entity(client, "Club", "internal", parent_id=bda["id"])
    ext = _make_entity(client, "Ext", "external")
    _make_tx(client, date="2025-05-01", label="Achat club", amount=3000,
             from_entity_id=club["id"], to_entity_id=ext["id"])
    fy = _make_fy(client)

    cr = client.get("/api/reports/compte-resultat",
                    params={"fiscal_year_id": fy["id"], "entity_id": club["id"]}).json()
    assert cr["total_charges"] == 3000
    assert cr["resultat"] == -3000


def test_cr_club_flux_intra_perimetre_neutre(client):
    """Un flux entre le club et son sous-club (intra-périmètre) est neutre."""
    club = _make_entity(client, "Club", "internal")
    sous = _make_entity(client, "Sous-club", "internal", parent_id=club["id"])
    ext = _make_entity(client, "Ext", "external")
    _make_tx(client, date="2025-03-01", label="Recette", amount=8000,
             from_entity_id=ext["id"], to_entity_id=club["id"])
    _make_tx(client, date="2025-04-01", label="Reversement interne", amount=4000,
             from_entity_id=club["id"], to_entity_id=sous["id"])
    fy = _make_fy(client)

    cr = client.get("/api/reports/compte-resultat",
                    params={"fiscal_year_id": fy["id"], "entity_id": club["id"]}).json()
    assert cr["total_produits"] == 8000   # le flux intra-périmètre ne compte pas
    assert cr["total_charges"] == 0
    assert cr["resultat"] == 8000


# ─── Bilan par club ──────────────────────────────────────────────────────────

def test_bilan_club_equilibre(client):
    bda = _make_entity(client, "BDA", "internal")
    club = _make_entity(client, "Club", "internal", parent_id=bda["id"])
    ext = _make_entity(client, "Ext", "external")
    _make_tx(client, date="2025-03-01", label="Dotation", amount=10000,
             from_entity_id=bda["id"], to_entity_id=club["id"])
    _make_tx(client, date="2025-05-01", label="Achat club", amount=3000,
             from_entity_id=club["id"], to_entity_id=ext["id"])
    fy = _make_fy(client)

    data = client.get("/api/reports/bilan",
                      params={"fiscal_year_id": fy["id"], "entity_id": club["id"]}).json()
    assert data["equilibre"] is True
    assert data["passif"]["report_a_nouveau"] == 0
    assert data["passif"]["resultat_exercice"] == 7000   # 10000 dotation - 3000 charge
    assert data["actif"]["total"] == 7000
    assert data["entity_id"] == club["id"]


def test_bilan_club_equilibre_avec_ouverture(client):
    bda = _make_entity(client, "BDA", "internal")
    club = _make_entity(client, "Club", "internal", parent_id=bda["id"])
    ext = _make_entity(client, "Ext", "external")
    _make_tx(client, date="2025-03-01", label="Dotation", amount=10000,
             from_entity_id=bda["id"], to_entity_id=club["id"])
    _make_tx(client, date="2025-05-01", label="Achat club", amount=3000,
             from_entity_id=club["id"], to_entity_id=ext["id"])
    fy = _make_fy(client)
    _set_opening(client, fy["id"], club["id"], 5000)

    data = client.get("/api/reports/bilan",
                      params={"fiscal_year_id": fy["id"], "entity_id": club["id"]}).json()
    assert data["equilibre"] is True
    assert data["passif"]["report_a_nouveau"] == 5000
    assert data["passif"]["resultat_exercice"] == 7000
    assert data["actif"]["total"] == 12000


def test_bilan_global_equilibre_inchange(client):
    """Sans entity_id, le bilan consolidé reste équilibré et inchangé."""
    bda = _make_entity(client, "BDA", "internal")
    club = _make_entity(client, "Club", "internal", parent_id=bda["id"])
    ext = _make_entity(client, "Ext", "external")
    _make_tx(client, date="2025-03-01", label="Recette", amount=30000,
             from_entity_id=ext["id"], to_entity_id=bda["id"])
    _make_tx(client, date="2025-04-01", label="Dotation", amount=10000,
             from_entity_id=bda["id"], to_entity_id=club["id"])
    fy = _make_fy(client)

    data = client.get("/api/reports/bilan", params={"fiscal_year_id": fy["id"]}).json()
    assert data["equilibre"] is True
    assert data["passif"]["resultat_exercice"] == 30000   # virement interne neutre
    assert data["actif"]["total"] == 30000


# ─── Validation entity_id ────────────────────────────────────────────────────

def test_cr_entity_externe_400(client):
    ext = _make_entity(client, "Ext", "external")
    fy = _make_fy(client)
    r = client.get("/api/reports/compte-resultat",
                   params={"fiscal_year_id": fy["id"], "entity_id": ext["id"]})
    assert r.status_code == 400


def test_cr_entity_inconnue_404(client):
    fy = _make_fy(client)
    r = client.get("/api/reports/compte-resultat",
                   params={"fiscal_year_id": fy["id"], "entity_id": 99999})
    assert r.status_code == 404


def test_bilan_entity_inconnue_404(client):
    fy = _make_fy(client)
    r = client.get("/api/reports/bilan",
                   params={"fiscal_year_id": fy["id"], "entity_id": 99999})
    assert r.status_code == 404


def test_cr_pdf_club(client):
    bda = _make_entity(client, "BDA", "internal")
    club = _make_entity(client, "Club", "internal", parent_id=bda["id"])
    _make_tx(client, date="2025-04-01", label="Dotation", amount=10000,
             from_entity_id=bda["id"], to_entity_id=club["id"])
    fy = _make_fy(client)
    r = client.get("/api/reports/compte-resultat/pdf",
                   params={"fiscal_year_id": fy["id"], "entity_id": club["id"]})
    assert r.status_code == 200, r.text
    assert r.content[:4] == b"%PDF"
