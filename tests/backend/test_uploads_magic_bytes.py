"""Validation des uploads par magic bytes : liste blanche PDF + images."""
import pytest

from backend.core.uploads import detect_allowed_type, UPLOAD_REJECT_MESSAGE
from tests.backend.conftest import MINIMAL_PDF, MINIMAL_PNG

JPEG_HEADER = b"\xff\xd8\xff\xe0" + b"\x00" * 20
GIF_HEADER = b"GIF89a" + b"\x00" * 20
WEBP_HEADER = b"RIFF" + b"\x24\x00\x00\x00" + b"WEBP" + b"VP8 " + b"\x00" * 20


@pytest.fixture
def transaction(client):
    r = client.post("/api/transactions/", json={
        "date": "2026-07-01", "label": "Achat test", "amount": 1000,
    })
    assert r.status_code == 201
    return r.json()


def test_detect_pdf():
    assert detect_allowed_type(MINIMAL_PDF) == "application/pdf"


def test_detect_png():
    assert detect_allowed_type(MINIMAL_PNG) == "image/png"


def test_detect_jpeg():
    assert detect_allowed_type(JPEG_HEADER) == "image/jpeg"


def test_detect_gif():
    assert detect_allowed_type(GIF_HEADER) == "image/gif"


def test_detect_webp():
    assert detect_allowed_type(WEBP_HEADER) == "image/webp"


@pytest.mark.parametrize("content", [
    b"",                              # vide
    b"bonjour, ceci est du texte",    # texte brut
    b"<html><script>alert(1)</script></html>",  # HTML
    b"MZ\x90\x00\x03" + b"\x00" * 20,  # exécutable Windows
    b"RIFF1234WAVE",                  # RIFF mais pas WebP
    b"%PD",                            # signature tronquée
])
def test_detect_rejects_other_types(content):
    assert detect_allowed_type(content) is None


def test_upload_transaction_fake_pdf_rejected(client, transaction):
    """Un faux PDF (extension et Content-Type menteurs) est refusé en 400."""
    r = client.post(
        f"/api/attachments/transaction/{transaction['id']}",
        files={"file": ("facture.pdf", b"ceci n'est pas un pdf", "application/pdf")},
    )
    assert r.status_code == 400
    assert "Type de fichier non autorisé" in r.json()["detail"]
    # Aucune ligne créée en base.
    assert client.get(f"/api/attachments/transaction/{transaction['id']}").json() == []


def test_upload_transaction_real_pdf_accepted_mime_detected(client, transaction):
    """Un vrai PDF passe, et le MIME stocké est celui DÉTECTÉ, pas le déclaré."""
    r = client.post(
        f"/api/attachments/transaction/{transaction['id']}",
        files={"file": ("facture.pdf", MINIMAL_PDF, "text/plain")},
    )
    assert r.status_code == 201
    assert r.json()["mime_type"] == "application/pdf"


def test_upload_transaction_png_accepted(client, transaction):
    r = client.post(
        f"/api/attachments/transaction/{transaction['id']}",
        files={"file": ("photo.png", MINIMAL_PNG, "image/png")},
    )
    assert r.status_code == 201
    assert r.json()["mime_type"] == "image/png"


def test_upload_submission_fake_pdf_rejected(client_and_db, login_as):
    """Le second endpoint d'upload (soumission) applique la même liste blanche."""
    client, db_path = client_and_db
    # Entités : une interne (périmètre du treasurer), une externe (contrepartie).
    r = client.post("/api/entities/", json={"name": "Club E2E", "type": "internal"})
    assert r.status_code == 201
    internal_id = r.json()["id"]
    r = client.post("/api/entities/", json={"name": "Fournisseur E2E", "type": "external"})
    assert r.status_code == 201
    external_id = r.json()["id"]

    treasurer = login_as("tresorier.magic@test.fr", roles=[(internal_id, "treasurer")])
    r = treasurer.post("/api/submissions/", json={
        "date": "2026-07-01", "label": "Achat gâteau", "amount": 2500,
        "entity_id": internal_id, "counterparty_entity_id": external_id,
        "direction": "expense",
    })
    assert r.status_code == 201
    submission_id = r.json()["id"]

    r = treasurer.post(
        f"/api/attachments/submission/{submission_id}",
        files={"file": ("justificatif.pdf", b"pas un pdf du tout", "application/pdf")},
    )
    assert r.status_code == 400
    assert "Type de fichier non autorisé" in r.json()["detail"]

    from tests.backend.conftest import MINIMAL_PDF as PDF
    r = treasurer.post(
        f"/api/attachments/submission/{submission_id}",
        files={"file": ("justificatif.pdf", PDF, "application/pdf")},
    )
    assert r.status_code == 201
    assert r.json()["mime_type"] == "application/pdf"
