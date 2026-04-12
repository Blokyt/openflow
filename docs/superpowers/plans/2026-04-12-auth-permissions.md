# Auth & Permissions — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter login/sessions/permissions scopees par entite a OpenFlow pour un deploiement serveur multi-utilisateurs.

**Architecture:** Sessions SQLite + cookie HTTP-only. Roles (tresorier/lecteur) assignes par entite. Tresorier de la racine = admin. Middleware FastAPI verifie le cookie sur chaque requete API. Frontend avec page login + protection des routes.

**Tech Stack:** Python 3, FastAPI, SQLite, bcrypt, uuid4, React 18

---

### Task 1: Migrer passwords vers bcrypt + ajouter tables sessions/user_entities

**Files:**
- Modify: `backend/modules/multi_users/models.py`
- Modify: `backend/modules/multi_users/manifest.json` (version bump)
- Modify: `requirements.txt` (ajouter bcrypt)
- Modify: `requirements-dev.txt`

- [ ] **Step 1: Ajouter bcrypt a requirements.txt**

Ajouter `bcrypt==4.2.1` a la fin de `requirements.txt`.

- [ ] **Step 2: Ajouter migration v1.1.0 a models.py**

```python
migrations = {
    "1.0.0": [ ... existing ... ],
    "1.1.0": [
        """CREATE TABLE sessions (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )""",
        """CREATE TABLE user_entities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            entity_id INTEGER NOT NULL,
            role TEXT NOT NULL DEFAULT 'lecteur',
            UNIQUE(user_id, entity_id)
        )""",
    ],
}
```

- [ ] **Step 3: Bump manifest version to 1.1.0**

- [ ] **Step 4: Install bcrypt, run migrate, verify**

```bash
pip install bcrypt==4.2.1
python tools/migrate.py
python tools/check.py
```

- [ ] **Step 5: Commit**

```bash
git add requirements.txt backend/modules/multi_users/
git commit -m "feat: add sessions and user_entities tables, bcrypt dependency"
```

---

### Task 2: Refactorer multi_users/api.py — bcrypt + login/logout/me

**Files:**
- Modify: `backend/modules/multi_users/api.py`
- Test: `tests/backend/test_auth.py`

- [ ] **Step 1: Rewrite api.py**

Replace SHA-256 with bcrypt. Add login/logout/me/password endpoints. Keep existing CRUD.

Key changes:
- `_hash_password` → bcrypt.hashpw
- `_verify_password` → bcrypt.checkpw
- `POST /login` → verify credentials, create session UUID, set cookie
- `POST /logout` → delete session from DB, clear cookie
- `GET /me` → read session cookie, return user + entity access list
- `PUT /me/password` → verify old password, hash new, invalidate other sessions
- VALID_ROLES changes from `{admin, treasurer, reader}` to `{tresorier, lecteur}` (role is per-entity now, not global)
- Keep existing CRUD endpoints (list, create, get, update, delete users)
- Add entity assignment endpoints:
  - `GET /{user_id}/entities` — list user's entity access
  - `POST /{user_id}/entities` — assign entity+role `{entity_id, role}`
  - `DELETE /{user_id}/entities/{entity_id}` — remove access

- [ ] **Step 2: Write tests**

`tests/backend/test_auth.py`:
- Login with correct credentials → 200 + cookie set
- Login with wrong password → 401
- Login with nonexistent user → 401
- GET /me with valid session → returns user data
- GET /me without cookie → 401
- Logout → session deleted, subsequent /me → 401
- Change password → old password required, new hash stored
- Change password invalidates other sessions
- Assign entity access to user
- List user entity access
- Remove entity access

- [ ] **Step 3: Run tests**

```bash
python -m pytest tests/backend/test_auth.py -v
```

- [ ] **Step 4: Commit**

```bash
git add backend/modules/multi_users/api.py tests/backend/test_auth.py
git commit -m "feat: login/logout/sessions + bcrypt + entity access management"
```

---

### Task 3: Middleware auth dans main.py

**Files:**
- Create: `backend/core/auth.py`
- Modify: `backend/main.py`
- Test: `tests/backend/test_auth_middleware.py`

- [ ] **Step 1: Create backend/core/auth.py**

