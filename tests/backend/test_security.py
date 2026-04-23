"""Tests de sécurité : headers HTTP, politique de mot de passe, rate limiting."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_user_and_login(client, username, password):
    """Crée un user et retourne le client avec session active."""
    client.post("/api/multi_users/", json={
        "username": username,
        "password": password,
        "role": "lecteur",
    })
    client.post("/api/multi_users/login", json={
        "username": username,
        "password": password,
    })
    return client


# ---------------------------------------------------------------------------
# Item D — Headers de sécurité HTTP
# ---------------------------------------------------------------------------

def test_security_headers_present(client):
    """Les headers de sécurité doivent être présents sur chaque réponse API."""
    resp = client.get("/api/modules")
    assert resp.status_code == 200
    assert resp.headers.get("X-Frame-Options") == "DENY"
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert resp.headers.get("Permissions-Policy") == "camera=(), microphone=(), geolocation=()"


def test_security_headers_no_hsts(client):
    """Pas de HSTS en HTTP local (sera ajouté quand HTTPS sera en place)."""
    resp = client.get("/api/modules")
    assert "Strict-Transport-Security" not in resp.headers


# ---------------------------------------------------------------------------
# Item C — Politique de mot de passe à la création
# ---------------------------------------------------------------------------

def test_password_too_short(client):
    """MDP de 6 chars doit retourner 400."""
    resp = client.post("/api/multi_users/", json={
        "username": "short_pwd_user",
        "password": "Ab1!xy",  # 6 chars
    })
    assert resp.status_code == 400
    assert "12" in resp.json()["detail"]


def test_password_no_uppercase(client):
    """MDP sans majuscule doit retourner 400."""
    resp = client.post("/api/multi_users/", json={
        "username": "no_upper_user",
        "password": "alllowercase1!xx",  # pas de maj
    })
    assert resp.status_code == 400
    assert "majuscule" in resp.json()["detail"]


def test_password_no_digit(client):
    """MDP sans chiffre doit retourner 400."""
    resp = client.post("/api/multi_users/", json={
        "username": "no_digit_user",
        "password": "NoDigitsHere!xxx",  # pas de chiffre
    })
    assert resp.status_code == 400
    assert "chiffre" in resp.json()["detail"]


def test_password_no_special(client):
    """MDP sans caractère spécial doit retourner 400."""
    resp = client.post("/api/multi_users/", json={
        "username": "no_special_user",
        "password": "NoSpecialChar1xx",  # pas de spécial
    })
    assert resp.status_code == 400
    assert "spécial" in resp.json()["detail"]


def test_password_valid(client):
    """MDP conforme doit permettre la création (201)."""
    resp = client.post("/api/multi_users/", json={
        "username": "valid_pwd_user",
        "password": "Secure123!valid",  # 15 chars, maj, chiffre, spécial
    })
    assert resp.status_code == 201


def test_password_exactly_12_chars(client):
    """MDP de exactement 12 chars conforme doit être accepté."""
    resp = client.post("/api/multi_users/", json={
        "username": "twelve_chars_user",
        "password": "ValidPass12!",  # 12 chars exactement
    })
    assert resp.status_code == 201


def test_password_11_chars_rejected(client):
    """MDP de 11 chars doit être rejeté même s'il a maj, chiffre, spécial."""
    resp = client.post("/api/multi_users/", json={
        "username": "eleven_chars_user",
        "password": "ValidPas1!x",  # 11 chars
    })
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Item C — Politique de mot de passe au changement de mot de passe
# ---------------------------------------------------------------------------

def test_change_password_policy_enforced(client):
    """PUT /me/password avec MDP faible doit retourner 400."""
    _create_user_and_login(client, "change_pwd_policy_user", "InitialPass1!xx")

    resp = client.put("/api/multi_users/me/password", json={
        "old_password": "InitialPass1!xx",
        "new_password": "tooshort",  # trop court, sans maj ni spécial
    })
    assert resp.status_code == 400


