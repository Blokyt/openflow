"""Tests des corrections de l'audit (robustesse, fidélité, intégrité).

Couvre les nouveaux comportements introduits par le nettoyage :
- cascade de suppression des catégories + détection de cycle ;
- validation des régularisations (entité interne) ;
- montant de remboursement strictement positif ;
- comblement des mois manquants dans la série temporelle du dashboard ;
- export de sauvegarde dynamique (toutes les tables, dont budget) ;
- snapshot d'import cohérent sous WAL (API backup SQLite, pas copie brute) ;
- cascade de suppression d'un exercice fiscal.
"""
import io
import json
import sqlite3
import zipfile


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _entity(client, name, entity_type):
    r = client.post("/api/entities/", json={"name": name, "type": entity_type})
    assert r.status_code == 201, r.text
    return r.json()


def _category(client, name, parent_id=None):
    payload = {"name": name}
    if parent_id is not None:
        payload["parent_id"] = parent_id
    r = client.post("/api/categories/", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _fiscal_year(client, name, start):
    r = client.post("/api/budget/fiscal-years", json={"name": name, "start_date": start, "notes": ""})
    assert r.status_code == 201, r.text
    return r.json()


def _tx(client, *, date, amount, from_id, to_id, category_id=None):
    payload = {"date": date, "label": "tx", "amount": amount,
               "from_entity_id": from_id, "to_entity_id": to_id}
    if category_id is not None:
        payload["category_id"] = category_id
    r = client.post("/api/transactions/", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


# --------------------------------------------------------------------------- #
# Cascade & cycle des catégories
# --------------------------------------------------------------------------- #

def test_delete_category_cascade(client):
    """Supprimer une catégorie parente : enfants rattachés à la racine et
    transactions dé-catégorisées (pas d'orphelins)."""
    ext = _entity(client, "Externe", "external")
    bda = _entity(client, "BDA", "internal")
    parent = _category(client, "Parent")
    child = _category(client, "Enfant", parent_id=parent["id"])
    tx = _tx(client, date="2025-03-01", amount=1000,
             from_id=ext["id"], to_id=bda["id"], category_id=parent["id"])

    r = client.delete(f"/api/categories/{parent['id']}")
    assert r.status_code == 200, r.text

    cats = {c["id"]: c for c in client.get("/api/categories/").json()}
    assert parent["id"] not in cats          # parent supprimé
    assert cats[child["id"]]["parent_id"] is None  # enfant rattaché à la racine

    got = client.get(f"/api/transactions/{tx['id']}").json()
    assert got["category_id"] is None        # transaction dé-catégorisée


def test_update_category_cycle_rejected(client):
    """Faire d'un descendant le parent crée un cycle -> 400 (anti boucle infinie)."""
    a = _category(client, "A")
    b = _category(client, "B", parent_id=a["id"])
    r = client.put(f"/api/categories/{a['id']}", json={"parent_id": b["id"]})
    assert r.status_code == 400, r.text


def test_update_category_self_parent_rejected(client):
    a = _category(client, "A")
    r = client.put(f"/api/categories/{a['id']}", json={"parent_id": a["id"]})
    assert r.status_code == 400, r.text


# --------------------------------------------------------------------------- #
# Régularisations : entité interne obligatoire
# --------------------------------------------------------------------------- #

def test_accrual_external_entity_rejected(client):
    ext = _entity(client, "Fournisseur", "external")
    fy = _fiscal_year(client, "2025", "2025-01-01")
    r = client.post("/api/reports/accruals", json={
        "fiscal_year_id": fy["id"], "kind": "creance", "amount": 5000,
        "label": "X", "entity_id": ext["id"],
    })
    assert r.status_code == 400, r.text


def test_accrual_internal_entity_ok(client):
    bda = _entity(client, "BDA", "internal")
    fy = _fiscal_year(client, "2025", "2025-01-01")
    r = client.post("/api/reports/accruals", json={
        "fiscal_year_id": fy["id"], "kind": "creance", "amount": 5000,
        "label": "X", "entity_id": bda["id"],
    })
    assert r.status_code == 201, r.text


# --------------------------------------------------------------------------- #
# Remboursements : montant strictement positif
# --------------------------------------------------------------------------- #

def test_reimbursement_amount_must_be_positive(client):
    for bad in (0, -100):
        r = client.post("/api/reimbursements/", json={"person_name": "X", "amount": bad})
        assert r.status_code == 400, f"amount={bad} devrait être rejeté"


# --------------------------------------------------------------------------- #
# Série temporelle : pas de trou de mois
# --------------------------------------------------------------------------- #

def test_timeseries_has_no_month_gaps(client):
    """Deux transactions à plusieurs mois d'écart -> la série reste continue
    (les mois sans flux sont comblés, pas sautés)."""
    ext = _entity(client, "Externe", "external")
    bda = _entity(client, "BDA", "internal")
    _tx(client, date="2026-01-15", amount=1000, from_id=ext["id"], to_id=bda["id"])
    _tx(client, date="2026-04-15", amount=2000, from_id=ext["id"], to_id=bda["id"])

    series = client.get("/api/dashboard/timeseries").json()
    assert len(series) >= 2
    months = [s["month"] for s in series]
    # Mois strictement consécutifs (différence de 1 mois entre points voisins).
    ords = [int(m[:4]) * 12 + int(m[5:7]) for m in months]
    assert all(b - a == 1 for a, b in zip(ords, ords[1:])), months
    # Les mois intermédiaires sans transaction (février, mars) sont présents.
    assert "2026-02" in months and "2026-03" in months


# --------------------------------------------------------------------------- #
# Sauvegarde : export dynamique de toutes les tables de données
# --------------------------------------------------------------------------- #

def test_backup_export_includes_budget_tables(client):
    """L'export dynamique embarque les tables de tous les modules (ex. budget),
    pas seulement une liste figée (sinon perte de données à la restauration)."""
    _fiscal_year(client, "2025", "2025-01-01")
    r = client.get("/api/backup/export")
    assert r.status_code == 200, r.text
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        data = json.loads(zf.read("data.json"))
    assert "fiscal_years" in data
    assert any(row.get("name") == "2025" for row in data["fiscal_years"])


# --------------------------------------------------------------------------- #
# Sauvegarde : snapshot d'import cohérent sous WAL
# --------------------------------------------------------------------------- #

def test_import_snapshot_coherent_sous_wal(client_and_db):
    """Le snapshot de sécurité pris avant un import doit inclure les données
    encore dans le journal WAL (API backup SQLite, pas une copie brute du .db).

    Un lecteur avec transaction ouverte AVANT l'écriture empêche le checkpoint
    de fusionner le WAL dans le fichier .db (comme des requêtes concurrentes en
    production) : une copie brute du fichier raterait alors la donnée."""
    client, db_path = client_and_db

    # Lecteur ouvert avant l'écriture : bloque l'avancée du checkpoint.
    reader = sqlite3.connect(str(db_path))
    try:
        reader.execute("BEGIN")
        reader.execute("SELECT COUNT(*) FROM entities").fetchone()

        # Donnée écrite via l'API juste avant l'import (reste dans le -wal).
        ext = _entity(client, "Fournisseur WAL", "external")

        # Import valide : on réimporte un export complet de l'état courant. Il
        # inclut les utilisateurs, requis par la garde anti-verrouillage de
        # l'import (un backup sans utilisateurs est refusé en 400 pour ne pas
        # verrouiller l'accès). Le test ne vérifie de toute façon que la
        # cohérence du snapshot pris AVANT la restauration.
        exp = client.get("/api/backup/export")
        assert exp.status_code == 200, exp.text
        r = client.post(
            "/api/backup/import",
            files={"file": ("b.zip", exp.content, "application/zip")},
        )
        assert r.status_code == 200, r.text
        backup_path = r.json()["backup_created"]
    finally:
        reader.rollback()
        reader.close()

    # Le snapshot est une base SQLite valide contenant la donnée pré-import.
    snap = sqlite3.connect(backup_path)
    try:
        row = snap.execute(
            "SELECT name FROM entities WHERE id = ?", (ext["id"],)
        ).fetchone()
    finally:
        snap.close()
    assert row is not None and row[0] == "Fournisseur WAL"


# --------------------------------------------------------------------------- #
# Sauvegarde pre-migration : coherente sous WAL (tools/migrate.py)
# --------------------------------------------------------------------------- #

def test_migrate_backup_coherent_sous_wal(client_and_db):
    """La sauvegarde de securite prise par tools/migrate.py avant chaque
    migration doit inclure les donnees encore dans le journal WAL.

    Avant correctif, `tools/migrate.py` faisait une copie brute
    (shutil.copy2) du seul fichier .db : sous WAL, les transactions commitees
    mais pas encore checkpointees dans le -wal etaient silencieusement
    omises. C'est le meme risque que le snapshot d'import corrige plus haut
    (test_import_snapshot_coherent_sous_wal) ; ce test verifie que
    `backend.core.database.backup_database`, desormais utilisee par
    migrate.py, s'en sort correctement.

    Un lecteur avec transaction ouverte AVANT l'ecriture empeche le
    checkpoint de fusionner le WAL dans le fichier .db (comme des requetes
    concurrentes en production, ou le serveur qui tourne encore pendant
    qu'un /repair lance migrate.py en sous-processus)."""
    from backend.core.database import backup_database

    client, db_path = client_and_db

    # Lecteur ouvert avant l'écriture : bloque l'avancée du checkpoint.
    reader = sqlite3.connect(str(db_path))
    try:
        reader.execute("BEGIN")
        reader.execute("SELECT COUNT(*) FROM entities").fetchone()

        # Donnée écrite via l'API juste avant le backup (reste dans le -wal).
        ext = _entity(client, "Fournisseur WAL Migrate", "external")

        backup_path = db_path.parent / "openflow.db.backup.test"
        backup_database(db_path, backup_path)
    finally:
        reader.rollback()
        reader.close()

    # La copie est une base SQLite valide et intègre, contenant la donnée
    # pré-backup (celle qui n'était encore que dans le -wal).
    snap = sqlite3.connect(str(backup_path))
    try:
        row = snap.execute(
            "SELECT name FROM entities WHERE id = ?", (ext["id"],)
        ).fetchone()
        integrity = snap.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        snap.close()
    assert row is not None and row[0] == "Fournisseur WAL Migrate"
    assert integrity == "ok"


# --------------------------------------------------------------------------- #
# Cascade de suppression d'un exercice fiscal
# --------------------------------------------------------------------------- #

def test_delete_fiscal_year_cascades_accruals(client):
    bda = _entity(client, "BDA", "internal")
    fy = _fiscal_year(client, "2025", "2025-01-01")
    client.post("/api/reports/accruals", json={
        "fiscal_year_id": fy["id"], "kind": "creance", "amount": 5000,
        "label": "X", "entity_id": bda["id"],
    })
    r = client.delete(f"/api/budget/fiscal-years/{fy['id']}")
    assert r.status_code == 200, r.text
    items = client.get("/api/reports/accruals", params={"fiscal_year_id": fy["id"]}).json()
    assert items == []
