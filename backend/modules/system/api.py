"""System API — status, maintenance, repair.

Endpoints:
  GET  /status           Disk usage, temp files, backups, DB health
  GET  /backups          List of auto-backups with sizes
  DELETE /backups/{name} Delete a specific backup
  GET  /settings         Current system settings (max_backups, temp_max_age)
  PUT  /settings         Update system settings
  POST /cleanup          Remove old temp files + prune backups above limit
  POST /repair           Restore code from pristine snapshot + re-apply config
  GET  /pristine/status  Compare current files vs pristine snapshot
"""
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.core.auth import require_admin
from backend.core.database import get_db_path

router = APIRouter(dependencies=[Depends(require_admin)])

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
# ATTACHMENTS_DIR reste fixe sur data/attachments du dépôt : c'est là que le
# module attachments (backend/modules/attachments/api.py) stocke toujours ses
# fichiers, quel que soit le db_path configuré pour l'instance.
ATTACHMENTS_DIR = DATA_DIR / "attachments"
PRISTINE_ZIP = PROJECT_ROOT / "install" / "pristine.zip"

DEFAULT_SETTINGS = {
    "max_backups": 5,
    "temp_max_age_hours": 24,
}


# ─── Chemins dérivés du db_path de l'instance (PAS data/ du dépôt) ─────────
#
# Une instance peut être lancée avec un db_path personnalisé (tests, E2E,
# déploiement alternatif). Les sauvegardes automatiques de migrate.py sont
# toujours créées à côté du fichier de base (<nom-db>.backup.<timestamp>) :
# on doit donc dériver ces chemins de get_db_path() à chaque appel plutôt que
# de les figer sur data/ du dépôt au chargement du module.

def _db_dir() -> Path:
    return Path(get_db_path()).parent


def _backup_prefix() -> str:
    return Path(get_db_path()).name + ".backup"


def _settings_file() -> Path:
    return _db_dir() / "system_settings.json"

# Directories considered "code" (restorable from pristine)
CODE_DIRS = ["backend", "frontend/src", "frontend/public", "tools"]
# Files at project root considered "code"
CODE_ROOT_FILES = ["start.py", "setup.py", "requirements.txt", "requirements-dev.txt",
                   "frontend/package.json", "frontend/vite.config.ts", "frontend/tsconfig.json",
                   "frontend/tailwind.config.js", "frontend/postcss.config.js"]


# ─── Settings helpers ───────────────────────────────────────────────────────

def _load_settings():
    settings_file = _settings_file()
    if settings_file.exists():
        try:
            return {**DEFAULT_SETTINGS, **json.loads(settings_file.read_text())}
        except Exception:
            pass
    return dict(DEFAULT_SETTINGS)


def _save_settings(s):
    settings_file = _settings_file()
    settings_file.parent.mkdir(parents=True, exist_ok=True)
    settings_file.write_text(json.dumps(s, indent=2))


def _dir_size(path: Path) -> int:
    """Return total size of a directory in bytes."""
    if not path.exists():
        return 0
    total = 0
    try:
        for p in path.rglob("*"):
            if p.is_file():
                try:
                    total += p.stat().st_size
                except OSError:
                    pass
    except OSError:
        pass
    return total


def _format_bytes(n: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _list_db_backups() -> list[dict]:
    """List auto-backup files from migrate.py (<nom-db>.backup.* pattern)."""
    backups = []
    db_dir = _db_dir()
    if db_dir.exists():
        for p in db_dir.glob(f"{_backup_prefix()}*"):
            try:
                st = p.stat()
                backups.append({
                    "name": p.name,
                    "size": st.st_size,
                    "size_human": _format_bytes(st.st_size),
                    "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(),
                    "age_seconds": time.time() - st.st_mtime,
                })
            except OSError:
                continue
    backups.sort(key=lambda b: -b["age_seconds"])  # oldest first
    return backups



# ─── Endpoints ──────────────────────────────────────────────────────────────

@router.get("/status")
def status():
    """Full system status report."""
    settings = _load_settings()
    db_path = Path(get_db_path())

    backups = _list_db_backups()

    usage = {
        "database": db_path.stat().st_size if db_path.exists() else 0,
        "attachments": _dir_size(ATTACHMENTS_DIR),
        "auto_backups": sum(b["size"] for b in backups),
        "backend_code": _dir_size(PROJECT_ROOT / "backend"),
        "frontend_src": _dir_size(PROJECT_ROOT / "frontend" / "src"),
        "frontend_dist": _dir_size(PROJECT_ROOT / "frontend" / "dist"),
    }
    usage_human = {k: _format_bytes(v) for k, v in usage.items()}
    total_user_data = usage["database"] + usage["attachments"] + usage["auto_backups"]
    total_code = usage["backend_code"] + usage["frontend_src"] + usage["frontend_dist"]

    # DB health
    db_health = {"connected": False, "modules": []}
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        db_health["connected"] = True
        db_health["tables_count"] = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
        ).fetchone()[0]
        db_health["transactions"] = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        db_health["entities"] = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
        db_health["modules"] = [
            {"id": r["id"], "version": r["installed_version"]}
            for r in conn.execute("SELECT id, installed_version FROM _modules ORDER BY id").fetchall()
        ]
        conn.close()
    except Exception as e:
        db_health["error"] = str(e)

    # Pristine snapshot availability
    pristine = {
        "available": PRISTINE_ZIP.exists(),
        "size": PRISTINE_ZIP.stat().st_size if PRISTINE_ZIP.exists() else 0,
        "mtime": datetime.fromtimestamp(PRISTINE_ZIP.stat().st_mtime).isoformat() if PRISTINE_ZIP.exists() else None,
    }

    return {
        "version": "1.0.0",
        "settings": settings,
        "usage": usage,
        "usage_human": usage_human,
        "totals": {
            "user_data": total_user_data,
            "user_data_human": _format_bytes(total_user_data),
            "temp": 0,
            "temp_human": "0 B",
            "code": total_code,
            "code_human": _format_bytes(total_code),
        },
        "db": db_health,
        "pristine": pristine,
        "backups": backups,
        "temp_imports": [],
    }


