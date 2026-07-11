"""Intégrité référentielle des suppressions (PRAGMA foreign_keys OFF).

Sans contrainte FK au runtime, c'est le code applicatif qui doit nettoyer les
lignes dépendantes. Ces tests capturent les fuites trouvées à l'audit :
- delete_entity oubliait report_accruals (bilan silencieusement faux) et
  user_entity_roles (rôle fantôme), et n'interdisait pas la suppression de
  l'entité par défaut ;
- accept_invitation réinsérait un rôle sur une entité supprimée entretemps.
"""
import sqlite3

PAST = "2020-01-01T00:00:00+00:00"


def _create_internal_entity(client, name="Club Test"):
    r = client.post("/api/entities/", json={"name": name, "type": "internal"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _create_fiscal_year(client, name="Exercice 2025", start_date="2025-01-01"):
    r = client.post("/api/budget/fiscal-years", json={"name": name, "start_date": start_date})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_delete_entity_detaches_report_accruals(client_and_db):
    """Supprimer une entité portant une créance ne doit pas la faire disparaître
    silencieusement du bilan : la régularisation est détachée (entity_id NULL),
    pas orpheline sur un entity_id inexistant."""
    client, db_path = client_and_db
    entity_id = _create_internal_entity(client)
    fy_id = _create_fiscal_year(client)
    r = client.post("/api/reports/accruals", json={
        "fiscal_year_id": fy_id, "kind": "creance", "amount": 50000,
        "entity_id": entity_id, "label": "Subvention à recevoir",
    })
    assert r.status_code == 201, r.text
    accrual_id = r.json()["id"]

    assert client.delete(f"/api/entities/{entity_id}").status_code == 200

    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT entity_id FROM report_accruals WHERE id = ?", (accrual_id,)
        ).fetchone()
    finally:
        conn.close()
    assert row is not None, "la régularisation ne doit pas être supprimée"
    assert row[0] is None, "la régularisation doit être détachée (entity_id NULL), pas orpheline"


def test_delete_entity_removes_user_roles(client_and_db):
    """Supprimer une entité doit retirer les rôles utilisateurs qui la visent,
    sinon un rôle fantôme persiste (affiché côté admin sans nom d'entité)."""
    client, db_path = client_and_db
    entity_id = _create_internal_entity(client)

    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute(
            "INSERT INTO users (email, display_name, password_hash, is_admin, is_active, created_at) "
            "VALUES ('tresorier@test.local', 'Tresorier', 'x', 0, 1, ?)", (PAST,),
        )
        user_id = cur.lastrowid
        conn.execute(
            "INSERT INTO user_entity_roles (user_id, entity_id, role, created_at) VALUES (?, ?, 'treasurer', ?)",
            (user_id, entity_id, PAST),
        )
        conn.commit()
    finally:
        conn.close()

    assert client.delete(f"/api/entities/{entity_id}").status_code == 200

    conn = sqlite3.connect(str(db_path))
    try:
        remaining = conn.execute(
            "SELECT COUNT(*) FROM user_entity_roles WHERE entity_id = ?", (entity_id,)
        ).fetchone()[0]
    finally:
        conn.close()
    assert remaining == 0, "aucun rôle ne doit subsister sur une entité supprimée"


def test_delete_default_entity_is_blocked(client_and_db):
    """L'entité par défaut (racine de la vue globale) ne doit pas être supprimable :
    sa disparition changerait silencieusement le calcul du dashboard."""
    client, db_path = client_and_db
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute(
            "INSERT INTO entities (name, type, parent_id, is_default, color, position, created_at, updated_at) "
            "VALUES ('Racine', 'internal', NULL, 1, '#000000', 0, ?, ?)", (PAST, PAST),
        )
        default_id = cur.lastrowid
        conn.commit()
    finally:
        conn.close()

    r = client.delete(f"/api/entities/{default_id}")
    assert r.status_code == 400, "la suppression de l'entité par défaut doit être refusée"


def test_accept_invitation_skips_deleted_entity_role(client_and_db):
    """Si l'entité ciblée par une invitation est supprimée avant l'acceptation,
    le rôle correspondant doit être ignoré, pas créé sur une entité inexistante."""
    client, db_path = client_and_db
    entity_id = _create_internal_entity(client)
    r = client.post("/api/users/invitations", json={
        "email": "invite@test.local", "is_admin": False,
        "roles": [{"entity_id": entity_id, "role": "viewer"}],
    })
    assert r.status_code == 201, r.text
    token = r.json()["token"]

    assert client.delete(f"/api/entities/{entity_id}").status_code == 200

    r = client.post("/api/users/invitations/accept", json={
        "token": token, "display_name": "Invité", "password": "motdepasse-long",
    })
    assert r.status_code == 200, r.text

    conn = sqlite3.connect(str(db_path))
    try:
        orphans = conn.execute(
            "SELECT COUNT(*) FROM user_entity_roles WHERE entity_id = ?", (entity_id,)
        ).fetchone()[0]
    finally:
        conn.close()
    assert orphans == 0, "aucun rôle ne doit être créé sur une entité supprimée"
