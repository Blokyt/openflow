"""Champs bureau (président / trésorier) sur l'exercice — migration budget 1.6.0."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


def test_create_fiscal_year_with_bureau(client):
    r = client.post("/api/budget/fiscal-years", json={
        "name": "2030-2031",
        "start_date": "2030-09-01",
        "president_name": "Alice Présidente",
        "tresorier_name": "Bob Trésorier",
    })
    assert r.status_code == 201
    fy = r.json()
    assert fy["president_name"] == "Alice Présidente"
    assert fy["tresorier_name"] == "Bob Trésorier"


def test_bureau_defaults_to_empty(client):
    r = client.post("/api/budget/fiscal-years", json={
        "name": "2031-2032", "start_date": "2031-09-01",
    })
    assert r.status_code == 201
    fy = r.json()
    assert fy["president_name"] == ""
    assert fy["tresorier_name"] == ""


def test_update_bureau_fields(client):
    fy = client.post("/api/budget/fiscal-years", json={
        "name": "2032-2033", "start_date": "2032-09-01", "president_name": "Alice",
    }).json()
    r = client.put(f"/api/budget/fiscal-years/{fy['id']}", json={"tresorier_name": "Carole"})
    assert r.status_code == 200
    data = r.json()
    assert data["tresorier_name"] == "Carole"
    assert data["president_name"] == "Alice"  # untouched

    listed = client.get("/api/budget/fiscal-years").json()
    match = next(y for y in listed if y["id"] == fy["id"])
    assert match["president_name"] == "Alice"
    assert match["tresorier_name"] == "Carole"
