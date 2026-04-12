# OpenFlow — Nettoyage et mise en partage GitHub

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rendre OpenFlow propre, testé et partageable sur GitHub — avec le skill Claude inclus.

**Architecture:** Supprimer le code mort SQLAlchemy, transformer config.yaml en config.example.yaml, ajouter README + LICENSE MIT, mettre à jour le skill pour qu'il gère la config initiale depuis l'exemple, mettre à jour les scripts de vérification, et valider le tout avec les tests.

**Tech Stack:** Python 3, FastAPI, SQLite, React/Vite/Tailwind, pytest

---

### Task 1: Supprimer le code mort SQLAlchemy

**Files:**
- Delete: `backend/core/models.py`
- Delete: `backend/core/database.py`
- Delete: `tests/backend/test_database.py`
- Modify: `requirements.txt`

- [ ] **Step 1: Supprimer `backend/core/models.py`**

Supprimer le fichier entier. Ce fichier contient les classes SQLAlchemy `SystemBase`, `ModuleRecord`, `ConfigRecord`, `DashboardWidget` — jamais importées par le code applicatif (seul `migrate.py` utilise du sqlite3 brut).

- [ ] **Step 2: Supprimer `backend/core/database.py`**

Supprimer le fichier entier. Contient `create_engine_from_path`, `create_system_tables`, `get_session_factory`, `register_module`, `get_module_version` — tout est fait en sqlite3 brut dans `migrate.py`.

- [ ] **Step 3: Supprimer `tests/backend/test_database.py`**

Supprimer le fichier entier. Ce test ne fait que valider le code mort SQLAlchemy.

- [ ] **Step 4: Retirer sqlalchemy de `requirements.txt`**

```
fastapi==0.115.0
uvicorn==0.32.0
pydantic==2.10.0
pyyaml==6.0.2
jsonschema==4.23.0
python-multipart==0.0.12
```

- [ ] **Step 5: Vérifier qu'aucun import ne casse**

Run: `cd openflow && python -c "from backend.main import create_app; print('OK')"`
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add -u backend/core/models.py backend/core/database.py tests/backend/test_database.py requirements.txt
git commit -m "chore: remove unused SQLAlchemy ORM layer"
```

---

### Task 2: config.example.yaml + .gitignore

**Files:**
- Rename: `config.yaml` → `config.example.yaml`
- Modify: `.gitignore`
- Modify: `config.test.yaml` (garder tel quel, déjà gitignore-safe)

- [ ] **Step 1: Copier config.yaml vers config.example.yaml**

Le contenu reste identique — c'est le template de départ pour les nouveaux utilisateurs :

```yaml
entity:
  name: Mon Entite
  type: association
  currency: EUR
  logo: ''
  address: ''
  siret: ''
  rna: ''

balance:
  amount: 0.0
  date: '2025-01-01'

modules:
  transactions: true
  categories: true
  dashboard: true
  alerts: false
  annotations: false
  attachments: false
  audit: false
  bank_reconciliation: false
  budget: false
  divisions: false
  export: false
  fec_export: false
  forecasting: false
  grants: false
  invoices: false
  multi_accounts: false
  multi_users: false
  recurring: false
  reimbursements: false
  tax_receipts: false
  tiers: false
```

- [ ] **Step 2: Ajouter config.yaml au .gitignore**

Ajouter après la section "Data utilisateur" :

```gitignore
# Config utilisateur (chaque instance a sa propre config)
config.yaml
```

- [ ] **Step 3: Supprimer config.yaml du suivi git**

Run: `git rm --cached config.yaml`

Note : le fichier reste sur disque mais n'est plus suivi.

- [ ] **Step 4: Mettre à jour `setup.py` pour copier config.example → config.yaml**

Ajouter une étape 0 dans `setup.py` qui copie `config.example.yaml` vers `config.yaml` si celui-ci n'existe pas :

```python
# 0. Config
config_file = PROJECT_ROOT / "config.yaml"
config_example = PROJECT_ROOT / "config.example.yaml"
if not config_file.exists():
    if config_example.exists():
        import shutil
        shutil.copy2(str(config_example), str(config_file))
        print("  config.yaml cree depuis config.example.yaml")
    else:
        print("  ERREUR: config.example.yaml introuvable")
        sys.exit(1)
