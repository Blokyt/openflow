"""Backup API module for OpenFlow — export/import full database as ZIP."""
import io
import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import StreamingResponse

from backend.core.database import get_conn, row_to_dict

router = APIRouter()

# Tables to export (order matters for restore — parents before children)
EXPORT_TABLES = [
    "entities",
    "entity_balance_refs",
    "categories",
    "contacts",
    "divisions",
    "transactions",
    "budgets",
    "recurring_transactions",
    "reimbursements",
    "invoices",
    "invoice_lines",
    "attachments",
    "bank_statements",
    "alert_rules",
    "tax_receipts",
    "grants",
    "accounts",
    "transfers",
    "audit_log",
    "annotations",
    "users",
    "sessions",
    "user_entities",
]


def _existing_tables(conn) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {r[0] for r in rows}


def _export_table(conn, table_name, existing: set[str]):
    if table_name not in existing:
        return []
    rows = conn.execute(f"SELECT * FROM {table_name}").fetchall()
    return [row_to_dict(r) for r in rows]


def _restore_table(conn, table_name: str, rows: list[dict], existing: set[str]):
    """Delete all rows from table and re-insert from dicts. Skips missing tables."""
    if not rows or table_name not in existing:
        return
    conn.execute(f"DELETE FROM {table_name}")
    columns = list(rows[0].keys())
    placeholders = ", ".join(["?"] * len(columns))
    col_names = ", ".join(columns)
    for row in rows:
        values = [row.get(c) for c in columns]
        conn.execute(f"INSERT INTO {table_name} ({col_names}) VALUES ({placeholders})", values)


@router.get("/export")
def export_backup():
    """Generate a ZIP backup of the entire database + config."""
    conn = get_conn()
    try:
        existing = _existing_tables(conn)
        data = {}
        counts = {}
        for table in EXPORT_TABLES:
            rows = _export_table(conn, table, existing)
            data[table] = rows
            if rows:
                counts[table] = len(rows)
        for sys_table in ("_dashboard", "_config", "_modules"):
            data[sys_table] = _export_table(conn, sys_table, existing)
    finally:
        conn.close()

    # Read config.yaml
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config.yaml")
    config_content = ""
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            config_content = f.read()

    # Build metadata
    metadata = {
        "exported_at": datetime.now().isoformat(),
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
        existing = _existing_tables(conn)
        counts = {}
        for table in EXPORT_TABLES:
            if table in existing:
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

    # Validate ZIP
    try:
        zf = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Le fichier n'est pas un ZIP valide")

    required = {"metadata.json", "data.json"}
    if not required.issubset(set(zf.namelist())):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="ZIP invalide : metadata.json et data.json requis")

    metadata = json.loads(zf.read("metadata.json"))
    data = json.loads(zf.read("data.json"))

    # Backup current DB before overwriting
    from backend.core.database import get_db_path
    db_path = str(get_db_path())
    backup_path = db_path + f".backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    if os.path.exists(db_path):
        shutil.copy2(db_path, backup_path)

    # Restore config.yaml if present
    if "config.yaml" in zf.namelist():
        config_content = zf.read("config.yaml").decode("utf-8")
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config.yaml")
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(config_content)

    # Restore data
    conn = get_conn()
    try:
        existing = _existing_tables(conn)
        for table in EXPORT_TABLES:
            _restore_table(conn, table, data.get(table, []), existing)
        for sys_table in ("_dashboard", "_config", "_modules"):
            _restore_table(conn, sys_table, data.get(sys_table, []), existing)
        conn.commit()
    except Exception as e:
        conn.rollback()
        # Restore backup
        if os.path.exists(backup_path):
            shutil.copy2(backup_path, db_path)
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=f"Erreur lors de la restauration : {str(e)}")
    finally:
        conn.close()

    imported_counts = {t: len(rows) for t, rows in data.items() if rows and t in EXPORT_TABLES}

    return {
        "success": True,
        "message": "Sauvegarde importee avec succes",
        "backup_created": backup_path,
        "imported": imported_counts,
        "total_records": sum(imported_counts.values()),
        "metadata": metadata,
    }
