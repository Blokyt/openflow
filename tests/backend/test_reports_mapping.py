"""Tests des suggestions de classification comptable (mapping catégorie -> compte PCG)."""


def _account_id(client, code):
    accs = client.get("/api/reports/accounts").json()["accounts"]
    return next(a["id"] for a in accs if a["code"] == code)


def _make_cat(client, name):
    return client.post("/api/categories/", json={"name": name}).json()["id"]


def test_suggestion_cotisations_to_756(client):
    cid = _make_cat(client, "Cotisations")
    s = client.get("/api/reports/mapping/suggestions").json()["suggestions"]
    match = next((x for x in s if x["category_id"] == cid), None)
    assert match is not None
    assert match["suggested_account_code"] == "756"


def test_suggestion_loyer_to_61(client):
    cid = _make_cat(client, "Loyer salle")
    s = client.get("/api/reports/mapping/suggestions").json()["suggestions"]
    match = next((x for x in s if x["category_id"] == cid), None)
    assert match is not None
    assert match["suggested_account_code"] == "61"


def test_unmatched_category_has_no_suggestion(client):
    cid = _make_cat(client, "Zorglub")
    s = client.get("/api/reports/mapping/suggestions").json()["suggestions"]
    assert all(x["category_id"] != cid for x in s)


def test_mapped_category_excluded_from_suggestions(client):
    cid = _make_cat(client, "Cotisations")
    acc = _account_id(client, "756")
    client.put("/api/reports/mapping", json={"category_id": cid, "account_id": acc})
    s = client.get("/api/reports/mapping/suggestions").json()["suggestions"]
    assert all(x["category_id"] != cid for x in s)


def test_apply_suggestions_maps_categories(client):
    cid = _make_cat(client, "Cotisations")
    acc = _account_id(client, "756")
    r = client.post("/api/reports/mapping/apply-suggestions",
                    json={"entries": [{"category_id": cid, "account_id": acc}]})
    assert r.status_code == 200
    assert r.json()["applied"] == 1
    mapping = client.get("/api/reports/mapping").json()["mapping"]
    assert any(m["category_id"] == cid and m["account_code"] == "756" for m in mapping)


def test_apply_rejects_balance_account(client):
    cid = _make_cat(client, "Trésorerie")
    acc = _account_id(client, "512")  # disponibilités : compte d'actif, non mappable
    r = client.post("/api/reports/mapping/apply-suggestions",
                    json={"entries": [{"category_id": cid, "account_id": acc}]})
    assert r.status_code == 200
    assert r.json()["applied"] == 0
