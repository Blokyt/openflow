# OpenFlow

## Philosophie

OpenFlow est un outil de tresorerie **ultra-modulaire**. Les modules sont des unites
plug-and-play independantes. Chaque module contient son manifest, son API, ses
migrations et son composant frontend. Ne jamais hardcoder de logique inter-modules
dans le core — les modules se decouvrent dynamiquement via leurs manifests.

## Commands

```bash
python setup.py           # Installation complete (deps + build + migrate + check)
python start.py           # Lance l'app → http://127.0.0.1:8000
python tools/check.py     # Valide l'integrite (manifests, fichiers, deps)
python tools/migrate.py   # Applique les migrations DB (backup auto)
python tools/create_module.py <id> --name "Nom" --description "Desc"

pip install -r requirements-dev.txt   # Deps de test
python -m pytest tests/ -v            # 361 tests, ~2.5min

cd frontend && npm run build   # Build prod (Vite + React + Tailwind)
cd frontend && npm run dev     # Dev server HMR sur port 5173
```

## Architecture

```
backend/main.py             — FastAPI app factory, charge les modules actifs
backend/core/database.py    — get_conn() centralise, set_db_path() au demarrage
backend/core/config.py      — Dataclasses AppConfig, load/save YAML
backend/core/module_loader.py — Decouverte modules via manifest.json
backend/core/validator.py   — Validation schema manifest (cache lru)
backend/modules/<id>/       — Un module = manifest.json + api.py + models.py
frontend/src/core/          — Shell (Dashboard, Settings, Sidebar)
frontend/src/modules/       — Composants React par module
tools/                      — Scripts CLI (check, migrate, create_module)
config.example.yaml         — Template config (versionne)
config.yaml                 — Config utilisateur (gitignored, cree par setup.py)
```

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

## Testing

- `conftest.py` build une DB template une fois par session, puis la copie par test
- Chaque test a sa propre DB isolee — jamais de state partage
- Fixture `client` → TestClient avec DB isolee
- Fixture `client_and_db` → (TestClient, db_path) pour acces DB direct
- Les `test_coherence_*.py` verifient les calculs cross-modules

## Gotchas

- **Pas de SQLAlchemy** : tout est sqlite3 brut via `get_conn()` centralise
- **config.yaml gitignored** : setup.py/start.py le creent depuis config.example.yaml
- **PRAGMA foreign_keys OFF** partout — pas de contraintes FK au runtime
- **MODULE_CATEGORIES dans Settings.tsx** : hardcode le groupement par categorie
  (devrait a terme lire manifest.category dynamiquement)
- **CONFIG_PATH** : certains modules (transactions, dashboard, alerts, forecasting)
  lisent config.yaml directement pour calculer le solde — a centraliser si ca grossit
