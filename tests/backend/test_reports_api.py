"""Tests TDD pour le module reports (compte de résultat + bilan).

Convention monétaire (C1+C2) :
  - `amount` en DB = entier de centimes, TOUJOURS POSITIF.
  - Sens porté par from_entity_id -> to_entity_id.
  - PRODUIT/RECETTE = to_entity INTERNE et from_entity EXTERNE.
  - CHARGE/DÉPENSE  = from_entity INTERNE et to_entity EXTERNE.
  - VIREMENT INTERNE (les deux internes) = ni produit ni charge.
"""
import sqlite3
import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_entity(client, name: str, entity_type: str) -> dict:
    r = client.post("/api/entities/", json={"name": name, "type": entity_type})
    assert r.status_code == 201, r.text
    return r.json()


def _make_category(client, name: str) -> dict:
    r = client.post("/api/categories/", json={"name": name, "type": "both"})
    assert r.status_code == 201, r.text
    return r.json()


def _make_tx(client, *, date: str, label: str, amount: int,
             from_entity_id: int, to_entity_id: int,
             category_id: int = None) -> dict:
    payload = {
        "date": date, "label": label, "amount": amount,
        "from_entity_id": from_entity_id, "to_entity_id": to_entity_id,
    }
    if category_id is not None:
        payload["category_id"] = category_id
    r = client.post("/api/transactions/", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _make_fy(client, name="2025-2026", start="2025-09-01", end="2026-08-31") -> dict:
    r = client.post("/api/budget/fiscal-years", json={"name": name, "start_date": start, "notes": ""})
    assert r.status_code == 201, r.text
    fy = r.json()
    # close it so end_date is set
    if end:
        r2 = client.post(f"/api/budget/fiscal-years/{fy['id']}/close", json={"end_date": end})
        assert r2.status_code == 200, r2.text
        fy = r2.json()
    return fy


# ---------------------------------------------------------------------------
# Compte de résultat — structure de base
# ---------------------------------------------------------------------------

def test_compte_resultat_structure(client):
    """Le compte de résultat renvoie les clés attendues même sans transactions."""
    r = client.get("/api/reports/compte-resultat", params={"start_date": "2025-01-01", "end_date": "2025-12-31"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert "produits" in data
    assert "charges" in data
    assert "total_produits" in data
    assert "total_charges" in data
    assert "resultat" in data


def test_compte_resultat_produits_et_charges(client):
    """Recettes (from externe -> to interne) et dépenses (from interne -> to externe)
    sont correctement ventilées par catégorie."""
    int_e = _make_entity(client, "BDA", "internal")
    ext_e = _make_entity(client, "Fournisseur", "external")
    cat_recette = _make_category(client, "Cotisations")
    cat_charge = _make_category(client, "Matériel")

    # 2 recettes de 150 € (15000 c) et 100 € (10000 c) dans la même catégorie
    _make_tx(client, date="2025-03-10", label="Cotis A", amount=15000,
             from_entity_id=ext_e["id"], to_entity_id=int_e["id"],
             category_id=cat_recette["id"])
    _make_tx(client, date="2025-04-05", label="Cotis B", amount=10000,
             from_entity_id=ext_e["id"], to_entity_id=int_e["id"],
             category_id=cat_recette["id"])
    # 1 dépense de 80 € (8000 c)
    _make_tx(client, date="2025-05-20", label="Achat matériel", amount=8000,
             from_entity_id=int_e["id"], to_entity_id=ext_e["id"],
             category_id=cat_charge["id"])

    r = client.get("/api/reports/compte-resultat",
                   params={"start_date": "2025-01-01", "end_date": "2025-12-31"})
    assert r.status_code == 200, r.text
    data = r.json()

    assert data["total_produits"] == 25000   # 15000 + 10000
    assert data["total_charges"] == 8000
    assert data["resultat"] == 17000          # 25000 - 8000

    # Vérifier la ligne produits par catégorie
    produits_by_cat = {p["category_name"]: p["montant"] for p in data["produits"]}
    assert produits_by_cat.get("Cotisations") == 25000

    charges_by_cat = {c["category_name"]: c["montant"] for c in data["charges"]}
    assert charges_by_cat.get("Matériel") == 8000


def test_compte_resultat_virement_interne_ignore(client):
    """Un virement interne (from interne -> to interne) n'apparaît
    ni en produit ni en charge."""
    int1 = _make_entity(client, "BDA", "internal")
    int2 = _make_entity(client, "Gastronomine", "internal")
    ext_e = _make_entity(client, "Ext", "external")
    cat = _make_category(client, "Divers")

    # Virement interne : 5000 centimes
    _make_tx(client, date="2025-06-01", label="Virement interne", amount=5000,
             from_entity_id=int1["id"], to_entity_id=int2["id"],
             category_id=cat["id"])
    # Une vraie recette pour avoir au moins 1 produit
    _make_tx(client, date="2025-06-15", label="Recette externe", amount=2000,
             from_entity_id=ext_e["id"], to_entity_id=int1["id"],
             category_id=cat["id"])

    r = client.get("/api/reports/compte-resultat",
                   params={"start_date": "2025-01-01", "end_date": "2025-12-31"})
    assert r.status_code == 200, r.text
    data = r.json()

    assert data["total_produits"] == 2000
    assert data["total_charges"] == 0
    assert data["resultat"] == 2000


def test_compte_resultat_periode_filtre(client):
    """Seules les transactions dans la période demandée sont comptées."""
    int_e = _make_entity(client, "Asso", "internal")
    ext_e = _make_entity(client, "Tiers", "external")

    # Dans la période
    _make_tx(client, date="2025-03-15", label="In", amount=10000,
             from_entity_id=ext_e["id"], to_entity_id=int_e["id"])
    # Hors période
    _make_tx(client, date="2024-12-31", label="Out", amount=50000,
             from_entity_id=ext_e["id"], to_entity_id=int_e["id"])

    r = client.get("/api/reports/compte-resultat",
                   params={"start_date": "2025-01-01", "end_date": "2025-12-31"})
    data = r.json()
    assert data["total_produits"] == 10000   # seule la tx de mars 2025


def test_compte_resultat_via_fiscal_year_id(client):
    """fiscal_year_id est accepté ; les bornes sont lues depuis fiscal_years."""
    int_e = _make_entity(client, "BDA", "internal")
    ext_e = _make_entity(client, "Ext", "external")

    # Créer les transactions AVANT de fermer l'exercice (le module transactions
    # bloque les écritures dans un exercice clôturé).
    _make_tx(client, date="2025-06-01", label="Recette FY", amount=30000,
             from_entity_id=ext_e["id"], to_entity_id=int_e["id"])
    _make_tx(client, date="2024-01-01", label="Hors FY", amount=99999,
             from_entity_id=ext_e["id"], to_entity_id=int_e["id"])

    fy = _make_fy(client, name="FY2025", start="2025-01-01", end="2025-12-31")

    r = client.get("/api/reports/compte-resultat",
                   params={"fiscal_year_id": fy["id"]})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total_produits"] == 30000


# ---------------------------------------------------------------------------
# Bilan simplifié
# ---------------------------------------------------------------------------

def test_bilan_structure(client):
    """GET /api/reports/bilan renvoie les clés attendues."""
    r = client.get("/api/reports/bilan")
    assert r.status_code == 200, r.text
    data = r.json()
    assert "tresorerie_par_entite" in data
    assert "total_actif" in data


def test_bilan_tresorerie(client):
    """La trésorerie reflète le solde consolidé des entités internes racines."""
    int_e = _make_entity(client, "BDA", "internal")
    ext_e = _make_entity(client, "Ext", "external")

    # Recette de 200 € = 20000 c
    _make_tx(client, date="2025-06-01", label="Recette", amount=20000,
             from_entity_id=ext_e["id"], to_entity_id=int_e["id"])
    # Dépense de 50 € = 5000 c
    _make_tx(client, date="2025-06-15", label="Dépense", amount=5000,
             from_entity_id=int_e["id"], to_entity_id=ext_e["id"])

    r = client.get("/api/reports/bilan")
    assert r.status_code == 200, r.text
    data = r.json()

    entities = {e["entity_id"]: e for e in data["tresorerie_par_entite"]}
    assert int_e["id"] in entities
    assert entities[int_e["id"]]["solde"] == 15000  # 20000 - 5000


def test_bilan_tresorerie_total_actif_est_une_somme_signee(client):
    """Une entité racine en découvert réduit le total_actif au lieu de contribuer 0
    (régression : l'ancien code ne sommait que les soldes strictement positifs)."""
    int_ok = _make_entity(client, "BDA", "internal")
    int_deficit = _make_entity(client, "Gastronomine", "internal")
    ext_e = _make_entity(client, "Ext", "external")

    # Racine bénéficiaire : +300 € = 30000 c
    _make_tx(client, date="2025-06-01", label="Recette", amount=30000,
             from_entity_id=ext_e["id"], to_entity_id=int_ok["id"])
    # Racine en découvert : dépense de 100 € sans recette -> solde = -10000 c
    _make_tx(client, date="2025-06-10", label="Dépense sans recette", amount=10000,
             from_entity_id=int_deficit["id"], to_entity_id=ext_e["id"])

    r = client.get("/api/reports/bilan")
    assert r.status_code == 200, r.text
    data = r.json()

    entities = {e["entity_id"]: e for e in data["tresorerie_par_entite"]}
    assert entities[int_ok["id"]]["solde"] == 30000
    assert entities[int_deficit["id"]]["solde"] == -10000
    # Somme signée : 30000 + (-10000) = 20000 (et non 30000 si le découvert
    # avait été ignoré).
    assert data["total_actif"] == 20000
    assert "positifs" not in data["hypotheses"].lower()


# ---------------------------------------------------------------------------
# Guard d'autorisation (simplifié : plus d'auth, accès toujours ouvert)
# ---------------------------------------------------------------------------

def test_compte_resultat_sans_auth_passe(client):
    """L'accès est toujours ouvert (pas d'authentification)."""
    r = client.get("/api/reports/compte-resultat",
                   params={"start_date": "2025-01-01", "end_date": "2025-12-31"})
    assert r.status_code == 200
