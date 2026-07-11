"""Cohérence comptable croisée : exercices et régularisations globales.

1. Deux exercices ne doivent pas se chevaucher, sinon une transaction datée sur
   la frontière est comptée dans les deux (double comptage du réalisé).
2. Une régularisation « globale » (sans entité) ne doit apparaître QUE dans le
   bilan de l'association, jamais additionnée dans le bilan de chaque club (la
   somme des bilans de clubs dépasserait alors le bilan global).
"""


def _entity(client, name, type_="internal"):
    r = client.post("/api/entities/", json={"name": name, "type": type_})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_overlapping_fiscal_years_are_rejected(client):
    r = client.post("/api/budget/fiscal-years", json={"name": "Mandat 2023-2024", "start_date": "2023-09-01"})
    assert r.status_code == 201, r.text
    fy_a = r.json()["id"]
    r = client.post(f"/api/budget/fiscal-years/{fy_a}/close", json={"end_date": "2024-08-31"})
    assert r.status_code == 200, r.text

    # Début le jour même de la fin de l'exercice précédent : chevauchement d'un jour.
    r = client.post("/api/budget/fiscal-years", json={"name": "Mandat 2024-2025", "start_date": "2024-08-31"})
    assert r.status_code == 400, f"le chevauchement doit être refusé, obtenu {r.status_code} {r.text}"

    # Début le lendemain : accepté.
    r = client.post("/api/budget/fiscal-years", json={"name": "Mandat 2024-2025", "start_date": "2024-09-01"})
    assert r.status_code == 201, r.text


def test_global_accrual_not_counted_per_club(client):
    club_a = _entity(client, "Club A")
    club_b = _entity(client, "Club B")
    r = client.post("/api/budget/fiscal-years", json={"name": "Exercice 2025", "start_date": "2025-01-01"})
    assert r.status_code == 201, r.text
    fy_id = r.json()["id"]

    # Régularisation globale (sans entité) : subvention non affectée à un club.
    r = client.post("/api/reports/accruals", json={
        "fiscal_year_id": fy_id, "kind": "creance", "amount": 30000,
        "label": "Subvention non affectée",
    })
    assert r.status_code == 201, r.text

    # Bilan global (association) : la régularisation globale y figure.
    glob = client.get(f"/api/reports/bilan?fiscal_year_id={fy_id}")
    assert glob.status_code == 200, glob.text
    assert glob.json()["actif"]["total_creances"] == 30000
    assert glob.json()["equilibre"] is True

    # Bilan par club : la régularisation globale ne doit PAS y être comptée.
    for eid in (club_a, club_b):
        b = client.get(f"/api/reports/bilan?fiscal_year_id={fy_id}&entity_id={eid}")
        assert b.status_code == 200, b.text
        assert b.json()["actif"]["total_creances"] == 0, \
            f"la régularisation globale ne doit pas apparaître dans le bilan du club {eid}"
        assert b.json()["equilibre"] is True
