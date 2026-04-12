#!/usr/bin/env python3
"""Apply versioned database migrations for all OpenFlow modules."""
import argparse
import importlib.util
import json
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


def version_tuple(version_str):
    """Convert '1.2.3' to (1, 2, 3) for sorting."""
    return tuple(int(x) for x in version_str.split("."))


def load_migrations(models_py_path):
    """Dynamically load the migrations dict from a module's models.py."""
    spec = importlib.util.spec_from_file_location("_models_tmp", str(models_py_path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, "migrations", {})


def ensure_system_tables(conn):
    """Create system tables if they don't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS _modules (
            id TEXT PRIMARY KEY,
            installed_version TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS _config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS _dashboard (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            widget_id TEXT NOT NULL,
            module_id TEXT NOT NULL,
            visible INTEGER NOT NULL DEFAULT 1,
            position INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.commit()


def get_installed_version(conn, module_id):
    """Get the currently installed version of a module, or None if not installed."""
    cur = conn.execute(
        "SELECT installed_version FROM _modules WHERE id = ?", (module_id,)
    )
    row = cur.fetchone()
    return row[0] if row else None


def set_installed_version(conn, module_id, version):
    """Insert or update the installed version of a module."""
    now = datetime.utcnow().isoformat()
    conn.execute(
        """
        INSERT INTO _modules (id, installed_version, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            installed_version = excluded.installed_version,
            updated_at = excluded.updated_at
        """,
        (module_id, version, now),
    )
    conn.commit()


def apply_migrations(conn, module_id, migrations, installed_version, target_version):
    """Apply any pending migrations for a module."""
    installed_tuple = version_tuple(installed_version) if installed_version else (0, 0, 0)
    target_tuple = version_tuple(target_version)

    # Sort migrations by version
    pending = [
        (ver, sqls)
        for ver, sqls in migrations.items()
        if version_tuple(ver) > installed_tuple
    ]
    pending.sort(key=lambda x: version_tuple(x[0]))

    if not pending:
        print(f"  Module '{module_id}': already at version {target_version}, nothing to do.")
        return

    for version, sql_statements in pending:
        print(f"  Module '{module_id}': applying migration {version}...")
        for sql in sql_statements:
            sql = sql.strip()
            if not sql:
                continue
            try:
                conn.execute(sql)
            except sqlite3.OperationalError as e:
                if "already exists" in str(e):
                    print(f"    Skipping (already exists): {sql[:60]}...")
                else:
                    raise
        conn.commit()

    set_installed_version(conn, module_id, target_version)
    print(f"  Module '{module_id}': migrated to version {target_version}.")


def main():
    parser = argparse.ArgumentParser(description="Apply OpenFlow database migrations")
    parser.add_argument(
        "--project-dir",
        default=str(Path(__file__).parent.parent),
        help="Path to the OpenFlow project root",
    )
    args = parser.parse_args()

    project = Path(args.project_dir)
    data_dir = project / "data"
    db_path = data_dir / "openflow.db"
    modules_dir = project / "backend" / "modules"

    # Step 1: Ensure data/ directory exists
    data_dir.mkdir(parents=True, exist_ok=True)

    # Step 2: Back up existing DB
    if db_path.exists():
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        backup_path = data_dir / f"openflow.db.backup.{timestamp}"
        shutil.copy2(str(db_path), str(backup_path))
        print(f"Backup created: {backup_path.name}")

    # Step 3: Connect and create system tables
    conn = sqlite3.connect(str(db_path))
    try:
        ensure_system_tables(conn)

        # Step 4: Process each module
        if not modules_dir.exists():
            print("No backend/modules directory found. Nothing to migrate.")
            return

        for mod_dir in sorted(modules_dir.iterdir()):
            if not mod_dir.is_dir():
                continue

            manifest_path = mod_dir / "manifest.json"
            models_path = mod_dir / "models.py"

            if not manifest_path.exists():
                print(f"  Skipping '{mod_dir.name}': no manifest.json")
                continue

            with open(manifest_path, encoding="utf-8") as f:
                try:
                    manifest = json.load(f)
                except json.JSONDecodeError as e:
                    print(f"  Skipping '{mod_dir.name}': invalid manifest.json ({e})")
                    continue

            module_id = manifest.get("id", mod_dir.name)
            target_version = manifest.get("version", "1.0.0")

            if not models_path.exists():
                print(f"  Module '{module_id}': no models.py, skipping migrations.")
                continue

            try:
                migrations = load_migrations(models_path)
            except Exception as e:
                print(f"  Module '{module_id}': failed to load models.py: {e}", file=sys.stderr)
                continue

            installed_version = get_installed_version(conn, module_id)
            apply_migrations(conn, module_id, migrations, installed_version, target_version)

    finally:
        conn.close()

    print("\nMigration complete.")


if __name__ == "__main__":
    main()
