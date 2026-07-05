"""Configuration d'écoute réseau + comportement des cookies en HTTP (LAN)."""
from pathlib import Path

from fastapi.testclient import TestClient

from backend.core.config import load_config, save_config
from tests.backend.conftest import ADMIN_EMAIL


def _write_config(tmp_path: Path, content: str) -> str:
    p = tmp_path / "config.yaml"
    p.write_text(content, encoding="utf-8")
    return str(p)


def test_server_defaults_when_section_absent(tmp_path):
    path = _write_config(tmp_path, "modules:\n  transactions: true\n")
    config = load_config(path)
    assert config.server.host == "127.0.0.1"
    assert config.server.port == 8000


def test_server_section_parsed(tmp_path):
    path = _write_config(
        tmp_path,
        "modules:\n  transactions: true\nserver:\n  host: 0.0.0.0\n  port: 8080\n",
    )
    config = load_config(path)
    assert config.server.host == "0.0.0.0"
    assert config.server.port == 8080


def test_save_config_roundtrip_includes_server(tmp_path):
    path = _write_config(tmp_path, "server:\n  host: 0.0.0.0\n  port: 9000\n")
    config = load_config(path)
    save_config(config, path)
    reloaded = load_config(path)
    assert reloaded.server.host == "0.0.0.0"
    assert reloaded.server.port == 9000


def test_login_cookie_not_secure_over_http(app_and_db):
    """En HTTP (LAN), le cookie de session ne doit PAS porter l'attribut Secure."""
    app, _ = app_and_db
    tc = TestClient(app, base_url="http://testserver")
    r = tc.post("/api/users/login",
                json={"email": ADMIN_EMAIL, "password": "admin-test-password"})
    assert r.status_code == 200
    set_cookie = r.headers["set-cookie"]
    assert "httponly" in set_cookie.lower()
    assert "samesite=lax" in set_cookie.lower()
    assert "secure" not in set_cookie.lower()


def test_login_cookie_secure_over_https(app_and_db):
    app, _ = app_and_db
    tc = TestClient(app, base_url="https://testserver")
    r = tc.post("/api/users/login",
                json={"email": ADMIN_EMAIL, "password": "admin-test-password"})
    assert r.status_code == 200
    assert "secure" in r.headers["set-cookie"].lower()
