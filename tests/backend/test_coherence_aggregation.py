"""Coherence tests: aggregation calculations across modules."""
import pytest


# ============================================================
# BUDGET — legacy tests removed; budget module rewritten in 1.2.0
# (see tests/backend/test_budget.py and test_coherence_budget.py)
# ============================================================


# ============================================================
# REIMBURSEMENTS
# ============================================================

def test_reimbursements_summary_groups_by_person(client):
    """Summary groups pending reimbursements by person with correct totals."""
    client.post("/api/reimbursements/", json={"person_name": "Alice", "amount": 150, "description": "Taxi", "status": "pending"})
    client.post("/api/reimbursements/", json={"person_name": "Alice", "amount": 50, "description": "Repas", "status": "pending"})
    client.post("/api/reimbursements/", json={"person_name": "Bob", "amount": 200, "description": "Train", "status": "pending"})
    # Reimbursed — should NOT appear in summary
    client.post("/api/reimbursements/", json={"person_name": "Alice", "amount": 100, "description": "Ancien", "status": "reimbursed"})

    summary = client.get("/api/reimbursements/summary").json()
    alice = next((s for s in summary if s["person_name"] == "Alice"), None)
    bob = next((s for s in summary if s["person_name"] == "Bob"), None)
    assert alice is not None
    assert alice["total_pending"] == pytest.approx(200.0)
    assert alice["count"] == 2
    assert bob is not None
    assert bob["total_pending"] == pytest.approx(200.0)
    assert bob["count"] == 1


def test_reimbursements_summary_empty(client):
    """No pending reimbursements: empty summary."""
    summary = client.get("/api/reimbursements/summary").json()
    assert summary == []


