"""Modules ops admin-only (backup, system, direns, helloasso) : un non-admin
(viewer ou treasurer, peu importe le rôle) doit recevoir 403 sur toutes les
lectures ; un admin garde son accès (200, ou un code métier non 401/403 pour
les endpoints qui exigent des paramètres). Couvre aussi le scope tiers.

Anonyme -> 401 est déjà couvert par test_auth_enforcement (garde globale
require_session) : ce fichier ne teste que la frontière admin/non-admin.
"""
import sqlite3

NOW = "2026-01-01T00:00:00+00:00"


def _seed_tree(db_path):
    """BDA -> Gastronomine (+ CCMP hors périmètre) + un externe + 2 transactions
    du contact partagé : une dans le périmètre du treasurer, une hors périmètre."""
    conn = sqlite3.connect(str(db_path))
    ids = {}

    def entity(name, typ="internal", parent=None):
        cur = conn.execute(
            "INSERT INTO entities (name, type, parent_id, is_default, color, position, created_at, updated_at) "
            "VALUES (?, ?, ?, 0, '#000', 0, ?, ?)", (name, typ, parent, NOW, NOW))
        ids[name] = cur.lastrowid
        return cur.lastrowid

    bda = entity("BDA")
    entity("Gastronomine", parent=bda)
    entity("CCMP", parent=bda)
    ext = entity("Fournisseur", typ="external")

    cur = conn.execute(
        "INSERT INTO contacts (name, type, email, phone, address, notes, created_at, updated_at) "
        "VALUES ('Le Fournisseur', 'other', '', '', '', '', ?, ?)", (NOW, NOW))
    ids["contact"] = cur.lastrowid

    def tx(label, frm, to, contact_id):
        cur = conn.execute(
            "INSERT INTO transactions (date, label, description, amount, category_id, contact_id, "
            "created_by, created_at, updated_at, from_entity_id, to_entity_id) "
            "VALUES ('2026-01-15', ?, '', 1000, NULL, ?, '', ?, ?, ?, ?)",
            (label, contact_id, NOW, NOW, frm, to))
        ids[f"tx_{label}"] = cur.lastrowid

    tx("in_scope", ids["Gastronomine"], ext, ids["contact"])
    tx("out_scope", ids["CCMP"], ext, ids["contact"])

    conn.commit(); conn.close()
    return ids


# ─── modules ops admin-only : lectures ──────────────────────────────────────

ADMIN_ONLY_GET_ENDPOINTS = [
    "/api/backup/export",
    "/api/backup/preview",
    "/api/direns/export",
    "/api/helloasso/campaigns",
    "/api/system/status",
    "/api/system/settings",
    "/api/system/backups",
]


def test_non_admin_forbidden_on_admin_only_modules(client_and_db, login_as):
    _, db_path = client_and_db
    ids = _seed_tree(db_path)
    tres = login_as("visitor@t.fr", roles=[(ids["Gastronomine"], "treasurer")])
    for path in ADMIN_ONLY_GET_ENDPOINTS:
        r = tres.get(path)
        assert r.status_code == 403, f"{path} attendu 403 pour un non-admin, reçu {r.status_code}"


def test_no_role_forbidden_on_admin_only_modules(client_and_db, login_as):
    _, db_path = client_and_db
    _seed_tree(db_path)
    nobody = login_as("nobody@t.fr")
    for path in ADMIN_ONLY_GET_ENDPOINTS:
        r = nobody.get(path)
        assert r.status_code == 403, f"{path} attendu 403 sans rôle, reçu {r.status_code}"


def test_admin_unaffected_on_admin_only_modules(client_and_db):
    client, db_path = client_and_db
    _seed_tree(db_path)
    for path in ADMIN_ONLY_GET_ENDPOINTS:
        r = client.get(path)
        # Certains endpoints exigent des paramètres (ex : direns/export sans
        # bilan_fiscal_year_id) : on n'exige que l'absence de 401/403, pas un 200 strict.
        assert r.status_code not in (401, 403), f"{path} bloqué pour l'admin ({r.status_code})"


# ─── tiers/{contact_id}/transactions scopé ──────────────────────────────────

def test_tiers_transactions_scoped_for_treasurer(client_and_db, login_as):
    _, db_path = client_and_db
    ids = _seed_tree(db_path)
    tres = login_as("tres@gastro.fr", roles=[(ids["Gastronomine"], "treasurer")])
    r = tres.get(f"/api/tiers/{ids['contact']}/transactions")
    assert r.status_code == 200
    labels = {t["label"] for t in r.json()}
    assert labels == {"in_scope"}


def test_tiers_transactions_admin_sees_all(client_and_db):
    client, db_path = client_and_db
    ids = _seed_tree(db_path)
    r = client.get(f"/api/tiers/{ids['contact']}/transactions")
    assert r.status_code == 200
    labels = {t["label"] for t in r.json()}
    assert labels == {"in_scope", "out_scope"}


def test_tiers_transactions_empty_scope_returns_empty(client_and_db, login_as):
    _, db_path = client_and_db
    ids = _seed_tree(db_path)
    nobody = login_as("norole@t.fr")
    r = nobody.get(f"/api/tiers/{ids['contact']}/transactions")
    assert r.status_code == 200
    assert r.json() == []


def test_tiers_transactions_404_unknown_contact(client_and_db, login_as):
    _, db_path = client_and_db
    ids = _seed_tree(db_path)
    tres = login_as("tres2@gastro.fr", roles=[(ids["Gastronomine"], "treasurer")])
    assert tres.get("/api/tiers/999999/transactions").status_code == 404