@router.get("/settings")
def get_settings():
    return _load_settings()


class SettingsUpdate(BaseModel):
    max_backups: Optional[int] = None
    temp_max_age_hours: Optional[int] = None


@router.put("/settings")
def update_settings(body: SettingsUpdate):
    s = _load_settings()
    if body.max_backups is not None:
        if body.max_backups < 1:
            raise HTTPException(400, "max_backups must be >= 1")
        s["max_backups"] = body.max_backups
    if body.temp_max_age_hours is not None:
        if body.temp_max_age_hours < 1:
            raise HTTPException(400, "temp_max_age_hours must be >= 1")
        s["temp_max_age_hours"] = body.temp_max_age_hours
    _save_settings(s)
    return s


@router.get("/backups")
def list_backups():
    return _list_db_backups()


@router.delete("/backups/{name}")
def delete_backup(name: str):
    # Anti path traversal : on résout le chemin et on vérifie qu'il reste dans
    # le dossier de la base (celle de l'instance, via get_db_path()) ET que le
    # fichier porte bien le préfixe de backup. Un nom comme
    # "<nom-db>.backup../../config.yaml" passe le startswith mais sort du
    # dossier de la base : is_relative_to le rejette.
    base = _db_dir().resolve()
    path = (_db_dir() / name).resolve()
    if not path.is_relative_to(base) or not path.name.startswith(_backup_prefix()):
        raise HTTPException(400, "Nom de sauvegarde invalide")
    if not path.exists():
        raise HTTPException(404, "Backup not found")
    path.unlink()
    return {"deleted": name}


class CleanupRequest(BaseModel):
    prune_backups: bool = True
    clean_pycache: bool = False


@router.post("/cleanup")
def cleanup(body: CleanupRequest):
    """Clean temp files and prune old backups."""
    settings = _load_settings()
    removed = {"pruned_backups": 0, "pycache_dirs": 0, "total_bytes": 0}

    if body.prune_backups:
        backups = sorted(_list_db_backups(), key=lambda b: b["mtime"], reverse=True)
        to_remove = backups[settings["max_backups"]:]
        for b in to_remove:
            try:
                path = _db_dir() / b["name"]
                removed["total_bytes"] += path.stat().st_size
                path.unlink()
                removed["pruned_backups"] += 1
            except OSError:
                pass

    if body.clean_pycache:
        for p in PROJECT_ROOT.rglob("__pycache__"):
            if p.is_dir():
                try:
                    size = _dir_size(p)
                    shutil.rmtree(p)
                    removed["pycache_dirs"] += 1
                    removed["total_bytes"] += size
                except OSError:
                    pass

    removed["freed_human"] = _format_bytes(removed["total_bytes"])
    return removed


# ─── Pristine / Repair ─────────────────────────────────────────────────────

