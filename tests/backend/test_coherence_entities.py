"""Coherence tests: comportement des modules scopés par entité.

Convention (refonte C1+C2) :
  - `amount` : entier de centimes, TOUJOURS POSITIF.
  - Sens via from_entity_id -> to_entity_id :
      recette   = from EXTERNE -> to INTERNE
      dépense   = from INTERNE -> to EXTERNE
      virement  = INTERNE -> INTERNE
"""
import pytest


def _setup_entities(client):
    """Crée BDA (racine) + Gastro (enfant) + Fournisseur (externe) + transactions.

    Transactions (montants en centimes) :
      - Recette BDA     : ext -> BDA       200000 centimes  (+200000 pour BDA)
      - Dépense Gastro  : Gastro -> ext     30000 centimes  (-30000  pour Gastro)
      - Virement BDA->Gastro : BDA -> Gastro 50000 centimes
            => -50000 pour BDA,  +50000 pour Gastro

    Soldes propres (ref BDA=500000, ref Gastro=100000) :
      BDA   = 500000 + 200000 (recette) - 50000 (virement sortant) = 650000
      Gastro= 100000 + 50000  (virement entrant) - 30000 (dépense) = 120000

    Consolidé BDA (own mode, pas aggregate) = 650000 + 120000 = 770000
    """
    bda    = client.post("/api/entities/", json={"name": "BDA",         "type": "internal"}).json()
    gastro = client.post("/api/entities/", json={
        "name": "Gastro", "type": "internal", "parent_id": bda["id"]
    }).json()
    ext    = client.post("/api/entities/", json={"name": "Fournisseur", "type": "external"}).json()

    # Références de solde (en centimes)
    client.put(f"/api/entities/{bda['id']}/balance-ref", json={
        "reference_date": "2025-01-01", "reference_amount": 500000
    })
    client.put(f"/api/entities/{gastro['id']}/balance-ref", json={
        "reference_date": "2025-01-01", "reference_amount": 100000
    })

    # Recette BDA : ext -> BDA, 200000 centimes
    client.post("/api/transactions/", json={
        "date": "2025-06-01", "label": "Don",
        "amount": 200000,
        "from_entity_id": ext["id"], "to_entity_id": bda["id"],
    })
    # Dépense Gastro : Gastro -> ext, 30000 centimes
    client.post("/api/transactions/", json={
        "date": "2025-06-15", "label": "Achat",
        "amount": 30000,
        "from_entity_id": gastro["id"], "to_entity_id": ext["id"],
    })
    # Virement interne BDA -> Gastro, 50000 centimes
    client.post("/api/transactions/", json={
        "date": "2025-06-10", "label": "Allocation",
        "amount": 50000,
        "from_entity_id": bda["id"], "to_entity_id": gastro["id"],
    })

    return bda, gastro, ext


def test_dashboard_entity_balance_matches_entity_endpoint(client):
    """Le solde du dashboard filtré par entité doit correspondre à l'endpoint entité."""
    bda, gastro, ext = _setup_entities(client)

    entity_bal = client.get(f"/api/entities/{bda['id']}/balance").json()
    dash       = client.get(f"/api/dashboard/summary?entity_id={bda['id']}").json()
    assert dash["balance"] == pytest.approx(entity_bal["balance"])


def test_dashboard_without_entity_is_legacy(client):
    """Le dashboard sans entity_id retourne le solde global (legacy)."""
    _setup_entities(client)
    dash       = client.get("/api/dashboard/summary").json()
    legacy_bal = client.get("/api/transactions/balance").json()
    assert dash["balance"] == pytest.approx(legacy_bal["balance"])



def test_internal_transfer_consolidated_unchanged(client):
    """Un virement interne BDA->Gastro ne doit pas modifier le consolidé de BDA.

    Soldes propres :
      BDA   = 500000 + 200000 - 50000 = 650000
      Gastro= 100000 + 50000  - 30000 = 120000

    Le virement (interne->interne) déplace de l'argent de BDA vers Gastro ;
    le consolidé BDA = propre_BDA + propre_Gastro = 650000 + 120000 = 770000.
    Sans le virement, consolidé = (500000+200000) + (100000-30000) = 770000.
    Le virement est bien sans effet sur le consolidé.
    """
    bda, gastro, ext = _setup_entities(client)

    consolidated = client.get(f"/api/entities/{bda['id']}/consolidated").json()
    # BDA propre  : 500000 + 200000 - 50000 = 650000
    # Gastro propre : 100000 + 50000 - 30000 = 120000
    # Consolidé : 650000 + 120000 = 770000
    assert consolidated["consolidated_balance"] == pytest.approx(770000)