def test_change_password_no_uppercase_rejected(client):
    """Changement MDP sans majuscule doit retourner 400."""
    _create_user_and_login(client, "change_no_upper_user", "InitialPass1!xx")

    resp = client.put("/api/multi_users/me/password", json={
        "old_password": "InitialPass1!xx",
        "new_password": "alllowercase1!xx",
    })
    assert resp.status_code == 400


def test_change_password_valid(client):
    """Changement MDP conforme doit retourner 200."""
    _create_user_and_login(client, "change_valid_pwd_user", "InitialPass1!xx")

    resp = client.put("/api/multi_users/me/password", json={
        "old_password": "InitialPass1!xx",
        "new_password": "NewSecure123!ok",
    })
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Item A — Auto-generate password respecte la politique
# ---------------------------------------------------------------------------

def test_autogenerate_password_is_returned(client):
    """Un user créé sans MDP doit avoir un generated_password dans la réponse."""
    resp = client.post("/api/multi_users/", json={
        "username": "autogen_pwd_user",
        "password": "",  # vide = auto-généré
    })
    assert resp.status_code == 201
    data = resp.json()
    assert "generated_password" in data
    pwd = data["generated_password"]
    # Doit satisfaire la politique
    import re
    assert len(pwd) >= 12
    assert re.search(r"[A-Z]", pwd), "Auto-generated password must have uppercase"
    assert re.search(r"[0-9]", pwd), "Auto-generated password must have digit"
    assert re.search(r"[^A-Za-z0-9]", pwd), "Auto-generated password must have special char"


# ---------------------------------------------------------------------------
# Item A — Rate limiting (test d'existence du mécanisme)
# ---------------------------------------------------------------------------

def test_rate_limit_endpoint_configured(client):
    """Le rate limiter est actif : après 5 tentatives, le login retourne 429.

    Note : slowapi partage son compteur en mémoire par IP ("testclient" dans
    les tests). On envoie jusqu'à 10 requêtes et on vérifie qu'au moins l'une
    d'entre elles déclenche le 429 — ce qui prouve que le mécanisme est actif.
    """
    # Crée un user pour avoir un endpoint login fonctionnel
    client.post("/api/multi_users/", json={
        "username": "rate_limit_test_user",
        "password": "RateLimit1!xyzA",
    })

    # Envoie jusqu'à 10 requêtes et collecte les codes de statut
    statuses = []
    for _ in range(10):
        resp = client.post("/api/multi_users/login", json={
            "username": "rate_limit_test_user",
            "password": "RateLimit1!xyzA",
        })
        statuses.append(resp.status_code)

    assert 429 in statuses, (
        f"Expected at least one 429 in {statuses}. "
        "Vérifier que slowapi est actif dans create_app() avec la limite 5/15minutes."
    )


# ---------------------------------------------------------------------------
# Item C — Politique de mot de passe sur la mise à jour admin (PUT /{user_id})
# ---------------------------------------------------------------------------

def test_admin_update_user_password_policy_enforced(authed_client):
    """PUT /multi_users/{user_id} avec MDP faible doit retourner 400.

    Vérifie que la politique de mot de passe est appliquée côté admin,
    pas seulement lors de la création ou du changement de MDP par le user.
    Utilise authed_client (admin root déjà loggué et lié à l'entité racine).
    """
    # Crée un utilisateur cible via l'admin déjà authentifié
    target_resp = authed_client.post("/api/multi_users/", json={
        "username": "target_user_pwd_policy",
        "password": "TargetPass1!xyz",
        "role": "lecteur",
    })
    assert target_resp.status_code == 201, target_resp.text
    target_id = target_resp.json()["id"]

    # Tente de mettre à jour le MDP avec un mot de passe faible (sans maj ni spécial)
    resp = authed_client.put(f"/api/multi_users/{target_id}", json={
        "password": "weakpass",
    })
    assert resp.status_code == 400, (
        f"Expected 400 for weak password in admin update, got {resp.status_code}: {resp.json()}"
    )
