def test_links_empty_then_upsert(client):
    assert client.get("/api/helloasso/links").json() == []

    payload = {"form_type": "Membership", "form_slug": "cotis",
               "category_id": 20, "from_entity_id": 7, "to_entity_id": 1}
    r = client.put("/api/helloasso/links", json=payload)
    assert r.status_code == 200

    links = client.get("/api/helloasso/links").json()
    assert len(links) == 1
    assert links[0]["form_slug"] == "cotis"
    assert links[0]["to_entity_id"] == 1


def test_link_upsert_is_unique_per_campaign(client):
    base = {"form_type": "Membership", "form_slug": "cotis",
            "category_id": 20, "from_entity_id": 7, "to_entity_id": 1}
    client.put("/api/helloasso/links", json=base)
    client.put("/api/helloasso/links", json={**base, "category_id": 21})

    links = client.get("/api/helloasso/links").json()
    assert len(links) == 1            # pas de doublon
    assert links[0]["category_id"] == 21  # mis à jour
