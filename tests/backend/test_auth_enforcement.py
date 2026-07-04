"""Deny-by-default : toute route /api exige une session ; mutations réservées à l'admin."""
from backend.core.auth import PUBLIC_API_PATHS


def test_all_api_routes_require_session(client_and_db):
    """Chaque route /api renvoie 401 sans cookie, sauf l'allowlist publique."""
    client, _ = client_and_db
    app = client.app
    import starlette.routing

    checked = 0
    for route in app.routes:
        if not isinstance(route, starlette.routing.Route):
            continue
        path = route.path
        if not path.startswith("/api") or path in PUBLIC_API_PATHS:
            continue
        # Substitue une valeur bidon aux paramètres de chemin.
        concrete = path.replace("{path:path}", "x")
        while "{" in concrete:
            start, end = concrete.index("{"), concrete.index("}")
            concrete = concrete[:start] + "1" + concrete[end + 1:]
        method = next(iter(route.methods - {"HEAD", "OPTIONS"}), "GET")
        client.cookies.clear()
        r = client.request(method, concrete)
        assert r.status_code == 401, f"{method} {path} devrait exiger une session, a renvoyé {r.status_code}"
        checked += 1
    assert checked > 50  # garde-fou : la boucle a bien parcouru l'API


def test_non_admin_cannot_mutate(client_and_db, login_as):
    _, _ = client_and_db
    viewer = login_as("viewer@test.local")
    # Échantillon de mutations sur plusieurs modules : toutes 403 pour un non-admin.
    assert viewer.post("/api/transactions/", json={}).status_code == 403
    assert viewer.delete("/api/transactions/1").status_code == 403
    assert viewer.post("/api/categories/", json={}).status_code == 403
    assert viewer.put("/api/config/balance", json={}).status_code == 403
    assert viewer.post("/api/entities/", json={}).status_code == 403


def test_non_admin_can_read(client_and_db, login_as):
    _, _ = client_and_db
    viewer = login_as("viewer2@test.local")
    r = viewer.get("/api/users/me")
    assert r.status_code == 200


def test_admin_client_still_works(client):
    """La fixture client (admin) passe le deny-by-default."""
    assert client.get("/api/modules").status_code == 200


def test_users_module_cannot_be_deactivated(client):
    r = client.put("/api/config/modules/users?active=false")
    assert r.status_code == 400
