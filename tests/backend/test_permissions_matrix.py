"""Matrice rôle x mutation : seule l'admin écrit ; treasurer/viewer/anonyme sont bloqués.

Parcourt TOUTES les routes mutantes de l'app (comme test_auth_enforcement
parcourt les 401) pour que tout futur endpoint soit couvert d'office.
"""
import starlette.routing

from backend.core.auth import NON_ADMIN_MUTATIONS, NON_ADMIN_MUTATION_PATTERNS, PUBLIC_API_PATHS, is_non_admin_mutation

MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


def _mutating_api_routes(app):
    for route in app.routes:
        if not isinstance(route, starlette.routing.Route):
            continue
        if not route.path.startswith("/api"):
            continue
        for method in sorted((route.methods or set()) & MUTATING):
            yield method, route.path


def _concretize(path):
    while "{" in path:
        start, end = path.index("{"), path.index("}")
        path = path[:start] + "1" + path[end + 1:]
    return path


def test_every_mutation_is_admin_only(client_and_db, login_as):
    client, _ = client_and_db
    treasurer = login_as("matrix-tres@test.local")
    covered = 0
    for method, path in _mutating_api_routes(client.app):
        if path in PUBLIC_API_PATHS or is_non_admin_mutation(_concretize(path)):
            continue
        r = treasurer.request(method, _concretize(path), json={})
        assert r.status_code == 403, (
            f"{method} {path} : un non-admin a obtenu {r.status_code} au lieu de 403"
        )
        covered += 1
    assert covered > 30


def test_non_admin_mutations_allowlist_is_minimal():
    assert NON_ADMIN_MUTATIONS == {
        "/api/users/login",
        "/api/users/logout",
        "/api/users/me/password",
        "/api/users/invitations/accept",
        "/api/submissions/",
    }
    assert [p.pattern for p in NON_ADMIN_MUTATION_PATTERNS] == [
        r"^/api/submissions/\d+/cancel$",
    ]