```python
"""Authentication middleware and helpers."""
import sqlite3
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from backend.core.database import get_conn

# Paths that don't require auth
PUBLIC_PATHS = {"/api/multi_users/login"}


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        
        # Skip auth for non-API routes (frontend) and public endpoints
        if not path.startswith("/api/") or path in PUBLIC_PATHS:
            return await call_next(request)
        
        session_id = request.cookies.get("session_id")
        if not session_id:
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        conn = get_conn()
        try:
            session = conn.execute(
                "SELECT user_id FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if not session:
                raise HTTPException(status_code=401, detail="Invalid session")
            
            user = conn.execute(
                "SELECT * FROM users WHERE id = ?", (session["user_id"],)
            ).fetchone()
            if not user:
                raise HTTPException(status_code=401, detail="User not found")
            
            # Load user's entity access
            entities = conn.execute(
                "SELECT entity_id, role FROM user_entities WHERE user_id = ?",
                (user["id"],),
            ).fetchall()
            
            request.state.user = dict(user)
            request.state.user_entities = [dict(e) for e in entities]
        finally:
            conn.close()
        
        return await call_next(request)


def get_current_user(request: Request) -> dict:
    """Get the authenticated user from request state."""
    if not hasattr(request.state, "user"):
        raise HTTPException(status_code=401, detail="Not authenticated")
    return request.state.user


def has_entity_access(request: Request, entity_id: int) -> bool:
    """Check if current user has any access to an entity (or its ancestors)."""
    user_entities = getattr(request.state, "user_entities", [])
    accessible_ids = {ue["entity_id"] for ue in user_entities}
    
    # Check direct access
    if entity_id in accessible_ids:
        return True
    
    # Check ancestor access (user with access to BDA can see Gastronomine)
    conn = get_conn()
    try:
        current = entity_id
        while current:
            row = conn.execute("SELECT parent_id FROM entities WHERE id = ?", (current,)).fetchone()
            if not row:
                break
            parent = row["parent_id"]
            if parent in accessible_ids:
                return True
            current = parent
    finally:
        conn.close()
    
    return False


def has_write_access(request: Request, entity_id: int) -> bool:
    """Check if current user has tresorier access to an entity (or its ancestors)."""
    user_entities = getattr(request.state, "user_entities", [])
    tresorier_ids = {ue["entity_id"] for ue in user_entities if ue["role"] == "tresorier"}
    
    if entity_id in tresorier_ids:
        return True
    
    conn = get_conn()
    try:
        current = entity_id
        while current:
            row = conn.execute("SELECT parent_id FROM entities WHERE id = ?", (current,)).fetchone()
            if not row:
                break
            parent = row["parent_id"]
            if parent in tresorier_ids:
                return True
            current = parent
    finally:
        conn.close()
    
    return False


def is_root_admin(request: Request) -> bool:
    """Check if user is tresorier on the root entity (= admin)."""
    user_entities = getattr(request.state, "user_entities", [])
    tresorier_ids = {ue["entity_id"] for ue in user_entities if ue["role"] == "tresorier"}
    
    conn = get_conn()
    try:
        root = conn.execute(
            "SELECT id FROM entities WHERE parent_id IS NULL AND type = 'internal' AND is_default = 1"
        ).fetchone()
        if root and root["id"] in tresorier_ids:
            return True
    finally:
        conn.close()
    
    return False
```

- [ ] **Step 2: Add middleware to main.py**

In `create_app()`, after `app.add_middleware(CORSMiddleware, ...)`:

```python
from backend.core.auth import AuthMiddleware

# Add auth middleware (only if multi_users module is active)
if config.modules.get("multi_users", False):
    app.add_middleware(AuthMiddleware)
```

This way auth is only enforced when multi_users is activated — backward compatible.

- [ ] **Step 3: Write middleware tests**

`tests/backend/test_auth_middleware.py`:
- Request without cookie to /api/transactions/ → 401
- Request with valid session cookie → 200
- Request with invalid session cookie → 401
- Request to /api/multi_users/login without cookie → 200 (public)
- Request to non-API path (frontend) without cookie → 200

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/backend/test_auth_middleware.py -v
python -m pytest tests/ -q --tb=line
```

- [ ] **Step 5: Commit**

```bash
git add backend/core/auth.py backend/main.py tests/backend/test_auth_middleware.py
git commit -m "feat: auth middleware — session cookie verification on all API routes"
```

---

### Task 4: Session cleanup + protection CRUD admin

**Files:**
- Modify: `backend/modules/multi_users/api.py`
- Test: `tests/backend/test_auth_admin.py`

- [ ] **Step 1: Add admin guards to user CRUD**

The existing list/create/update/delete user endpoints should require `is_root_admin`. Import from `backend.core.auth`:

```python
from fastapi import Request
from backend.core.auth import is_root_admin

