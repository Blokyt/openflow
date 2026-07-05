"""OpenFlow FastAPI application."""
import importlib
from dataclasses import asdict
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest

from backend.core.auth import require_session
from backend.core.config import load_config, save_config
from backend.core.database import init_db_pragmas, set_db_path
from backend.core.module_loader import discover_modules, filter_active
from backend.core.rate_limit import limiter


def safe_static_file(build_dir: Path, path: str) -> Path | None:
    """Renvoie le chemin du fichier demandé s'il existe ET reste confiné dans
    build_dir. Renvoie None sinon (anti path traversal sur le SPA fallback)."""
    try:
        base = build_dir.resolve()
        target = (build_dir / path).resolve()
    except (ValueError, OSError):
        return None
    if target.is_file() and target.is_relative_to(base):
        return target
    return None



def _migrate_reimbursement_contacts(db_path: Path):
    """Auto-create contacts from existing reimbursement person_names and populate contact_id."""
    import sqlite3
    from datetime import datetime, timezone

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        # Check if contact_id column exists
        cols = [row[1] for row in conn.execute("PRAGMA table_info(reimbursements)").fetchall()]
        if "contact_id" not in cols:
            return

        # Find reimbursements with person_name but no contact_id
        rows = conn.execute(
            "SELECT DISTINCT person_name FROM reimbursements WHERE contact_id IS NULL AND person_name != ''"
        ).fetchall()
        if not rows:
            return

        now = datetime.now(timezone.utc).isoformat()
        migrated = 0
        for row in rows:
            name = row[0]
            # Check if contact already exists (case-insensitive)
            existing = conn.execute(
                "SELECT id FROM contacts WHERE LOWER(name) = LOWER(?)", (name,)
            ).fetchone()
            if existing:
                contact_id = existing[0]
            else:
                conn.execute(
                    "INSERT INTO contacts (name, type, email, phone, address, notes, created_at, updated_at) VALUES (?, 'membre', '', '', '', '', ?, ?)",
                    (name, now, now),
                )
                contact_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            # Update reimbursements
            conn.execute(
                "UPDATE reimbursements SET contact_id = ? WHERE person_name = ? AND contact_id IS NULL",
                (contact_id, name),
            )
            migrated += 1
        conn.commit()
        if migrated:
            print(f"  Migrated {migrated} reimbursement person_name(s) to contacts.")
    except Exception as e:
        print(f"  Reimbursement contact migration skipped: {e}")
    finally:
        conn.close()


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Injecte des headers de sécurité HTTP sur chaque réponse."""

    async def dispatch(self, request: StarletteRequest, call_next):
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        # CSP adaptée au SPA servi par FastAPI : tout vient de la même origine.
        # 'unsafe-inline' UNIQUEMENT pour les styles (attributs style= de React
        # et Recharts) ; les scripts restent strictement same-origin.
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            "font-src 'self' data:; "
            "connect-src 'self'; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "form-action 'self'; "
            "frame-ancestors 'none'"
        )
        # Pas de HSTS tant qu'on est en HTTP local — à ajouter quand HTTPS sera en place
        return response


def create_app(config_path: str = "config.yaml", db_path: str = "data/openflow.db", bootstrap: bool = True) -> FastAPI:
    app = FastAPI(title="OpenFlow", version="0.1.0", dependencies=[Depends(require_session)])

    # Item A — Rate limiting
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    project_root = Path(__file__).parent.parent
    config_file = project_root / config_path
    config = load_config(str(config_file))

    # Auto-activate tiers if reimbursements is active (they are tightly coupled)
    if config.modules.get("reimbursements", False) and not config.modules.get("tiers", False):
        config.modules["tiers"] = True
        save_config(config, str(config_file))
        print("  Auto-activated 'tiers' module (required by reimbursements).")

    # SecurityHeadersMiddleware ajouté en dernier = plus externe dans la chaîne Starlette
    # (dernier add_middleware = premier middleware traversé à l'entrée de la requête)
    app.add_middleware(SecurityHeadersMiddleware)

    modules_dir = project_root / "backend" / "modules"
    all_modules = discover_modules(str(modules_dir))
    active_modules = filter_active(all_modules, config.modules)

    set_db_path(project_root / db_path)
    init_db_pragmas()

    for manifest in active_modules:
        module_id = manifest["id"]
        for route_file in manifest.get("api_routes", []):
            route_path = modules_dir / module_id / route_file
            if route_path.exists():
                module_name = f"backend.modules.{module_id}.{route_file.replace('.py', '')}"
                try:
                    mod = importlib.import_module(module_name)
                    if hasattr(mod, "router"):
                        app.include_router(mod.router, prefix=f"/api/{module_id}", tags=[manifest["name"]])
                except Exception as e:
                    print(f"Warning: failed to load routes for {module_id}: {e}")

    # Migrate existing person_names to contacts
    if bootstrap and config.modules.get("reimbursements", False):
        _migrate_reimbursement_contacts(project_root / db_path)

    @app.get("/api/modules")
    def get_modules():
        return filter_active(all_modules, config.modules)

    @app.get("/api/modules/all")
    def get_all_modules():
        return all_modules

    @app.get("/api/config")
    def get_config():
        return asdict(config)

    @app.put("/api/config/entity")
    def update_entity(entity: dict):
        for key, value in entity.items():
            if hasattr(config.entity, key):
                setattr(config.entity, key, value)
        save_config(config, str(config_file))
        return asdict(config.entity)

    @app.put("/api/config/modules/{module_id}")
    def toggle_module(module_id: str, active: bool):
        if module_id not in config.modules:
            raise HTTPException(404, f"Module '{module_id}' not found")
        if module_id == "users" and not active:
            raise HTTPException(400, "Le module users ne peut pas être désactivé (verrouillage de l'accès)")
        if active:
            module_manifest = next((m for m in all_modules if m["id"] == module_id), None)
            if module_manifest:
                for dep in module_manifest.get("dependencies", []):
                    if not config.modules.get(dep, False):
                        raise HTTPException(400, f"Cannot activate '{module_id}': dependency '{dep}' is not active")
        config.modules[module_id] = active
        save_config(config, str(config_file))
        return {"module_id": module_id, "active": active}

    @app.put("/api/config/balance")
    def update_balance(balance: dict):
        if "date" in balance:
            config.balance.date = balance["date"]
        if "amount" in balance:
            config.balance.amount = balance["amount"]
        save_config(config, str(config_file))
        return asdict(config.balance)

    build_dir = project_root / "frontend" / "dist"
    if build_dir.exists():
        # Serve static assets (JS, CSS, images)
        app.mount("/assets", StaticFiles(directory=str(build_dir / "assets")), name="assets")

        # SPA fallback: any non-API route serves index.html.
        # Le chemin est confiné à build_dir via safe_static_file (anti path traversal).
        @app.get("/{path:path}")
        async def spa_fallback(path: str):
            target = safe_static_file(build_dir, path)
            if target is not None:
                return FileResponse(str(target))
            return FileResponse(str(build_dir / "index.html"))

    return app
