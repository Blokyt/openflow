"""Validation de la pagination des transactions.

limit/offset negatifs ne doivent pas etre acceptes silencieusement (SQLite
interprete LIMIT -1 comme "aucune limite", ce qui contourne le bornage et peut
renvoyer une reponse non bornee sur un gros volume). On veut un 422 propre.
"""


def test_negative_limit_is_rejected(client):
    r = client.get("/api/transactions/?limit=-1")
    assert r.status_code == 422, r.text


def test_negative_offset_is_rejected(client):
    r = client.get("/api/transactions/?offset=-5")
    assert r.status_code == 422, r.text


def test_zero_limit_is_valid(client):
    r = client.get("/api/transactions/?limit=0")
    assert r.status_code == 200, r.text
    assert r.json()["items"] == []
