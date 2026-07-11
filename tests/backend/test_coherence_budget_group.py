"""Cohérence croisée : réalisé de groupe budget vs dashboard.

Un groupe interne qui dote un club interne (virement parent -> enfant) ne doit
pas voir ses dépenses/recettes brutes gonflées par ce virement, compté une fois
en sortie du parent et une fois en entrée de l'enfant. Le réalisé « frontière »
du groupe doit égaler les seuls flux qui franchissent la frontière du sous-arbre,
exactement comme le dashboard (méthode frontière) et les rapports.
"""


def _entity(client, name, type_, parent_id=None):
    payload = {"name": name, "type": type_}
    if parent_id is not None:
        payload["parent_id"] = parent_id
    r = client.post("/api/entities/", json=payload)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _tx(client, from_id, to_id, amount, date="2025-03-01", label="op"):
    r = client.post("/api/transactions/", json={
        "date": date, "label": label, "amount": amount,
        "from_entity_id": from_id, "to_entity_id": to_id,
    })
    assert r.status_code == 201, r.text
    return r.json()


def _find_node(groups, eid):
    for g in groups:
        if g["entity_id"] == eid:
            return g
        found = _find_node(g["children"], eid)
        if found:
            return found
    return None


def test_group_realized_excludes_internal_transfers(client):
    bda = _entity(client, "BDA", "internal")
    cine = _entity(client, "Cine", "internal", parent_id=bda)
    fournisseur = _entity(client, "Fournisseur", "external")
    r = client.post("/api/budget/fiscal-years", json={"name": "Exercice 2025", "start_date": "2025-01-01"})
    assert r.status_code == 201, r.text
    fy_id = r.json()["id"]

    # Dotation interne BDA -> Cine (50000) et depense externe Cine -> Fournisseur (20000).
    _tx(client, bda, cine, 50000)
    _tx(client, cine, fournisseur, 20000)

    view = client.get(f"/api/budget/view?fiscal_year_id={fy_id}")
    assert view.status_code == 200, view.text
    node = _find_node(view.json()["groups"], bda)
    assert node is not None

    # Frontiere du sous-arbre {BDA, Cine} : seule la depense externe sort (20000),
    # aucune recette n'entre. Le virement interne 50000 est neutralise des deux cotes.
    assert node["realized_expense"] == 20000, node
    assert node["realized_income"] == 0, node
    assert node["realized_net"] == -20000

    # Le club feuille garde bien son propre realise (la dotation recue EST une
    # recette propre du club, la depense externe EST sa depense).
    leaf = _find_node(view.json()["groups"], cine)
    assert leaf["realized_income"] == 50000
    assert leaf["realized_expense"] == 20000

    # Coherence croisee avec le dashboard (meme perimetre, methode frontiere).
    summ = client.get(f"/api/dashboard/summary?entity_id={bda}&include_children=true")
    assert summ.status_code == 200, summ.text
    s = summ.json()
    assert s["total_expenses"] == node["realized_expense"]
    assert s["total_income"] == node["realized_income"]
