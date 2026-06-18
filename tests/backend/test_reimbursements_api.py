import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import pytest

def test_list_reimbursements_empty(client):
    response = client.get("/api/reimbursements/")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_create_reimbursement(client):
    # Les montants sont des entiers de centimes (42,50 € = 4250 centimes)
    payload = {"person_name": "Alice Dupont", "amount": 4250}
    response = client.post("/api/reimbursements/", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["person_name"] == "Alice Dupont"
    assert data["amount"] == 4250
    assert data["status"] == "pending"
    assert "id" in data

def test_create_reimbursement_with_notes(client):
    payload = {"person_name": "Bob Martin", "amount": 15.0, "notes": "repas équipe"}
    response = client.post("/api/reimbursements/", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["notes"] == "repas équipe"

def test_get_reimbursement(client):
    created = client.post("/api/reimbursements/", json={"person_name": "Claire", "amount": 20.0}).json()
    response = client.get(f"/api/reimbursements/{created['id']}")
    assert response.status_code == 200
    assert response.json()["person_name"] == "Claire"

def test_get_reimbursement_not_found(client):
    response = client.get("/api/reimbursements/999999")
    assert response.status_code == 404

def test_filter_by_status(client):
    # "validated" n'existe plus dans le workflow — on utilise "approved"
    client.post("/api/reimbursements/", json={"person_name": "Pending Person", "amount": 1000, "status": "pending"})
    r_approved = client.post("/api/reimbursements/", json={"person_name": "Approved Person", "amount": 2000, "status": "pending"})
    client.put(f"/api/reimbursements/{r_approved.json()['id']}", json={"status": "approved"})
    response = client.get("/api/reimbursements/?status=pending")
    assert response.status_code == 200
    results = response.json()
    assert all(r["status"] == "pending" for r in results)
    assert any(r["person_name"] == "Pending Person" for r in results)

def test_filter_by_status_reimbursed(client):
    client.post("/api/reimbursements/", json={"person_name": "Done Person", "amount": 30.0, "status": "reimbursed"})
    response = client.get("/api/reimbursements/?status=reimbursed")
    assert response.status_code == 200
    results = response.json()
    assert all(r["status"] == "reimbursed" for r in results)

def test_update_status(client):
    # Transition valide : pending -> approved
    created = client.post("/api/reimbursements/", json={"person_name": "Status Test", "amount": 5000}).json()
    assert created["status"] == "pending"
    response = client.put(f"/api/reimbursements/{created['id']}", json={"status": "approved"})
    assert response.status_code == 200
    assert response.json()["status"] == "approved"

def test_update_reimbursed_date_field(client):
    """Vérifier que reimbursed_date est bien persisté indépendamment du statut."""
    created = client.post("/api/reimbursements/", json={"person_name": "DateTest", "amount": 2500}).json()
    # Mettre à jour uniquement reimbursed_date sans changer le statut
    response = client.put(
        f"/api/reimbursements/{created['id']}", json={"reimbursed_date": "2026-04-11"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["reimbursed_date"] == "2026-04-11"
    # Le statut reste pending (pas de transition)
    assert data["status"] == "pending"

def test_delete_reimbursement(client):
    created = client.post("/api/reimbursements/", json={"person_name": "To Delete", "amount": 5.0}).json()
    response = client.delete(f"/api/reimbursements/{created['id']}")
    assert response.status_code == 200
    assert response.json()["deleted"] == created["id"]
    assert client.get(f"/api/reimbursements/{created['id']}").status_code == 404

def test_summary_endpoint(client):
    # Create multiple pending reimbursements for same person
    client.post("/api/reimbursements/", json={"person_name": "Summary Person", "amount": 100.0, "status": "pending"})
    client.post("/api/reimbursements/", json={"person_name": "Summary Person", "amount": 50.0, "status": "pending"})
    # Create a reimbursed one that should NOT appear in summary
    client.post("/api/reimbursements/", json={"person_name": "Summary Person", "amount": 999.0, "status": "reimbursed"})

    response = client.get("/api/reimbursements/summary")
    assert response.status_code == 200
    results = response.json()
    assert isinstance(results, list)
    summary_person = next((r for r in results if r["person_name"] == "Summary Person"), None)
    assert summary_person is not None
    assert summary_person["total_pending"] == 150.0
    assert summary_person["count"] == 2

def test_summary_not_matched_by_id_route(client):
    # Ensure /summary is not treated as /{id}
    response = client.get("/api/reimbursements/summary")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
