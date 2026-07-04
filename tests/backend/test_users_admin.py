"""Administration des comptes : CRUD, rôles, invitations, mot de passe."""
import sqlite3

from backend.core.auth import SESSION_COOKIE

PASSWORD = "mot-de-passe-solide"


def test_create_and_accept_invitation(client_and_db):
    client, db_path = client_and_db
    r = client.post("/api/users/invitations",
                    json={"email": "Tresorier@Gastro.fr", "roles": []})
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == "tresorier@gastro.fr"   # normalisé minuscules
    token = body["token"]
    assert token and "token" not in client.get("/api/users/invitations").json()[0]

    # Preview publique
    fresh = client
    fresh.cookies.clear()
    r = fresh.get(f"/api/users/invitations/preview?token={token}")
    assert r.status_code == 200 and r.json()["email"] == "tresorier@gastro.fr"

    # Acceptation : crée le compte et connecte
    r = fresh.post("/api/users/invitations/accept",
                   json={"token": token, "display_name": "Gastro", "password": PASSWORD})
    assert r.status_code == 200
    assert SESSION_COOKIE in r.cookies
    assert fresh.get("/api/users/me").json()["email"] == "tresorier@gastro.fr"

    # Usage unique
    r = fresh.post("/api/users/invitations/accept",
                   json={"token": token, "display_name": "X", "password": PASSWORD})
    assert r.status_code == 404


def test_accept_rejects_short_password(client_and_db):
    client, _ = client_and_db
    token = client.post("/api/users/invitations",
                        json={"email": "a@b.fr"}).json()["token"]
    client.cookies.clear()
    r = client.post("/api/users/invitations/accept",
                    json={"token": token, "display_name": "A", "password": "court"})
    assert r.status_code == 400


def test_expired_invitation(client_and_db):
    client, db_path = client_and_db
    token = client.post("/api/users/invitations",
                        json={"email": "a@b.fr"}).json()["token"]
    conn = sqlite3.connect(str(db_path))
    conn.execute("UPDATE invitations SET expires_at = '2020-01-01T00:00:00+00:00'")
    conn.commit(); conn.close()
    client.cookies.clear()
    assert client.get(f"/api/users/invitations/preview?token={token}").status_code == 404
    r = client.post("/api/users/invitations/accept",
                    json={"token": token, "display_name": "A", "password": PASSWORD})
    assert r.status_code == 404


def test_invitation_conflicts_with_existing_account(client_and_db, login_as):
    client, _ = client_and_db
    login_as("deja@la.fr")
    r = client.post("/api/users/invitations", json={"email": "deja@la.fr"})
    assert r.status_code == 400


def test_list_update_roles_and_deactivate(client_and_db, login_as):
    client, db_path = client_and_db
    login_as("cible@test.local")
    users = client.get("/api/users/").json()
    target = next(u for u in users if u["email"] == "cible@test.local")

    # Attribution de rôles (nécessite une entité réelle)
    conn = sqlite3.connect(str(db_path))
    cur = conn.execute(
        "INSERT INTO entities (name, type, parent_id, is_default, color, position, created_at, updated_at) "
        "VALUES ('Club', 'internal', NULL, 0, '#000', 0, '2026-01-01', '2026-01-01')")
    entity_id = cur.lastrowid
    conn.commit(); conn.close()

    r = client.put(f"/api/users/{target['id']}/roles",
                   json={"roles": [{"entity_id": entity_id, "role": "treasurer"}]})
    assert r.status_code == 200
    assert r.json()["roles"] == [{"entity_id": entity_id, "role": "treasurer"}]

    r = client.put(f"/api/users/{target['id']}/roles",
                   json={"roles": [{"entity_id": entity_id, "role": "capitaine"}]})
    assert r.status_code == 422  # role hors enum pydantic

    r = client.put(f"/api/users/{target['id']}", json={"is_active": False})
    assert r.status_code == 200 and r.json()["is_active"] == 0


def test_admin_cannot_demote_self(client):
    me = client.get("/api/users/me").json()
    assert client.put(f"/api/users/{me['id']}", json={"is_admin": False}).status_code == 400
    assert client.put(f"/api/users/{me['id']}", json={"is_active": False}).status_code == 400


def test_force_logout(client_and_db, login_as):
    client, _ = client_and_db
    other = login_as("kick@test.local")
    target_id = other.get("/api/users/me").json()["id"]
    r = client.delete(f"/api/users/{target_id}/sessions")
    assert r.status_code == 200 and r.json()["deleted"] >= 1
    assert other.get("/api/users/me").status_code == 401


def test_update_unknown_user(client):
    assert client.put("/api/users/99999", json={"is_active": False}).status_code == 404


def test_admin_only_gets_blocked_for_non_admin(client_and_db, login_as):
    _, _ = client_and_db
    other = login_as("simple@test.local")
    assert other.get("/api/users/").status_code == 403
    assert other.get("/api/users/invitations").status_code == 403


def test_set_roles_rejects_duplicate_entity(client_and_db, login_as):
    client, db_path = client_and_db
    login_as("doublon@test.local")
    users = client.get("/api/users/").json()
    target = next(u for u in users if u["email"] == "doublon@test.local")

    conn = sqlite3.connect(str(db_path))
    cur = conn.execute(
        "INSERT INTO entities (name, type, parent_id, is_default, color, position, created_at, updated_at) "
        "VALUES ('Club Doublon', 'internal', NULL, 0, '#000', 0, '2026-01-01', '2026-01-01')")
    entity_id = cur.lastrowid
    conn.commit(); conn.close()

    r = client.put(f"/api/users/{target['id']}/roles",
                   json={"roles": [
                       {"entity_id": entity_id, "role": "treasurer"},
                       {"entity_id": entity_id, "role": "viewer"},
                   ]})
    assert r.status_code == 400


def test_change_own_password(client_and_db, login_as):
    client, db_path = client_and_db
    user = login_as("moi@test.local")
    # login_as pose un hash bidon 'x' : donner un vrai mot de passe d'abord.
    from backend.core.auth import hash_password
    conn = sqlite3.connect(str(db_path))
    conn.execute("UPDATE users SET password_hash = ? WHERE email = 'moi@test.local'",
                 (hash_password(PASSWORD),))
    conn.commit(); conn.close()

    r = user.put("/api/users/me/password",
                 json={"current_password": "faux-mot-de-passe", "new_password": PASSWORD + "2"})
    assert r.status_code == 401
    r = user.put("/api/users/me/password",
                 json={"current_password": PASSWORD, "new_password": "court"})
    assert r.status_code == 400
    r = user.put("/api/users/me/password",
                 json={"current_password": PASSWORD, "new_password": PASSWORD + "2"})
    assert r.status_code == 200
    # La session courante survit.
    assert user.get("/api/users/me").status_code == 200
