"""Coherence tests: balance consistency across modules."""
import pytest


def _create_transactions(client):
    """Create a known set of transactions for testing."""
    txs = [
        {"date": "2025-03-15", "label": "Vente A", "amount": 1000.0},
        {"date": "2025-04-10", "label": "Vente B", "amount": 500.0},
        {"date": "2025-05-20", "label": "Achat fournisseur", "amount": -300.0},
        {"date": "2025-06-01", "label": "Loyer", "amount": -700.0},
        {"date": "2025-07-15", "label": "Prestation", "amount": 2000.0},
    ]
    for tx in txs:
        resp = client.post("/api/transactions/", json=tx)
        assert resp.status_code == 201, f"Failed to create tx: {resp.text}"
    return txs


# --- Balance calculations ---

def test_balance_with_no_transactions(client):
    """Empty DB: balance = reference_amount (0.0)."""
    resp = client.get("/api/transactions/balance")
    assert resp.status_code == 200
    data = resp.json()
    assert data["balance"] == 0.0
    assert data["transactions_sum"] == 0.0


def test_balance_matches_manual_sum(client):
    """Balance must equal reference_amount + sum of all transaction amounts."""
    txs = _create_transactions(client)
    expected_sum = sum(t["amount"] for t in txs)  # 1000+500-300-700+2000 = 2500
    resp = client.get("/api/transactions/balance")
    data = resp.json()
    assert data["transactions_sum"] == pytest.approx(expected_sum)
    assert data["balance"] == pytest.approx(data["reference_amount"] + expected_sum)


def test_balance_income_minus_expenses(client):
    """Verify income - expenses = net (transactions_sum)."""
    _create_transactions(client)
    resp = client.get("/api/transactions/balance")
    data = resp.json()
    # Manual: income=3500, expenses=1000, net=2500
    assert data["transactions_sum"] == pytest.approx(2500.0)


# --- Cross-module: transactions/balance == dashboard/summary.balance ---

def test_dashboard_balance_equals_transactions_balance(client):
    """Dashboard summary balance must match transactions balance endpoint."""
    _create_transactions(client)
    bal = client.get("/api/transactions/balance").json()
    dash = client.get("/api/dashboard/summary").json()
    assert dash["balance"] == pytest.approx(bal["balance"])


def test_dashboard_income_expenses_coherent(client):
    """Dashboard total_income and total_expenses must match actual transactions."""
    _create_transactions(client)
    dash = client.get("/api/dashboard/summary").json()
    # Income: 1000 + 500 + 2000 = 3500
    assert dash["total_income"] == pytest.approx(3500.0)
    # Expenses: abs(-300 + -700) = 1000
    assert dash["total_expenses"] == pytest.approx(1000.0)


def test_dashboard_transaction_count(client):
    """Dashboard must report correct transaction count."""
    txs = _create_transactions(client)
    dash = client.get("/api/dashboard/summary").json()
    assert dash["transaction_count"] == len(txs)


# --- Balance with only income or only expenses ---

def test_balance_income_only(client):
    """Balance with only positive transactions."""
    client.post("/api/transactions/", json={"date": "2025-06-01", "label": "Don", "amount": 100.0})
    client.post("/api/transactions/", json={"date": "2025-06-02", "label": "Don2", "amount": 250.0})
    bal = client.get("/api/transactions/balance").json()
    assert bal["balance"] == pytest.approx(350.0)
    assert bal["transactions_sum"] == pytest.approx(350.0)


def test_balance_expenses_only(client):
    """Balance with only negative transactions — should be negative."""
    client.post("/api/transactions/", json={"date": "2025-06-01", "label": "Achat", "amount": -150.0})
    client.post("/api/transactions/", json={"date": "2025-06-02", "label": "Achat2", "amount": -50.0})
    bal = client.get("/api/transactions/balance").json()
    assert bal["balance"] == pytest.approx(-200.0)


def test_balance_zero_amount_transaction(client):
    """Zero-amount transaction should not affect balance."""
    client.post("/api/transactions/", json={"date": "2025-06-01", "label": "Nul", "amount": 0.0})
    bal = client.get("/api/transactions/balance").json()
    assert bal["balance"] == pytest.approx(0.0)
    assert bal["transactions_sum"] == pytest.approx(0.0)