@router.get("/")
def list_users(request: Request):
    if not is_root_admin(request):
        raise HTTPException(403, "Admin access required")
    ...
```

Same for create, update, delete, and entity assignment endpoints.

- [ ] **Step 2: Add session cleanup endpoint**

```python
@router.post("/cleanup-sessions")
def cleanup_sessions(request: Request):
    """Remove sessions older than 24h. Admin only."""
    if not is_root_admin(request):
        raise HTTPException(403, "Admin access required")
    conn = get_conn()
    try:
        # Delete sessions older than 24h
        conn.execute(
            "DELETE FROM sessions WHERE datetime(created_at) < datetime('now', '-24 hours')"
        )
        conn.commit()
        remaining = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        return {"remaining_sessions": remaining}
    finally:
        conn.close()
```

- [ ] **Step 3: Write admin tests**

Tests: non-admin user can't list users (403), can't create users (403), admin can.

- [ ] **Step 4: Run all tests, commit**

---

### Task 5: Frontend — page login + route protection

**Files:**
- Create: `frontend/src/core/AuthContext.tsx`
- Create: `frontend/src/core/Login.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/api.ts`

- [ ] **Step 1: Add auth API endpoints to api.ts**

```typescript
  login: (username: string, password: string) =>
    request<any>("/multi_users/login", { method: "POST", body: JSON.stringify({ username, password }) }),
  logout: () => request<any>("/multi_users/logout", { method: "POST" }),
  getMe: () => request<any>("/multi_users/me"),
  changePassword: (old_password: string, new_password: string) =>
    request<any>("/multi_users/me/password", { method: "PUT", body: JSON.stringify({ old_password, new_password }) }),
  getUserEntities: (userId: number) => request<any[]>(`/multi_users/${userId}/entities`),
  assignUserEntity: (userId: number, entityId: number, role: string) =>
    request<any>(`/multi_users/${userId}/entities`, { method: "POST", body: JSON.stringify({ entity_id: entityId, role }) }),
  removeUserEntity: (userId: number, entityId: number) =>
    request<any>(`/multi_users/${userId}/entities/${entityId}`, { method: "DELETE" }),
```

- [ ] **Step 2: Create AuthContext.tsx**

React context that:
- On mount, calls `GET /me` to check if already logged in
- If 401, sets `authenticated = false`
- Provides `login(username, password)`, `logout()`, `user`, `authenticated`

- [ ] **Step 3: Create Login.tsx**

Full-screen login page (dark theme, centered form):
- Username + password inputs
- "Connexion" button
- Error message on bad credentials

- [ ] **Step 4: Modify App.tsx**

- Wrap in `<AuthProvider>`
- If not authenticated, render `<Login />` instead of the main app
- If authenticated, render sidebar + routes as before
- If multi_users module is not active, skip auth entirely (backward compat)

- [ ] **Step 5: Build frontend**

```bash
cd frontend && npm run build
```

- [ ] **Step 6: Commit**

```bash
git add frontend/
git commit -m "feat: frontend login page + auth context + route protection"
```

---

### Task 6: Frontend — admin panel pour gerer users + acces

**Files:**
- Create: `frontend/src/modules/multi_users/UserManager.tsx`
- Modify: `frontend/src/App.tsx` (add route)
- Modify: `frontend/src/core/Sidebar.tsx` (add nav link for admin)

- [ ] **Step 1: Create UserManager.tsx**

Page admin visible seulement par le tresorier racine:
- Liste des users (username, display_name, acces)
- Bouton creer user (modal: username, password, display_name)
- Par user : liste des entites assignees + role, bouton ajouter/supprimer acces
- Bouton supprimer user

- [ ] **Step 2: Add route + nav**

Add to MODULE_ROUTES in App.tsx. Add to Sidebar (visible only if `is_root_admin` from user data).

- [ ] **Step 3: Add password change to Settings**

In Settings.tsx, add a section "Mon compte" with old/new password fields.

- [ ] **Step 4: Build + commit**

---

### Task 7: Verification finale

- [ ] **Step 1:** `python tools/check.py` — PASS, 22 modules
- [ ] **Step 2:** `python -m pytest tests/ -v` — all pass
- [ ] **Step 3:** `python start.py` — app starts, login page appears
- [ ] **Step 4:** `cd frontend && npm run build` — succeeds
