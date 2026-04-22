# OpenFlow

## Philosophie

OpenFlow est un outil de tresorerie **ultra-modulaire**. Les modules sont des unites
plug-and-play independantes. Chaque module contient son manifest, son API, ses
migrations et son composant frontend. Ne jamais hardcoder de logique inter-modules
dans le core — les modules se decouvrent dynamiquement via leurs manifests.

**Principe fondamental :** les transactions sont la source de verite. Chaque transaction
a toujours `from_entity_id` ET `to_entity_id` specifies — jamais null. Le solde est
100% dynamique : reference + SUM entrant - SUM sortant par entite.

## Commands

```bash
python setup.py           # Installation complete (deps + build + migrate + check)
python start.py           # Lance l'app → http://127.0.0.1:8000
python tools/check.py     # Valide l'integrite (manifests, fichiers, deps)
python tools/migrate.py   # Applique les migrations DB (backup auto)
python tools/create_module.py <id> --name "Nom" --description "Desc"

pip install -r requirements-dev.txt   # Deps de test
python -m pytest tests/ -v            # 435 tests, ~2.5min

cd frontend && npm run build   # Build prod (Vite + React + Tailwind)
cd frontend && npm run dev     # Dev server HMR sur port 5173
```

## Architecture

```
backend/main.py             — FastAPI app factory, charge les modules actifs
backend/core/database.py    — get_conn() centralise, set_db_path() au demarrage
backend/core/config.py      — Dataclasses AppConfig, load/save YAML
backend/core/balance.py     — Calcul de solde centralise (legacy + entity-aware)
backend/core/module_loader.py — Decouverte modules via manifest.json
backend/core/validator.py   — Validation schema manifest (cache lru)
backend/modules/<id>/       — Un module = manifest.json + api.py + models.py
frontend/src/core/          — Shell (Dashboard, Settings, Sidebar)
frontend/src/modules/       — Composants React par module
tools/                      — Scripts CLI (check, migrate, create_module)
config.example.yaml         — Template config (versionne)
config.yaml                 — Config utilisateur (gitignored, cree par setup.py)
```

## Systeme d'entites

Le module `entities` introduit un arbre d'entites librement hierarchique :

- **Type `internal`** : entites dont on gere la tresorerie (ex: BDA, Gastronomine)
- **Type `external`** : tiers externes (fournisseurs, clients, banque)
- **Hierarchie** : `parent_id` libre, profondeur illimitee
- **Chaque transaction** a `from_entity_id → to_entity_id` (JAMAIS null)
- **Solde propre** : reference + SUM entrant - SUM sortant pour une entite
- **Solde consolide** : propre + tous les descendants (CTE recursive)
- **`entity_balance_refs`** : table de references de solde par entite

Toute la logique de calcul de solde est dans `backend/core/balance.py` :
- `compute_legacy_balance()` — retrocompatibilite pour modules non entity-aware
- `compute_entity_balance()` — solde propre d'une entite
- `compute_consolidated_balance()` — solde consolide avec enfants

## Systeme d'auth

Le module `multi_users` gere l'authentification et les permissions :

- **`users`** : username + password_hash (bcrypt, min 6 chars) + active
- **`sessions`** : cookie httponly, token UUID, supprime a la fermeture navigateur
- **`user_entities`** : `(user_id, entity_id, role)` — role par entite
- **Roles** : `tresorier` (lire + ecrire) ou `lecteur` (consultation seule)
- **Tresorier de la racine = admin** — gere les users, la structure, tout
- **Heritage** : acces a une entite = acces a ses enfants
- Middleware auth actif dans `main.py` quand `multi_users` est active
- Sans users en DB → app ouverte (bootstrap du premier admin)

## Budget & Exercices

Le module `budget` (1.2.0) introduit trois tables :
- `fiscal_years` : tranches d'affichage libres (pas de verrou sur les tx)
- `fiscal_year_opening_balances` : solde bancaire reel par entite interne a l'ouverture
- `budget_allocations` : allocation (entite, categorie optionnelle) = montant

`backend/core/balance.py::compute_entity_balance_for_period` calcule le realise
sur un intervalle de dates pour une entite (± categorie), utilisant la meme
convention de signe que `compute_entity_balance`.

L'endpoint composite `/api/budget/view?fiscal_year_id=X` renvoie la vue
complete (entites + categories + N-1) consommee par la page `/budget` et le
widget dashboard.

Le contexte React `FiscalYearContext` expose `currentYear` et `selectedYear`
(persiste dans `localStorage` sous la cle `openflow_fiscal_year_id`).

## Convention modules

Chaque module = un dossier `backend/modules/<id>/` avec :
- **manifest.json** : id, name, description, help, version, category, dependencies,
  api_routes, db_models, dashboard_widgets, settings_schema
- **api.py** : FastAPI router. Importe `get_conn` depuis `backend.core.database`
- **models.py** : dict `migrations` avec les SQL par version
- **frontend** : composant React dans `frontend/src/modules/<id>/`

Le manifest est la source de verite. Schema dans `tools/schemas/manifest.schema.json`.
Toujours lancer `check.py` apres modification d'un manifest.

Pour creer un module : `python tools/create_module.py <id> --name "..." --description "..."`

## 17 modules disponibles

**Noyau (toujours actifs, 10) :** transactions, categories, dashboard, entities,
system, annotations, attachments, export, audit, fec_export

**Metier (6) :** invoices, reimbursements, budget, tiers, smart_import, backup

**Avance (1) :** multi_users

## Testing

- `conftest.py` build une DB template une fois par session, puis la copie par test
- Chaque test a sa propre DB isolee — jamais de state partage
- Fixture `client` → TestClient avec DB isolee
- Fixture `client_and_db` → (TestClient, db_path) pour acces DB direct
- Les `test_coherence_*.py` verifient les calculs cross-modules
- `test_balance_core.py` et `test_coherence_entities.py` couvrent le systeme d'entites

## Gotchas

- **Pas de SQLAlchemy** : tout est sqlite3 brut via `get_conn()` centralise
- **config.yaml gitignored** : setup.py/start.py le creent depuis config.example.yaml
- **PRAGMA foreign_keys OFF** partout — pas de contraintes FK au runtime
- **Noms de modules dans l'UI** : aucun nom hardcode dans les composants React.
  Tout passe par `manifest.name`, `manifest.help`, `manifest.example`,
  `manifest.menu.label`, ou `INTEGRATED_LOCATIONS` dans `frontend/src/routes.tsx`.
  Le test `tests/backend/test_ui_text_coherence.py` fait tomber CI si une reference
  orpheline apparait.
- **Solde centralise dans balance.py** : ne pas recalculer le solde dans les modules,
  toujours importer depuis `backend.core.balance`
- **from_entity_id / to_entity_id** : toujours specifies sur les transactions — le
  calcul de solde repose dessus. Ne jamais les laisser null en insertion.
