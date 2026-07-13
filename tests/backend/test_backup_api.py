"""Tests de l'API backup : export/import complet de la base.

Couvre le round-trip export -> import, l'intégrité de la restauration des
tables vides (FIX 1), l'allowlist anti-injection sur les noms de colonnes
(FIX 3) et le chemin de config.yaml résolu à la racine du projet (FIX 2).

Chaque test d'import repart d'un export réel du client (déjà authentifié),
puis ne modifie que la table ciblée dans le `data.json` avant de le
réimporter : les autres tables (dont `users`/`sessions`) restent identiques
à elles-mêmes, ce qui évite de casser la session utilisée par le test.
"""
import io
import json
import sqlite3
import zipfile
from pathlib import Path


def _seed_categories(db_path, names):
    conn = sqlite3.connect(str(db_path))
    try:
        for name in names:
            conn.execute("INSERT INTO categories (name) VALUES (?)", (name,))
        conn.commit()
    finally:
        conn.close()


def _fetch_category_names(db_path):
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute("SELECT name FROM categories ORDER BY name").fetchall()
    finally:
        conn.close()
    return [r[0] for r in rows]


def _export_zip(client):
    r = client.get("/api/backup/export")
    assert r.status_code == 200, r.text
    return zipfile.ZipFile(io.BytesIO(r.content))


def _build_import_zip(metadata_bytes: bytes, data: dict) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("metadata.json", metadata_bytes)
        zf.writestr("data.json", json.dumps(data, ensure_ascii=False))
    return buffer.getvalue()


# --------------------------------------------------------------------------- #
# 1. Round-trip export -> import
# --------------------------------------------------------------------------- #

