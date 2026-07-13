"""Tests de l'API system : status, backups, settings, cleanup.

Couvre la régression où le module Système pointait en dur sur `data/` du
dépôt au lieu du db_path configuré de l'instance. Une instance lancée avec un
db_path personnalisé (tests, E2E) ne doit voir, lister, compter ni supprimer
que les fichiers situés à côté de SA propre base, jamais ceux de `data/` du
dépôt principal.
"""
import json
import sqlite3
import time
from pathlib import Path


def _make_backup_file(db_path: Path, suffix: str, *, mtime_offset: float = 0.0) -> Path:
    """Crée un fichier <nom-db>.backup.<suffix> à côté de la DB de test."""
    backup = db_path.parent / f"{db_path.name}.backup.{suffix}"
    backup.write_bytes(b"fake-sqlite-backup-content")
    if mtime_offset:
        t = time.time() + mtime_offset
        import os
        os.utime(backup, (t, t))
    return backup


# --------------------------------------------------------------------------- #
# GET /api/system/backups : ne liste que les sauvegardes à côté de la DB de test
# --------------------------------------------------------------------------- #

def test_list_backups_uses_configured_db_dir_not_repo_data(client_and_db):
    client, db_path = client_and_db
    _make_backup_file(db_path, "20260101T000000")
    _make_backup_file(db_path, "20260102T000000")

    r = client.get("/api/system/backups")
    assert r.status_code == 200, r.text
    names = {b["name"] for b in r.json()}
    assert names == {
        f"{db_path.name}.backup.20260101T000000",
        f"{db_path.name}.backup.20260102T000000",
    }
    # Aucune trace d'un nom de sauvegarde de la vraie base du dépôt.
    for b in r.json():
        assert not b["name"].startswith("openflow.db.backup") or db_path.name == "openflow.db"


def test_list_backups_does_not_see_real_repo_backups(client_and_db, tmp_path, monkeypatch):
    """Simule la présence de vraies sauvegardes data/openflow.db.backup.* du
    dépôt (autre dossier) : elles ne doivent jamais apparaître pour une
    instance dont le db_path pointe ailleurs (tmp_path de test)."""
    client, db_path = client_and_db

    # db_path de test est déjà hors du dépôt (tmp_path pytest). On crée en
    # plus un faux "data/" du dépôt à côté pour vérifier qu'il est ignoré.
    fake_repo_data = tmp_path / "fake_repo_data"
    fake_repo_data.mkdir()
    (fake_repo_data / "openflow.db.backup.20250101T000000").write_bytes(b"real-prod-backup")

    _make_backup_file(db_path, "20260101T000000")

    r = client.get("/api/system/backups")
    assert r.status_code == 200, r.text
    names = {b["name"] for b in r.json()}
    assert "openflow.db.backup.20250101T000000" not in names


# --------------------------------------------------------------------------- #
# GET /api/system/status : usage.auto_backups compte les fichiers de l'instance
# --------------------------------------------------------------------------- #

def test_status_auto_backups_usage_matches_test_db_dir(client_and_db):
    client, db_path = client_and_db
    b1 = _make_backup_file(db_path, "20260101T000000")
    b2 = _make_backup_file(db_path, "20260102T000000")
    expected_size = b1.stat().st_size + b2.stat().st_size

    r = client.get("/api/system/status")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["usage"]["auto_backups"] == expected_size
    assert len(body["backups"]) == 2


# --------------------------------------------------------------------------- #
# DELETE /api/system/backups/{name}
# --------------------------------------------------------------------------- #

def test_delete_backup_removes_file_next_to_test_db(client_and_db):
    client, db_path = client_and_db
    backup = _make_backup_file(db_path, "20260101T000000")
    name = backup.name

    r = client.delete(f"/api/system/backups/{name}")
    assert r.status_code == 200, r.text
    assert r.json()["deleted"] == name
    assert not backup.exists()


def test_delete_backup_never_touches_real_repo_data_dir(client_and_db):
    """Une instance de test ne doit JAMAIS pouvoir atteindre data/ du dépôt
    principal via cet endpoint, même avec un nom de fichier existant là-bas."""
    client, db_path = client_and_db
    repo_data_dir = Path(__file__).resolve().parent.parent.parent / "data"
    # On ne suppose pas qu'un vrai fichier existe côté dépôt ; on vérifie
    # simplement que la suppression échoue (400, préfixe invalide) plutôt que
    # de réussir en silence sur un chemin hors du dossier de la DB de test.
    r = client.delete("/api/system/backups/openflow.db.backup.99999999T000000")
    if db_path.name != "openflow.db":
        assert r.status_code in (400, 404)
    real_backup_would_be = repo_data_dir / "openflow.db.backup.99999999T000000"
    assert not real_backup_would_be.exists()


def test_delete_backup_rejects_name_without_backup_prefix(client_and_db):
    client, _ = client_and_db
    r = client.delete("/api/system/backups/autre.txt")
    assert r.status_code == 400, r.text


def test_delete_backup_rejects_path_traversal(client_and_db):
    client, db_path = client_and_db
    traversal_name = f"{db_path.name}.backup.20260101T000000..%2F..%2Fconfig.yaml"
    r = client.delete(f"/api/system/backups/{traversal_name}")
    # Peu importe la mécanique de routage exacte (le "/" décodé peut faire
    # sortir la requête du pattern {name} et produire 404/405 avant même
    # d'atteindre le handler) : ce qui compte est que la suppression
    # n'aboutisse jamais (jamais 200).
    assert r.status_code != 200, r.text


# --------------------------------------------------------------------------- #
# POST /api/system/cleanup : élague les plus vieux fichiers au-delà de max_backups
# --------------------------------------------------------------------------- #

def test_cleanup_prunes_oldest_backups_beyond_max_backups(client_and_db):
    client, db_path = client_and_db

    r = client.put("/api/system/settings", json={"max_backups": 2})
    assert r.status_code == 200, r.text

    # 4 sauvegardes, mtimes échelonnées (la plus ancienne en premier).
    oldest = _make_backup_file(db_path, "20260101T000000", mtime_offset=-400)
    older = _make_backup_file(db_path, "20260102T000000", mtime_offset=-300)
    newer = _make_backup_file(db_path, "20260103T000000", mtime_offset=-200)
    newest = _make_backup_file(db_path, "20260104T000000", mtime_offset=-100)

    r = client.post("/api/system/cleanup", json={"prune_backups": True, "clean_pycache": False})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pruned_backups"] == 2

    assert not oldest.exists()
    assert not older.exists()
    assert newer.exists()
    assert newest.exists()


# --------------------------------------------------------------------------- #
# PUT /api/system/settings : system_settings.json écrit à côté de la DB de test
# --------------------------------------------------------------------------- #

def test_settings_written_next_to_test_db_not_repo_data(client_and_db):
    client, db_path = client_and_db

    repo_data_dir = Path(__file__).resolve().parent.parent.parent / "data"
    repo_settings_file = repo_data_dir / "system_settings.json"
    before = repo_settings_file.read_bytes() if repo_settings_file.exists() else None

    r = client.put("/api/system/settings", json={"max_backups": 7})
    assert r.status_code == 200, r.text
    assert r.json()["max_backups"] == 7

    settings_file = db_path.parent / "system_settings.json"
    assert settings_file.exists()
    written = json.loads(settings_file.read_text())
    assert written["max_backups"] == 7

    # Le fichier du dépôt (data/system_settings.json), s'il existe, ne doit
    # pas avoir été touché par l'écriture faite via l'instance de test.
    after = repo_settings_file.read_bytes() if repo_settings_file.exists() else None
    assert after == before
