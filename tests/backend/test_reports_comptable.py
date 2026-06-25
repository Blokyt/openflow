"""Tests TDD — couche comptable officielle du module reports (Phase 1).

Plan comptable associatif simplifié + pont catégorie -> compte, compte de
résultat ventilé par compte (classes 6/7), bilan par exercice équilibré
(actif = passif). Méthode : trésorerie (la couche engagement créances/dettes
arrive en Phase 2).

Convention : montants en CENTIMES entiers positifs ; sens via from/to.
  - PRODUIT = from EXTERNE -> to INTERNE
  - CHARGE  = from INTERNE -> to EXTERNE
  - VIREMENT INTERNE (interne -> interne) = ni produit ni charge
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
    payload = {
        "date": date, "label": label, "amount": amount,
        "from_entity_id": from_entity_id, "to_entity_id": to_entity_id,
    }
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
    r = client.put(
        f"/api/budget/fiscal-years/{fy_id}/opening-balances/{entity_id}",
        json={"amount": amount, "source": "test", "notes": ""},
    )
    assert r.status_code in (200, 201), r.text
    return r.json()


def _accounts(client):
    r = client.get("/api/reports/accounts")
    assert r.status_code == 200, r.text
    return r.json()["accounts"]


def _account_id_by_code(client, code):
    for a in _accounts(client):
        if a["code"] == code:
            return a["id"]
    raise AssertionError(f"Compte {code} absent du plan comptable")


def _map(client, category_id, account_id):
    r = client.put("/api/reports/mapping", json={"category_id": category_id, "account_id": account_id})
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------------------
# Plan comptable (seed)
# ---------------------------------------------------------------------------

def test_accounts_seed_present(client):
    """Le plan comptable simplifié est seedé : produits, charges, comptes par défaut."""
    accounts = _accounts(client)
    codes = {a["code"] for a in accounts}
    # produits classe 7
    assert {"70", "74", "756", "76", "77"}.issubset(codes)
    # charges classe 6
    assert {"60", "61", "62", "67"}.issubset(codes)
    # postes de bilan
    assert {"512", "10", "12"}.issubset(codes)

    produits_defaut = [a for a in accounts if a["kind"] == "produit" and a["is_default"]]
    charges_defaut = [a for a in accounts if a["kind"] == "charge" and a["is_default"]]
    assert len(produits_defaut) == 1, "Un seul compte produit par défaut attendu"
    assert len(charges_defaut) == 1, "Un seul compte charge par défaut attendu"


# ---------------------------------------------------------------------------
# Pont catégorie -> compte
# ---------------------------------------------------------------------------

def test_mapping_crud(client):
    """Une catégorie peut être associée à un compte, puis l'association est lue."""
    cat = _make_category(client, "Cotisations")
    acc_id = _account_id_by_code(client, "756")

    # Avant mapping : la catégorie est non mappée.
    before = client.get("/api/reports/mapping")
    assert before.status_code == 200, before.text
    unmapped_codes = {u["category_id"] for u in before.json().get("unmapped", [])}
    assert cat["id"] in unmapped_codes

    _map(client, cat["id"], acc_id)

    after = client.get("/api/reports/mapping").json()
    by_cat = {m["category_id"]: m for m in after["mapping"]}
    assert cat["id"] in by_cat
    assert by_cat[cat["id"]]["account_code"] == "756"


# ---------------------------------------------------------------------------
# Compte de résultat ventilé par compte
# ---------------------------------------------------------------------------

def test_compte_resultat_regroupe_par_compte(client):
    """Les catégories mappées sont regroupées sous leur compte ; les totaux
    restent ceux du calcul par sens from/to (le mapping ne change pas les totaux)."""
    bda = _make_entity(client, "BDA", "internal")
    ext = _make_entity(client, "Ext", "external")
    cot = _make_category(client, "Cotisations")
    buv = _make_category(client, "Buvette")

    _map(client, cot["id"], _account_id_by_code(client, "756"))
    _map(client, buv["id"], _account_id_by_code(client, "70"))

    _make_tx(client, date="2025-03-01", label="Cotis", amount=20000,
             from_entity_id=ext["id"], to_entity_id=bda["id"], category_id=cot["id"])
    _make_tx(client, date="2025-04-01", label="Buvette", amount=5000,
             from_entity_id=ext["id"], to_entity_id=bda["id"], category_id=buv["id"])

    data = client.get("/api/reports/compte-resultat",
                      params={"start_date": "2025-01-01", "end_date": "2025-12-31"}).json()

    assert data["total_produits"] == 25000
    par_compte = {p["code"]: p for p in data["produits_par_compte"]}
    assert par_compte["756"]["montant"] == 20000
    assert par_compte["70"]["montant"] == 5000
    # le détail catégorie est conservé sous le compte
    cats_756 = {c["category_name"] for c in par_compte["756"]["categories"]}
    assert "Cotisations" in cats_756


