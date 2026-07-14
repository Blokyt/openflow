"""Audit exhaustif des routes GET : classification, 401 anonyme, 403 non-admin.

Toute nouvelle route GET doit être classée ici, sinon le test échoue :
c'est le pendant lecture de test_permissions_matrix.py (mutations).

Catégories :
- "public"    : accessible sans session (allowlist PUBLIC_API_PATHS)
- "admin"     : 403 pour un connecté non-admin (GET sensibles)
- "connected" : accessible à tout connecté ; le contenu est filtré par le
                périmètre d'entités ou par des contrôles fins dans l'endpoint
                (couvert par les tests de scoping de la phase 1/2)
"""
import re

EXPECTED_GET = {
    # core (main.py)
    "/api/modules": "connected",
    "/api/modules/all": "connected",
    "/api/config": "connected",
    # users
    "/api/users/me": "connected",
    "/api/users/invitations/preview": "public",
    "/api/users/reset/preview": "public",
    "/api/users/": "admin",
    "/api/users/invitations": "admin",
    "/api/users/login-events": "admin",
    # transactions
    "/api/transactions/": "connected",
    "/api/transactions/balance": "admin",
    "/api/transactions/{tx_id}": "connected",
    # categories
    "/api/categories/": "connected",
    "/api/categories/tree": "connected",
    "/api/categories/{cat_id}": "connected",
    "/api/categories/{cat_id}/usage": "connected",
    # dashboard
    "/api/dashboard/widgets": "connected",
    "/api/dashboard/layout": "connected",
    "/api/dashboard/summary": "connected",
    "/api/dashboard/timeseries": "connected",
    "/api/dashboard/top-categories": "connected",
    "/api/dashboard/recent": "connected",
    # entities
    "/api/entities/": "connected",
    "/api/entities/tree": "connected",
    "/api/entities/{entity_id}": "connected",
    "/api/entities/{entity_id}/balance": "connected",
    "/api/entities/{entity_id}/consolidated": "connected",
    "/api/entities/{entity_id}/balance-ref": "connected",
    # budget
    "/api/budget/fiscal-years": "connected",
    "/api/budget/fiscal-years/current": "connected",
    "/api/budget/fiscal-years/{fy_id}/opening-balances": "connected",
    "/api/budget/fiscal-years/{fy_id}/allocations": "connected",
    "/api/budget/view": "connected",
    "/api/budget/view/categories": "connected",
    # reimbursements
    "/api/reimbursements/": "connected",
    "/api/reimbursements/summary": "connected",
    "/api/reimbursements/{reimbursement_id}": "connected",
    # tiers
    "/api/tiers/": "connected",
    "/api/tiers/{contact_id}": "connected",
    "/api/tiers/{contact_id}/transactions": "connected",
    # reports
    "/api/reports/accounts": "connected",
    "/api/reports/mapping": "connected",
    "/api/reports/mapping/suggestions": "connected",
    "/api/reports/compte-resultat": "connected",
    "/api/reports/compte-resultat/pdf": "connected",
    "/api/reports/bilan": "connected",
    "/api/reports/bilan/pdf": "connected",
    "/api/reports/accruals": "connected",
    # attachments (contrôles fins par ressource dans l'endpoint)
    "/api/attachments/transaction/{tx_id}": "connected",
    "/api/attachments/submission/{submission_id}": "connected",
    "/api/attachments/{id}/preview": "connected",
    "/api/attachments/{id}/download": "connected",
    # submissions
    "/api/submissions/": "admin",
    "/api/submissions/mine": "connected",
    "/api/submissions/{submission_id}": "connected",
    # modules d'exploitation : routers entiers sous require_admin
    "/api/backup/export": "admin",
    "/api/backup/preview": "admin",
    "/api/direns/export": "admin",
    "/api/helloasso/config": "admin",
    "/api/helloasso/campaigns": "admin",
    "/api/helloasso/campaigns/{campaign_id}/links": "admin",
    "/api/helloasso/campaigns/{campaign_id}/suggestions": "admin",
    "/api/system/status": "admin",
    "/api/system/settings": "admin",
    "/api/system/backups": "admin",
    "/api/system/pristine/status": "admin",
}


def _get_api_routes(app):
    routes = set()
    for route in app.routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", None) or set()
        if path.startswith("/api") and "GET" in methods:
            routes.add(path)
    return routes


def _fill(path):
    """Substitue chaque paramètre de chemin par 1 (id plausible)."""
    return re.sub(r"\{[^}]+\}", "1", path)


def test_every_get_route_is_classified(client):
    discovered = _get_api_routes(client.app)
    missing = discovered - set(EXPECTED_GET)
    stale = set(EXPECTED_GET) - discovered
    assert not missing, (
        f"Routes GET non classées dans l'audit (ajoutez-les à EXPECTED_GET "
        f"avec la bonne catégorie) : {sorted(missing)}"
    )
    assert not stale, f"Routes disparues, à retirer d'EXPECTED_GET : {sorted(stale)}"


def test_get_routes_deny_anonymous(client_and_db):
    """Deny-by-default : tout GET non public répond 401 sans session."""
    client, _ = client_and_db
    client.cookies.clear()
    failures = []
    for path, category in EXPECTED_GET.items():
        if category == "public":
            continue
        r = client.get(_fill(path))
        if r.status_code != 401:
            failures.append(f"{path} -> {r.status_code}")
    assert not failures, f"GET accessibles sans session : {failures}"


def test_admin_get_routes_deny_non_admin(login_as):
    """Les GET sensibles répondent 403 à un connecté non-admin (même sans rôle)."""
    viewer = login_as("auditeur.get@test.fr", roles=[])
    failures = []
    for path, category in EXPECTED_GET.items():
        if category != "admin":
            continue
        r = viewer.get(_fill(path))
        if r.status_code != 403:
            failures.append(f"{path} -> {r.status_code}")
    assert not failures, f"GET admin-only accessibles à un non-admin : {failures}"


def test_public_get_routes_reachable_anonymous(client_and_db):
    """Les routes publiques ne demandent pas de session (404 admis : token bidon)."""
    client, _ = client_and_db
    client.cookies.clear()
    r = client.get("/api/users/invitations/preview?token=inexistant")
    assert r.status_code in (400, 404, 422)  # tout sauf 401/403


def test_config_redacts_operational_fields_for_non_admin(client, login_as):
    """GET /api/config expose server et external_backup à l'admin uniquement.

    Le chemin de sauvegarde externe (external_backup.destination) et l'écoute
    réseau (server) n'ont aucun usage côté UI non-admin et révéleraient la
    topologie du déploiement : ils sont retirés de la réponse pour un connecté
    non-admin. entity, balance et modules restent visibles (le frontend en a
    besoin)."""
    admin_cfg = client.get("/api/config")
    assert admin_cfg.status_code == 200
    assert "server" in admin_cfg.json()
    assert "external_backup" in admin_cfg.json()

    viewer = login_as("lecteur.config@test.fr", roles=[])
    r = viewer.get("/api/config")
    assert r.status_code == 200
    body = r.json()
    assert "server" not in body
    assert "external_backup" not in body
    # Les champs légitimes restent présents pour l'UI.
    assert "entity" in body and "balance" in body and "modules" in body