else:
    print("  config.yaml deja present")
```

- [ ] **Step 5: Mettre à jour `start.py` pour vérifier config.yaml**

Ajouter au début de `main()` :

```python
config_file = PROJECT_ROOT / "config.yaml"
if not config_file.exists():
    config_example = PROJECT_ROOT / "config.example.yaml"
    if config_example.exists():
        import shutil
        shutil.copy2(str(config_example), str(config_file))
        print("config.yaml cree depuis config.example.yaml")
    else:
        print("ERREUR: config.yaml introuvable. Lancez: python setup.py")
        sys.exit(1)
```

- [ ] **Step 6: Mettre à jour `tools/check.py` pour vérifier config**

Ajouter une vérification dans `main()`, après la vérification du schema, avant la boucle des modules :

```python
# Check config exists
config_path = project / "config.yaml"
config_example_path = project / "config.example.yaml"
if not config_example_path.exists():
    errors.append("config.example.yaml not found at project root")
if not config_path.exists():
    warnings.append("config.yaml not found — run 'python setup.py' or copy config.example.yaml")
```

- [ ] **Step 7: Commit**

```bash
git add config.example.yaml .gitignore setup.py start.py tools/check.py
git rm --cached config.yaml
git commit -m "chore: config.example.yaml + gitignore config.yaml"
```

---

### Task 3: Ajouter pytest et httpx aux dépendances de test

**Files:**
- Modify: `requirements.txt`
- Create: `requirements-dev.txt`

- [ ] **Step 1: Créer `requirements-dev.txt`**

```
-r requirements.txt
pytest==8.3.3
httpx==0.27.2
```

- [ ] **Step 2: Vérifier que les tests passent**

Run: `cd openflow && python -m pytest tests/ -v --tb=short 2>&1 | tail -30`
Expected: tous les tests passent (sauf test_database.py qui a été supprimé à la Task 1)

- [ ] **Step 3: Commit**

```bash
git add requirements-dev.txt
git commit -m "chore: add requirements-dev.txt with pytest and httpx"
```

---

### Task 4: Ajouter la licence MIT

**Files:**
- Create: `LICENSE`

- [ ] **Step 1: Créer le fichier LICENSE**

```
MIT License

Copyright (c) 2026 OpenFlow Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- [ ] **Step 2: Commit**

```bash
git add LICENSE
git commit -m "chore: add MIT license"
```

---

### Task 5: Inclure le skill Claude dans le repo

**Files:**
- Create: `skill/SKILL.md`

- [ ] **Step 1: Créer le dossier `skill/` et copier le skill**

Copier le contenu du skill depuis `~/.claude/skills/openflow/SKILL.md` vers `skill/SKILL.md` dans le repo, avec les modifications suivantes :

**Modifications à apporter au skill :**

1. Dans "Mode Init — Etape 4 : Generation du projet", remplacer l'étape de copie du template par :
```
1. Si `config.yaml` n'existe pas, copie `config.example.yaml` vers `config.yaml`
2. Modifie `config.yaml` avec les choix de l'utilisateur (entity, balance, modules)
3. Lance `python setup.py` pour installer les dependances et initialiser la DB
4. Lance `python tools/check.py` pour valider
5. Lance `python start.py` pour demarrer l'app
```

2. Remplacer la section "Architecture de reference" pour ajouter :
```
├── config.example.yaml         # Template de configuration (ne pas modifier)
├── config.yaml                 # Configuration locale (gitignored, cree par setup.py)
├── skill/
│   └── SKILL.md                # Skill Claude Code pour OpenFlow
├── requirements-dev.txt        # Dependances de dev (pytest, httpx)
```

3. Ajouter une nouvelle section "## Installation du skill Claude" à la fin :
```
## Installation du skill Claude

Pour utiliser l'assistant OpenFlow dans Claude Code :
1. Copier `skill/SKILL.md` vers `~/.claude/skills/openflow/SKILL.md`
2. Ou creer un lien symbolique : `mklink /J "%USERPROFILE%\.claude\skills\openflow" skill\` (Windows)
```

4. Supprimer toute référence au "chemin de reference" vers `C:/Users/bloki/Desktop/BDA/openflow/`.

- [ ] **Step 2: Commit**

```bash
git add skill/SKILL.md
git commit -m "feat: include Claude skill in repository"
```

