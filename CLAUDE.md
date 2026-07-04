# OpenFlow

## Regles d'execution — Claude doit tout faire lui-meme

**Ne jamais demander a l'utilisateur de relancer le serveur, builder le frontend ou lancer les tests.**
Claude execute directement :

- **Apres tout changement backend** → relancer `python dev.py` (ou verifier que le reload a pris)
- **Apres tout changement frontend** → `cd frontend && npm run build` (build prod) ou verifier HMR si dev en cours
- **Apres tout ajout de route ou migration** → `python tools/migrate.py && python tools/check.py`
- **Apres toute nouvelle fonctionnalite** → `python -m pytest tests/ -v` (ou le fichier de test concerne)
- **Toujours tuer les anciens processus** avant de relancer : `taskkill /F /IM python.exe` + `taskkill /F /IM node.exe`
- **Toujours utiliser des chemins absolus** pour `python dev.py` car le CWD peut avoir derive (`cd frontend && ...`)
- dev.py lance uvicorn --reload (port 8000) + npm dev (port 5173 ou suivant si occupe)

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

## 14 modules disponibles

**Noyau (8) :** transactions, categories, dashboard, entities, system, attachments, backup, users

**Metier (6) :** reimbursements, budget, tiers, reports, helloasso, direns

## Testing

**Regle absolue : toute nouvelle fonctionnalite ou endpoint doit avoir ses tests avant
d'etre consideree terminee. Un code sans test n'est pas fonctionnel.**

- Chaque nouvel endpoint API → au moins : 200/201 success, 404 si ressource absente, 400 si payload invalide
- Chaque nouveau champ de reponse → verifier qu'il est present et correct dans les tests
- Chaque comportement metier → un test qui le capture (ex : contact_name dans list_users apres association)
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
- **Snapshot pristine du module `system`** : la page Système affiche les fichiers différents
  du snapshot `install/pristine.zip`. Ce compteur est attendu en rouge pendant le développement
  d'une feature. Régénérer uniquement lors d'une release (bouton "Mettre à jour" ou
  régénération manuelle du ZIP). Ne pas paniquer si 14 fichiers sont marqués modifiés pendant
  un WIP.
- **Auth deny-by-default** : toute route /api exige une session (backend/core/auth.py,
  dépendance globale dans main.py). Les mutations sont réservées à l'admin sauf
  NON_ADMIN_MUTATIONS. En test, les fixtures client/client_and_db sont connectées en
  admin ; utiliser login_as(email, roles=[...]) pour tester treasurer/viewer.
