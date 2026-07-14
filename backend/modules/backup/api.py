"""Backup API module for OpenFlow — export/import full database as ZIP."""
import io
import json
import os
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile, HTTPException
from fastapi.responses import StreamingResponse

from backend.core.auth import require_admin
from backend.core.database import backup_database, get_conn, row_to_dict

router = APIRouter(dependencies=[Depends(require_admin)])

# Tables système (état des modules/config/dashboard, dont le suivi des migrations).
SYSTEM_TABLES = ("_dashboard", "_config", "_modules")

# Limite de taille d'un import (anti-OOM).
MAX_IMPORT_BYTES = 200 * 1024 * 1024  # 200 Mo


def _existing_tables(conn) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {r[0] for r in rows}


def _data_tables(conn) -> list[str]:
    """Toutes les tables de données utilisateur, découvertes dynamiquement.

    On exclut les tables internes SQLite (`sqlite_%`) et les tables système
    OpenFlow (`_%`). Cette découverte dynamique évite que le backup oublie des
    tables ajoutées par de nouveaux modules (cause de pertes de données quand la
    liste était figée). PRAGMA foreign_keys étant OFF, l'ordre n'importe pas.
    """
    rows = conn.execute(
        r"SELECT name FROM sqlite_master WHERE type='table' "
        r"AND name NOT LIKE 'sqlite\_%' ESCAPE '\' "
        r"AND name NOT LIKE '\_%' ESCAPE '\' "
        "ORDER BY name"
    ).fetchall()
    return [r[0] for r in rows]


def _export_table(conn, table_name, existing: set[str]):
    if table_name not in existing:
        return []
    rows = conn.execute(f"SELECT * FROM {table_name}").fetchall()
    return [row_to_dict(r) for r in rows]


def _restore_table(conn, table_name: str, rows: list[dict], existing: set[str]):
    """Vide la table puis ré-insère depuis les dicts. Saute les tables absentes.

    - Toujours vider la table si elle existe (même si `rows` est vide), pour que
      la restauration soit réellement complète (« replacing all existing data »).
    - Les noms de colonnes du fichier importé sont validés contre les colonnes
      réelles de la table (allowlist via PRAGMA table_info) pour empêcher toute
      injection SQL par identifiant, et quotés en identifiants SQLite.
    """
    if table_name not in existing:
        return
    conn.execute(f"DELETE FROM {table_name}")
    if not rows:
        return
    valid_cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}
    columns = [c for c in rows[0].keys() if c in valid_cols]
    if not columns:
        return
    col_names = ", ".join(f'"{c}"' for c in columns)
    placeholders = ", ".join(["?"] * len(columns))
    for row in rows:
        values = [row.get(c) for c in columns]
        conn.execute(f'INSERT INTO {table_name} ({col_names}) VALUES ({placeholders})', values)



@router.get("/export")
def export_backup():
    """Generate a ZIP backup of the entire database + config."""
    conn = get_conn()
    try:
        existing = _existing_tables(conn)
        data = {}
        counts = {}
        for table in _data_tables(conn):
            rows = _export_table(conn, table, existing)
            data[table] = rows
            if rows:
                counts[table] = len(rows)
        for sys_table in SYSTEM_TABLES:
            data[sys_table] = _export_table(conn, sys_table, existing)
    finally:
        conn.close()

    # Read config.yaml
    config_path = Path(__file__).parent.parent.parent.parent / "config.yaml"
    config_content = ""
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            config_content = f.read()

    # Build metadata
    metadata = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "openflow_version": "1.0.0",
        "tables": counts,
        "total_records": sum(counts.values()),
    }

    # Create ZIP in memory
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("metadata.json", json.dumps(metadata, ensure_ascii=False, indent=2))
        zf.writestr("config.yaml", config_content)
        zf.writestr("data.json", json.dumps(data, ensure_ascii=False, indent=2))

    buffer.seek(0)
    filename = f"openflow-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip"

    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/preview")
def preview_backup():
    """Return metadata about what would be exported (for UI display)."""
    conn = get_conn()
    try:
        counts = {}
        for table in _data_tables(conn):
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            if count > 0:
                counts[table] = count
    finally:
        conn.close()

    return {
        "tables": counts,
        "total_records": sum(counts.values()),
    }


@router.post("/import")
async def import_backup(file: UploadFile = File(...)):
    """Import a ZIP backup, replacing all existing data."""
    content = await file.read()
    if len(content) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=413, detail="Fichier trop volumineux (limite 200 Mo)")

    # Validate ZIP
    try:
        zf = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Le fichier n'est pas un ZIP valide")

    required = {"metadata.json", "data.json"}
    if not required.issubset(set(zf.namelist())):
        raise HTTPException(status_code=400, detail="ZIP invalide : metadata.json et data.json requis")

    metadata = json.loads(zf.read("metadata.json"))
    data = json.loads(zf.read("data.json"))

    # Garde anti-verrouillage : un import qui ne contient pas d'utilisateurs
    # viderait la table `users` (restauration complète) et verrouillerait tout
    # le monde hors de l'application. Un export légitime contient toujours les
    # utilisateurs ; on refuse donc un backup partiel ou malformé plutôt que de
    # supprimer silencieusement les comptes.
    guard_conn = get_conn()
    try:
        guard_tables = _existing_tables(guard_conn)
        if "users" in guard_tables:
            current_users = guard_conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            if current_users > 0 and not data.get("users"):
                raise HTTPException(
                    status_code=400,
                    detail="Sauvegarde invalide : aucun utilisateur dans le fichier importé. "
                           "Import refusé pour ne pas verrouiller l'accès à l'application.",
                )
    finally:
        guard_conn.close()

    # Backup current DB before overwriting
    from backend.core.database import get_db_path
    db_path = str(get_db_path())
    backup_path = db_path + f".backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    if os.path.exists(db_path):
        # Snapshot cohérent sous WAL (les pages du -wal sont incluses).
        backup_database(db_path, backup_path)

    # Restore config.yaml if present
    if "config.yaml" in zf.namelist():
        config_content = zf.read("config.yaml").decode("utf-8")
        config_path = Path(__file__).parent.parent.parent.parent / "config.yaml"
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(config_content)

    # Restore data
    conn = get_conn()
    try:
        existing = _existing_tables(conn)
        for table in _data_tables(conn):
            _restore_table(conn, table, data.get(table, []), existing)
        for sys_table in SYSTEM_TABLES:
            _restore_table(conn, sys_table, data.get(sys_table, []), existing)
        conn.commit()
    except Exception as e:
        conn.rollback()
        # Rollback : restaure le snapshot dans la vraie base via l'API backup
        # (pas de copie brute qui laisserait des sidecars -wal/-shm en décalage).
        if os.path.exists(backup_path):
            backup_database(backup_path, db_path)
        raise HTTPException(status_code=500, detail=f"Erreur lors de la restauration : {str(e)}")
    finally:
        conn.close()

    imported_counts = {t: len(rows) for t, rows in data.items() if rows and not t.startswith("_")}

    return {
        "success": True,
        "message": "Sauvegarde importée avec succès",
        "backup_created": backup_path,
        "imported": imported_counts,
        "total_records": sum(imported_counts.values()),
        "metadata": metadata,
    }