def test_compte_resultat_categorie_non_mappee_va_au_defaut(client):
    """Une charge dont la catégorie n'est pas mappée tombe dans le compte
    charge par défaut (is_default)."""
    bda = _make_entity(client, "BDA", "internal")
    ext = _make_entity(client, "Ext", "external")
    mat = _make_category(client, "Matériel")  # non mappée volontairement

    _make_tx(client, date="2025-05-01", label="Achat", amount=8000,
             from_entity_id=bda["id"], to_entity_id=ext["id"], category_id=mat["id"])

    data = client.get("/api/reports/compte-resultat",
                      params={"start_date": "2025-01-01", "end_date": "2025-12-31"}).json()

    accounts = _accounts(client)
    defaut_charge = next(a for a in accounts if a["kind"] == "charge" and a["is_default"])
    par_compte = {c["code"]: c for c in data["charges_par_compte"]}
    assert defaut_charge["code"] in par_compte
    assert par_compte[defaut_charge["code"]]["montant"] == 8000
    assert data["total_charges"] == 8000


# ---------------------------------------------------------------------------
# Bilan par exercice — équilibre actif = passif
# ---------------------------------------------------------------------------

def test_bilan_equilibre_sans_ouverture(client):
    """Bilan d'un exercice sans solde d'ouverture : actif = passif, report à
    nouveau nul, résultat = produits - charges."""
    bda = _make_entity(client, "BDA", "internal")
    ext = _make_entity(client, "Ext", "external")

    _make_tx(client, date="2025-03-01", label="Recette", amount=30000,
             from_entity_id=ext["id"], to_entity_id=bda["id"])
    _make_tx(client, date="2025-05-01", label="Dépense", amount=12000,
             from_entity_id=bda["id"], to_entity_id=ext["id"])

    fy = _make_fy(client, name="EX2025", start="2025-01-01", end="2025-12-31")

    data = client.get("/api/reports/bilan", params={"fiscal_year_id": fy["id"]}).json()

    assert data["equilibre"] is True
    assert data["actif"]["total"] == data["passif"]["total"]
    assert data["passif"]["report_a_nouveau"] == 0
    assert data["passif"]["resultat_exercice"] == 18000   # 30000 - 12000
    assert data["actif"]["total"] == 18000


def test_bilan_equilibre_avec_ouverture(client):
    """Avec un solde d'ouverture saisi, le report à nouveau le reflète et le
    bilan reste équilibré."""
    bda = _make_entity(client, "BDA", "internal")
    ext = _make_entity(client, "Ext", "external")

    _make_tx(client, date="2025-03-01", label="Recette", amount=30000,
             from_entity_id=ext["id"], to_entity_id=bda["id"])
    _make_tx(client, date="2025-05-01", label="Dépense", amount=12000,
             from_entity_id=bda["id"], to_entity_id=ext["id"])

    fy = _make_fy(client, name="EX2025", start="2025-01-01", end="2025-12-31")
    _set_opening(client, fy["id"], bda["id"], 50000)  # 500 € de report à nouveau

    data = client.get("/api/reports/bilan", params={"fiscal_year_id": fy["id"]}).json()

    assert data["equilibre"] is True
    assert data["passif"]["report_a_nouveau"] == 50000
    assert data["passif"]["resultat_exercice"] == 18000
    assert data["passif"]["total"] == 68000
    assert data["actif"]["total"] == 68000   # trésorerie de clôture = 50000 + 18000


def test_bilan_resultat_egale_compte_resultat(client):
    """Le résultat affiché au bilan est identique au résultat du compte de résultat."""
    bda = _make_entity(client, "BDA", "internal")
    ext = _make_entity(client, "Ext", "external")

    _make_tx(client, date="2025-02-01", label="Recette", amount=42000,
             from_entity_id=ext["id"], to_entity_id=bda["id"])
    _make_tx(client, date="2025-06-01", label="Dépense", amount=15500,
             from_entity_id=bda["id"], to_entity_id=ext["id"])

    fy = _make_fy(client, name="EX2025", start="2025-01-01", end="2025-12-31")

    cr = client.get("/api/reports/compte-resultat", params={"fiscal_year_id": fy["id"]}).json()
    bilan = client.get("/api/reports/bilan", params={"fiscal_year_id": fy["id"]}).json()

    assert bilan["passif"]["resultat_exercice"] == cr["resultat"]


def test_bilan_virement_interne_neutre(client):
    """Un virement BDA -> club ne déséquilibre pas le bilan consolidé et
    n'affecte pas le résultat."""
    bda = _make_entity(client, "BDA", "internal")
    club = _make_entity(client, "Gastronomine", "internal")
    ext = _make_entity(client, "Ext", "external")

    _make_tx(client, date="2025-03-01", label="Recette", amount=30000,
             from_entity_id=ext["id"], to_entity_id=bda["id"])
    # Virement interne BDA -> club : ne doit rien changer au consolidé.
    _make_tx(client, date="2025-04-01", label="Dotation club", amount=10000,
             from_entity_id=bda["id"], to_entity_id=club["id"])

    fy = _make_fy(client, name="EX2025", start="2025-01-01", end="2025-12-31")
    data = client.get("/api/reports/bilan", params={"fiscal_year_id": fy["id"]}).json()

    assert data["equilibre"] is True
    assert data["passif"]["resultat_exercice"] == 30000   # le virement interne est neutre
    assert data["actif"]["total"] == 30000