def test_export_import_round_trip_preserves_data(client_and_db):
    """Un export réimporté tel quel doit restituer exactement les mêmes données."""
    client, db_path = client_and_db
    _seed_categories(db_path, ["Cotisations", "Subventions"])

    zf = _export_zip(client)
    metadata_bytes = zf.read("metadata.json")
    data = json.loads(zf.read("data.json"))
    assert sorted(row["name"] for row in data["categories"]) == ["Cotisations", "Subventions"]

    zip_bytes = _build_import_zip(metadata_bytes, data)
    r = client.post(
        "/api/backup/import",
        files={"file": ("backup.zip", zip_bytes, "application/zip")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    # Verrouille le message de succès accentué (régression : accents manquants).
    assert body["message"] == "Sauvegarde importée avec succès"

    assert _fetch_category_names(db_path) == ["Cotisations", "Subventions"]


# --------------------------------------------------------------------------- #
# 2. FIX 1 : intégrité - une table vide dans le backup doit vider la table
# --------------------------------------------------------------------------- #

def test_import_empties_table_that_is_empty_in_backup(client_and_db):
    """Si le backup importé contient une table vide, la table cible doit être
    intégralement vidée après import : aucune ligne fantôme ne doit survivre
    (l'ancien bug retournait avant le DELETE FROM quand `rows` était vide)."""
    client, db_path = client_and_db
    _seed_categories(db_path, ["A supprimer 1", "A supprimer 2"])

    zf = _export_zip(client)
    metadata_bytes = zf.read("metadata.json")
    data = json.loads(zf.read("data.json"))
    assert len(data["categories"]) == 2  # bien peuplé avant le test d'import

    data["categories"] = []  # simule un backup où la table était vide côté source
    zip_bytes = _build_import_zip(metadata_bytes, data)

    r = client.post(
        "/api/backup/import",
        files={"file": ("backup.zip", zip_bytes, "application/zip")},
    )
    assert r.status_code == 200, r.text

    assert _fetch_category_names(db_path) == []


# --------------------------------------------------------------------------- #
# 3. FIX 3 : anti-injection - noms de colonnes du JSON importé sous allowlist
# --------------------------------------------------------------------------- #

def test_import_ignores_unknown_column_names_no_sql_error(client_and_db):
    """Une clé de colonne forgée dans le JSON importé (tentative d'injection
    par nom d'identifiant SQL) ne doit ni lever d'erreur SQL non maîtrisée, ni
    être exécutée : elle est simplement ignorée grâce à l'allowlist basée sur
    PRAGMA table_info."""
    client, db_path = client_and_db
    _seed_categories(db_path, ["Ancienne"])

    zf = _export_zip(client)
    metadata_bytes = zf.read("metadata.json")
    data = json.loads(zf.read("data.json"))

    data["categories"] = [
        {"id) VALUES (1);--": "malicious", "name": "OK"},
    ]
    zip_bytes = _build_import_zip(metadata_bytes, data)

    r = client.post(
        "/api/backup/import",
        files={"file": ("backup.zip", zip_bytes, "application/zip")},
    )
    assert r.status_code == 200, r.text  # pas de 500 : la colonne inconnue est juste ignorée

    conn = sqlite3.connect(str(db_path))
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(categories)").fetchall()}
        rows = conn.execute("SELECT name FROM categories").fetchall()
    finally:
        conn.close()

    # Aucune colonne parasite n'a été ajoutée au schéma de la table.
    assert cols == {"id", "name", "parent_id", "color", "icon", "position"}
    # Seule la colonne valide ("name") a été prise en compte pour la ligne importée.
    assert [r[0] for r in rows] == ["OK"]


# --------------------------------------------------------------------------- #
# 4. FIX 2 : chemin de config.yaml résolu à la racine du projet
# --------------------------------------------------------------------------- #

def test_config_path_source_uses_four_levels_up():
    """Les deux calculs du chemin de config.yaml dans backup/api.py doivent
    remonter 4 niveaux depuis le fichier (racine du projet), pas 3
    (`backend/config.yaml`, symptôme de l'ancien bug fantôme)."""
    project_root = Path(__file__).resolve().parent.parent.parent
    backup_api_source = (
        project_root / "backend" / "modules" / "backup" / "api.py"
    ).read_text(encoding="utf-8")

    assert backup_api_source.count("parent.parent.parent.parent") == 2
    assert "dirname(os.path.dirname(os.path.dirname(__file__" not in backup_api_source


def test_config_path_resolves_to_actual_project_root():
    """La formule utilisée dans backup/api.py, appliquée à l'emplacement réel
    du module, doit désigner la racine du dépôt et non `backend/`. Ce test ne
    lit ni n'écrit le vrai config.yaml, il ne calcule qu'un chemin."""
    from backend.modules.backup import api as backup_api

    module_file = Path(backup_api.__file__).resolve()
    resolved = module_file.parent.parent.parent.parent / "config.yaml"

    project_root = Path(__file__).resolve().parent.parent.parent
    assert resolved == project_root / "config.yaml"
    assert resolved.parent.name != "backend"


# --------------------------------------------------------------------------- #
# 5. CRITICAL : garde anti-verrouillage - un import sans utilisateurs est refusé
# --------------------------------------------------------------------------- #

def _fetch_user_count(db_path):
    conn = sqlite3.connect(str(db_path))
    try:
        return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    finally:
        conn.close()


def test_import_with_empty_users_list_is_rejected_and_does_not_wipe_users(client_and_db):
    """Un backup dont data.json contient "users": [] doit être refusé (400) :
    l'accepter viderait la table `users` (restauration complète) et
    verrouillerait tout le monde hors de l'application. La table `users` doit
    rester intacte après l'appel (régression CRITICAL corrigée)."""
    client, db_path = client_and_db
    users_before = _fetch_user_count(db_path)
    assert users_before >= 1  # l'admin de la fixture existe déjà

    zf = _export_zip(client)
    metadata_bytes = zf.read("metadata.json")
    data = json.loads(zf.read("data.json"))
    assert len(data["users"]) >= 1  # l'export contient bien l'utilisateur admin

    data["users"] = []  # simule un backup partiel où la table users était vide
    zip_bytes = _build_import_zip(metadata_bytes, data)

    r = client.post(
        "/api/backup/import",
        files={"file": ("backup.zip", zip_bytes, "application/zip")},
    )
    assert r.status_code == 400, r.text

    users_after = _fetch_user_count(db_path)
    assert users_after == users_before  # table users non vidée


def test_import_without_users_key_is_rejected_and_does_not_wipe_users(client_and_db):
    """Un data.json qui omet carrément la clé "users" (format d'une autre
    version, JSON édité à la main) doit aussi être refusé, pas seulement le cas
    d'une liste vide explicite."""
    client, db_path = client_and_db
    users_before = _fetch_user_count(db_path)
    assert users_before >= 1

    zf = _export_zip(client)
    metadata_bytes = zf.read("metadata.json")
    data = json.loads(zf.read("data.json"))
    del data["users"]
    zip_bytes = _build_import_zip(metadata_bytes, data)

    r = client.post(
        "/api/backup/import",
        files={"file": ("backup.zip", zip_bytes, "application/zip")},
    )
    assert r.status_code == 400, r.text

    users_after = _fetch_user_count(db_path)
    assert users_after == users_before
