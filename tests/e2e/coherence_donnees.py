#!/usr/bin/env python3
"""E2E de cohérence des données : les chiffres affichés se recoupent partout.

Seed un jeu de données réaliste (arbre d'entités, catégories, transactions,
exercice budgétaire avec allocation) sur un vrai uvicorn (port 8793), puis
vérifie que chaque endpoint qui alimente l'UI renvoie des chiffres cohérents
ENTRE EUX :

  - solde propre et solde consolidé (arbre) exacts ;
  - dashboard (chiffres des cartes + données des graphes) exacts ;
  - top-catégories (graphe de répartition) exact ;
  - série temporelle (graphe d'évolution) finit sur le solde courant ;
  - budget : réalisé et alloué concordent avec les transactions et le dashboard ;
  - rapports (compte de résultat, bilan) accessibles et structurés.

Données seedées (montants en centimes) :
  BDA (racine) -> Gastronomine, CCMP.  Donateur, Fournisseur (externes).
  Catégories : Dons, Alimentation, Materiel.
  Donateur -> Gastronomine : +100000 (Dons)
  Gastronomine -> Fournisseur : -30000 (Alimentation), -20000 (Materiel)
  Donateur -> CCMP : +50000 (Dons)
  CCMP -> Fournisseur : -15000 (Alimentation)
  => Gastro propre = +50000 ; CCMP propre = +35000 ; BDA consolidé = +85000
  => recettes = 150000 ; dépenses = 65000 ; 5 transactions.

Usage : python tests/e2e/coherence_donnees.py  (non collecté par pytest).
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

PORT = 8793
BASE = f"http://127.0.0.1:{PORT}"
ADMIN_EMAIL = "admin@coherence.local"
ADMIN_PASSWORD = "MotDePasseCoherence!42"
TX_DATE = "2026-03-15"

checks = {"ok": 0, "ko": 0}
ids = {}


def check(label, condition, detail=""):
    status = "OK " if condition else "KO "
    checks["ok" if condition else "ko"] += 1
    print(f"  {status} {label}" + (f"  {detail}" if detail and not condition else ""))


def _entity(conn, now, name, type_, parent_id=None, is_default=0):
    cur = conn.execute(
        "INSERT INTO entities (name, description, type, parent_id, is_default, is_divers, color, position, created_at, updated_at) "
        "VALUES (?, '', ?, ?, ?, 0, '#6B7280', 0, ?, ?)",
        (name, type_, parent_id, is_default, now, now))
    return cur.lastrowid


def _category(conn, name):
    cur = conn.execute("INSERT INTO categories (name, color, icon, position) VALUES (?, '#6B7280', 'tag', 0)", (name,))
    return cur.lastrowid


def _tx(conn, now, label, amount, cat, from_id, to_id):
    conn.execute(
        "INSERT INTO transactions (date, label, description, amount, category_id, contact_id, created_by, "
        "from_entity_id, to_entity_id, created_at, updated_at) "
        "VALUES (?, ?, '', ?, ?, NULL, '', ?, ?, ?, ?)",
        (TX_DATE, label, amount, cat, from_id, to_id, now, now))


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
        "VALUES (?, 'Admin Coherence', ?, 1, 1, ?)",
        (ADMIN_EMAIL, hash_password(ADMIN_PASSWORD), now))

    bda = _entity(conn, now, "BDA", "internal", None, is_default=1)
    gastro = _entity(conn, now, "Gastronomine", "internal", bda)
    ccmp = _entity(conn, now, "CCMP", "internal", bda)
    donateur = _entity(conn, now, "Donateur", "external")
    fournisseur = _entity(conn, now, "Fournisseur", "external")
    dons = _category(conn, "Dons")
    alim = _category(conn, "Alimentation")
    materiel = _category(conn, "Materiel")

    _tx(conn, now, "Don au club gastro", 100000, dons, donateur, gastro)
    _tx(conn, now, "Achat nourriture", 30000, alim, gastro, fournisseur)
    _tx(conn, now, "Achat materiel cuisine", 20000, materiel, gastro, fournisseur)
    _tx(conn, now, "Don au CCMP", 50000, dons, donateur, ccmp)
    _tx(conn, now, "Achat boissons CCMP", 15000, alim, ccmp, fournisseur)

    conn.commit()
    conn.close()
    ids.update(bda=bda, gastro=gastro, ccmp=ccmp, donateur=donateur,
               fournisseur=fournisseur, dons=dons, alim=alim, materiel=materiel)


def run_checks() -> None:
    c = httpx.Client(base_url=BASE, timeout=15)
    try:
        r = c.post("/api/users/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        check("connexion admin -> 200", r.status_code == 200, f"(reçu {r.status_code})")

        # [1] Soldes propres et consolidés (base de tous les chiffres)
        print("\n[1] Soldes des entités (source de vérité)")
        rg = c.get(f"/api/entities/{ids['gastro']}/balance").json()
        check("solde propre Gastronomine = +50000", rg.get("balance") == 50000, f"(reçu {rg.get('balance')})")
        rc = c.get(f"/api/entities/{ids['ccmp']}/balance").json()
        check("solde propre CCMP = +35000", rc.get("balance") == 35000, f"(reçu {rc.get('balance')})")
        rb = c.get(f"/api/entities/{ids['bda']}/consolidated").json()
        check("solde consolidé BDA = propre + enfants = +85000",
              rb.get("consolidated_balance") == 85000, f"(reçu {rb.get('consolidated_balance')})")
        check("consolidé BDA = own + somme enfants (cohérence de l'arbre)",
              rb.get("consolidated_balance") == rb.get("own_balance", 0) + 50000 + 35000,
              f"(own={rb.get('own_balance')})")

        # [2] Dashboard : cartes chiffrées
        print("\n[2] Dashboard : cartes (toutes entités)")
        s = c.get("/api/dashboard/summary").json()
        check("solde global dashboard = consolidé racine = 85000", s.get("balance") == 85000, f"(reçu {s.get('balance')})")
        check("recettes totales = 150000", s.get("total_income") == 150000, f"(reçu {s.get('total_income')})")
        check("dépenses totales = 65000", s.get("total_expenses") == 65000, f"(reçu {s.get('total_expenses')})")
        check("nombre de transactions = 5", s.get("transaction_count") == 5, f"(reçu {s.get('transaction_count')})")
        # Recette - dépense = variation nette, cohérente avec les soldes (pas de solde d'ouverture ici)
        check("recettes - dépenses = solde global (aucun solde de référence)",
              s.get("total_income", 0) - s.get("total_expenses", 0) == s.get("balance"),
              f"(150000-65000 vs {s.get('balance')})")

        # [3] Graphe de répartition : top-catégories (dépenses)
        print("\n[3] Graphe top-catégories (dépenses)")
        tc = c.get("/api/dashboard/top-categories").json()
        by_name = {row["name"]: row["total"] for row in tc}
        check("Alimentation = 30000 + 15000 = 45000", by_name.get("Alimentation") == 45000, f"(reçu {by_name.get('Alimentation')})")
        check("Materiel = 20000", by_name.get("Materiel") == 20000, f"(reçu {by_name.get('Materiel')})")
        check("total du graphe = dépenses du dashboard (65000)",
              sum(by_name.values()) == 65000, f"(reçu {sum(by_name.values())})")
        check("les catégories sont triées par montant décroissant",
              [row["total"] for row in tc] == sorted((row["total"] for row in tc), reverse=True))
        check("Dons (recette) n'apparaît PAS dans les dépenses", "Dons" not in by_name)

        # [4] Graphe d'évolution : la série temporelle finit sur le solde courant
        print("\n[4] Graphe d'évolution (série temporelle)")
        ts = c.get("/api/dashboard/timeseries").json()
        check("la série n'est pas vide", isinstance(ts, list) and len(ts) > 0)
        if ts:
            check("le dernier point de la courbe = solde courant (85000)",
                  ts[-1].get("balance") == 85000, f"(reçu {ts[-1].get('balance')})")
            check("les mois sont ordonnés chronologiquement",
                  [p["month"] for p in ts] == sorted(p["month"] for p in ts))

        # [5] Dashboard scopé sur un sous-club (cohérence du périmètre)
        print("\n[5] Dashboard scopé sur Gastronomine")
        sg = c.get(f"/api/dashboard/summary?entity_id={ids['gastro']}").json()
        check("solde Gastronomine dans le dashboard = 50000", sg.get("balance") == 50000, f"(reçu {sg.get('balance')})")
        check("recettes Gastronomine = 100000", sg.get("total_income") == 100000, f"(reçu {sg.get('total_income')})")
        check("dépenses Gastronomine = 50000", sg.get("total_expenses") == 50000, f"(reçu {sg.get('total_expenses')})")

        # [6] Budget : réalisé et alloué concordent avec les transactions ET le dashboard
        print("\n[6] Budget : exercice, allocation, réalisé")
        r = c.post("/api/budget/fiscal-years", json={"name": "Exercice 2026", "start_date": "2026-01-01"})
        check("création de l'exercice -> 201", r.status_code == 201, f"(reçu {r.status_code})")
        fy = r.json().get("id")
        r = c.post(f"/api/budget/fiscal-years/{fy}/allocations", json={
            "entity_id": ids["gastro"], "category_id": ids["alim"], "direction": "expense", "amount": 40000,
        })
        check("création d'une allocation (Gastro/Alimentation = 40000) -> 201", r.status_code == 201, f"(reçu {r.status_code})")
        view = c.get(f"/api/budget/view?fiscal_year_id={fy}").json()
        ent_by_id = {e["entity_id"]: e for e in view.get("entities", [])}
        g = ent_by_id.get(ids["gastro"], {})
        check("budget : réalisé dépenses Gastronomine = 50000 (concorde avec les transactions)",
              g.get("realized_expense") == 50000, f"(reçu {g.get('realized_expense')})")
        check("budget : réalisé recettes Gastronomine = 100000",
              g.get("realized_income") == 100000, f"(reçu {g.get('realized_income')})")
        check("budget : alloué dépenses Gastronomine = 40000", g.get("allocated_expense") == 40000, f"(reçu {g.get('allocated_expense')})")
        totals = view.get("totals", {})
        check("budget : total réalisé dépenses = dépenses du dashboard (65000)",
              totals.get("realized_expense") == 65000, f"(reçu {totals.get('realized_expense')})")
        check("budget : total réalisé recettes = recettes du dashboard (150000)",
              totals.get("realized_income") == 150000, f"(reçu {totals.get('realized_income')})")

        # [7] Rapports comptables accessibles et structurés
        print("\n[7] Rapports comptables")
        r = c.get(f"/api/reports/compte-resultat?fiscal_year_id={fy}")
        check("compte de résultat accessible -> 200", r.status_code == 200, f"(reçu {r.status_code})")
        r = c.get(f"/api/reports/bilan?fiscal_year_id={fy}")
        check("bilan accessible -> 200", r.status_code == 200, f"(reçu {r.status_code})")

        # [8] Endpoints de liste et remboursements (pas de plantage, structure cohérente)
        print("\n[8] Listes et remboursements")
        r = c.get("/api/transactions/")
        body = r.json()
        # La liste est paginée : {"total": N, "items": [...]}.
        total = body.get("total") if isinstance(body, dict) else None
        rows = body.get("items", []) if isinstance(body, dict) else []
        check("liste des transactions -> 200 avec 5 lignes (total et items cohérents)",
              r.status_code == 200 and total == 5 and len(rows) == 5,
              f"(reçu {r.status_code}, total={total}, items={len(rows)})")
        r = c.get("/api/reimbursements/summary")
        check("résumé des remboursements accessible -> 200", r.status_code == 200, f"(reçu {r.status_code})")
        r = c.get("/api/dashboard/recent")
        check("transactions récentes (dashboard) -> 200", r.status_code == 200, f"(reçu {r.status_code})")
    finally:
        c.close()


def main():
    scratch = Path(tempfile.mkdtemp(prefix="openflow-e2e-coherence-"))
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
        run_checks()
    finally:
        if server is not None:
            server.should_exit = True
        if thread is not None and thread.is_alive():
            thread.join(timeout=5)
        shutil.rmtree(scratch, ignore_errors=True)
    total = checks["ok"] + checks["ko"]
    print(f"\nE2E cohérence des données : {checks['ok']}/{total} vérifications OK")
    sys.exit(1 if checks["ko"] else 0)


if __name__ == "__main__":
    main()
