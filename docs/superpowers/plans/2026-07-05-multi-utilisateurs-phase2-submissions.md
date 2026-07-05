# Phase 2 multi-utilisateurs : module `submissions` — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un treasurer soumet une dépense/recette (avec justificatif PDF) dans son périmètre ; l'admin approuve (une vraie transaction est créée) ou refuse avec commentaire ; les soumissions non approuvées n'affectent jamais aucun solde.

**Architecture:** Nouveau module plug-and-play `submissions` avec sa table `transaction_submissions` séparée (jamais de statut pending sur `transactions` : `FROM transactions` apparaît dans 15 fichiers, un filtre oublié fausserait un solde). Le module `attachments` gagne une colonne nullable `submission_id` (rebuild de table, `transaction_id` devient nullable). La garde centrale `require_session` (backend/core/auth.py) gagne une allowlist à motifs regex pour les mutations non-admin paramétrées, avec vérification fine par endpoint.

**Tech Stack:** FastAPI + sqlite3 brut (`get_conn()`), pytest (fixtures `client_and_db` / `login_as`), React + Tailwind (build Vite), manifest.json source de vérité.

## Global Constraints

- **Français avec accents partout** dans les textes UI et messages d'erreur (é è ê à â î ô ù ç). Jamais de tiret cadratin (—) ni demi-cadratin (–) : virgules, parenthèses, deux-points ou tirets simples.
- **Design system** : respecter DESIGN.md à la racine (fond `#0a0a0a`, cartes `bg-[#111] border border-[#222] rounded-2xl`, accent doré `#F2C48D`, bouton primaire pill doré texte noir, montants via `formatEuros`).
- **Aucun nom de module hardcodé dans l'UI** : tout passe par `manifest.name` / `manifest.menu.label` (test_ui_text_coherence.py doit rester vert).
- **Montants en centimes, toujours strictement positifs** ; le sens vient de `direction` puis de from/to à l'approbation.
- **PRAGMA foreign_keys OFF** au runtime : aucune contrainte FK effective, les nettoyages sont manuels.
- **Chaque endpoint livré avec ses tests** : succès, 404, 400, matrice de rôles (admin / treasurer / viewer / non-propriétaire).
- **Commandes** : tests `python -m pytest tests/backend/<fichier> -v` depuis `C:\Users\bloki\Desktop\OpenFlow\openflow` ; intégrité `python tools/check.py` ; build front `cd frontend && npm run build`.
- **Git : ne JAMAIS utiliser `git add -A` ni `git add .`** Le working tree contient des modifications préexistantes non liées (balance.py, Dashboard.tsx, plusieurs tests, install/pristine.zip, DESIGN.md et PRODUCT.md non suivis) : elles ne doivent être ni commitées ni écrasées. Toujours `git add <chemins explicites>`.
- **Le compteur de fichiers modifiés de la page Système (pristine.zip) restera rouge pendant tout le chantier : c'est attendu, ne pas régénérer le snapshot.**
- Convention de commit : préfixes français type `feat(submissions): ...`, `fix(...)`, `test(...)`, comme l'historique.

## Rappels de contexte pour les exécutants

- La garde centrale `require_session` (backend/core/auth.py:113) fait le deny-by-default : toute route `/api` exige une session, et toute mutation (POST/PUT/PATCH/DELETE) est réservée à l'admin **sauf** allowlist `NON_ADMIN_MUTATIONS` (comparaison de chemin EXACTE aujourd'hui). Les GET passent pour tout connecté : un GET admin-only doit porter `Depends(require_admin)` explicitement.
- `get_allowed_entity_ids(conn, user)` (auth.py:160) renvoie `None` pour l'admin (tout), sinon l'union des sous-arbres des entités où le user a un rôle (CTE récursive).
- `tests/backend/test_permissions_matrix.py` parcourt TOUTES les routes mutantes de l'app et exige 403 pour un non-admin sauf allowlist : tout nouvel endpoint mutant non-admin doit être ajouté à l'allowlist ET couvert par des tests fins.
- `tests/backend/conftest.py` : `client` / `client_and_db` sont connectés en admin ; `login_as(email, roles=[(entity_id, "treasurer"|"viewer")])` fabrique d'autres profils. La DB template applique automatiquement les migrations de TOUS les modules présents dans backend/modules/.
- Le fichier `config.test.yaml` liste les modules actifs pour les tests : le nouveau module doit y être activé.
- `tools/check.py` : un manifest avec un champ `menu` DOIT avoir un frontend (dossier `frontend/src/modules/<id>/` ou entrée dans routes.tsx), sinon échec. Donc : manifest SANS `menu` jusqu'à la tâche frontend (même pivot qu'en phase 1).
- Table `entities` : type `internal` (trésorerie gérée) ou `external` (tiers). `GET /api/entities/?type=external` est lisible par tout connecté (contreparties). La contrepartie d'une soumission est une entité **externe**, pas un contact du module tiers.

## Structure de fichiers (vue d'ensemble)

- Créer : `backend/modules/submissions/{__init__.py, manifest.json, models.py, api.py}`
- Modifier : `backend/core/auth.py` (rôle filtré + allowlist à motifs)
- Modifier : `backend/modules/attachments/{models.py, manifest.json, api.py}` (submission_id)
- Modifier : `config.example.yaml`, `config.test.yaml`
- Créer : `tests/backend/{test_submissions_api.py, test_submissions_workflow.py, test_submissions_attachments.py, test_coherence_submissions.py}`
- Modifier : `tests/backend/test_permissions_matrix.py`, `tests/backend/test_auth_scope.py`
- Créer : `frontend/src/modules/submissions/index.tsx`
- Modifier : `frontend/src/{api.ts, routes.tsx, core/Sidebar.tsx}`
- Modifier : `CLAUDE.md`, `.superpowers/sdd/progress.md`

---

### Task 1 : Branche + squelette backend du module `submissions`

**Files:**
- Create: `backend/modules/submissions/__init__.py` (vide)
- Create: `backend/modules/submissions/manifest.json`
- Create: `backend/modules/submissions/models.py`
- Create: `backend/modules/submissions/api.py` (router vide)
- Modify: `config.example.yaml` (ajout `submissions: true`)
- Modify: `config.test.yaml` (ajout `submissions: true`)
- Test: `tests/backend/test_submissions_api.py`

**Interfaces:**
- Produces: table `transaction_submissions` (colonnes ci-dessous), module `submissions` monté sous `/api/submissions`, constante `VALID_STATUSES` dans api.py.

- [ ] **Step 1 : Créer la branche de travail**

```bash
cd C:\Users\bloki\Desktop\OpenFlow\openflow
git checkout -b feature/multi-utilisateurs-phase2
```

Les fichiers déjà modifiés du working tree (balance.py, Dashboard.tsx, tests, pristine.zip...) suivent la branche sans être commités : ne pas y toucher.

- [ ] **Step 2 : Écrire les tests d'existence (qui échouent)**

Créer `tests/backend/test_submissions_api.py` :

```python
"""Module submissions : création et lectures scopées."""
import sqlite3

NOW = "2026-01-01T00:00:00+00:00"


def _entity(db_path, name, type="internal", parent_id=None):
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute(
            "INSERT INTO entities (name, type, parent_id, is_default, color, position, created_at, updated_at) "
            "VALUES (?, ?, ?, 0, '#000000', 0, ?, ?)",
            (name, type, parent_id, NOW, NOW),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def test_submissions_module_active(client):
    mods = client.get("/api/modules").json()
    assert any(m["id"] == "submissions" for m in mods)


def test_submissions_table_exists(client_and_db):
    _, db_path = client_and_db
    conn = sqlite3.connect(str(db_path))
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(transaction_submissions)").fetchall()}
    finally:
        conn.close()
    assert {
        "id", "date", "label", "description", "amount", "category_id",
        "entity_id", "counterparty_entity_id", "direction", "status",
        "submitted_by", "reviewed_by", "reviewed_at", "review_comment",
        "transaction_id", "created_at", "updated_at",
    } <= cols
```

- [ ] **Step 3 : Vérifier l'échec**

Run : `python -m pytest tests/backend/test_submissions_api.py -v`
Attendu : FAIL (module absent de /api/modules, table inexistante).

- [ ] **Step 4 : Créer le module**

`backend/modules/submissions/__init__.py` : fichier vide.

`backend/modules/submissions/manifest.json` (PAS de champ `menu` pour l'instant : check.py exige un frontend dès qu'un menu existe ; il sera ajouté en Task 9) :

```json
{
  "id": "submissions",
  "name": "Soumissions",
  "description": "Soumission de transactions par les trésoriers, validation par l'admin",
  "help": "Les trésoriers de sous-entités soumettent leurs dépenses et recettes avec justificatif PDF. L'administrateur approuve (la transaction entre en comptabilité) ou refuse avec un commentaire. Une soumission en attente n'affecte jamais les soldes.",
  "version": "1.0.0",
  "origin": "builtin",
  "category": "standard",
  "dependencies": ["transactions", "entities", "attachments", "users"],
  "api_routes": ["api.py"],
  "db_models": ["models.py"],
  "dashboard_widgets": [],
  "settings_schema": {},
  "example": "Le trésorier de Gastronomine soumet 45,50 € de courses avec le ticket en PDF ; je valide et la transaction est créée."
}
```

`backend/modules/submissions/models.py` :

```python
migrations = {
    "1.0.0": [
        """CREATE TABLE transaction_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            label TEXT NOT NULL,
            description TEXT DEFAULT '',
            amount INTEGER NOT NULL,
            category_id INTEGER,
            entity_id INTEGER NOT NULL,
            counterparty_entity_id INTEGER NOT NULL,
            direction TEXT NOT NULL CHECK(direction IN ('expense','income')),
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK(status IN ('pending','approved','rejected','cancelled')),
            submitted_by INTEGER NOT NULL,
            reviewed_by INTEGER,
            reviewed_at TEXT,
            review_comment TEXT DEFAULT '',
            transaction_id INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""",
        "CREATE INDEX idx_submissions_status ON transaction_submissions(status)",
        "CREATE INDEX idx_submissions_submitted_by ON transaction_submissions(submitted_by)",
    ],
}
```

`backend/modules/submissions/api.py` :

```python
"""Soumissions de transactions : les trésoriers proposent, l'admin valide."""
from fastapi import APIRouter

router = APIRouter()

VALID_STATUSES = {"pending", "approved", "rejected", "cancelled"}
```

- [ ] **Step 5 : Activer le module dans les configs**

Dans `config.example.yaml`, bloc `modules:`, ajouter (ordre alphabétique) :

```yaml
  submissions: true
```

Dans `config.test.yaml`, bloc `modules:`, ajouter :

```yaml
  submissions: true
```

- [ ] **Step 6 : Vérifier**

