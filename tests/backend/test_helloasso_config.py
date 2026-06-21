def test_config_initially_not_configured(client):
    r = client.get("/api/helloasso/config")
    assert r.status_code == 200
    body = r.json()
    assert body["configured"] is False
    assert body["organization_slug"] == ""
    assert "client_secret" not in body  # jamais exposé


def test_put_config_then_get_masks_secret(client):
    r = client.put("/api/helloasso/config", json={
        "client_id": "abc",
        "client_secret": "topsecret",
        "organization_slug": "bda-ens",
    })
    assert r.status_code == 200

    r = client.get("/api/helloasso/config")
    body = r.json()
    assert body["configured"] is True
    assert body["organization_slug"] == "bda-ens"
    assert body["has_secret"] is True
    assert "client_secret" not in body


def test_put_config_requires_fields(client):
    r = client.put("/api/helloasso/config", json={"client_id": ""})
    assert r.status_code == 422  # champs manquants (validation Pydantic)
