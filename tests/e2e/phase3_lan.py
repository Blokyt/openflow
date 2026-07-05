#!/usr/bin/env python3
"""E2E phase 3 sur serveur réel : verrouillage du login, faux PDF, journal, WAL, CSP.

Lance un uvicorn réel sur une base scratch (port 8791) puis exécute des
requêtes HTTP réelles (httpx). Durée : environ 45 s (attente du déverrouillage).

Usage : python tests/e2e/phase3_lan.py
Non collecté par pytest (pas de préfixe test_).
"""
import json
import shutil
import socket
import sqlite3
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import uvicorn

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.auth import hash_password  # noqa: E402
from backend.main import create_app  # noqa: E402
from tools.migrate import apply_migrations, ensure_system_tables, load_migrations  # noqa: E402

PORT = 8791
BASE = f"http://127.0.0.1:{PORT}"
ADMIN_EMAIL = "admin@e2e.local"
ADMIN_PASSWORD = "MotDePasseE2E!42"

MINIMAL_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\n"
    b"trailer<</Size 3/Root 1 0 R>>\n"
    b"%%EOF\n"
)

checks = {"ok": 0, "ko": 0}


def check(label, condition, detail=""):
    status = "OK " if condition else "KO "
    checks["ok" if condition else "ko"] += 1
    print(f"  {status} {label}" + (f" {detail}" if detail and not condition else ""))


def build_scratch_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    ensure_system_tables(conn)
    modules_dir = PROJECT_ROOT / "backend" / "modules"
    for mod_dir in sorted(modules_dir.iterdir()):
        manifest_path = mod_dir / "manifest.json"
        models_path = mod_dir / "models.py"
        if not mod_dir.is_dir() or not manifest_path.exists() or not models_path.exists():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        apply_migrations(conn, manifest["id"], load_migrations(models_path), None,
                         manifest.get("version", "1.0.0"))
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO users (email, display_name, password_hash, is_admin, is_active, created_at) "
        "VALUES (?, 'Admin E2E', ?, 1, 1, ?)",
        (ADMIN_EMAIL, hash_password(ADMIN_PASSWORD), now))
    conn.execute(
        "INSERT INTO entities (name, type, parent_id, is_default, color, position, created_at, updated_at) "
        "VALUES ('Interne E2E', 'internal', NULL, 1, '#888888', 0, ?, ?)", (now, now))
    conn.execute(
        "INSERT INTO entities (name, type, parent_id, is_default, color, position, created_at, updated_at) "
        "VALUES ('Externe E2E', 'external', NULL, 0, '#888888', 1, ?, ?)", (now, now))
    conn.commit()
    conn.close()


