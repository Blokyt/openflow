"""Tests de sécurité : headers HTTP."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest


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


def test_csp_header_present(client):
    resp = client.get("/api/modules")
    csp = resp.headers.get("Content-Security-Policy", "")
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "object-src 'none'" in csp
    # Les styles inline (attributs style= de React/Recharts) doivent rester permis.
    assert "style-src 'self' 'unsafe-inline'" in csp