Run : `python -m pytest tests/backend/test_submissions_api.py -v` → PASS (2 tests).
Run : `python tools/check.py` → `Result: PASS` (le module apparaît dans la liste).
Run : `python -m pytest tests/backend/ -q` → la suite complète reste verte (les tests génériques test_auth_enforcement / test_permissions_matrix découvrent le nouveau router sans le casser : il n'a pas encore de routes).

- [ ] **Step 7 : Commit**

```bash
git add backend/modules/submissions tests/backend/test_submissions_api.py config.example.yaml config.test.yaml
git commit -m "feat(submissions): squelette du module (manifest, table transaction_submissions)"
```

---

### Task 2 : auth.py — filtre de rôle + allowlist de mutations à motifs

**Files:**
- Modify: `backend/core/auth.py`
- Modify: `tests/backend/test_permissions_matrix.py`
- Test: `tests/backend/test_auth_scope.py` (ajouts)

**Interfaces:**
- Consumes: `get_allowed_entity_ids(conn, user)` existant.
- Produces: `get_allowed_entity_ids(conn, user, role: str | None = None)` (signature étendue, rétrocompatible : `role=None` = tous rôles ; `role="treasurer"` restreint aux sous-arbres où le user est treasurer ; admin renvoie toujours `None`). `is_non_admin_mutation(path: str) -> bool` et `NON_ADMIN_MUTATION_PATTERNS` (liste de regex compilées). Allowlist enrichie de `POST /api/submissions/` (exact) et `/api/submissions/<id>/cancel` (motif).

- [ ] **Step 1 : Écrire les tests (qui échouent)**

Ajouter à la fin de `tests/backend/test_auth_scope.py` :

```python
def test_role_filter_treasurer_only(db_path):
    conn = _conn(db_path)
    try:
        bda = _entity(conn, "BDA2")
        gastro = _entity(conn, "Gastronomine2", bda)
        cave = _entity(conn, "Cave2", gastro)
        ccmp = _entity(conn, "CCMP2", bda)
        conn.execute(
            "INSERT INTO users (email, display_name, password_hash, is_admin, is_active, created_at) "
            "VALUES ('mix@c.fr', 'M', 'x', 0, 1, ?)", (NOW,))
        uid = conn.execute("SELECT id FROM users WHERE email='mix@c.fr'").fetchone()["id"]
        conn.execute(
            "INSERT INTO user_entity_roles (user_id, entity_id, role, created_at) "
            "VALUES (?, ?, 'treasurer', ?)", (uid, gastro, NOW))
        conn.execute(
            "INSERT INTO user_entity_roles (user_id, entity_id, role, created_at) "
            "VALUES (?, ?, 'viewer', ?)", (uid, ccmp, NOW))
        conn.commit()
        user = {"id": uid, "is_admin": 0}
        # Sans filtre : union des deux sous-arbres.
        assert get_allowed_entity_ids(conn, user) == {gastro, cave, ccmp}
        # Filtre treasurer : seulement le sous-arbre treasurer.
        assert get_allowed_entity_ids(conn, user, role="treasurer") == {gastro, cave}
        # Filtre viewer : seulement le sous-arbre viewer.
        assert get_allowed_entity_ids(conn, user, role="viewer") == {ccmp}
        # Admin : None quel que soit le filtre.
        assert get_allowed_entity_ids(conn, {"id": 1, "is_admin": 1}, role="treasurer") is None
    finally:
        conn.close()


def test_is_non_admin_mutation_patterns():
    from backend.core.auth import is_non_admin_mutation
    assert is_non_admin_mutation("/api/users/logout")            # entrée exacte existante
    assert is_non_admin_mutation("/api/submissions/")            # création par treasurer
    assert is_non_admin_mutation("/api/submissions/42/cancel")   # annulation par motif
    assert not is_non_admin_mutation("/api/submissions/42/approve")
    assert not is_non_admin_mutation("/api/submissions/42/reject")
    assert not is_non_admin_mutation("/api/transactions/")
    assert not is_non_admin_mutation("/api/submissions/abc/cancel")
```

Note import en tête de fichier : `test_auth_scope.py` importe déjà `get_allowed_entity_ids` ; rien à changer pour lui.

- [ ] **Step 2 : Vérifier l'échec**

Run : `python -m pytest tests/backend/test_auth_scope.py -v`
Attendu : FAIL (`role` inattendu, `is_non_admin_mutation` inexistant).

- [ ] **Step 3 : Implémenter dans backend/core/auth.py**

Ajouter `import re` en tête (avec les autres imports stdlib). Sous `NON_ADMIN_MUTATIONS`, ajouter :

```python
# Mutations non-admin dont le chemin contient un paramètre : motifs regex.
# La vérification FINE (propriétaire, statut, périmètre) reste dans l'endpoint ;
# ici on ne fait qu'ouvrir le passage de la garde centrale.
NON_ADMIN_MUTATION_PATTERNS = [
    re.compile(r"^/api/submissions/\d+/cancel$"),
]


def is_non_admin_mutation(path: str) -> bool:
    return path in NON_ADMIN_MUTATIONS or any(p.match(path) for p in NON_ADMIN_MUTATION_PATTERNS)
```

Ajouter `"/api/submissions/"` au set `NON_ADMIN_MUTATIONS` existant (création par treasurer ; seule la route POST existe à ce chemin, une autre méthode donnerait 405).

Dans `require_session`, remplacer la condition finale :

```python
    if request.method in _MUTATING_METHODS and not request.state.user["is_admin"] \
            and not is_non_admin_mutation(path):
        raise HTTPException(status_code=403, detail="Action réservée à l'administrateur")
```

Étendre `get_allowed_entity_ids` (remplacer la requête des racines, le reste inchangé) :

```python
def get_allowed_entity_ids(conn, user, role: str | None = None):
    """Périmètre du user : None = tout (admin), sinon l'union des sous-arbres
    des entités où il a un rôle. `role` restreint aux lignes de ce rôle
    (ex : "treasurer" pour les écritures). CTE récursive multi-racines."""
    if user["is_admin"]:
        return None
    if role is None:
        rows = conn.execute(
            "SELECT entity_id FROM user_entity_roles WHERE user_id = ?", (user["id"],)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT entity_id FROM user_entity_roles WHERE user_id = ? AND role = ?",
            (user["id"], role),
        ).fetchall()
    roots = [r[0] for r in rows]
    if not roots:
        return set()
    # ... (suite inchangée : placeholders + CTE récursive)
```

- [ ] **Step 4 : Mettre à jour test_permissions_matrix.py**

Le test générique doit ignorer les chemins couverts par motifs, en concrétisant d'abord (`{param}` → `1`) :

```python
from backend.core.auth import NON_ADMIN_MUTATIONS, NON_ADMIN_MUTATION_PATTERNS, PUBLIC_API_PATHS, is_non_admin_mutation
```

Dans `test_every_mutation_is_admin_only`, remplacer :

```python
        if path in PUBLIC_API_PATHS or path in NON_ADMIN_MUTATIONS:
            continue
```

par :

```python
        if path in PUBLIC_API_PATHS or is_non_admin_mutation(_concretize(path)):
            continue
```

Remplacer `test_non_admin_mutations_allowlist_is_minimal` par :

```python
def test_non_admin_mutations_allowlist_is_minimal():
    assert NON_ADMIN_MUTATIONS == {
        "/api/users/login",
        "/api/users/logout",
        "/api/users/me/password",
        "/api/users/invitations/accept",
        "/api/submissions/",
    }
    assert [p.pattern for p in NON_ADMIN_MUTATION_PATTERNS] == [
        r"^/api/submissions/\d+/cancel$",
    ]
```

- [ ] **Step 5 : Vérifier**

Run : `python -m pytest tests/backend/test_auth_scope.py tests/backend/test_permissions_matrix.py tests/backend/test_auth_enforcement.py -v`
Attendu : PASS.

- [ ] **Step 6 : Commit**

```bash
git add backend/core/auth.py tests/backend/test_auth_scope.py tests/backend/test_permissions_matrix.py
git commit -m "feat(auth): filtre de role sur le perimetre + allowlist de mutations a motifs"
```

---

### Task 3 : POST /api/submissions/ — création par un treasurer dans son périmètre

**Files:**
- Modify: `backend/modules/submissions/api.py`
- Test: `tests/backend/test_submissions_api.py` (ajouts)

**Interfaces:**
- Consumes: `get_allowed_entity_ids(conn, user, role="treasurer")` (Task 2), garde centrale ouverte sur `POST /api/submissions/` (Task 2).
- Produces: endpoint `POST /api/submissions/` (201, corps `SubmissionCreate`), helper interne `_fetch_serialized(conn, submission_id) -> dict` (SELECT enrichi : `entity_name`, `counterparty_name`, `category_name`, `category_color`, `submitted_by_name`, `submitted_by_email`, `reviewed_by_name`). Les tâches 4 à 7 réutilisent `_fetch_serialized` et `_SELECT`.

- [ ] **Step 1 : Écrire les tests (qui échouent)**

Ajouter à `tests/backend/test_submissions_api.py` :

```python
def _payload(entity_id, counterparty_id, **over):
    p = {
        "date": "2026-05-10", "label": "Courses atelier", "description": "Farine et beurre",
        "amount": 4550, "category_id": None, "entity_id": entity_id,
        "counterparty_entity_id": counterparty_id, "direction": "expense",
    }
    p.update(over)
    return p


def _setup_tree(db_path):
    """BDA > Gastronomine > Cave ; CCMP à part ; un tiers externe."""
    bda = _entity(db_path, "BDA")
    gastro = _entity(db_path, "Gastronomine", parent_id=bda)
    cave = _entity(db_path, "Cave", parent_id=gastro)
    ccmp = _entity(db_path, "CCMP", parent_id=bda)
    fournisseur = _entity(db_path, "Boulangerie Martin", type="external")
    return bda, gastro, cave, ccmp, fournisseur


def test_treasurer_creates_submission_in_scope(client_and_db, login_as):
    _, db_path = client_and_db
    _, gastro, cave, _, fournisseur = _setup_tree(db_path)
    tres = login_as("tres@test.local", roles=[(gastro, "treasurer")])
    r = tres.post("/api/submissions/", json=_payload(cave, fournisseur))
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "pending"
    assert body["amount"] == 4550
    assert body["direction"] == "expense"
    assert body["entity_id"] == cave
    assert body["entity_name"] == "Cave"
    assert body["counterparty_name"] == "Boulangerie Martin"
    assert body["transaction_id"] is None
    assert body["submitted_by_email"] == "tres@test.local"


def test_admin_creates_submission_anywhere(client_and_db):
    client, db_path = client_and_db
    _, gastro, _, _, fournisseur = _setup_tree(db_path)
    r = client.post("/api/submissions/", json=_payload(gastro, fournisseur))
    assert r.status_code == 201


def test_treasurer_out_of_scope_403(client_and_db, login_as):
    _, db_path = client_and_db
    _, gastro, _, ccmp, fournisseur = _setup_tree(db_path)
    tres = login_as("tres2@test.local", roles=[(gastro, "treasurer")])
    r = tres.post("/api/submissions/", json=_payload(ccmp, fournisseur))
    assert r.status_code == 403


def test_viewer_cannot_submit(client_and_db, login_as):
    _, db_path = client_and_db
    _, gastro, _, _, fournisseur = _setup_tree(db_path)
    viewer = login_as("viewer@test.local", roles=[(gastro, "viewer")])
    r = viewer.post("/api/submissions/", json=_payload(gastro, fournisseur))
    assert r.status_code == 403


def test_create_validations(client_and_db, login_as):
    _, db_path = client_and_db
    _, gastro, _, _, fournisseur = _setup_tree(db_path)
    tres = login_as("tres3@test.local", roles=[(gastro, "treasurer")])
    # Montant non strictement positif.
    assert tres.post("/api/submissions/", json=_payload(gastro, fournisseur, amount=0)).status_code == 400
    assert tres.post("/api/submissions/", json=_payload(gastro, fournisseur, amount=-500)).status_code == 400
    # Entité == contrepartie.
    assert tres.post("/api/submissions/", json=_payload(gastro, gastro)).status_code == 400
    # Entité inexistante -> 403 (hors périmètre du rôle avant même l'existence),
    # contrepartie inexistante -> 400.
    assert tres.post("/api/submissions/", json=_payload(99999, fournisseur)).status_code in (400, 403)
    assert tres.post("/api/submissions/", json=_payload(gastro, 99999)).status_code == 400
    # Entité externe comme entity_id -> 400 (doit être interne).
    assert tres.post("/api/submissions/", json=_payload(fournisseur, gastro)).status_code in (400, 403)
    # Catégorie inexistante -> 400.
    assert tres.post("/api/submissions/", json=_payload(gastro, fournisseur, category_id=99999)).status_code == 400
    # Direction invalide -> 422 (validation pydantic Literal).
    assert tres.post("/api/submissions/", json=_payload(gastro, fournisseur, direction="transfer")).status_code == 422


def test_anonymous_401(client_and_db):
    from fastapi.testclient import TestClient
    client, _ = client_and_db
    anon = TestClient(client.app)
    assert anon.post("/api/submissions/", json={}).status_code == 401
```

- [ ] **Step 2 : Vérifier l'échec**

Run : `python -m pytest tests/backend/test_submissions_api.py -v`
Attendu : FAIL (405/404 : la route n'existe pas).

- [ ] **Step 3 : Implémenter l'endpoint**

Remplacer le contenu de `backend/modules/submissions/api.py` par :

```python
"""Soumissions de transactions : les trésoriers proposent, l'admin valide."""
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from backend.core.auth import get_allowed_entity_ids, get_current_user
from backend.core.database import get_conn, row_to_dict

router = APIRouter()

VALID_STATUSES = {"pending", "approved", "rejected", "cancelled"}

# SELECT enrichi commun à toutes les lectures (noms d'entités, catégorie, auteurs).
_SELECT = """SELECT s.*,
       e.name AS entity_name,
       ce.name AS counterparty_name,
       c.name AS category_name, c.color AS category_color,
       u.display_name AS submitted_by_name, u.email AS submitted_by_email,
       ru.display_name AS reviewed_by_name
FROM transaction_submissions s
LEFT JOIN entities e ON s.entity_id = e.id
LEFT JOIN entities ce ON s.counterparty_entity_id = ce.id
LEFT JOIN categories c ON s.category_id = c.id
LEFT JOIN users u ON s.submitted_by = u.id
LEFT JOIN users ru ON s.reviewed_by = ru.id"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fetch_serialized(conn, submission_id: int) -> dict:
    row = conn.execute(_SELECT + " WHERE s.id = ?", (submission_id,)).fetchone()
    return row_to_dict(row)


class SubmissionCreate(BaseModel):
    date: str
    label: str
    description: str = ""
    amount: int  # centimes, strictement positif ; le sens vient de direction
    category_id: Optional[int] = None
    entity_id: int
    counterparty_entity_id: int
    direction: Literal["expense", "income"]


@router.post("/", status_code=201)
def create_submission(sub: SubmissionCreate, request: Request):
    user = get_current_user(request)
    if sub.amount <= 0:
        raise HTTPException(status_code=400, detail="Le montant doit être strictement positif")
    if sub.entity_id == sub.counterparty_entity_id:
        raise HTTPException(status_code=400, detail="L'entité et la contrepartie doivent être différentes")
    conn = get_conn()
    try:
        # Périmètre d'écriture : seules les entités où le user est TREASURER
        # (le rôle viewer ne suffit pas). Admin : partout (None).
        treasurer_ids = get_allowed_entity_ids(conn, user, role="treasurer")
        if treasurer_ids is not None and sub.entity_id not in treasurer_ids:
            raise HTTPException(status_code=403, detail="Vous n'êtes pas trésorier de cette entité")
        entity = conn.execute("SELECT type FROM entities WHERE id = ?", (sub.entity_id,)).fetchone()
        if entity is None or entity["type"] != "internal":
            raise HTTPException(status_code=400, detail="entity_id doit référencer une entité interne existante")
        counterparty = conn.execute(
            "SELECT id FROM entities WHERE id = ?", (sub.counterparty_entity_id,)
        ).fetchone()
        if counterparty is None:
            raise HTTPException(status_code=400, detail="counterparty_entity_id ne référence aucune entité")
        if sub.category_id is not None:
            cat = conn.execute("SELECT id FROM categories WHERE id = ?", (sub.category_id,)).fetchone()
            if cat is None:
                raise HTTPException(status_code=400, detail=f"Catégorie {sub.category_id} introuvable")
        now = _now()
        cur = conn.execute(
            """INSERT INTO transaction_submissions
               (date, label, description, amount, category_id, entity_id,
                counterparty_entity_id, direction, status, submitted_by, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)""",
            (sub.date, sub.label, sub.description, sub.amount, sub.category_id,
             sub.entity_id, sub.counterparty_entity_id, sub.direction, user["id"], now, now),
        )
        data = _fetch_serialized(conn, cur.lastrowid)
        conn.commit()
        return data
    finally:
        conn.close()
```

- [ ] **Step 4 : Vérifier**

Run : `python -m pytest tests/backend/test_submissions_api.py tests/backend/test_permissions_matrix.py -v`
Attendu : PASS (la matrice saute `/api/submissions/` car allowlistée, les tests fins couvrent viewer/hors périmètre).

- [ ] **Step 5 : Commit**

```bash
git add backend/modules/submissions/api.py tests/backend/test_submissions_api.py
git commit -m "feat(submissions): creation d'une soumission par un tresorier dans son perimetre"
```

---

### Task 4 : Lectures — GET /mine, GET / (admin), GET /{id}

**Files:**
- Modify: `backend/modules/submissions/api.py`
- Test: `tests/backend/test_submissions_api.py` (ajouts)

**Interfaces:**
- Consumes: `_SELECT`, `_fetch_serialized` (Task 3), `require_admin` (auth.py).
- Produces: `GET /api/submissions/mine` (liste des soumissions du user connecté, tous statuts, tri created_at DESC), `GET /api/submissions/?status=pending` (admin only, filtre statut optionnel), `GET /api/submissions/{submission_id}` (admin ou auteur). Le frontend (Tasks 9-10) consomme ces trois routes.

**Piège connu : la garde centrale ne couvre PAS les GET.** `GET /api/submissions/` liste les soumissions de tout le monde : il DOIT porter `Depends(require_admin)` explicitement.

- [ ] **Step 1 : Écrire les tests (qui échouent)**

Ajouter à `tests/backend/test_submissions_api.py` :

```python
def test_mine_returns_only_own_submissions(client_and_db, login_as):
    _, db_path = client_and_db
    _, gastro, _, ccmp, fournisseur = _setup_tree(db_path)
    tres_a = login_as("a@test.local", roles=[(gastro, "treasurer")])
    tres_b = login_as("b@test.local", roles=[(ccmp, "treasurer")])
    tres_a.post("/api/submissions/", json=_payload(gastro, fournisseur, label="De A"))
    tres_b.post("/api/submissions/", json=_payload(ccmp, fournisseur, label="De B"))
    mine = tres_a.get("/api/submissions/mine")
    assert mine.status_code == 200
    labels = [s["label"] for s in mine.json()]
    assert labels == ["De A"]


def test_admin_list_is_admin_only(client_and_db, login_as):
    client, db_path = client_and_db
    _, gastro, _, _, fournisseur = _setup_tree(db_path)
    tres = login_as("c@test.local", roles=[(gastro, "treasurer")])
    tres.post("/api/submissions/", json=_payload(gastro, fournisseur))
    # Admin : 200, liste complète.
    r = client.get("/api/submissions/")
    assert r.status_code == 200
    assert len(r.json()) == 1
    # Filtre par statut.
    assert len(client.get("/api/submissions/?status=pending").json()) == 1
    assert client.get("/api/submissions/?status=approved").json() == []
    assert client.get("/api/submissions/?status=bidon").status_code == 400
    # Treasurer et viewer : 403 (GET admin-only explicite).
    assert tres.get("/api/submissions/").status_code == 403
    viewer = login_as("d@test.local", roles=[(gastro, "viewer")])
    assert viewer.get("/api/submissions/").status_code == 403


def test_get_one_owner_or_admin(client_and_db, login_as):
    client, db_path = client_and_db
    _, gastro, _, ccmp, fournisseur = _setup_tree(db_path)
    tres = login_as("e@test.local", roles=[(gastro, "treasurer")])
    other = login_as("f@test.local", roles=[(ccmp, "treasurer")])
    sid = tres.post("/api/submissions/", json=_payload(gastro, fournisseur)).json()["id"]
    assert tres.get(f"/api/submissions/{sid}").status_code == 200
    assert client.get(f"/api/submissions/{sid}").status_code == 200
    assert other.get(f"/api/submissions/{sid}").status_code == 403
    assert client.get("/api/submissions/99999").status_code == 404
```

- [ ] **Step 2 : Vérifier l'échec**

Run : `python -m pytest tests/backend/test_submissions_api.py -v` → FAIL (404 sur les nouvelles routes).

- [ ] **Step 3 : Implémenter**

Dans `backend/modules/submissions/api.py`, ajouter `Depends` et `require_admin` aux imports :

```python
from fastapi import APIRouter, Depends, HTTPException, Request
from backend.core.auth import get_allowed_entity_ids, get_current_user, require_admin
```

Ajouter les routes APRÈS `create_submission`. Déclarer `/mine` AVANT `/{submission_id}` :

```python
@router.get("/mine")
def list_my_submissions(request: Request):
    """Suivi de ses propres soumissions (tous statuts)."""
    user = get_current_user(request)
    conn = get_conn()
    try:
        rows = conn.execute(
            _SELECT + " WHERE s.submitted_by = ? ORDER BY s.created_at DESC, s.id DESC",
            (user["id"],),
        ).fetchall()
        return [row_to_dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/")
def list_submissions(status: Optional[str] = None, admin: dict = Depends(require_admin)):
    """File de validation : réservée à l'admin (GET non couvert par la garde centrale)."""
    if status is not None and status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Statut invalide : {status}")
    conn = get_conn()
    try:
        sql = _SELECT
        params = []
        if status is not None:
            sql += " WHERE s.status = ?"
            params.append(status)
        sql += " ORDER BY s.created_at DESC, s.id DESC"
        return [row_to_dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


@router.get("/{submission_id}")
def get_submission(submission_id: int, request: Request):
    user = get_current_user(request)
    conn = get_conn()
    try:
        data = _fetch_serialized(conn, submission_id)
        if data is None:
            raise HTTPException(status_code=404, detail=f"Soumission {submission_id} introuvable")
        if not user["is_admin"] and data["submitted_by"] != user["id"]:
            raise HTTPException(status_code=403, detail="Accès refusé à cette soumission")
        return data
    finally:
        conn.close()
```

Adapter `_fetch_serialized` pour renvoyer `None` si absent :

```python
def _fetch_serialized(conn, submission_id: int):
    row = conn.execute(_SELECT + " WHERE s.id = ?", (submission_id,)).fetchone()
    return row_to_dict(row) if row is not None else None
```

- [ ] **Step 4 : Vérifier**

Run : `python -m pytest tests/backend/test_submissions_api.py -v` → PASS.

- [ ] **Step 5 : Commit**

```bash
git add backend/modules/submissions/api.py tests/backend/test_submissions_api.py
git commit -m "feat(submissions): lectures (mes soumissions, file admin, detail) avec GET admin-only explicite"
```

---

### Task 5 : POST /{id}/cancel — annulation par l'auteur

**Files:**
- Modify: `backend/modules/submissions/api.py`
- Test: `tests/backend/test_submissions_api.py` (ajouts)

**Interfaces:**
- Consumes: allowlist motif `^/api/submissions/\d+/cancel$` (Task 2), `_fetch_serialized` (Task 3).
- Produces: `POST /api/submissions/{submission_id}/cancel` (auteur ou admin, statut pending uniquement, 409 sinon).

- [ ] **Step 1 : Écrire les tests (qui échouent)**

Ajouter à `tests/backend/test_submissions_api.py` :

```python
def test_owner_cancels_pending(client_and_db, login_as):
    _, db_path = client_and_db
    _, gastro, _, _, fournisseur = _setup_tree(db_path)
    tres = login_as("g@test.local", roles=[(gastro, "treasurer")])
    sid = tres.post("/api/submissions/", json=_payload(gastro, fournisseur)).json()["id"]
    r = tres.post(f"/api/submissions/{sid}/cancel")
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"
    # Une soumission annulée ne se ré-annule pas.
    assert tres.post(f"/api/submissions/{sid}/cancel").status_code == 409


def test_cancel_permissions(client_and_db, login_as):
    client, db_path = client_and_db
    _, gastro, _, ccmp, fournisseur = _setup_tree(db_path)
    tres = login_as("h@test.local", roles=[(gastro, "treasurer")])
    other = login_as("i@test.local", roles=[(ccmp, "treasurer")])
    sid = tres.post("/api/submissions/", json=_payload(gastro, fournisseur)).json()["id"]
    # Un autre treasurer ne peut pas annuler.
    assert other.post(f"/api/submissions/{sid}/cancel").status_code == 403
    # L'admin peut annuler.
    assert client.post(f"/api/submissions/{sid}/cancel").status_code == 200
    # 404 sur id inconnu.
    assert client.post("/api/submissions/99999/cancel").status_code == 404
```

- [ ] **Step 2 : Vérifier l'échec**

Run : `python -m pytest tests/backend/test_submissions_api.py -v` → FAIL.

- [ ] **Step 3 : Implémenter**

Ajouter dans `backend/modules/submissions/api.py` (après `get_submission`) :

```python
@router.post("/{submission_id}/cancel")
def cancel_submission(submission_id: int, request: Request):
    """L'auteur (ou l'admin) annule une soumission encore en attente."""
    user = get_current_user(request)
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT submitted_by, status FROM transaction_submissions WHERE id = ?",
            (submission_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Soumission {submission_id} introuvable")
        if not user["is_admin"] and row["submitted_by"] != user["id"]:
            raise HTTPException(status_code=403, detail="Seul l'auteur peut annuler sa soumission")
        if row["status"] != "pending":
            raise HTTPException(status_code=409, detail="Seule une soumission en attente peut être annulée")
        conn.execute(
            "UPDATE transaction_submissions SET status = 'cancelled', updated_at = ? WHERE id = ?",
            (_now(), submission_id),
        )
        data = _fetch_serialized(conn, submission_id)
        conn.commit()
        return data
    finally:
        conn.close()
```

- [ ] **Step 4 : Vérifier**

Run : `python -m pytest tests/backend/test_submissions_api.py tests/backend/test_permissions_matrix.py -v` → PASS.

- [ ] **Step 5 : Commit**

```bash
git add backend/modules/submissions/api.py tests/backend/test_submissions_api.py
git commit -m "feat(submissions): annulation d'une soumission pending par son auteur"
```

---

### Task 6 : Module attachments 1.1.0 — justificatifs de soumission

**Files:**
- Modify: `backend/modules/attachments/models.py` (migration 1.1.0 : rebuild, `transaction_id` nullable + `submission_id`)
- Modify: `backend/modules/attachments/manifest.json` (version 1.1.0)
- Modify: `backend/modules/attachments/api.py` (upload/liste sur soumission, contrôle d'accès étendu, delete à vérification fine)
- Modify: `backend/core/auth.py` (2 motifs d'allowlist en plus)
- Modify: `tests/backend/test_permissions_matrix.py` (allowlist attendue)
- Test: `tests/backend/test_submissions_attachments.py` (nouveau)

**Interfaces:**
- Consumes: table `transaction_submissions` (Task 1), `is_non_admin_mutation` (Task 2).
- Produces: colonne `attachments.submission_id` (nullable), `POST /api/attachments/submission/{submission_id}` (201, multipart `file`), `GET /api/attachments/submission/{submission_id}` (liste), preview/download/delete étendus. La Task 7 (approbation) fera `UPDATE attachments SET transaction_id = ? WHERE submission_id = ?`.

- [ ] **Step 1 : Écrire les tests (qui échouent)**

Créer `tests/backend/test_submissions_attachments.py` :

```python
"""Justificatifs liés à une soumission : upload, accès, suppression."""
import io
import sqlite3

NOW = "2026-01-01T00:00:00+00:00"
PDF_BYTES = b"%PDF-1.4 test"


def _entity(db_path, name, type="internal", parent_id=None):
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute(
            "INSERT INTO entities (name, type, parent_id, is_default, color, position, created_at, updated_at) "
            "VALUES (?, ?, ?, 0, '#000000', 0, ?, ?)",
            (name, type, parent_id, NOW, NOW),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def _submission(tc, entity_id, counterparty_id, **over):
    p = {
        "date": "2026-05-10", "label": "Courses", "description": "",
        "amount": 4550, "category_id": None, "entity_id": entity_id,
        "counterparty_entity_id": counterparty_id, "direction": "expense",
    }
    p.update(over)
    r = tc.post("/api/submissions/", json=p)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _upload(tc, sid, name="facture.pdf"):
    return tc.post(
        f"/api/attachments/submission/{sid}",
        files={"file": (name, io.BytesIO(PDF_BYTES), "application/pdf")},
    )


def _env(db_path, login_as):
    gastro = _entity(db_path, "Gastronomine")
    ccmp = _entity(db_path, "CCMP")
    fournisseur = _entity(db_path, "Fournisseur", type="external")
    tres = login_as("tres-att@test.local", roles=[(gastro, "treasurer")])
    other = login_as("other-att@test.local", roles=[(ccmp, "treasurer")])
    return gastro, fournisseur, tres, other


def test_attachments_table_has_submission_id(client_and_db):
    _, db_path = client_and_db
    conn = sqlite3.connect(str(db_path))
    try:
        info = {r[1]: r for r in conn.execute("PRAGMA table_info(attachments)").fetchall()}
    finally:
        conn.close()
    assert "submission_id" in info
    # transaction_id est devenu nullable (notnull == 0).
    assert info["transaction_id"][3] == 0


def test_upload_and_list_on_submission(client_and_db, login_as):
    _, db_path = client_and_db
    gastro, fournisseur, tres, other = _env(db_path, login_as)
    sid = _submission(tres, gastro, fournisseur)
    r = _upload(tres, sid)
    assert r.status_code == 201
    att = r.json()
    assert att["submission_id"] == sid
    assert att["transaction_id"] is None
    # Liste : auteur et admin OK, autre treasurer 403.
    assert len(tres.get(f"/api/attachments/submission/{sid}").json()) == 1
    client, _ = client_and_db
    assert len(client.get(f"/api/attachments/submission/{sid}").json()) == 1
    assert other.get(f"/api/attachments/submission/{sid}").status_code == 403
    # 404 sur soumission inconnue.
    assert _upload(tres, 99999).status_code == 404
    assert tres.get("/api/attachments/submission/99999").status_code == 404


def test_upload_forbidden_for_non_owner_and_non_pending(client_and_db, login_as):
    client, db_path = client_and_db
    gastro, fournisseur, tres, other = _env(db_path, login_as)
    sid = _submission(tres, gastro, fournisseur)
    assert _upload(other, sid).status_code == 403
    tres.post(f"/api/submissions/{sid}/cancel")
    assert _upload(tres, sid).status_code == 409


def test_preview_download_access(client_and_db, login_as):
    client, db_path = client_and_db
    gastro, fournisseur, tres, other = _env(db_path, login_as)
    sid = _submission(tres, gastro, fournisseur)
    att_id = _upload(tres, sid).json()["id"]
    assert tres.get(f"/api/attachments/{att_id}/preview").status_code == 200
    assert tres.get(f"/api/attachments/{att_id}/download").status_code == 200
    assert client.get(f"/api/attachments/{att_id}/preview").status_code == 200
    assert other.get(f"/api/attachments/{att_id}/preview").status_code == 403
    assert other.get(f"/api/attachments/{att_id}/download").status_code == 403


def test_delete_own_pending_submission_attachment(client_and_db, login_as):
    client, db_path = client_and_db
    gastro, fournisseur, tres, other = _env(db_path, login_as)
    sid = _submission(tres, gastro, fournisseur)
    att_id = _upload(tres, sid).json()["id"]
    # Un autre treasurer ne peut pas supprimer.
    assert other.delete(f"/api/attachments/{att_id}").status_code == 403
    # L'auteur peut supprimer tant que la soumission est pending.
    assert tres.delete(f"/api/attachments/{att_id}").status_code == 200
    # Une pièce liée à une transaction reste inaccessible au treasurer.
    tx = client.post("/api/transactions/", json={
        "date": "2026-05-01", "label": "Tx admin", "amount": 1000,
        "from_entity_id": gastro, "to_entity_id": fournisseur,
    }).json()
    r = client.post(
        f"/api/attachments/transaction/{tx['id']}",
        files={"file": ("f.pdf", io.BytesIO(PDF_BYTES), "application/pdf")},
    )
    tx_att = r.json()["id"]
    assert tres.delete(f"/api/attachments/{tx_att}").status_code == 403
    # L'admin garde tous les droits.
    assert client.delete(f"/api/attachments/{tx_att}").status_code == 200
```

- [ ] **Step 2 : Vérifier l'échec**

Run : `python -m pytest tests/backend/test_submissions_attachments.py -v` → FAIL (colonne absente, routes absentes).

- [ ] **Step 3 : Migration 1.1.0 (rebuild de table)**

SQLite ne sait pas retirer un NOT NULL : on reconstruit. Dans `backend/modules/attachments/models.py`, ajouter la clé `"1.1.0"` au dict :

```python
    "1.1.0": [
        # transaction_id devient nullable et submission_id apparaît : un
        # justificatif est lié soit à une transaction, soit à une soumission
        # (les deux après approbation, pour l'historique).
        """CREATE TABLE attachments_v2 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id INTEGER,
            submission_id INTEGER,
            filename TEXT NOT NULL,
            original_name TEXT NOT NULL,
            mime_type TEXT DEFAULT '',
            size INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )""",
        """INSERT INTO attachments_v2 (id, transaction_id, submission_id, filename, original_name, mime_type, size, created_at)
           SELECT id, transaction_id, NULL, filename, original_name, mime_type, size, created_at FROM attachments""",
        "DROP TABLE attachments",
        "ALTER TABLE attachments_v2 RENAME TO attachments",
    ],
```

Dans `backend/modules/attachments/manifest.json`, passer `"version": "1.0.0"` à `"version": "1.1.0"`.

- [ ] **Step 4 : Allowlist des deux nouvelles mutations non-admin**

Dans `backend/core/auth.py`, compléter `NON_ADMIN_MUTATION_PATTERNS` :

```python
NON_ADMIN_MUTATION_PATTERNS = [
    re.compile(r"^/api/submissions/\d+/cancel$"),
    # Upload d'un justificatif sur SA soumission pending (vérif fine dans l'endpoint).
    re.compile(r"^/api/attachments/submission/\d+$"),
    # Suppression d'un justificatif : l'endpoint n'autorise un non-admin QUE sur
    # une pièce liée à sa propre soumission pending.
    re.compile(r"^/api/attachments/\d+$"),
]
```

Dans `tests/backend/test_permissions_matrix.py`, mettre à jour l'assertion des motifs :

```python
    assert [p.pattern for p in NON_ADMIN_MUTATION_PATTERNS] == [
        r"^/api/submissions/\d+/cancel$",
        r"^/api/attachments/submission/\d+$",
        r"^/api/attachments/\d+$",
    ]
```

- [ ] **Step 5 : Étendre backend/modules/attachments/api.py**

Remplacer `_require_tx_access` et ses usages par un contrôle qui couvre les deux liens. Ajouter après `_require_tx_access` :

```python
def _require_submission_access(conn, request: Request, submission_id: int) -> None:
    """Accès à une soumission : son auteur ou l'admin."""
    user = get_current_user(request)
    if user["is_admin"]:
        return
    sub = conn.execute(
        "SELECT submitted_by FROM transaction_submissions WHERE id = ?", (submission_id,)
    ).fetchone()
    if sub is None or sub["submitted_by"] != user["id"]:
        raise HTTPException(status_code=403, detail="Accès refusé à cette pièce jointe")


def _require_attachment_access(conn, request: Request, attachment: dict) -> None:
    """Une pièce liée à une transaction suit le périmètre de la transaction ;
    une pièce liée seulement à une soumission suit l'auteur de la soumission."""
    if attachment["transaction_id"] is not None:
        _require_tx_access(conn, request, attachment["transaction_id"])
        return
    if attachment.get("submission_id") is not None:
        _require_submission_access(conn, request, attachment["submission_id"])
        return
    # Pièce orpheline : admin uniquement.
    user = get_current_user(request)
    if not user["is_admin"]:
        raise HTTPException(status_code=403, detail="Accès refusé à cette pièce jointe")
```

Dans `preview_attachment` et `download_attachment`, remplacer la ligne
`_require_tx_access(conn, request, attachment["transaction_id"])` par
`_require_attachment_access(conn, request, attachment)`.

Ajouter l'import `get_current_user` s'il n'y est pas déjà (il y est : ligne 11).

Ajouter les deux routes soumission (avant `@router.get("/{id}/preview")` pour la lisibilité ; pas de collision de chemin) :

```python
@router.get("/submission/{submission_id}")
def list_submission_attachments(submission_id: int, request: Request):
    conn = get_conn()
    try:
        sub = conn.execute(
            "SELECT id FROM transaction_submissions WHERE id = ?", (submission_id,)
        ).fetchone()
        if sub is None:
            raise HTTPException(status_code=404, detail=f"Soumission {submission_id} introuvable")
        _require_submission_access(conn, request, submission_id)
        cur = conn.execute(
            "SELECT * FROM attachments WHERE submission_id = ? ORDER BY created_at ASC",
            (submission_id,),
        )
        return [row_to_dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


@router.post("/submission/{submission_id}", status_code=201)
async def upload_submission_attachment(submission_id: int, request: Request, file: UploadFile = File(...)):
    ensure_attachments_dir()
    conn = get_conn()
    try:
        sub = conn.execute(
            "SELECT submitted_by, status FROM transaction_submissions WHERE id = ?",
            (submission_id,),
        ).fetchone()
        if sub is None:
            raise HTTPException(status_code=404, detail=f"Soumission {submission_id} introuvable")
        user = get_current_user(request)
        if not user["is_admin"] and sub["submitted_by"] != user["id"]:
            raise HTTPException(status_code=403, detail="Seul l'auteur peut joindre un justificatif")
        if sub["status"] != "pending":
            raise HTTPException(status_code=409, detail="La soumission n'est plus en attente")

        content = await file.read(MAX_ATTACHMENT_SIZE + 1)
        if len(content) > MAX_ATTACHMENT_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"Fichier trop volumineux (max {MAX_ATTACHMENT_SIZE // (1024 * 1024)} Mo)",
            )
        original_name = _sanitize_filename(file.filename or "upload")
        unique_filename = f"{uuid.uuid4()}_{original_name}"
        file_path = ATTACHMENTS_DIR / unique_filename
        if not file_path.resolve().is_relative_to(ATTACHMENTS_DIR.resolve()):
            raise HTTPException(status_code=400, detail="Nom de fichier invalide")
        file_path.write_bytes(content)

        now = datetime.now(timezone.utc).isoformat()
        cur = conn.execute(
            "INSERT INTO attachments (transaction_id, submission_id, filename, original_name, mime_type, size, created_at) "
            "VALUES (NULL, ?, ?, ?, ?, ?, ?)",
            (submission_id, unique_filename, original_name, file.content_type or "", len(content), now),
        )
        row = conn.execute("SELECT * FROM attachments WHERE id = ?", (cur.lastrowid,)).fetchone()
        data = row_to_dict(row)
        conn.commit()
        return data
    finally:
        conn.close()
```

Durcir `delete_attachment` (la garde centrale laisse maintenant passer les non-admins sur DELETE `/api/attachments/{id}` : la vérification fine est ICI) :

```python
@router.delete("/{id}")
def delete_attachment(id: int, request: Request):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM attachments WHERE id = ?", (id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Attachment {id} not found")
        attachment = row_to_dict(row)

        user = get_current_user(request)
        if not user["is_admin"]:
            # Un non-admin ne supprime que les pièces de SA soumission encore pending.
            allowed = False
            if attachment["transaction_id"] is None and attachment["submission_id"] is not None:
                sub = conn.execute(
                    "SELECT submitted_by, status FROM transaction_submissions WHERE id = ?",
                    (attachment["submission_id"],),
                ).fetchone()
                allowed = (
                    sub is not None
                    and sub["submitted_by"] == user["id"]
                    and sub["status"] == "pending"
                )
            if not allowed:
                raise HTTPException(status_code=403, detail="Suppression réservée à l'administrateur")

        conn.execute("DELETE FROM attachments WHERE id = ?", (id,))
        conn.commit()
    finally:
        conn.close()

    file_path = ATTACHMENTS_DIR / attachment["filename"]
    if file_path.exists():
        file_path.unlink()

    return {"deleted": id}
```

- [ ] **Step 6 : Vérifier**

Run : `python -m pytest tests/backend/test_submissions_attachments.py tests/backend/test_attachments_api.py tests/backend/test_attachments_access.py tests/backend/test_permissions_matrix.py -v`
Attendu : PASS (les tests attachments existants restent verts : les chemins transaction ne changent pas).

Run : `python -m pytest tests/backend/ -q` → suite complète verte.

- [ ] **Step 7 : Commit**

```bash
git add backend/modules/attachments backend/core/auth.py tests/backend/test_submissions_attachments.py tests/backend/test_permissions_matrix.py
git commit -m "feat(attachments): justificatifs lies a une soumission (submission_id, upload treasurer, acces fin)"
```

---

### Task 7 : Approbation et refus (admin)

**Files:**
- Modify: `backend/modules/submissions/api.py`
- Test: `tests/backend/test_submissions_workflow.py` (nouveau)

**Interfaces:**
- Consumes: colonne `attachments.submission_id` (Task 6), `require_admin`, `_fetch_serialized`.
- Produces: `POST /api/submissions/{submission_id}/approve?force=false` (crée la transaction, re-lie les justificatifs, renvoie la soumission avec `transaction_id` renseigné), `POST /api/submissions/{submission_id}/reject` (corps `{"comment": "..."}` obligatoire).

**Déduction from/to :** direction `expense` → `from = entity_id`, `to = counterparty_entity_id` ; direction `income` → l'inverse. `created_by` de la transaction = email du soumetteur.

- [ ] **Step 1 : Écrire les tests (qui échouent)**

Créer `tests/backend/test_submissions_workflow.py` :

```python
"""Workflow complet : approbation (transaction créée, justificatifs re-liés) et refus."""
import io
import sqlite3

NOW = "2026-01-01T00:00:00+00:00"
PDF_BYTES = b"%PDF-1.4 test"


def _entity(db_path, name, type="internal", parent_id=None):
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute(
            "INSERT INTO entities (name, type, parent_id, is_default, color, position, created_at, updated_at) "
            "VALUES (?, ?, ?, 0, '#000000', 0, ?, ?)",
            (name, type, parent_id, NOW, NOW),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def _submission(tc, entity_id, counterparty_id, **over):
    p = {
        "date": "2026-05-10", "label": "Courses atelier", "description": "Farine",
        "amount": 4550, "category_id": None, "entity_id": entity_id,
        "counterparty_entity_id": counterparty_id, "direction": "expense",
    }
    p.update(over)
    r = tc.post("/api/submissions/", json=p)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _env(db_path, login_as):
    gastro = _entity(db_path, "Gastronomine")
    fournisseur = _entity(db_path, "Fournisseur", type="external")
    tres = login_as("tres-wf@test.local", roles=[(gastro, "treasurer")])
    return gastro, fournisseur, tres


def test_approve_expense_creates_transaction(client_and_db, login_as):
    client, db_path = client_and_db
    gastro, fournisseur, tres = _env(db_path, login_as)
    sid = _submission(tres, gastro, fournisseur)
    r = client.post(f"/api/submissions/{sid}/approve")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "approved"
    assert body["transaction_id"] is not None
    assert body["reviewed_by_name"] == "Admin Test"
    tx = client.get(f"/api/transactions/{body['transaction_id']}").json()
    # Dépense : l'argent sort de l'entité vers la contrepartie.
    assert tx["from_entity_id"] == gastro
    assert tx["to_entity_id"] == fournisseur
    assert tx["amount"] == 4550
    assert tx["label"] == "Courses atelier"
    assert tx["created_by"] == "tres-wf@test.local"


def test_approve_income_swaps_from_to(client_and_db, login_as):
    client, db_path = client_and_db
    gastro, fournisseur, tres = _env(db_path, login_as)
    sid = _submission(tres, gastro, fournisseur, direction="income", label="Subvention")
    tx_id = client.post(f"/api/submissions/{sid}/approve").json()["transaction_id"]
    tx = client.get(f"/api/transactions/{tx_id}").json()
    # Recette : l'argent vient de la contrepartie vers l'entité.
    assert tx["from_entity_id"] == fournisseur
    assert tx["to_entity_id"] == gastro


def test_approve_relinks_attachments(client_and_db, login_as):
    client, db_path = client_and_db
    gastro, fournisseur, tres = _env(db_path, login_as)
    sid = _submission(tres, gastro, fournisseur)
    att = tres.post(
        f"/api/attachments/submission/{sid}",
        files={"file": ("facture.pdf", io.BytesIO(PDF_BYTES), "application/pdf")},
    ).json()
    tx_id = client.post(f"/api/submissions/{sid}/approve").json()["transaction_id"]
    # Le justificatif est maintenant lié à la transaction ET garde son submission_id.
    linked = client.get(f"/api/attachments/transaction/{tx_id}").json()
    assert [a["id"] for a in linked] == [att["id"]]
    assert linked[0]["submission_id"] == sid


def test_approve_guards(client_and_db, login_as):
    client, db_path = client_and_db
    gastro, fournisseur, tres = _env(db_path, login_as)
    sid = _submission(tres, gastro, fournisseur)
    # Un treasurer ne peut pas approuver (garde centrale).
    assert tres.post(f"/api/submissions/{sid}/approve").status_code == 403
    # 404 sur id inconnu.
    assert client.post("/api/submissions/99999/approve").status_code == 404
    # Double approbation -> 409.
    assert client.post(f"/api/submissions/{sid}/approve").status_code == 200
    assert client.post(f"/api/submissions/{sid}/approve").status_code == 409
    # Une soumission annulée ne s'approuve pas.
    sid2 = _submission(tres, gastro, fournisseur)
    tres.post(f"/api/submissions/{sid2}/cancel")
    assert client.post(f"/api/submissions/{sid2}/approve").status_code == 409


def test_approve_closed_fiscal_year_needs_force(client_and_db, login_as):
    client, db_path = client_and_db
    gastro, fournisseur, tres = _env(db_path, login_as)
    # Exercice clôturé couvrant la date de la soumission.
    client.post("/api/budget/fiscal-years", json={"name": "Ex 2026", "start_date": "2026-01-01"})
    fy = client.get("/api/budget/fiscal-years").json()[0]
    client.post(f"/api/budget/fiscal-years/{fy['id']}/close", json={"end_date": "2026-12-31"})
    sid = _submission(tres, gastro, fournisseur)  # date 2026-05-10, dans l'exercice clos
    assert client.post(f"/api/submissions/{sid}/approve").status_code == 409
    r = client.post(f"/api/submissions/{sid}/approve?force=true")
    assert r.status_code == 200


def test_reject_requires_comment(client_and_db, login_as):
    client, db_path = client_and_db
    gastro, fournisseur, tres = _env(db_path, login_as)
    sid = _submission(tres, gastro, fournisseur)
    assert client.post(f"/api/submissions/{sid}/reject", json={"comment": ""}).status_code == 400
    assert client.post(f"/api/submissions/{sid}/reject", json={"comment": "   "}).status_code == 400
    r = client.post(f"/api/submissions/{sid}/reject", json={"comment": "Justificatif illisible"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "rejected"
    assert body["review_comment"] == "Justificatif illisible"
    assert body["transaction_id"] is None
    # Double refus -> 409 ; refus après approbation -> 409 ; 404 sur inconnu.
    assert client.post(f"/api/submissions/{sid}/reject", json={"comment": "encore"}).status_code == 409
    assert client.post("/api/submissions/99999/reject", json={"comment": "x"}).status_code == 404
    # Treasurer -> 403 (garde centrale).
    assert tres.post(f"/api/submissions/{sid}/reject", json={"comment": "x"}).status_code == 403
```

Remarque : si la fermeture d'exercice utilise un autre chemin d'API que `POST /api/budget/fiscal-years/{id}/close`, adapter le test en s'inspirant de `tests/backend/test_fiscal_close.py` (le corps `{"end_date": ...}` y est vérifié).

- [ ] **Step 2 : Vérifier l'échec**

Run : `python -m pytest tests/backend/test_submissions_workflow.py -v` → FAIL (routes absentes).

- [ ] **Step 3 : Implémenter approve et reject**

Dans `backend/modules/submissions/api.py`, ajouter :

```python
def _date_in_closed_period(conn, date: str) -> bool:
    """Copie locale du verrou de clôture de transactions/api.py (pas d'import
    inter-modules : la table peut ne pas exister si le module budget est inactif)."""
    try:
        row = conn.execute(
            """SELECT 1 FROM fiscal_years
               WHERE end_date IS NOT NULL
                 AND ? BETWEEN start_date AND end_date""",
            (date,),
        ).fetchone()
        return row is not None
    except Exception:
        return False


class RejectPayload(BaseModel):
    comment: str


@router.post("/{submission_id}/approve")
def approve_submission(submission_id: int, force: bool = False, admin: dict = Depends(require_admin)):
    """Crée la vraie transaction (from/to déduits de entité + contrepartie +
    direction), re-lie les justificatifs, marque la soumission approuvée.
    Tout est commité en une seule transaction SQLite."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM transaction_submissions WHERE id = ?", (submission_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Soumission {submission_id} introuvable")
        if row["status"] != "pending":
            raise HTTPException(status_code=409, detail="Seule une soumission en attente peut être approuvée")
        if not force and _date_in_closed_period(conn, row["date"]):
            raise HTTPException(status_code=409, detail="Exercice clôturé : approuver quand même ?")
        # Les entités peuvent avoir disparu depuis la soumission (FK OFF).
        for field in ("entity_id", "counterparty_entity_id"):
            if conn.execute("SELECT 1 FROM entities WHERE id = ?", (row[field],)).fetchone() is None:
                raise HTTPException(status_code=400, detail=f"L'entité référencée par {field} n'existe plus")
        if row["direction"] == "expense":
            from_id, to_id = row["entity_id"], row["counterparty_entity_id"]
        else:
            from_id, to_id = row["counterparty_entity_id"], row["entity_id"]
        submitter = conn.execute(
            "SELECT email FROM users WHERE id = ?", (row["submitted_by"],)
        ).fetchone()
        created_by = submitter["email"] if submitter else ""
        now = _now()
        cur = conn.execute(
            """INSERT INTO transactions
               (date, label, description, amount, category_id, contact_id, created_by,
                from_entity_id, to_entity_id, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?)""",
            (row["date"], row["label"], row["description"], row["amount"],
             row["category_id"], created_by, from_id, to_id, now, now),
        )
        tx_id = cur.lastrowid
        # Justificatifs re-liés à la transaction, submission_id conservé (historique).
        conn.execute(
            "UPDATE attachments SET transaction_id = ? WHERE submission_id = ?",
            (tx_id, submission_id),
        )
        conn.execute(
            """UPDATE transaction_submissions
               SET status = 'approved', reviewed_by = ?, reviewed_at = ?,
                   transaction_id = ?, updated_at = ?
               WHERE id = ?""",
            (admin["id"], now, tx_id, now, submission_id),
        )
        data = _fetch_serialized(conn, submission_id)
        conn.commit()
        return data
    finally:
        conn.close()


@router.post("/{submission_id}/reject")
def reject_submission(submission_id: int, payload: RejectPayload, admin: dict = Depends(require_admin)):
    comment = payload.comment.strip()
    if not comment:
        raise HTTPException(status_code=400, detail="Un commentaire est requis pour refuser une soumission")
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT status FROM transaction_submissions WHERE id = ?", (submission_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Soumission {submission_id} introuvable")
        if row["status"] != "pending":
            raise HTTPException(status_code=409, detail="Seule une soumission en attente peut être refusée")
        now = _now()
        conn.execute(
            """UPDATE transaction_submissions
               SET status = 'rejected', reviewed_by = ?, reviewed_at = ?,
                   review_comment = ?, updated_at = ?
               WHERE id = ?""",
            (admin["id"], now, comment, now, submission_id),
        )
        data = _fetch_serialized(conn, submission_id)
        conn.commit()
        return data
    finally:
        conn.close()
```

- [ ] **Step 4 : Vérifier**

Run : `python -m pytest tests/backend/test_submissions_workflow.py tests/backend/test_permissions_matrix.py -v` → PASS.
Run : `python -m pytest tests/backend/ -q` → suite complète verte.

- [ ] **Step 5 : Commit**

```bash
git add backend/modules/submissions/api.py tests/backend/test_submissions_workflow.py
git commit -m "feat(submissions): approbation (transaction creee, justificatifs re-lies) et refus commente"
```

---

### Task 8 : test_coherence_submissions.py — aucune soumission non approuvée n'affecte un solde

**Files:**
- Test: `tests/backend/test_coherence_submissions.py` (nouveau)

**Interfaces:**
- Consumes: tout le module submissions (Tasks 3-7), endpoints existants `/api/entities/{id}/balance`, `/api/dashboard/summary`, `/api/budget/view`, `/api/reports/compte-resultat`, `/api/transactions/`.

- [ ] **Step 1 : Écrire le test de cohérence**

Créer `tests/backend/test_coherence_submissions.py` :

```python
"""Cohérence : une soumission pending/rejected/cancelled n'affecte JAMAIS un
solde, un budget, un rapport ni une liste de transactions. Seule l'approbation
fait entrer le montant en comptabilité."""
import sqlite3

NOW = "2026-01-01T00:00:00+00:00"


def _entity(db_path, name, type="internal", parent_id=None):
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute(
            "INSERT INTO entities (name, type, parent_id, is_default, color, position, created_at, updated_at) "
            "VALUES (?, ?, ?, 0, '#000000', 0, ?, ?)",
            (name, type, parent_id, NOW, NOW),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def _payload(entity_id, counterparty_id, **over):
    p = {
        "date": "2026-05-10", "label": "Soumission test", "description": "",
        "amount": 12345, "category_id": None, "entity_id": entity_id,
        "counterparty_entity_id": counterparty_id, "direction": "expense",
    }
    p.update(over)
    return p


def _snapshot(client, entity_id, fy_id):
    """Photographie tous les agrégats financiers exposés par l'API."""
    return {
        "balance": client.get(f"/api/entities/{entity_id}/balance").json(),
        "consolidated": client.get(f"/api/entities/{entity_id}/consolidated").json(),
        "summary": client.get("/api/dashboard/summary").json(),
        "tx_total": client.get("/api/transactions/").json()["total"],
        "budget_view": client.get(f"/api/budget/view?fiscal_year_id={fy_id}").json(),
        "compte_resultat": client.get(
            f"/api/reports/compte-resultat?fiscal_year_id={fy_id}"
        ).json(),
    }


def test_non_approved_submissions_never_affect_balances(client_and_db, login_as):
    client, db_path = client_and_db
    gastro = _entity(db_path, "Gastronomine")
    fournisseur = _entity(db_path, "Fournisseur", type="external")
    tres = login_as("tres-coh@test.local", roles=[(gastro, "treasurer")])

    # Un exercice ouvert pour donner un cadre au budget et aux rapports.
    client.post("/api/budget/fiscal-years", json={"name": "Exercice test", "start_date": "2026-01-01"})
    fy_id = client.get("/api/budget/fiscal-years").json()[0]["id"]

    # Une transaction réelle de référence pour que le baseline soit non trivial.
    client.post("/api/transactions/", json={
        "date": "2026-02-01", "label": "Référence", "amount": 5000,
        "from_entity_id": gastro, "to_entity_id": fournisseur,
    })

    before = _snapshot(client, gastro, fy_id)

    # 1. Une soumission pending.
    sid_pending = tres.post("/api/submissions/", json=_payload(gastro, fournisseur)).json()["id"]
    # 2. Une soumission refusée.
    sid_rejected = tres.post("/api/submissions/", json=_payload(gastro, fournisseur)).json()["id"]
    client.post(f"/api/submissions/{sid_rejected}/reject", json={"comment": "Non conforme"})
    # 3. Une soumission annulée.
    sid_cancelled = tres.post("/api/submissions/", json=_payload(gastro, fournisseur)).json()["id"]
    tres.post(f"/api/submissions/{sid_cancelled}/cancel")

    after = _snapshot(client, gastro, fy_id)
    assert after == before, "Une soumission non approuvée a modifié un agrégat financier"

    # L'approbation, elle, fait bouger le solde du montant exact.
    client.post(f"/api/submissions/{sid_pending}/approve")
    final = _snapshot(client, gastro, fy_id)
    assert final != before
    assert final["balance"]["balance"] == before["balance"]["balance"] - 12345
    assert final["tx_total"] == before["tx_total"] + 1


def test_submissions_table_never_read_by_balance_queries(client_and_db):
    """Garde-fou statique : balance.py ne référence jamais la table des soumissions."""
    from pathlib import Path
    balance_src = (Path(__file__).parent.parent.parent / "backend" / "core" / "balance.py").read_text(encoding="utf-8")
    assert "transaction_submissions" not in balance_src
```

Remarque : si la clé du solde renvoyé par `/api/entities/{id}/balance` n'est pas `balance` (vérifier dans `backend/modules/entities/api.py` ou `test_balance_core.py`), adapter l'assertion `final["balance"]["balance"]` au vrai nom de champ. Le snapshot par égalité stricte (`after == before`) reste valable quel que soit le schéma.

- [ ] **Step 2 : Exécuter**

Run : `python -m pytest tests/backend/test_coherence_submissions.py -v`
Attendu : PASS directement (c'est un test de non-régression par construction : si ça échoue, il y a un vrai bug à corriger AVANT de continuer, ne pas adapter le test pour le faire passer).

- [ ] **Step 3 : Commit**

```bash
git add tests/backend/test_coherence_submissions.py
git commit -m "test(submissions): coherence, aucune soumission non approuvee n'affecte soldes, budget ni rapports"
```

---

### Task 9 : Frontend — page Soumissions (treasurer) + menu + api.ts

**Files:**
- Modify: `frontend/src/api.ts` (fonctions soumissions)
- Create: `frontend/src/modules/submissions/index.tsx`
- Modify: `frontend/src/routes.tsx` (route `/submissions`)
- Modify: `frontend/src/core/Sidebar.tsx` (MODULE_PATH_MAP)
- Modify: `backend/modules/submissions/manifest.json` (ajout du bloc `menu`)

**Interfaces:**
- Consumes: endpoints Tasks 3-7, `useAuth()` (`user.roles`, `isAdmin`), `api.getEntityTree()` (arbre interne scopé), `api.getEntities("external")` (contreparties), `api.getCategories()`, `formatEuros` (`frontend/src/utils/format.ts`).
- Produces: page `/submissions` avec vue treasurer (formulaire + suivi) ; la vue admin arrive en Task 10 (la page affiche déjà un onglet vide pour l'admin).

- [ ] **Step 1 : Ajouter les fonctions API**

Dans `frontend/src/api.ts`, ajouter au sein de l'objet `api` (après le bloc Tiers / Contacts) :

```ts
  // Soumissions (module submissions)
  createSubmission: (s: any) =>
    request<any>("/submissions/", { method: "POST", body: JSON.stringify(s) }),
  getMySubmissions: () => request<any[]>("/submissions/mine"),
  getSubmissions: (status?: string) =>
    request<any[]>(`/submissions/${status ? `?status=${encodeURIComponent(status)}` : ""}`),
  cancelSubmission: (id: number) =>
    request<any>(`/submissions/${id}/cancel`, { method: "POST" }),
  approveSubmission: (id: number, force = false) =>
    request<any>(`/submissions/${id}/approve${force ? "?force=true" : ""}`, { method: "POST" }),
  rejectSubmission: (id: number, comment: string) =>
    request<any>(`/submissions/${id}/reject`, { method: "POST", body: JSON.stringify({ comment }) }),
  listSubmissionAttachments: (id: number) => request<any[]>(`/attachments/submission/${id}`),
  uploadSubmissionAttachment: async (id: number, file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    const response = await fetch(`${BASE_URL}/attachments/submission/${id}`, { method: "POST", body: formData });
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(error.detail || response.statusText);
    }
    return response.json();
  },
  deleteAttachment: (id: number) => request<any>(`/attachments/${id}`, { method: "DELETE" }),
```

- [ ] **Step 2 : Créer la page**

Créer `frontend/src/modules/submissions/index.tsx`. Contenu complet (vue treasurer ; le composant `AdminQueue` est un placeholder rempli en Task 10) :

```tsx
import { useCallback, useEffect, useMemo, useState } from "react";
import { FileUp, Paperclip, X } from "lucide-react";
import { api } from "../../api";
import { useAuth } from "../../core/AuthContext";
import { formatEuros } from "../../utils/format";

// Libellés français des statuts (design system : chips fond couleur+"20").
export const STATUS_LABELS: Record<string, { label: string; color: string }> = {
  pending: { label: "En attente", color: "#F2C48D" },
  approved: { label: "Approuvée", color: "#00C853" },
  rejected: { label: "Refusée", color: "#FF5252" },
  cancelled: { label: "Annulée", color: "#B0B0B0" },
};

export function StatusChip({ status }: { status: string }) {
  const s = STATUS_LABELS[status] ?? { label: status, color: "#B0B0B0" };
  return (
    <span
      className="text-xs font-medium rounded-full px-2.5 py-0.5"
      style={{ backgroundColor: s.color + "20", color: s.color }}
    >
      {s.label}
    </span>
  );
}

// Aplatis l'arbre interne en gardant seulement les sous-arbres où le user est
// treasurer (l'admin voit tout). L'arbre renvoyé par /entities/tree est déjà
// scopé au périmètre global du user ; on restreint ici aux racines treasurer.
function flattenTreasurerEntities(tree: any[], treasurerRoots: Set<number>, isAdmin: boolean): any[] {
  const out: any[] = [];
  function walk(nodes: any[], depth: number, inScope: boolean) {
    for (const n of nodes) {
      const scoped = isAdmin || inScope || treasurerRoots.has(n.id);
      if (scoped) out.push({ ...n, depth });
      walk(n.children ?? [], scoped ? depth + 1 : depth, scoped);
    }
  }
  walk(tree, 0, false);
  return out;
}

function SubmissionForm({ onCreated }: { onCreated: () => void }) {
  const { user, isAdmin } = useAuth();
  const [entities, setEntities] = useState<any[]>([]);
  const [externals, setExternals] = useState<any[]>([]);
  const [categories, setCategories] = useState<any[]>([]);
  const [files, setFiles] = useState<File[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({
    date: new Date().toISOString().slice(0, 10),
    label: "",
    description: "",
    amount: "",
    category_id: "",
    entity_id: "",
    counterparty_entity_id: "",
    direction: "expense",
  });

  const treasurerRoots = useMemo(
    () => new Set((user?.roles ?? []).filter((r) => r.role === "treasurer").map((r) => r.entity_id)),
    [user],
  );

  useEffect(() => {
    api.getEntityTree().then((tree) => {
      const flat = flattenTreasurerEntities(tree, treasurerRoots, isAdmin);
      setEntities(flat);
      if (flat.length === 1) setForm((f) => ({ ...f, entity_id: String(flat[0].id) }));
    }).catch(() => {});
    api.getEntities("external").then(setExternals).catch(() => {});
    api.getCategories().then(setCategories).catch(() => {});
  }, [treasurerRoots, isAdmin]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const cents = Math.round(parseFloat(form.amount.replace(",", ".")) * 100);
    if (!Number.isFinite(cents) || cents <= 0) {
      setError("Le montant doit être un nombre strictement positif.");
      return;
    }
    setSaving(true);
    try {
      const created = await api.createSubmission({
        date: form.date,
        label: form.label,
        description: form.description,
        amount: cents,
        category_id: form.category_id ? Number(form.category_id) : null,
        entity_id: Number(form.entity_id),
        counterparty_entity_id: Number(form.counterparty_entity_id),
        direction: form.direction,
      });
      for (const file of files) {
        await api.uploadSubmissionAttachment(created.id, file);
      }
      setForm((f) => ({ ...f, label: "", description: "", amount: "" }));
      setFiles([]);
      onCreated();
    } catch (err: any) {
      setError(err?.message || "Erreur lors de la soumission.");
    } finally {
      setSaving(false);
    }
  }

  const inputCls =
    "w-full bg-[#0a0a0a] border border-[#222] rounded-xl px-3 py-2 text-sm text-white " +
    "focus:border-[#F2C48D] focus:outline-none [color-scheme:dark]";

  return (
    <form onSubmit={submit} className="bg-[#111] border border-[#222] rounded-2xl p-6 space-y-4">
      <h2 className="text-sm font-semibold text-white">Soumettre une dépense ou une recette</h2>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-xs uppercase tracking-wider text-[#666]">Sens</label>
          <select className={inputCls} value={form.direction}
            onChange={(e) => setForm({ ...form, direction: e.target.value })}>
            <option value="expense">Dépense</option>
            <option value="income">Recette</option>
          </select>
        </div>
        <div>
          <label className="text-xs uppercase tracking-wider text-[#666]">Date</label>
          <input type="date" required className={inputCls} value={form.date}
            onChange={(e) => setForm({ ...form, date: e.target.value })} />
        </div>
      </div>
      <div>
        <label className="text-xs uppercase tracking-wider text-[#666]">Libellé</label>
        <input required maxLength={200} className={inputCls} value={form.label}
          placeholder="Ex : courses pour l'atelier cuisine"
          onChange={(e) => setForm({ ...form, label: e.target.value })} />
      </div>
      <div>
        <label className="text-xs uppercase tracking-wider text-[#666]">Description (facultatif)</label>
        <textarea rows={2} className={inputCls} value={form.description}
          onChange={(e) => setForm({ ...form, description: e.target.value })} />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-xs uppercase tracking-wider text-[#666]">Montant (€)</label>
          <input required inputMode="decimal" placeholder="45,50" className={inputCls} value={form.amount}
            onChange={(e) => setForm({ ...form, amount: e.target.value })} />
        </div>
        <div>
          <label className="text-xs uppercase tracking-wider text-[#666]">Catégorie</label>
          <select className={inputCls} value={form.category_id}
            onChange={(e) => setForm({ ...form, category_id: e.target.value })}>
            <option value="">Aucune</option>
            {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-xs uppercase tracking-wider text-[#666]">Entité</label>
          <select required className={inputCls} value={form.entity_id}
            onChange={(e) => setForm({ ...form, entity_id: e.target.value })}>
            <option value="">Choisir…</option>
            {entities.map((en) => (
              <option key={en.id} value={en.id}>{" ".repeat(en.depth * 2)}{en.name}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="text-xs uppercase tracking-wider text-[#666]">Contrepartie (tiers)</label>
          <select required className={inputCls} value={form.counterparty_entity_id}
            onChange={(e) => setForm({ ...form, counterparty_entity_id: e.target.value })}>
            <option value="">Choisir…</option>
            {externals.map((ex) => <option key={ex.id} value={ex.id}>{ex.name}</option>)}
          </select>
        </div>
      </div>
      <div>
        <label className="text-xs uppercase tracking-wider text-[#666]">Justificatifs (PDF, images)</label>
        <input type="file" multiple accept=".pdf,image/*"
          className="block w-full text-sm text-[#B0B0B0] file:mr-3 file:rounded-full file:border-0 file:bg-[#222] file:px-3 file:py-1.5 file:text-sm file:text-white"
          onChange={(e) => setFiles(Array.from(e.target.files ?? []))} />
        {files.length > 0 && (
          <p className="mt-1 text-xs text-[#666]">{files.length} fichier(s) sélectionné(s)</p>
        )}
      </div>
      {error && <p className="text-sm text-[#FF5252]">{error}</p>}
      <button type="submit" disabled={saving}
        className="rounded-full bg-[#F2C48D] px-5 py-2 text-sm font-semibold text-black hover:bg-[#e8b87a] transition-colors disabled:opacity-50">
        {saving ? "Envoi…" : "Soumettre"}
      </button>
    </form>
  );
}

function AttachmentLinks({ submissionId }: { submissionId: number }) {
  const [items, setItems] = useState<any[]>([]);
  useEffect(() => {
    api.listSubmissionAttachments(submissionId).then(setItems).catch(() => {});
  }, [submissionId]);
  if (items.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-2 mt-1">
      {items.map((a) => (
        <a key={a.id} href={`/api/attachments/${a.id}/preview`} target="_blank" rel="noreferrer"
          className="inline-flex items-center gap-1 text-xs text-[#B0B0B0] hover:text-white">
          <Paperclip size={12} /> {a.original_name}
        </a>
      ))}
    </div>
  );
}

function MySubmissions({ refreshKey }: { refreshKey: number }) {
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    api.getMySubmissions().then(setItems).catch(() => {}).finally(() => setLoading(false));
  }, []);
  useEffect(load, [load, refreshKey]);

  async function cancel(id: number) {
    await api.cancelSubmission(id);
    load();
  }

  if (loading) return null;
  if (items.length === 0) {
    return (
      <p className="text-sm text-[#666]">
        Aucune soumission pour l'instant. Votre première demande apparaîtra ici avec son statut.
      </p>
    );
  }
  return (
    <div className="bg-[#111] border border-[#222] rounded-2xl overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-xs uppercase tracking-wider text-[#666] text-left">
            <th className="px-4 py-3">Date</th>
            <th className="px-4 py-3">Libellé</th>
            <th className="px-4 py-3">Entité</th>
            <th className="px-4 py-3 text-right">Montant</th>
            <th className="px-4 py-3">Statut</th>
            <th className="px-4 py-3" />
          </tr>
        </thead>
        <tbody>
          {items.map((s) => (
            <tr key={s.id} className="border-t border-[#1a1a1a] hover:bg-[#1a1a1a]">
              <td className="px-4 py-3 text-[#B0B0B0]">{s.date}</td>
              <td className="px-4 py-3 text-white">
                {s.label}
                <AttachmentLinks submissionId={s.id} />
                {s.status === "rejected" && s.review_comment && (
                  <p className="text-xs text-[#FF5252] mt-1">Motif du refus : {s.review_comment}</p>
                )}
              </td>
              <td className="px-4 py-3 text-[#B0B0B0]">{s.entity_name}</td>
              <td className="px-4 py-3 text-right font-semibold"
                style={{ color: s.direction === "income" ? "#00C853" : "#FF5252" }}>
                {formatEuros(s.amount)}
              </td>
              <td className="px-4 py-3"><StatusChip status={s.status} /></td>
              <td className="px-4 py-3 text-right">
                {s.status === "pending" && (
                  <button onClick={() => cancel(s.id)} title="Annuler cette soumission"
                    className="text-[#666] hover:text-white transition-colors">
                    <X size={15} />
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// Rempli en Task 10 (file de validation admin).
function AdminQueue() {
  return null;
}

export default function SubmissionsPage() {
  const { isAdmin } = useAuth();
  const [refreshKey, setRefreshKey] = useState(0);

  return (
    <div className="p-8 max-w-4xl space-y-6">
      <div className="flex items-center gap-3">
        <FileUp size={22} className="text-[#F2C48D]" strokeWidth={1.5} />
        <h1 className="text-3xl font-bold text-white" style={{ letterSpacing: "-0.02em" }}>
          Soumissions
        </h1>
      </div>
      {isAdmin ? (
        <AdminQueue />
      ) : (
        <>
          <SubmissionForm onCreated={() => setRefreshKey((k) => k + 1)} />
          <div className="space-y-2">
            <h2 className="text-xs uppercase tracking-wider text-[#666]">Mes soumissions</h2>
            <MySubmissions refreshKey={refreshKey} />
          </div>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 3 : Brancher route, sidebar et manifest**

`frontend/src/routes.tsx` :
- ajouter le lazy import : `const SubmissionsPage = lazy(() => import("./modules/submissions/index"));`
- ajouter dans `MODULE_ROUTES` : `submissions: { path: "/submissions", element: <Page><SubmissionsPage /></Page> },`

`frontend/src/core/Sidebar.tsx` : ajouter dans `MODULE_PATH_MAP` :

```ts
  submissions: "/submissions",
```

`backend/modules/submissions/manifest.json` : ajouter le bloc `menu` (après `"dependencies"`) :

```json
  "menu": {
    "label": "Soumissions",
    "icon": "file-up",
    "position": 4
  },
```

(`file-up` existe déjà dans `ICON_MAP` de Sidebar.tsx.)

- [ ] **Step 4 : Vérifier**

```bash
python tools/check.py
cd frontend && npm run build
```

Attendu : check PASS (menu + frontend présents), build sans erreur TypeScript.

Run : `python -m pytest tests/backend/test_ui_text_coherence.py tests/backend/test_module_loader.py -v` → PASS.

- [ ] **Step 5 : Commit**

```bash
git add frontend/src/api.ts frontend/src/modules/submissions frontend/src/routes.tsx frontend/src/core/Sidebar.tsx backend/modules/submissions/manifest.json
git commit -m "feat(front): page Soumissions pour tresorier (formulaire, justificatifs, suivi, annulation)"
```

---

### Task 10 : Frontend — file de validation admin + badge sidebar

**Files:**
- Modify: `frontend/src/modules/submissions/index.tsx` (remplir `AdminQueue`)
- Modify: `frontend/src/core/Sidebar.tsx` (badge de comptage)

**Interfaces:**
- Consumes: `api.getSubmissions("pending")`, `api.approveSubmission`, `api.rejectSubmission`, `StatusChip`, `AttachmentLinks` (Task 9).
- Produces: vue admin complète, badge doré sur l'entrée « Soumissions » de la sidebar (comptage des pending, admin uniquement).

- [ ] **Step 1 : Remplacer le placeholder AdminQueue**

Dans `frontend/src/modules/submissions/index.tsx`, remplacer `function AdminQueue() { return null; }` par :

```tsx
function AdminQueue() {
  const [tab, setTab] = useState<"pending" | "all">("pending");
  const [items, setItems] = useState<any[]>([]);
  const [rejectingId, setRejectingId] = useState<number | null>(null);
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    const p = tab === "pending" ? api.getSubmissions("pending") : api.getSubmissions();
    p.then(setItems).catch(() => {});
  }, [tab]);
  useEffect(load, [load]);

  async function approve(id: number) {
    setError(null);
    try {
      await api.approveSubmission(id);
    } catch (err: any) {
      // Verrou d'exercice clôturé : on propose de forcer.
      if (String(err?.message || "").includes("Exercice clôturé")) {
        if (window.confirm("Exercice clôturé : approuver quand même ?")) {
          await api.approveSubmission(id, true);
        }
      } else {
        setError(err?.message || "Erreur lors de l'approbation.");
        return;
      }
    }
    load();
  }

  async function reject(id: number) {
    setError(null);
    try {
      await api.rejectSubmission(id, comment);
      setRejectingId(null);
      setComment("");
      load();
    } catch (err: any) {
      setError(err?.message || "Erreur lors du refus.");
    }
  }

  const tabCls = (active: boolean) =>
    `px-4 py-1.5 rounded-full text-sm font-medium transition-colors ${
      active ? "bg-[#F2C48D] text-black" : "text-[#666] hover:text-white"
    }`;

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        <button className={tabCls(tab === "pending")} onClick={() => setTab("pending")}>
          File de validation
        </button>
        <button className={tabCls(tab === "all")} onClick={() => setTab("all")}>
          Historique
        </button>
      </div>
      {error && <p className="text-sm text-[#FF5252]">{error}</p>}
      {items.length === 0 ? (
        <p className="text-sm text-[#666]">
          {tab === "pending"
            ? "Aucune soumission en attente de validation."
            : "Aucune soumission enregistrée."}
        </p>
      ) : (
        <div className="space-y-3">
          {items.map((s) => (
            <div key={s.id} className="bg-[#111] border border-[#222] rounded-2xl p-5 space-y-2">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-white font-medium">{s.label}</p>
                  <p className="text-xs text-[#666]">
                    {s.date} · {s.entity_name} → {s.counterparty_name}
                    {s.category_name ? ` · ${s.category_name}` : ""} · par {s.submitted_by_name || s.submitted_by_email}
                  </p>
                  {s.description && <p className="text-sm text-[#B0B0B0] mt-1">{s.description}</p>}
                  <AttachmentLinks submissionId={s.id} />
                  {s.status === "rejected" && s.review_comment && (
                    <p className="text-xs text-[#FF5252] mt-1">Motif du refus : {s.review_comment}</p>
                  )}
                </div>
                <div className="text-right flex-shrink-0">
                  <p className="font-semibold"
                    style={{ color: s.direction === "income" ? "#00C853" : "#FF5252" }}>
                    {s.direction === "income" ? "+" : "-"}{formatEuros(s.amount)}
                  </p>
                  <div className="mt-1"><StatusChip status={s.status} /></div>
                </div>
              </div>
              {s.status === "pending" && (
                rejectingId === s.id ? (
                  <div className="flex items-center gap-2 pt-1">
                    <input autoFocus value={comment} placeholder="Motif du refus (obligatoire)"
                      className="flex-1 bg-[#0a0a0a] border border-[#222] rounded-xl px-3 py-2 text-sm text-white focus:border-[#F2C48D] focus:outline-none"
                      onChange={(e) => setComment(e.target.value)} />
                    <button onClick={() => reject(s.id)} disabled={!comment.trim()}
                      className="rounded-full bg-[#FF5252] px-4 py-2 text-sm font-semibold text-black disabled:opacity-40">
                      Refuser
                    </button>
                    <button onClick={() => { setRejectingId(null); setComment(""); }}
                      className="text-sm text-[#666] hover:text-white">
                      Annuler
                    </button>
                  </div>
                ) : (
                  <div className="flex gap-2 pt-1">
                    <button onClick={() => approve(s.id)}
                      className="rounded-full bg-[#F2C48D] px-4 py-2 text-sm font-semibold text-black hover:bg-[#e8b87a] transition-colors">
                      Approuver
                    </button>
                    <button onClick={() => setRejectingId(s.id)}
                      className="rounded-full border border-[#333] px-4 py-2 text-sm text-white hover:border-[#555] transition-colors">
                      Refuser…
                    </button>
                  </div>
                )
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2 : Badge de comptage dans la sidebar (admin)**

Dans `frontend/src/core/Sidebar.tsx`, dans le composant `Sidebar`, récupérer `isAdmin` (remplacer `const { user } = useAuth();` par `const { user, isAdmin } = useAuth();`) puis ajouter, après le bloc du badge budget :

```tsx
  const [pendingSubmissions, setPendingSubmissions] = useState(0);
  const submissionsActive = activeModules.some((m) => m.id === "submissions");
  useEffect(() => {
    if (!submissionsActive || !isAdmin) { setPendingSubmissions(0); return; }
    let cancelled = false;
    api.getSubmissions("pending")
      .then((d) => { if (!cancelled) setPendingSubmissions(Array.isArray(d) ? d.length : 0); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [submissionsActive, isAdmin]);
```

Et dans le mapping `optionalItems`, compléter les deux ternaires :

```tsx
    badge:
      m.id === "reimbursements" ? pendingReimbursements :
      m.id === "budget" ? budgetBadge :
      m.id === "submissions" ? pendingSubmissions :
      undefined,
    badgeTitle:
      m.id === "reimbursements" ? "Avances en attente de remboursement" :
      m.id === "budget" ? "Entités ayant atteint 95 % de leur budget alloué" :
      m.id === "submissions" ? "Soumissions en attente de validation" :
      undefined,
```

- [ ] **Step 3 : Vérifier le build et l'app réelle**

```bash
cd frontend && npm run build
```

Attendu : build sans erreur.

Puis vérification visuelle sur serveur réel (tuer les anciens process d'abord) :

```bash
taskkill /F /IM python.exe 2>nul & taskkill /F /IM node.exe 2>nul
python C:\Users\bloki\Desktop\OpenFlow\openflow\start.py
```

Vérifier avec l'admin (http://127.0.0.1:8000) : l'onglet « Soumissions » apparaît, la file de validation se charge, le badge s'affiche quand une soumission pending existe. Arrêter le serveur ensuite (`taskkill /F /IM python.exe`).

- [ ] **Step 4 : Commit**

```bash
git add frontend/src/modules/submissions/index.tsx frontend/src/core/Sidebar.tsx
git commit -m "feat(front): file de validation admin des soumissions avec badge de comptage"
```

---

### Task 11 : Finalisation — migration réelle, suite complète, documentation, ledger

**Files:**
- Modify: `CLAUDE.md` (15 modules, note submissions, gotcha allowlist à motifs)
- Modify: `.superpowers/sdd/progress.md` (section phase 2)
- Modify: `docs/superpowers/specs/2026-07-04-multi-utilisateurs-design.md` (statut phase 2 si un statut y est tenu)

- [ ] **Step 1 : Migration et intégrité sur la base réelle**

```bash
cd C:\Users\bloki\Desktop\OpenFlow\openflow
python tools/migrate.py
python tools/check.py
```

Attendu : migration `submissions 1.0.0` et `attachments 1.1.0` appliquées, check PASS.

- [ ] **Step 2 : Suite complète**

```bash
python -m pytest tests/ -v
```

Attendu : 100 % vert (504 tests existants + les nouveaux). En cas d'échec : diagnostiquer et corriger, ne jamais ignorer.

- [ ] **Step 3 : Mettre à jour CLAUDE.md**

- Section « 14 modules disponibles » → « 15 modules disponibles », ajouter `submissions` à la liste métier : `**Metier (7) :** reimbursements, budget, tiers, reports, helloasso, direns, submissions`.
- Dans « Gotchas », compléter la puce auth : après « ...utiliser login_as(email, roles=[...]) pour tester treasurer/viewer. », ajouter : « Les mutations non-admin à chemin paramétré (annulation de soumission, justificatifs de soumission) passent par NON_ADMIN_MUTATION_PATTERNS (regex) dans auth.py, avec vérification fine (propriétaire, statut pending) dans l'endpoint. Les GET admin-only (file de validation /api/submissions/) portent Depends(require_admin) explicitement. »
- Ajouter une courte section « Soumissions » après « Budget & Exercices » :

```markdown
## Soumissions

Le module `submissions` (1.0.0) porte le workflow treasurer → admin :
table `transaction_submissions` séparée (JAMAIS de statut sur `transactions`),
approbation = création d'une vraie transaction (from/to déduits de
entité + contrepartie + direction) et re-liaison des justificatifs
(`attachments.submission_id`, conservé pour l'historique).
`test_coherence_submissions.py` garantit qu'une soumission non approuvée
n'affecte jamais un solde, un budget ni un rapport.
```

- Mettre à jour le compte de tests dans « Commands » (`python -m pytest tests/ -v` : remplacer « 435 tests » par le nombre réel observé au Step 2).

- [ ] **Step 4 : Ledger**

Ajouter à `.superpowers/sdd/progress.md` une section :

```
---
# Ledger phase 2 submissions — plan docs/superpowers/plans/2026-07-05-multi-utilisateurs-phase2-submissions.md
(une ligne par tâche au fil de l'exécution)
```

- [ ] **Step 5 : Commit final**

```bash
git add CLAUDE.md .superpowers/sdd/progress.md docs/superpowers/plans/2026-07-05-multi-utilisateurs-phase2-submissions.md
git commit -m "docs(submissions): CLAUDE.md 15 modules, ledger phase 2"
```

Ne PAS merger dans main sans validation explicite de Vicente (skill superpowers:finishing-a-development-branch en fin de chantier).

---

## Auto-revue du plan (faite à la rédaction)

- **Couverture spec phase 2** : table à part ✔ (Task 1), soumission treasurer périmètre strict ✔ (Tasks 2-3), justificatif PDF via attachments + submission_id nullable ✔ (Task 6), annulation pending ✔ (Task 5), approbation avec transaction from/to déduits + re-liaison ✔ (Task 7), refus commenté ✔ (Task 7), cohérence soldes/budget/rapports ✔ (Task 8), allowlist garde centrale + GET admin-only explicites ✔ (Tasks 2, 4, 6), frontend treasurer + file admin + badge ✔ (Tasks 9-10), manifest/check.py ✔ (Tasks 1, 9), tests par endpoint + suite verte ✔ (toutes).
- **Cohérence des noms inter-tâches** : `_fetch_serialized`/`_SELECT` (3→4,5,7), `is_non_admin_mutation`/`NON_ADMIN_MUTATION_PATTERNS` (2→6), `STATUS_LABELS`/`StatusChip`/`AttachmentLinks` (9→10), `api.getSubmissions` (9→10, Sidebar).
- **Points d'attention signalés aux exécutants** : clé exacte du solde dans le snapshot (Task 8), chemin exact de clôture d'exercice (Task 7), interdiction de `git add -A` (working tree sale), manifest sans `menu` jusqu'à la Task 9.