---

### Task 6: Écrire le README.md

**Files:**
- Create: `README.md`

- [ ] **Step 1: Créer README.md**

```markdown
# OpenFlow

Outil de gestion de tresorerie modulaire. Deployez votre comptabilite depuis un CSV/Excel bordélique vers une app locale avec des modules ultra-personnalisables.

## Quickstart

```bash
# Cloner le repo
git clone https://github.com/<user>/openflow.git
cd openflow

# Installer (Python 3.10+, Node.js 18+)
python setup.py

# Lancer
python start.py
# → http://127.0.0.1:8000
```

## Modules disponibles

| Module | Categorie | Description |
|--------|-----------|-------------|
| transactions | noyau | CRUD, filtres, solde dynamique |
| categories | noyau | Hierarchie parent/enfant |
| dashboard | noyau | Cartes de synthese, widgets |
| invoices | standard | Factures & devis |
| reimbursements | standard | Suivi des avances |
| budget | standard | Enveloppes budgetaires |
| divisions | standard | Poles/services/projets |
| tiers | standard | Contacts client/fournisseur |
| attachments | standard | Pieces jointes |
| annotations | standard | Notes sur transactions |
| export | standard | CSV/JSON/bilan |
| bank_reconciliation | avance | Import releves, matching |
| recurring | avance | Transactions recurrentes |
| multi_accounts | avance | Plusieurs comptes |
| audit | avance | Journal des modifications |
| forecasting | avance | Projection cash-flow |
| alerts | avance | Seuils et echeances |
| tax_receipts | avance | Recus fiscaux cerfa |
| grants | avance | Suivi subventions |
| fec_export | avance | Export FEC legal |
| multi_users | avance | Roles admin/tresorier/lecteur |

Activez/desactivez les modules dans `config.yaml` section `modules`, puis relancez l'app.

## Configuration

A la premiere installation, `setup.py` cree `config.yaml` depuis `config.example.yaml`. Editez-le pour configurer votre entite :

```yaml
entity:
  name: Mon Association
  type: association  # association, entreprise, auto-entrepreneur
  currency: EUR
balance:
  amount: 3200.0     # Solde de reference
  date: '2025-06-01' # A cette date
```

## Skill Claude Code

OpenFlow inclut un skill pour [Claude Code](https://claude.ai/claude-code) qui vous guide dans la configuration, l'import de donnees et l'evolution de votre tresorerie.

Pour l'installer :
1. Copiez `skill/SKILL.md` vers `~/.claude/skills/openflow/SKILL.md`
2. Dans Claude Code, le skill se declenche automatiquement quand vous parlez de tresorerie

## Dev

```bash
# Tests
pip install -r requirements-dev.txt
python -m pytest tests/ -v

# Verifier l'integrite du projet
python tools/check.py

# Creer un module custom
python tools/create_module.py mon_module --name "Mon Module" --description "Description"
```

## License

MIT
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add README"
```

---

### Task 7: Lancer les tests et vérifications finales

**Files:** aucun nouveau fichier

- [ ] **Step 1: Lancer check.py**

Run: `cd openflow && python tools/check.py`
Expected: `Result: PASS` avec 21 modules trouvés

- [ ] **Step 2: Lancer les tests**

Run: `cd openflow && python -m pytest tests/ -v --tb=short 2>&1 | tail -40`
Expected: tous les tests passent

- [ ] **Step 3: Vérifier que l'app démarre**

Run: `cd openflow && timeout 5 python -c "from backend.main import create_app; app = create_app(); print('App OK')" 2>&1`
Expected: `App OK`

- [ ] **Step 4: Commit final si corrections nécessaires**

Si des tests échouent, corriger et commiter.

---

### Task 8: Mettre à jour le skill local

**Files:**
- Modify: `~/.claude/skills/openflow/SKILL.md`

- [ ] **Step 1: Synchroniser le skill local avec la version du repo**

Copier `skill/SKILL.md` (la version mise à jour du repo) vers `~/.claude/skills/openflow/SKILL.md` pour que le skill local soit à jour avec les changements (config.example.yaml, setup.py, etc.).

- [ ] **Step 2: Vérifier que le skill se charge**

Tester en lançant `/openflow` dans une nouvelle session Claude Code.