# ---------------------------------------------------------------------------
# Export PDF (compte de résultat + bilan)
# ---------------------------------------------------------------------------

def test_compte_resultat_pdf(client):
    bda = _make_entity(client, "BDA", "internal")
    ext = _make_entity(client, "Ext", "external")
    _make_tx(client, date="2025-03-01", label="Recette", amount=12345,
             from_entity_id=ext["id"], to_entity_id=bda["id"])
    r = client.get("/api/reports/compte-resultat/pdf",
                   params={"start_date": "2025-01-01", "end_date": "2025-12-31"})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"


def test_compte_resultat_pdf_sans_periode_400(client):
    r = client.get("/api/reports/compte-resultat/pdf")
    assert r.status_code == 400


def test_bilan_pdf(client):
    bda = _make_entity(client, "BDA", "internal")
    ext = _make_entity(client, "Ext", "external")
    _make_tx(client, date="2025-03-01", label="Recette", amount=30000,
             from_entity_id=ext["id"], to_entity_id=bda["id"])
    fy = _make_fy(client, name="EX2025", start="2025-01-01", end="2025-12-31")
    r = client.get("/api/reports/bilan/pdf", params={"fiscal_year_id": fy["id"]})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"


def test_bilan_pdf_exercice_inconnu_404(client):
    r = client.get("/api/reports/bilan/pdf", params={"fiscal_year_id": 99999})
    assert r.status_code == 404


def test_compte_resultat_pdf_avec_categories(client):
    """Le PDF se génère même avec des contributions détaillées par catégorie."""
    bda = _make_entity(client, "BDA", "internal")
    ext = _make_entity(client, "Ext", "external")
    cot = _make_category(client, "Cotisations")
    buv = _make_category(client, "Buvette")
    _map(client, cot["id"], _account_id_by_code(client, "756"))
    _map(client, buv["id"], _account_id_by_code(client, "70"))
    _make_tx(client, date="2025-03-01", label="Cotis", amount=20000,
             from_entity_id=ext["id"], to_entity_id=bda["id"], category_id=cot["id"])
    _make_tx(client, date="2025-04-01", label="Buvette", amount=5000,
             from_entity_id=ext["id"], to_entity_id=bda["id"], category_id=buv["id"])
    r = client.get("/api/reports/compte-resultat/pdf",
                   params={"start_date": "2025-01-01", "end_date": "2025-12-31"})
    assert r.status_code == 200, r.text
    assert r.content[:4] == b"%PDF"


# ---------------------------------------------------------------------------
# Bilan : détail des créances / dettes par catégorie
# ---------------------------------------------------------------------------

def test_bilan_detaille_creances_dettes_par_categorie(client):
    """Le bilan expose le détail par catégorie des créances et dettes, dont la
    somme reconstitue exactement les totaux."""
    bda = _make_entity(client, "BDA", "internal")
    sub = _make_category(client, "Subvention")
    fy = _make_fy(client, name="EX2025", start="2025-01-01", end="2025-12-31")

    r1 = client.post("/api/reports/accruals", json={
        "fiscal_year_id": fy["id"], "kind": "creance", "amount": 30000,
        "label": "Subvention à recevoir", "category_id": sub["id"],
    })
    assert r1.status_code == 201, r1.text
    r2 = client.post("/api/reports/accruals", json={
        "fiscal_year_id": fy["id"], "kind": "dette", "amount": 12000,
        "label": "Facture à payer", "category_id": sub["id"],
    })
    assert r2.status_code == 201, r2.text

    data = client.get("/api/reports/bilan", params={"fiscal_year_id": fy["id"]}).json()
    cre = data["actif"]["creances_detail"]
    det = data["passif"]["dettes_detail"]
    assert any(r["category_name"] == "Subvention" and r["montant"] == 30000 for r in cre)
    assert any(r["category_name"] == "Subvention" and r["montant"] == 12000 for r in det)
    # Cohérence : la somme du détail = le total affiché.
    assert sum(r["montant"] for r in cre) == data["actif"]["total_creances"]
    assert sum(r["montant"] for r in det) == data["passif"]["total_dettes"]


def test_bilan_pdf_avec_accruals(client):
    """Le PDF du bilan se génère avec le détail créances/dettes par catégorie."""
    bda = _make_entity(client, "BDA", "internal")
    sub = _make_category(client, "Subvention")
    fy = _make_fy(client, name="EX2025", start="2025-01-01", end="2025-12-31")
    client.post("/api/reports/accruals", json={
        "fiscal_year_id": fy["id"], "kind": "creance", "amount": 30000,
        "label": "Subvention à recevoir", "category_id": sub["id"],
    })
    r = client.get("/api/reports/bilan/pdf", params={"fiscal_year_id": fy["id"]})
    assert r.status_code == 200, r.text
    assert r.content[:4] == b"%PDF"