def _file_hash(path: Path) -> str:
    """SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


_pristine_cache: dict = {"key": None, "result": None}


@router.get("/pristine/status")
def pristine_status():
    """Compare current code files vs pristine snapshot. Cached by ZIP mtime + code dir mtimes."""
    if not PRISTINE_ZIP.exists():
        raise HTTPException(404, "Pristine snapshot introuvable. Cr\u00e9ez-en un d'abord via POST /pristine/create.")

    zip_mtime = PRISTINE_ZIP.stat().st_mtime
    code_mtimes = []
    for d in CODE_DIRS:
        p = PROJECT_ROOT / d
        if p.exists():
            code_mtimes.append(p.stat().st_mtime)
    cache_key = (zip_mtime, tuple(code_mtimes))

    if _pristine_cache["key"] == cache_key and _pristine_cache["result"] is not None:
        return _pristine_cache["result"]

    differences = {"modified": [], "missing": [], "extra": []}

    with zipfile.ZipFile(PRISTINE_ZIP) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            current = PROJECT_ROOT / info.filename
            if not current.exists():
                differences["missing"].append(info.filename)
                continue
            with zf.open(info) as fp:
                pristine_hash = hashlib.sha256(fp.read()).hexdigest()
            try:
                current_hash = _file_hash(current)
            except Exception:
                differences["missing"].append(info.filename)
                continue
            if pristine_hash != current_hash:
                differences["modified"].append(info.filename)

    total_issues = len(differences["modified"]) + len(differences["missing"])
    result = {
        "healthy": total_issues == 0,
        "issues_count": total_issues,
        "differences": differences,
    }
    _pristine_cache["key"] = cache_key
    _pristine_cache["result"] = result
    return result


class PristineCreateRequest(BaseModel):
    overwrite: bool = False


@router.post("/pristine/create")
def pristine_create(body: PristineCreateRequest):
    """Create a pristine snapshot from current code state.

    This should be run ONCE when the app is in a known-good state.
    """
    if PRISTINE_ZIP.exists() and not body.overwrite:
        raise HTTPException(400, "Pristine existe d\u00e9j\u00e0. Utilisez overwrite=true pour le remplacer.")

    PRISTINE_ZIP.parent.mkdir(parents=True, exist_ok=True)
    files_added = 0

    with zipfile.ZipFile(PRISTINE_ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        for code_dir in CODE_DIRS:
            dir_path = PROJECT_ROOT / code_dir
            if not dir_path.exists():
                continue
            for p in dir_path.rglob("*"):
                if not p.is_file():
                    continue
                # Skip caches and build artifacts
                if any(part in ("__pycache__", ".pytest_cache", "node_modules", ".mypy_cache") for part in p.parts):
                    continue
                if p.suffix in (".pyc", ".pyo"):
                    continue
                rel = p.relative_to(PROJECT_ROOT)
                zf.write(p, str(rel).replace("\\", "/"))
                files_added += 1

        for rel_file in CODE_ROOT_FILES:
            p = PROJECT_ROOT / rel_file
            if p.exists() and p.is_file():
                zf.write(p, rel_file.replace("\\", "/"))
                files_added += 1

    return {
        "created": str(PRISTINE_ZIP),
        "size": PRISTINE_ZIP.stat().st_size,
        "size_human": _format_bytes(PRISTINE_ZIP.stat().st_size),
        "files_added": files_added,
    }


class RepairRequest(BaseModel):
    restore_pristine: bool = True
    run_migrations: bool = True
    rebuild_frontend: bool = False
    cleanup_temp: bool = True


@router.post("/repair")
def repair(body: RepairRequest):
    """Repair the app: restore code from pristine + re-apply migrations.

    NEVER touches data/openflow.db (except migrations) or config.yaml.
    """
    if body.restore_pristine and not PRISTINE_ZIP.exists():
        raise HTTPException(404, "Pristine snapshot introuvable. Impossible de r\u00e9parer.")

    report = {
        "steps": [],
        "restored_files": 0,
        "migrations_applied": False,
        "frontend_rebuilt": False,
        "temp_cleaned": 0,
    }

    # Step 1: Restore pristine files
    if body.restore_pristine:
        try:
            with zipfile.ZipFile(PRISTINE_ZIP) as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    # NEVER restore config.yaml or anything in data/
                    if info.filename.startswith("data/") or info.filename == "config.yaml":
                        continue
                    target = (PROJECT_ROOT / info.filename).resolve()
                    if not target.is_relative_to(PROJECT_ROOT.resolve()):
                        # Zip-slip : une entrée qui sortirait de la racine est ignorée.
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(info) as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    report["restored_files"] += 1
            report["steps"].append(f"[OK] {report['restored_files']} fichiers restaur\u00e9s")
        except Exception as e:
            report["steps"].append(f"[ERR] Restauration pristine: {e}")

    # Step 2: Run migrations
    if body.run_migrations:
        try:
            result = subprocess.run(
                [sys.executable, str(PROJECT_ROOT / "tools" / "migrate.py")],
                capture_output=True, text=True, cwd=str(PROJECT_ROOT), timeout=60,
            )
            if result.returncode == 0:
                report["migrations_applied"] = True
                report["steps"].append("[OK] Migrations appliquees")
            else:
                report["steps"].append(f"[ERR] Migrations: {result.stderr[:500]}")
        except Exception as e:
            report["steps"].append(f"[ERR] Migrations: {e}")

    # Step 3: Rebuild frontend (optional, slow)
    if body.rebuild_frontend:
        try:
            result = subprocess.run(
                ["bun", "run", "build"],
                capture_output=True, text=True, cwd=str(PROJECT_ROOT / "frontend"),
                timeout=300, shell=True,
            )
            if result.returncode == 0:
                report["frontend_rebuilt"] = True
                report["steps"].append("[OK] Frontend rebuild")
            else:
                report["steps"].append(f"[ERR] bun build: {result.stderr[:500]}")
        except Exception as e:
            report["steps"].append(f"[ERR] Frontend: {e}")

    if body.cleanup_temp:
        report["temp_cleaned"] = 0

    report["success"] = all("[OK]" in s for s in report["steps"]) or len(report["steps"]) == 0
    return report
