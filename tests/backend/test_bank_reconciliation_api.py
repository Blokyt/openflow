"""Tests for the bank_reconciliation module API."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_transaction(client, date="2026-03-10", label="Salaire", amount=2000.0):
    resp = client.post(
        "/api/transactions/",
        json={"date": date, "label": label, "amount": amount},
    )
    assert resp.status_code == 201
    return resp.json()


def import_entries(client, entries):
    return client.post("/api/bank_reconciliation/import", json={"entries": entries})


# ---------------------------------------------------------------------------
# Import tests
# ---------------------------------------------------------------------------

def test_import_returns_list(client):
    resp = import_entries(client, [
        {"date": "2026-01-05", "label": "Virement entrant", "amount": 500.0},
    ])
    assert resp.status_code == 201
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["label"] == "Virement entrant"
    assert data[0]["amount"] == 500.0
    assert data[0]["status"] in ("unmatched", "matched")


def test_import_multiple_entries(client):
    resp = import_entries(client, [
        {"date": "2026-01-10", "label": "Entry A", "amount": 100.0},
        {"date": "2026-01-11", "label": "Entry B", "amount": -50.0},
        {"date": "2026-01-12", "label": "Entry C", "amount": 200.0},
    ])
    assert resp.status_code == 201
    assert len(resp.json()) == 3


def test_import_sets_unmatched_status_when_no_transaction(client):
    resp = import_entries(client, [
        {"date": "2099-12-31", "label": "Future entry no match", "amount": 99999.99},
    ])
    assert resp.status_code == 201
    entry = resp.json()[0]
    assert entry["status"] == "unmatched"
    assert entry["matched_transaction_id"] is None


# ---------------------------------------------------------------------------
# Auto-matching tests
# ---------------------------------------------------------------------------

def test_auto_match_exact_same_day(client):
    """Import a bank entry that matches a transaction exactly (same date, same amount)."""
    tx = make_transaction(client, date="2026-04-01", amount=750.0, label="Paiement client")

    resp = import_entries(client, [
        {"date": "2026-04-01", "label": "Paiement client banque", "amount": 750.0},
    ])
    assert resp.status_code == 201
    entry = resp.json()[0]
    assert entry["status"] == "matched"
    assert entry["matched_transaction_id"] == tx["id"]


def test_auto_match_within_3_days(client):
    """Auto-match should succeed when dates differ by up to 3 days."""
    tx = make_transaction(client, date="2026-04-05", amount=300.0, label="Loyer")

    resp = import_entries(client, [
        {"date": "2026-04-07", "label": "Loyer banque", "amount": 300.0},
    ])
    assert resp.status_code == 201
    entry = resp.json()[0]
    assert entry["status"] == "matched"
    assert entry["matched_transaction_id"] == tx["id"]


def test_auto_match_no_match_when_amount_differs(client):
    """No auto-match when amount is different, even if date matches."""
    make_transaction(client, date="2026-04-10", amount=1000.0, label="Montant diff")

    resp = import_entries(client, [
        {"date": "2026-04-10", "label": "Montant diff banque", "amount": 999.0},
    ])
    assert resp.status_code == 201
    entry = resp.json()[0]
    assert entry["status"] == "unmatched"


def test_auto_match_no_match_when_multiple_candidates(client):
    """No auto-match when there are multiple candidates (ambiguous)."""
    make_transaction(client, date="2026-05-01", amount=500.0, label="Doublon A")
    make_transaction(client, date="2026-05-01", amount=500.0, label="Doublon B")

    resp = import_entries(client, [
        {"date": "2026-05-01", "label": "Ambiguous", "amount": 500.0},
    ])
    assert resp.status_code == 201
    entry = resp.json()[0]
    assert entry["status"] == "unmatched"


# ---------------------------------------------------------------------------
# List / filter tests
# ---------------------------------------------------------------------------

def test_list_statements(client):
    import_entries(client, [{"date": "2026-02-01", "label": "List test", "amount": 42.0}])
    resp = client.get("/api/bank_reconciliation/")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert len(resp.json()) >= 1


def test_list_filter_by_status_unmatched(client):
    import_entries(client, [{"date": "2099-01-01", "label": "Unmatched only", "amount": 77777.77}])
    resp = client.get("/api/bank_reconciliation/?status=unmatched")
    assert resp.status_code == 200
    for entry in resp.json():
        assert entry["status"] == "unmatched"


def test_list_filter_by_status_matched(client):
    tx = make_transaction(client, date="2026-06-15", amount=111.0, label="Match filter tx")
    import_entries(client, [{"date": "2026-06-15", "label": "Match filter bank", "amount": 111.0}])

    resp = client.get("/api/bank_reconciliation/?status=matched")
    assert resp.status_code == 200
    matched_ids = [e["matched_transaction_id"] for e in resp.json()]
    assert tx["id"] in matched_ids


# ---------------------------------------------------------------------------
# Suggestions tests
# ---------------------------------------------------------------------------

def test_suggestions_returns_candidates(client):
    tx = make_transaction(client, date="2026-07-10", amount=888.0, label="Suggestion tx")
    # Import an unmatched entry with same amount, within 5 days
    resp = import_entries(client, [
        {"date": "2026-07-13", "label": "Suggestion bank", "amount": 888.0},
    ])
    stmt = resp.json()[0]
    # Force it to be unmatched (may have auto-matched if tx was unique within ±3 days)
    if stmt["status"] == "matched":
        client.post(f"/api/bank_reconciliation/unmatch/{stmt['id']}")

    sug_resp = client.get(f"/api/bank_reconciliation/suggestions/{stmt['id']}")
    assert sug_resp.status_code == 200
    suggestions = sug_resp.json()
    assert isinstance(suggestions, list)
    tx_ids = [s["id"] for s in suggestions]
    assert tx["id"] in tx_ids


def test_suggestions_matched_entry_returns_empty(client):
    tx = make_transaction(client, date="2026-08-01", amount=123.0, label="Already matched tx")
    import_resp = import_entries(client, [
        {"date": "2026-08-01", "label": "Already matched bank", "amount": 123.0},
    ])
    stmt = import_resp.json()[0]
    assert stmt["status"] == "matched"

    sug_resp = client.get(f"/api/bank_reconciliation/suggestions/{stmt['id']}")
    assert sug_resp.status_code == 200
    assert sug_resp.json() == []


def test_suggestions_not_found(client):
    resp = client.get("/api/bank_reconciliation/suggestions/999999")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Manual match tests
# ---------------------------------------------------------------------------

def test_manual_match(client):
    tx = make_transaction(client, date="2026-09-01", amount=555.0, label="Manual tx")
    import_resp = import_entries(client, [
        {"date": "2099-09-01", "label": "Manual bank far date", "amount": 555.0},
    ])
    # This won't auto-match because the date is far from any transaction
    stmt = import_resp.json()[0]

    match_resp = client.post(
        "/api/bank_reconciliation/match",
        json={"statement_id": stmt["id"], "transaction_id": tx["id"]},
    )
    assert match_resp.status_code == 200
    data = match_resp.json()
    assert data["status"] == "matched"
    assert data["matched_transaction_id"] == tx["id"]


def test_manual_match_statement_not_found(client):
    tx = make_transaction(client, date="2026-09-02", amount=10.0, label="tx for 404 stmt")
    resp = client.post(
        "/api/bank_reconciliation/match",
        json={"statement_id": 999999, "transaction_id": tx["id"]},
    )
    assert resp.status_code == 404


def test_manual_match_transaction_not_found(client):
    import_resp = import_entries(client, [
        {"date": "2099-01-01", "label": "Stmt for 404 tx", "amount": 1.0},
    ])
    stmt_id = import_resp.json()[0]["id"]
    resp = client.post(
        "/api/bank_reconciliation/match",
        json={"statement_id": stmt_id, "transaction_id": 999999},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Unmatch tests
# ---------------------------------------------------------------------------

def test_unmatch(client):
    tx = make_transaction(client, date="2026-10-01", amount=250.0, label="Unmatch tx")
    import_resp = import_entries(client, [
        {"date": "2026-10-01", "label": "Unmatch bank", "amount": 250.0},
    ])
    stmt = import_resp.json()[0]
    assert stmt["status"] == "matched"

    unmatch_resp = client.post(f"/api/bank_reconciliation/unmatch/{stmt['id']}")
    assert unmatch_resp.status_code == 200
    data = unmatch_resp.json()
    assert data["status"] == "unmatched"
    assert data["matched_transaction_id"] is None


def test_unmatch_not_found(client):
    resp = client.post("/api/bank_reconciliation/unmatch/999999")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Delete tests
# ---------------------------------------------------------------------------

def test_delete_statement(client):
    import_resp = import_entries(client, [
        {"date": "2099-11-01", "label": "To delete", "amount": 1.23},
    ])
    stmt_id = import_resp.json()[0]["id"]

    del_resp = client.delete(f"/api/bank_reconciliation/{stmt_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["deleted"] == stmt_id

    # Verify gone from list
    list_resp = client.get("/api/bank_reconciliation/")
    ids = [e["id"] for e in list_resp.json()]
    assert stmt_id not in ids


def test_delete_not_found(client):
    resp = client.delete("/api/bank_reconciliation/999999")
    assert resp.status_code == 404
