"""Coherence tests: entity-scoped module behavior."""
import pytest


def _setup_entities(client):
    """Create BDA (root) + Gastro (child) + External entity + transactions."""
    bda = client.post("/api/entities/", json={"name": "BDA", "type": "internal"}).json()
    gastro = client.post("/api/entities/", json={
        "name": "Gastro", "type": "internal", "parent_id": bda["id"]
    }).json()
    ext = client.post("/api/entities/", json={"name": "Fournisseur", "type": "external"}).json()

    # Set balance refs
    client.put(f"/api/entities/{bda['id']}/balance-ref", json={
        "reference_date": "2025-01-01", "reference_amount": 5000
    })
    client.put(f"/api/entities/{gastro['id']}/balance-ref", json={
        "reference_date": "2025-01-01", "reference_amount": 1000
    })

    # BDA receives 2000 from external
    client.post("/api/transactions/", json={
        "date": "2025-06-01", "label": "Don", "amount": 2000,
        "from_entity_id": ext["id"], "to_entity_id": bda["id"],
    })
    # Gastro spends 300 to external
    client.post("/api/transactions/", json={
        "date": "2025-06-15", "label": "Achat", "amount": -300,
        "from_entity_id": gastro["id"], "to_entity_id": ext["id"],
    })
    # BDA transfers 500 to Gastro
    client.post("/api/transactions/", json={
        "date": "2025-06-10", "label": "Allocation", "amount": -500,
        "from_entity_id": bda["id"], "to_entity_id": gastro["id"],
    })

    return bda, gastro, ext


def test_dashboard_entity_balance_matches_entity_endpoint(client):
    """Dashboard summary with entity_id should match entity balance endpoint."""
    bda, gastro, ext = _setup_entities(client)

    entity_bal = client.get(f"/api/entities/{bda['id']}/balance").json()
    dash = client.get(f"/api/dashboard/summary?entity_id={bda['id']}").json()
    assert dash["balance"] == pytest.approx(entity_bal["balance"])


def test_dashboard_without_entity_is_legacy(client):
    """Dashboard without entity_id returns legacy global balance."""
    _setup_entities(client)
    dash = client.get("/api/dashboard/summary").json()
    legacy_bal = client.get("/api/transactions/balance").json()
    assert dash["balance"] == pytest.approx(legacy_bal["balance"])


def test_forecasting_entity_balance(client):
    """Forecasting with entity_id should use entity balance."""
    bda, gastro, ext = _setup_entities(client)

    entity_bal = client.get(f"/api/entities/{bda['id']}/balance").json()
    fc = client.get(f"/api/forecasting/projection?entity_id={bda['id']}").json()
    assert fc["current_balance"] == pytest.approx(entity_bal["balance"])


def test_export_entity_filter(client):
    """Export with entity_id only includes entity's transactions."""
    bda, gastro, ext = _setup_entities(client)

    # Export only Gastro transactions
    resp = client.get(f"/api/export/transactions/json?entity_id={gastro['id']}")
    txs = resp.json()
    # Gastro has 2 transactions: the spend (-300) and the allocation from BDA (+500 incoming)
    for tx in txs:
        assert tx["from_entity_id"] == gastro["id"] or tx["to_entity_id"] == gastro["id"]


def test_internal_transfer_consolidated_unchanged(client):
    """Internal transfer BDA->Gastro shouldn't change BDA consolidated balance."""
    bda, gastro, ext = _setup_entities(client)

    consolidated = client.get(f"/api/entities/{bda['id']}/consolidated").json()
    # BDA own: 5000 + incoming(to_bda=2000) - outgoing(from_bda,amount<0=500) = 6500
    # Gastro own: 1000 + incoming(to_gastro=amount=-500) - outgoing(from_gastro,amount<0=300) = 200
    #   (The allocation is a negative amount TO gastro, so it reduces Gastro's incoming sum)
    # Consolidated: 6500 + 200 = 6700
    assert consolidated["consolidated_balance"] == pytest.approx(6700.0)
