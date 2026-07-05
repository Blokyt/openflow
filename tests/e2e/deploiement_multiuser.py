#!/usr/bin/env python3
"""E2E de déploiement multi-utilisateurs : le workflow complet sur serveur réel.

Valide bout en bout, sur un vrai uvicorn (base scratch, port 8792), l'ensemble
du chantier multi-utilisateurs (phases 1 + 2 + 3) tel qu'un déploiement LAN
d'école l'exercerait :

  1. Bootstrap admin (create_admin) et connexion.
  2. Construction de l'arbre d'entités par l'admin.
  3. Invitation d'un trésorier scopé sur un sous-club, acceptation, connexion.
  4. Périmètre du trésorier : il ne voit que son sous-arbre, 403 ailleurs,
     mutations non-admin refusées.
  5. Soumission d'une dépense avec justificatif PDF (magic bytes), refus d'un
     faux PDF, refus de soumettre hors de son périmètre.
  6. Validation par l'admin : la vraie transaction est créée, le justificatif
     re-lié ; le trésorier n'accède pas à la file de validation.
  7. Solde : une soumission en attente ne bouge aucun solde, l'approbation si.
  8. Rôle viewer (transparence) : lecture seule, pas de soumission.
  9. Durcissement : anonyme refusé, verrouillage du login, CSP, WAL, ops
     réservées à l'admin.

Usage : python tests/e2e/deploiement_multiuser.py
Non collecté par pytest (pas de préfixe test_). Durée : environ 10 s.
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

PORT = 8792
BASE = f"http://127.0.0.1:{PORT}"
ADMIN_EMAIL = "tresorier.bda@e2e.local"
ADMIN_PASSWORD = "MotDePasseAdmin!42"
TREASURER_PASSWORD = "MotDePasseTreso!42"
VIEWER_PASSWORD = "MotDePasseViewer!42"

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
    print(f"  {status} {label}" + (f"  {detail}" if detail and not condition else ""))


def build_scratch_db(db_path: Path) -> None:
    """Base vierge migrée + un unique admin (comme create_admin en production)."""
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
        "VALUES (?, 'Admin BDA', ?, 1, 1, ?)",
        (ADMIN_EMAIL, hash_password(ADMIN_PASSWORD), now))
    conn.commit()
    conn.close()


def run_checks(db_path: Path) -> None:
    admin = httpx.Client(base_url=BASE, timeout=15)
    treasurer = httpx.Client(base_url=BASE, timeout=15)
    viewer = httpx.Client(base_url=BASE, timeout=15)
    try:
        # [1] Bootstrap admin et connexion
        print("\n[1] Bootstrap admin et connexion")
        r = admin.post("/api/users/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        check("connexion admin -> 200", r.status_code == 200, f"(reçu {r.status_code})")
        me = admin.get("/api/users/me")
        check("l'admin est bien administrateur", me.status_code == 200 and me.json().get("is_admin") == 1)

        # [2] L'admin construit l'arbre d'entités
        print("\n[2] Arbre d'entités (BDA -> Gastronomine, CCMP ; Fournisseur externe)")
        r = admin.post("/api/entities/", json={"name": "BDA", "type": "internal"})
        check("création BDA (racine) -> 201", r.status_code == 201, f"(reçu {r.status_code})")
        bda = r.json()["id"]
        r = admin.post("/api/entities/", json={"name": "Gastronomine", "type": "internal", "parent_id": bda})
        check("création Gastronomine (sous-club) -> 201", r.status_code == 201, f"(reçu {r.status_code})")
        gastro = r.json()["id"]
        r = admin.post("/api/entities/", json={"name": "CCMP", "type": "internal", "parent_id": bda})
        check("création CCMP (autre sous-club) -> 201", r.status_code == 201, f"(reçu {r.status_code})")
        ccmp = r.json()["id"]
        r = admin.post("/api/entities/", json={"name": "Fournisseur Traiteur", "type": "external"})
        check("création Fournisseur (externe) -> 201", r.status_code == 201, f"(reçu {r.status_code})")
        fournisseur = r.json()["id"]

        # [3] Invitation d'un trésorier scopé sur Gastronomine
        print("\n[3] Invitation du trésorier de Gastronomine")
        r = admin.post("/api/users/invitations", json={
            "email": "tresorier.gastro@e2e.local", "is_admin": False,
            "roles": [{"entity_id": gastro, "role": "treasurer"}],
        })
        check("création de l'invitation -> 201", r.status_code == 201, f"(reçu {r.status_code})")
        token = r.json().get("token", "")
        check("l'invitation renvoie un token", bool(token))
        r = treasurer.post("/api/users/invitations/accept", json={
            "token": token, "display_name": "Trésorier Gastro", "password": TREASURER_PASSWORD,
        })
        check("acceptation de l'invitation -> 200", r.status_code == 200, f"(reçu {r.status_code})")
        me = treasurer.get("/api/users/me")
        me_data = me.json() if me.status_code == 200 else {}
        check("le trésorier n'est pas admin", me_data.get("is_admin") == 0)
        check("le trésorier a le rôle treasurer sur Gastronomine",
              any(role.get("entity_id") == gastro and role.get("role") == "treasurer"
                  for role in me_data.get("roles", [])))

        # [4] Périmètre du trésorier
        print("\n[4] Périmètre du trésorier (scoping)")
        r = treasurer.get("/api/entities/tree")
        tree_ids = _collect_ids(r.json()) if r.status_code == 200 else set()
        check("le trésorier voit Gastronomine dans son arbre", gastro in tree_ids)
        check("le trésorier NE voit PAS CCMP (hors périmètre)", ccmp not in tree_ids)
        r = treasurer.get(f"/api/entities/{gastro}/balance")
        check("solde de Gastronomine accessible -> 200", r.status_code == 200, f"(reçu {r.status_code})")
        r = treasurer.get(f"/api/entities/{ccmp}/balance")
        check("solde de CCMP refusé -> 403", r.status_code == 403, f"(reçu {r.status_code})")
        r = treasurer.post("/api/categories/", json={"name": "Catégorie interdite", "type": "expense"})
        check("mutation non-admin (créer une catégorie) refusée -> 403",
              r.status_code == 403, f"(reçu {r.status_code})")

        # [5] Soumission d'une dépense avec justificatif
        print("\n[5] Soumission d'une dépense (250,00 EUR) avec justificatif")
        amount = 25000  # centimes
        r = treasurer.post("/api/submissions/", json={
            "date": "2026-07-06", "label": "Achat gâteaux gala", "amount": amount,
            "entity_id": gastro, "counterparty_entity_id": fournisseur, "direction": "expense",
        })
        check("soumission créée -> 201", r.status_code == 201, f"(reçu {r.status_code})")
        submission = r.json().get("id")
        r = treasurer.post("/api/submissions/", json={
            "date": "2026-07-06", "label": "Dépense hors périmètre", "amount": 1000,
            "entity_id": ccmp, "counterparty_entity_id": fournisseur, "direction": "expense",
        })
        check("soumission sur CCMP (hors périmètre) refusée -> 403", r.status_code == 403, f"(reçu {r.status_code})")
        r = treasurer.post(f"/api/attachments/submission/{submission}",
                           files={"file": ("facture.pdf", b"pas un vrai pdf", "application/pdf")})
        check("faux PDF refusé -> 400", r.status_code == 400, f"(reçu {r.status_code})")
        r = treasurer.post(f"/api/attachments/submission/{submission}",
                           files={"file": ("facture.pdf", MINIMAL_PDF, "application/pdf")})
        check("vrai justificatif PDF accepté -> 201", r.status_code == 201, f"(reçu {r.status_code})")
        r = treasurer.get("/api/submissions/mine")
        check("le trésorier suit sa soumission en attente",
              r.status_code == 200 and any(s.get("id") == submission and s.get("status") == "pending"
                                           for s in r.json()))

        # [6] et [7] Solde inchangé tant que la soumission est en attente
        print("\n[6] Solde inchangé tant que la soumission est en attente")
        r = admin.get(f"/api/entities/{gastro}/balance")
        check("solde de Gastronomine = 0 avant validation (soumission n'affecte rien)",
              r.status_code == 200 and r.json().get("balance") == 0,
              f"(reçu {r.json().get('balance') if r.status_code == 200 else r.status_code})")

        # [7] Validation par l'admin
        print("\n[7] Validation par l'admin")
        r = treasurer.get("/api/submissions/")
        check("le trésorier n'accède PAS à la file de validation -> 403", r.status_code == 403, f"(reçu {r.status_code})")
        r = admin.get("/api/submissions/?status=pending")
        check("l'admin voit la soumission en attente",
              r.status_code == 200 and any(s.get("id") == submission for s in r.json()))
        r = admin.post(f"/api/submissions/{submission}/approve")
        check("approbation -> 200", r.status_code == 200, f"(reçu {r.status_code})")
        tx_id = r.json().get("transaction_id")
        check("une vraie transaction est créée à l'approbation", isinstance(tx_id, int))
        r = admin.get(f"/api/attachments/transaction/{tx_id}")
        check("le justificatif est re-lié à la transaction",
              r.status_code == 200 and len(r.json()) == 1)

        # Solde après approbation : la dépense sort de Gastronomine
        print("\n[7b] Solde après approbation (la dépense a bougé le solde)")
        r = admin.get(f"/api/entities/{gastro}/balance")
        check("solde de Gastronomine = -250,00 EUR après validation",
              r.status_code == 200 and r.json().get("balance") == -amount,
              f"(reçu {r.json().get('balance') if r.status_code == 200 else r.status_code})")

        # [8] Rôle viewer (transparence, lecture seule sur le sous-arbre BDA)
        print("\n[8] Rôle viewer (transparence sur BDA, lecture seule)")
        r = admin.post("/api/users/invitations", json={
            "email": "membre.transparence@e2e.local", "is_admin": False,
            "roles": [{"entity_id": bda, "role": "viewer"}],
        })
        check("invitation du viewer -> 201", r.status_code == 201, f"(reçu {r.status_code})")
        token_v = r.json().get("token", "")
        r = viewer.post("/api/users/invitations/accept", json={
            "token": token_v, "display_name": "Membre Transparence", "password": VIEWER_PASSWORD,
        })
        check("acceptation viewer -> 200", r.status_code == 200, f"(reçu {r.status_code})")
        r = viewer.get(f"/api/entities/{gastro}/balance")
        check("le viewer (rôle sur BDA) voit le solde du sous-club Gastronomine -> 200",
              r.status_code == 200, f"(reçu {r.status_code})")
        r = viewer.post("/api/submissions/", json={
            "date": "2026-07-06", "label": "Le viewer ne peut pas soumettre", "amount": 500,
            "entity_id": gastro, "counterparty_entity_id": fournisseur, "direction": "expense",
        })
        check("le viewer ne peut PAS soumettre (pas trésorier) -> 403", r.status_code == 403, f"(reçu {r.status_code})")
        r = viewer.get("/api/config")
        vcfg = r.json() if r.status_code == 200 else {}
        check("le viewer NE voit PAS le chemin de sauvegarde (external_backup redacté)",
              "external_backup" not in vcfg and "server" not in vcfg)
        r = admin.get("/api/config")
        acfg = r.json() if r.status_code == 200 else {}
        check("l'admin voit bien server et external_backup dans /api/config",
              "external_backup" in acfg and "server" in acfg)

        # [9] Durcissement (phase 3) sur le déploiement réel
        print("\n[9] Durcissement : deny-by-default, verrouillage, headers, ops admin")
        anon = httpx.Client(base_url=BASE, timeout=15)
        try:
            r = anon.get("/api/transactions/")
            check("anonyme refusé sur une lecture -> 401", r.status_code == 401, f"(reçu {r.status_code})")
            victim = "cible.brute@e2e.local"
            for _ in range(5):
                anon.post("/api/users/login", json={"email": victim, "password": "faux"})
            r = anon.post("/api/users/login", json={"email": victim, "password": "faux"})
            check("verrouillage du login après 5 échecs -> 429", r.status_code == 429, f"(reçu {r.status_code})")
            check("en-tête Retry-After présent", "retry-after" in {k.lower() for k in r.headers})
        finally:
            anon.close()
        r = admin.get("/api/modules")
        check("CSP présent", "content-security-policy" in r.headers)
        check("pas de HSTS en HTTP", "strict-transport-security" not in r.headers)
        r = treasurer.get("/api/backup/export")
        check("export de sauvegarde refusé au trésorier -> 403", r.status_code == 403, f"(reçu {r.status_code})")
        r = admin.get("/api/backup/export")
        check("export de sauvegarde autorisé à l'admin -> 200", r.status_code == 200, f"(reçu {r.status_code})")
        conn = sqlite3.connect(str(db_path))
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        conn.close()
        check("base SQLite en WAL", mode.lower() == "wal", f"(reçu {mode})")
    finally:
        admin.close()
        treasurer.close()
        viewer.close()


def _collect_ids(nodes) -> set:
    """Aplatit récursivement un arbre d'entités en un ensemble d'id."""
    ids = set()
    for n in nodes or []:
        ids.add(n.get("id"))
        ids |= _collect_ids(n.get("children"))
    return ids


def main():
    scratch = Path(tempfile.mkdtemp(prefix="openflow-e2e-multiuser-"))
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
        run_checks(db_path)
    finally:
        if server is not None:
            server.should_exit = True
        if thread is not None and thread.is_alive():
            thread.join(timeout=5)
        shutil.rmtree(scratch, ignore_errors=True)
    total = checks["ok"] + checks["ko"]
    print(f"\nE2E déploiement multi-utilisateurs : {checks['ok']}/{total} vérifications OK")
    sys.exit(1 if checks["ko"] else 0)


if __name__ == "__main__":
    main()
