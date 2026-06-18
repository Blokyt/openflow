"""Coherence tests: cohérence des soldes entre les modules.

Convention (refonte C1+C2) :
  - `amount` est un entier de centimes, TOUJOURS POSITIF.
  - Le sens vient de from_entity_id -> to_entity_id :
      recette  = from EXTERNE -> to INTERNE
      dépense  = from INTERNE -> to EXTERNE
  - Solde = reference + SUM(entrées) - SUM(sorties).

La fixture `client` injecte automatiquement from=_TestDefaultFrom (INTERNE)
/ to=_TestDefaultTo (EXTERNE) quand from/to sont absents (= dépense par défaut).
Pour créer des recettes, il faut expliciter les deux champs.
"""
import pytest


def _setup_entities_for_income_expense(client):
    """Crée une paire interne/externe et retourne (internal_id, external_id)."""
    internal = client.post(
        "/api/entities/", json={"name": "_CoherenceInternal", "type": "internal"}
    ).json()
    external = client.post(
        "/api/entities/", json={"name": "_CoherenceExternal", "type": "external"}
    ).json()
    return internal["id"], external["id"]


def _create_transactions(client):
    """Crée un ensemble connu de transactions.

    Tous les montants sont en centimes, toujours positifs. Le sens est
    encodé via from/to :
      recettes  : 100000 + 50000 + 200000 = 350000 centimes
      dépenses  : 30000 + 70000           = 100000 centimes
      net       : 350000 - 100000         = 250000 centimes

    On utilise une paire interne/externe dédiée pour isoler ces transactions
    des entités injectées par le fixture client (qui sont aussi de type
    interne/externe, mais pour d'autres tests).
    """
    int_id, ext_id = _setup_entities_for_income_expense(client)

    txs_raw = [
        # recettes (from externe, to interne)
        {"date": "2025-03-15", "label": "Vente A",     "amount": 100000, "is_income": True},
        {"date": "2025-04-10", "label": "Vente B",     "amount": 50000,  "is_income": True},
        {"date": "2025-07-15", "label": "Prestation",  "amount": 200000, "is_income": True},
        # dépenses (from interne, to externe)
        {"date": "2025-05-20", "label": "Achat fournisseur", "amount": 30000, "is_income": False},
        {"date": "2025-06-01", "label": "Loyer",             "amount": 70000, "is_income": False},
    ]
    for tx in txs_raw:
        is_income = tx.pop("is_income")
        from_id = ext_id if is_income else int_id
        to_id   = int_id if is_income else ext_id
        payload = dict(tx, from_entity_id=from_id, to_entity_id=to_id)
        resp = client.post("/api/transactions/", json=payload)
        assert resp.status_code == 201, f"Échec création tx: {resp.text}"
    return int_id, ext_id


# --- Calcul du solde ---

def test_balance_with_no_transactions(client):
    """DB vide : balance = reference_amount (0)."""
    resp = client.get("/api/transactions/balance")
    assert resp.status_code == 200
    data = resp.json()
    assert data["balance"] == 0
    assert data["transactions_sum"] == 0


def test_balance_matches_manual_sum(client):
    """Balance = reference_amount + (recettes - dépenses)."""
    _create_transactions(client)
    # net global sur toutes les entités internes = 350000 - 100000 = 250000 centimes
    expected_net = 250000
    resp = client.get("/api/transactions/balance")
    data = resp.json()
    assert data["transactions_sum"] == pytest.approx(expected_net)
    assert data["balance"] == pytest.approx(data["reference_amount"] + expected_net)


def test_balance_income_minus_expenses(client):
    """Vérifier que recettes - dépenses = net (transactions_sum)."""
    _create_transactions(client)
    resp = client.get("/api/transactions/balance")
    data = resp.json()
    # recettes = 350000, dépenses = 100000, net = 250000
    assert data["transactions_sum"] == pytest.approx(250000)


# --- Cross-module : transactions/balance == dashboard/summary.balance ---

def test_dashboard_balance_equals_transactions_balance(client):
    """Le solde du dashboard doit correspondre à celui de l'endpoint transactions."""
    _create_transactions(client)
    bal  = client.get("/api/transactions/balance").json()
    dash = client.get("/api/dashboard/summary").json()
    assert dash["balance"] == pytest.approx(bal["balance"])


def test_dashboard_income_expenses_coherent(client):
    """Les totaux income/expenses du dashboard doivent correspondre aux transactions."""
    _create_transactions(client)
    dash = client.get("/api/dashboard/summary").json()
    # Recettes (from externe -> to interne) : 100000 + 50000 + 200000 = 350000
    assert dash["total_income"] == pytest.approx(350000)
    # Dépenses (from interne -> to externe) : 30000 + 70000 = 100000
    assert dash["total_expenses"] == pytest.approx(100000)


def test_dashboard_transaction_count(client):
    """Le dashboard doit reporter le nombre correct de transactions."""
    _create_transactions(client)
    dash = client.get("/api/dashboard/summary").json()
    assert dash["transaction_count"] == 5


# --- Solde avec uniquement des recettes ou uniquement des dépenses ---

def test_balance_income_only(client):
    """Solde avec uniquement des recettes (entrées)."""
    int_id, ext_id = _setup_entities_for_income_expense(client)
    client.post("/api/transactions/", json={
        "date": "2025-06-01", "label": "Don",
        "amount": 10000,
        "from_entity_id": ext_id, "to_entity_id": int_id,
    })
    client.post("/api/transactions/", json={
        "date": "2025-06-02", "label": "Don2",
        "amount": 25000,
        "from_entity_id": ext_id, "to_entity_id": int_id,
    })
    bal = client.get("/api/transactions/balance").json()
    assert bal["balance"] == pytest.approx(35000)
    assert bal["transactions_sum"] == pytest.approx(35000)


def test_balance_expenses_only(client):
    """Solde avec uniquement des dépenses (sorties). Doit être négatif si ref=0."""
    int_id, ext_id = _setup_entities_for_income_expense(client)
    client.post("/api/transactions/", json={
        "date": "2025-06-01", "label": "Achat",
        "amount": 15000,
        "from_entity_id": int_id, "to_entity_id": ext_id,
    })
    client.post("/api/transactions/", json={
        "date": "2025-06-02", "label": "Achat2",
        "amount": 5000,
        "from_entity_id": int_id, "to_entity_id": ext_id,
    })
    bal = client.get("/api/transactions/balance").json()
    # reference=0, net = 0 - 20000 = -20000
    assert bal["balance"] == pytest.approx(-20000)


def test_balance_zero_amount_transaction_rejected(client):
    """Une transaction de montant nul doit être rejetée (400)."""
    int_id, ext_id = _setup_entities_for_income_expense(client)
    resp = client.post("/api/transactions/", json={
        "date": "2025-06-01", "label": "Nul",
        "amount": 0,
        "from_entity_id": int_id, "to_entity_id": ext_id,
    })
    assert resp.status_code == 400
