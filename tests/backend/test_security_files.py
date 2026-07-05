"""Tests de sécurité fichiers : path traversal (upload + SPA), limite de taille.

Couvre le point C4 de l'audit :
- assainissement du nom de fichier à l'upload (anti path traversal),
- limite de taille d'upload (anti épuisement disque),
- confinement du SPA fallback (anti lecture de fichiers arbitraires).
"""
from tests.backend.conftest import MINIMAL_PDF


# ---------------------------------------------------------------------------
# C4a — Assainissement du nom de fichier (anti path traversal à l'upload)
# ---------------------------------------------------------------------------

def test_sanitize_filename_strips_traversal():
    from backend.modules.attachments.api import _sanitize_filename
    out = _sanitize_filename("../../etc/passwd")
    assert "/" not in out
    assert ".." not in out


def test_sanitize_filename_strips_backslash():
    from backend.modules.attachments.api import _sanitize_filename
    out = _sanitize_filename("..\\..\\windows\\system32\\evil.exe")
    assert "\\" not in out
    assert "/" not in out
    assert ".." not in out


def test_sanitize_filename_keeps_simple_name():
    from backend.modules.attachments.api import _sanitize_filename
    assert _sanitize_filename("facture_juin.pdf") == "facture_juin.pdf"


def test_sanitize_filename_empty_defaults_to_upload():
    from backend.modules.attachments.api import _sanitize_filename
    assert _sanitize_filename("") == "upload"
    assert _sanitize_filename("..") == "upload"


# ---------------------------------------------------------------------------
# C4b — Limite de taille d'upload
# ---------------------------------------------------------------------------

def test_upload_too_large_returns_413(client, monkeypatch):
    import backend.modules.attachments.api as att
    monkeypatch.setattr(att, "MAX_ATTACHMENT_SIZE", 10, raising=False)  # 10 octets
    tx = client.post("/api/transactions/", json={
        "date": "2025-06-01", "label": "T", "amount": 10,
    }).json()
    big = b"x" * 50
    resp = client.post(
        f"/api/attachments/transaction/{tx['id']}",
        files={"file": ("big.txt", big, "text/plain")},
    )
    assert resp.status_code == 413


def test_upload_within_limit_ok(client, monkeypatch):
    import backend.modules.attachments.api as att
    monkeypatch.setattr(att, "MAX_ATTACHMENT_SIZE", 1000, raising=False)
    tx = client.post("/api/transactions/", json={
        "date": "2025-06-01", "label": "T", "amount": 10,
    }).json()
    resp = client.post(
        f"/api/attachments/transaction/{tx['id']}",
        files={"file": ("ok.pdf", MINIMAL_PDF, "application/pdf")},
    )
    assert resp.status_code == 201


# ---------------------------------------------------------------------------
# C4c — Le nom de fichier stocké est assaini (pas de séquence de traversal)
# ---------------------------------------------------------------------------

def test_upload_stores_sanitized_filename(client):
    tx = client.post("/api/transactions/", json={
        "date": "2025-06-01", "label": "T", "amount": 10,
    }).json()
    resp = client.post(
        f"/api/attachments/transaction/{tx['id']}",
        files={"file": ("../../evil.pdf", MINIMAL_PDF, "application/pdf")},
    )
    assert resp.status_code == 201
    stored = resp.json()["filename"]
    assert "/" not in stored
    assert "\\" not in stored
    assert ".." not in stored


# ---------------------------------------------------------------------------
# C4d — SPA fallback confiné au répertoire de build
# ---------------------------------------------------------------------------

def test_safe_static_file_blocks_traversal(tmp_path):
    from backend.main import safe_static_file
    build = tmp_path / "dist"
    build.mkdir()
    (build / "index.html").write_text("<html></html>")
    (tmp_path / "secret.txt").write_text("SECRET")
    assert safe_static_file(build, "../secret.txt") is None
    assert safe_static_file(build, "../../etc/hosts") is None


def test_safe_static_file_allows_real_asset(tmp_path):
    from backend.main import safe_static_file
    build = tmp_path / "dist"
    build.mkdir()
    (build / "app.js").write_text("console.log(1)")
    result = safe_static_file(build, "app.js")
    assert result is not None
    assert result.name == "app.js"
