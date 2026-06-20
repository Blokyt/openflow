"""Tests TDD — couche engagement du module reports (Phase 2).

Rattachement à l'exercice via créances (produits à recevoir) et dettes (charges
à payer), avec contre-passation (extourne) automatique de l'exercice N-1 pour
éviter le double comptage. Le bilan complet (disponibilités + créances à l'actif ;
fonds associatifs + résultat + dettes au passif) reste équilibré.

Montants en CENTIMES entiers positifs ; sens via from/to.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_entity(client, name, entity_type):
    r = client.post("/api/entities/", json={"name": name, "type": entity_type})
    assert r.status_code == 201, r.text
    return r.json()


def _make_category(client, name):
    r = client.post("/api/categories/", json={"name": name})
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


def _open_fy(client, name, start):
    r = client.post("/api/budget/fiscal-years", json={"name": name, "start_date": start, "notes": ""})
    assert r.status_code == 201, r.text
    return r.json()


def _close_fy(client, fy_id, end):
    r = client.post(f"/api/budget/fiscal-years/{fy_id}/close", json={"end_date": end})
    assert r.status_code == 200, r.text
    return r.json()


def _make_accrual(client, *, fiscal_year_id, kind, amount, label,
                  category_id=None, entity_id=None):
    payload = {"fiscal_year_id": fiscal_year_id, "kind": kind, "amount": amount, "label": label}
    if category_id is not None:
        payload["category_id"] = category_id
    if entity_id is not None:
        payload["entity_id"] = entity_id
    r = client.post("/api/reports/accruals", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _cr(client, fy_id):
    return client.get("/api/reports/compte-resultat", params={"fiscal_year_id": fy_id}).json()


def _bilan(client, fy_id):
    return client.get("/api/reports/bilan", params={"fiscal_year_id": fy_id}).json()


# ---------------------------------------------------------------------------
# CRUD des régularisations
# ---------------------------------------------------------------------------

def test_accrual_create_and_list(client):
    bda = _make_entity(client, "BDA", "internal")
    fy = _open_fy(client, "2025", "2025-01-01")
    _make_accrual(client, fiscal_year_id=fy["id"], kind="creance", amount=50000,
                  label="Subvention à recevoir", entity_id=bda["id"])

    r = client.get("/api/reports/accruals", params={"fiscal_year_id": fy["id"]})
    assert r.status_code == 200, r.text
    items = r.json()
    assert len(items) == 1
    assert items[0]["kind"] == "creance"
    assert items[0]["amount"] == 50000


def test_accrual_kind_invalide_400(client):
    fy = _open_fy(client, "2025", "2025-01-01")
    r = client.post("/api/reports/accruals", json={
        "fiscal_year_id": fy["id"], "kind": "autre", "amount": 1000, "label": "X",
    })
    assert r.status_code == 400


def test_accrual_delete(client):
    fy = _open_fy(client, "2025", "2025-01-01")
    a = _make_accrual(client, fiscal_year_id=fy["id"], kind="dette", amount=3000, label="Facture")
    r = client.delete(f"/api/reports/accruals/{a['id']}")
    assert r.status_code == 200, r.text
    items = client.get("/api/reports/accruals", params={"fiscal_year_id": fy["id"]}).json()
    assert items == []


# ---------------------------------------------------------------------------
# Rattachement à l'exercice
# ---------------------------------------------------------------------------

def test_creance_reconnue_en_produit_de_l_exercice(client):
    """Une créance saisie en N est un produit de N, même sans encaissement."""
    bda = _make_entity(client, "BDA", "internal")
    fy = _open_fy(client, "2025", "2025-01-01")
    _make_accrual(client, fiscal_year_id=fy["id"], kind="creance", amount=50000,
                  label="Subvention BDE à recevoir", entity_id=bda["id"])
    _close_fy(client, fy["id"], "2025-12-31")

    cr = _cr(client, fy["id"])
    assert cr["total_produits"] == 50000
    assert cr["resultat"] == 50000


def test_non_double_comptage_creance_encaissee_en_n_plus_1(client):
    """Créance reconnue en N ; l'encaissement en N+1 ne recrée PAS le produit
    (extourne automatique de la créance N)."""
    bda = _make_entity(client, "BDA", "internal")
    ext = _make_entity(client, "Région", "external")

    # Exercice N : créance de 50 000, aucun encaissement.
    fyN = _open_fy(client, "N", "2025-01-01")
    _make_accrual(client, fiscal_year_id=fyN["id"], kind="creance", amount=50000,
                  label="Subvention à recevoir", entity_id=bda["id"])
    _close_fy(client, fyN["id"], "2025-12-31")

    # Exercice N+1 : la subvention est encaissée.
    fyN1 = _open_fy(client, "N+1", "2026-01-01")
    _make_tx(client, date="2026-03-01", label="Encaissement subvention", amount=50000,
             from_entity_id=ext["id"], to_entity_id=bda["id"])

    # N : produit reconnu.
    crN = _cr(client, fyN["id"])
    assert crN["resultat"] == 50000

    # N+1 : encaissement neutralisé par l'extourne -> résultat nul.
    crN1 = _cr(client, fyN1["id"])
    assert crN1["total_produits"] == 0
    assert crN1["resultat"] == 0


# ---------------------------------------------------------------------------
# Bilan en engagement — équilibre avec créances et dettes
# ---------------------------------------------------------------------------

def test_bilan_engagement_equilibre_creances_et_dettes(client):
    bda = _make_entity(client, "BDA", "internal")
    ext = _make_entity(client, "Ext", "external")

    _make_tx(client, date="2025-03-01", label="Recette", amount=30000,
             from_entity_id=ext["id"], to_entity_id=bda["id"])
    _make_tx(client, date="2025-05-01", label="Dépense", amount=12000,
             from_entity_id=bda["id"], to_entity_id=ext["id"])

    fy = _open_fy(client, "2025", "2025-01-01")
    _make_accrual(client, fiscal_year_id=fy["id"], kind="creance", amount=5000,
                  label="Cotisation à recevoir", entity_id=bda["id"])
    _make_accrual(client, fiscal_year_id=fy["id"], kind="dette", amount=3000,
                  label="Facture à payer", entity_id=bda["id"])
    _close_fy(client, fy["id"], "2025-12-31")

    cr = _cr(client, fy["id"])
    assert cr["total_produits"] == 35000   # 30000 trésorerie + 5000 créance
    assert cr["total_charges"] == 15000    # 12000 trésorerie + 3000 dette
    assert cr["resultat"] == 20000

    bilan = _bilan(client, fy["id"])
    assert bilan["equilibre"] is True
    assert bilan["actif"]["total_creances"] == 5000
    assert bilan["passif"]["total_dettes"] == 3000
    assert bilan["passif"]["resultat_exercice"] == 20000
    assert bilan["actif"]["total"] == bilan["passif"]["total"]
    assert bilan["actif"]["total"] == 23000   # disponibilités 18000 + créances 5000