def run_checks(client: httpx.Client, db_path: Path) -> None:
    # [1] Verrouillage progressif (compte inconnu : l'anti-énumération journalise aussi)
    print("\n[1] Verrouillage du login")
    victim = "cible@e2e.local"
    for i in range(5):
        r = client.post("/api/users/login", json={"email": victim, "password": "mauvais"})
        check(f"échec {i + 1} -> 401", r.status_code == 401, f"(reçu {r.status_code})")
    r = client.post("/api/users/login", json={"email": victim, "password": "mauvais"})
    check("6e tentative -> 429 verrouillé", r.status_code == 429, f"(reçu {r.status_code})")
    detail = r.json().get("detail", "") if r.status_code == 429 else ""
    check("message français de verrouillage", "Trop de tentatives" in detail, repr(detail))
    check("en-tête Retry-After", "retry-after" in {k.lower() for k in r.headers})

    # [2] Déverrouillage après le délai de base (30 s)
    print("\n[2] Déverrouillage après délai (attente 31 s)")
    time.sleep(31)
    r = client.post("/api/users/login", json={"email": victim, "password": "mauvais"})
    check("après le délai -> 401 (plus 429)", r.status_code == 401, f"(reçu {r.status_code})")

    # [3] Session admin en HTTP : cookie fonctionnel, sans attribut Secure
    print("\n[3] Session admin en HTTP LAN")
    r = client.post("/api/users/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    check("login admin -> 200", r.status_code == 200, f"(reçu {r.status_code})")
    set_cookie = r.headers.get("set-cookie", "")
    check("cookie HttpOnly", "httponly" in set_cookie.lower())
    check("cookie SANS attribut Secure (HTTP LAN)", "secure" not in set_cookie.lower())
    r = client.get("/api/users/me")
    check("session utilisable -> 200", r.status_code == 200, f"(reçu {r.status_code})")

    # [4] Journal des connexions
    print("\n[4] Journal des connexions")
    r = client.get("/api/users/login-events")
    check("journal admin -> 200", r.status_code == 200, f"(reçu {r.status_code})")
    events = r.json() if r.status_code == 200 else []
    check("échecs journalisés", any(e["email"] == victim and not e["success"] for e in events))
    check("succès journalisé", any(e["email"] == ADMIN_EMAIL and e["success"] for e in events))

    # [5] Uploads : magic bytes sur serveur réel
    print("\n[5] Uploads : magic bytes")
    r = client.post("/api/transactions/", json={
        "date": "2026-07-05", "label": "Transaction E2E", "amount": 1234,
        "from_entity_id": 1, "to_entity_id": 2,
    })
    check("création transaction -> 201", r.status_code == 201, f"(reçu {r.status_code})")
    tx_id = r.json()["id"]
    r = client.post(f"/api/attachments/transaction/{tx_id}",
                    files={"file": ("facture.pdf", b"ceci n'est pas un pdf", "application/pdf")})
    check("faux PDF refusé -> 400", r.status_code == 400, f"(reçu {r.status_code})")
    detail = r.json().get("detail", "") if r.status_code == 400 else ""
    check("message français du refus", "Type de fichier non autorisé" in detail, repr(detail))
    r = client.post(f"/api/attachments/transaction/{tx_id}",
                    files={"file": ("facture.pdf", MINIMAL_PDF, "text/plain")})
    check("vrai PDF accepté malgré un Content-Type menteur -> 201", r.status_code == 201,
          f"(reçu {r.status_code})")
    check("MIME stocké = détecté (application/pdf)",
          r.status_code == 201 and r.json().get("mime_type") == "application/pdf")

    # [6] Headers de sécurité
    print("\n[6] Headers")
    r = client.get("/api/modules")
    check("CSP présent", "content-security-policy" in r.headers)
    check("pas de HSTS en HTTP", "strict-transport-security" not in r.headers)
    check("X-Content-Type-Options", r.headers.get("x-content-type-options") == "nosniff")

    # [7] SQLite en WAL
    print("\n[7] SQLite")
    conn = sqlite3.connect(str(db_path))
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    conn.close()
    check("journal_mode = wal", mode.lower() == "wal", f"(reçu {mode})")


def main():
    # Le dossier scratch et le serveur doivent TOUJOURS être nettoyés, même si le
    # setup échoue (ex : port 8791 déjà occupé). On enveloppe donc tout le setup
    # ET les vérifications dans un seul try/finally.
    scratch = Path(tempfile.mkdtemp(prefix="openflow-e2e-phase3-"))
    server = None
    thread = None
    try:
        db_path = scratch / "e2e.db"
        build_scratch_db(db_path)
        app = create_app(config_path="config.test.yaml", db_path=str(db_path), bootstrap=False)
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning"))
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        for _ in range(50):
            try:
                with socket.create_connection(("127.0.0.1", PORT), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.2)
        else:
            raise RuntimeError("le serveur n'a pas démarré")
        with httpx.Client(base_url=BASE, timeout=15) as client:
            run_checks(client, db_path)
    finally:
        if server is not None:
            server.should_exit = True
        if thread is not None and thread.is_alive():
            thread.join(timeout=5)
        shutil.rmtree(scratch, ignore_errors=True)
    total = checks["ok"] + checks["ko"]
    print(f"\nE2E phase 3 : {checks['ok']}/{total} vérifications OK")
    sys.exit(1 if checks["ko"] else 0)


if __name__ == "__main__":
    main()
