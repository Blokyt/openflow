# OpenFlow - Design Spec

## 1. Vision

OpenFlow est un outil de gestion de tresorerie generique, modulaire et local. Il s'adapte a toute structure (association, entreprise, auto-entrepreneur) via un systeme de modules activables. Le skill `/openflow` agit comme assistant intelligent pour configurer, faire evoluer et diagnostiquer l'application.

**Nom** : OpenFlow
**Skill** : `/openflow`
**Premier cas d'application** : BDA Mines Paris (association etudiante)

## 2. Stack technique

| Composant | Choix | Justification |
|-----------|-------|---------------|
| Backend | Python + FastAPI | Leger, connu de l'utilisateur, facile a modifier par le skill |
| Frontend | React (Vite) | Composants modulaires, dynamisme (drag & drop, edition inline) |
| Base de donnees | SQLite (fichier unique `openflow.db`) | Zero config, backup = copier le fichier |
| Lancement | `python start.py` | Lance FastAPI + sert le build React, ouvre le navigateur |

App 100% locale, mono-fichier DB, pas de serveur externe.

**Build React** : le skill execute `npm run build` quand il modifie le frontend. `start.py` sert le build statique existant via FastAPI (`StaticFiles`). L'utilisateur ne voit jamais npm/node. En mode developpement (skill qui travaille), Vite dev server tourne separement.

## 3. Architecture du projet

```
openflow/
├── backend/
│   ├── main.py                     # Point d'entree FastAPI
│   ├── core/
│   │   ├── config.py               # Charge/sauve config.yaml
│   │   ├── database.py             # Connexion SQLite, session
│   │   ├── module_loader.py        # Decouvre et charge les modules actifs
│   │   ├── validator.py            # Verifie integrite modules/manifests
│   │   └── models.py               # Tables systeme (_config, _modules, _audit_log, _dashboard)
│   └── modules/
│       ├── transactions/           # Module noyau
│       ├── categories/             # Module noyau
│       └── dashboard/              # Module noyau
├── frontend/
│   ├── src/
│   │   ├── App.tsx                 # Shell principal
│   │   ├── core/
│   │   │   ├── ModuleLoader.tsx    # Charge dynamiquement les composants modules
│   │   │   ├── Dashboard.tsx       # Grille de widgets configurable
│   │   │   ├── Settings.tsx        # Page parametres/modules (toggles on/off)
│   │   │   └── Sidebar.tsx         # Navigation generee depuis les manifests
│   │   └── modules/
│   │       ├── transactions/
│   │       ├── categories/
│   │       └── dashboard/
│   ├── package.json
│   └── vite.config.ts
├── tools/
│   ├── create_module.py            # Scaffolde un nouveau module
│   ├── check.py                    # Verifie integrite globale
│   ├── migrate.py                  # Applique les migrations DB avec backup auto
│   └── schemas/
│       └── manifest.schema.json    # JSON Schema du manifest
├── config.yaml                     # Configuration globale
├── data/
│   ├── openflow.db                 # Base SQLite unique
│   └── attachments/                # Pieces jointes
└── start.py                        # Lance tout
```

## 4. Systeme de modules

### 4.1 Principe

Chaque module = un dossier autonome dans `backend/modules/` et `frontend/src/modules/` avec un `manifest.json` qui declare tout. Le systeme central scanne les modules actifs et branche routes API, composants React, widgets dashboard et entrees menu automatiquement.

### 4.2 Manifest standardise

Chaque module DOIT contenir un `manifest.json` valide contre `tools/schemas/manifest.schema.json` :

```json
{
  "id": "invoices",
  "name": "Factures & Devis",
  "description": "Emettre et suivre factures et devis",
  "version": "1.0.0",
  "origin": "builtin",
  "category": "standard",
  "dependencies": ["transactions", "tiers"],
  "menu": {
    "label": "Factures",
    "icon": "file-text",
    "position": 4
  },
  "api_routes": ["api.py"],
  "db_models": ["models.py"],
  "dashboard_widgets": [
    {
      "id": "unpaid_invoices",
      "name": "Factures impayees",
      "component": "widgets/UnpaidInvoices.tsx",
      "default_visible": true,
      "size": "half"
    }
  ],
  "settings_schema": {
    "auto_numbering": { "type": "boolean", "default": true },
    "prefix": { "type": "string", "default": "FAC-" },
    "default_due_days": { "type": "integer", "default": 30 }
  }
}
```

Champs cles :
- `origin` : `"builtin"` (livre de base) ou `"custom"` (cree par le skill pour l'utilisateur)
- `dependencies` : modules requis, actives automatiquement si necessaire
- `settings_schema` : config propre au module, editable dans l'interface Parametres

### 4.3 Cycle de vie

```
Creation (skill ou create_module.py)
  → Validation (check.py contre JSON Schema)
    → Activation (config.yaml + migration DB)
      → Chargement (module_loader au demarrage)
        → Utilisation (app)
          → Desactivation (tables conservees, module masque)
```

- Activation : cree les tables, ajoute au menu
- Desactivation : masque le module, conserve les donnees, l'utilisateur peut reactiver
- Mise a jour : migrations versionnees dans models.py, backup auto du .db avant chaque migration

### 4.4 Structure d'un module

```
modules/<module_id>/
├── manifest.json       # Declaration du module
├── models.py           # Tables SQLite + migrations versionnees
├── api.py              # Endpoints FastAPI
└── (frontend correspondant dans frontend/src/modules/<module_id>/)
    ├── index.tsx        # Composant principal / page
    ├── components/      # Sous-composants
    └── widgets/         # Widgets dashboard
```

### 4.5 Chargement automatique

**Backend (`module_loader.py`)** :
1. Scanne `backend/modules/`
2. Lit chaque `manifest.json`
3. Verifie que le module est actif dans `config.yaml`
4. Verifie que les dependances sont satisfaites
5. Execute les migrations si la version a change
6. Enregistre les routes API dans FastAPI
7. Expose la liste des modules actifs via `GET /api/modules`

**Frontend (`ModuleLoader.tsx`)** :
1. Appelle `GET /api/modules` au demarrage
2. Charge dynamiquement les composants des modules actifs
3. Genere le menu de navigation dans la Sidebar
4. Rend disponibles les widgets sur le Dashboard

## 5. Base de donnees

### 5.1 Un seul fichier

Toutes les tables dans `data/openflow.db`. La separation modulaire se fait au niveau du code, pas au niveau des fichiers.

### 5.2 Tables systeme (core)

```sql
_config         -- Parametres globaux (cle/valeur)
_modules        -- Modules installes : id, version, active, installed_at
_audit_log      -- Journal immuable : who, action, table, record_id, old_value, new_value, timestamp
_dashboard      -- Layout widgets : widget_id, module_id, position_x, position_y, size, visible
```

### 5.3 Migrations versionnees

Chaque module declare ses migrations dans `models.py` :

```python
migrations = {
    "1.0.0": ["CREATE TABLE invoices (...)"],
    "1.1.0": ["ALTER TABLE invoices ADD COLUMN due_date DATE"],
}
```

Le systeme compare la version installee (table `_modules`) vs la version du manifest et execute les migrations manquantes dans l'ordre. Backup automatique du `.db` avant toute migration.

### 5.4 Integrite

`check.py` verifie :
- Pas de conflit de noms de tables entre modules
- Toutes les tables declarees existent dans la DB
- Les cles etrangeres cross-modules sont valides
- Coherence versions manifest vs versions installees

## 6. Solde de reference

Le solde est defini a une date fixe dans `config.yaml` :

```yaml
balance:
  date: "2025-06-01"
  amount: 3200.00
```

Solde a n'importe quelle date = `balance.amount + SUM(transactions.amount WHERE date > balance.date AND date <= date_cible)`

Tout se reconstruit dynamiquement a partir de ce point de reference.

## 7. Configuration globale

Fichier `config.yaml` a la racine :

```yaml
entity:
  name: "BDA Mines Paris"
  type: "association"
  currency: "EUR"
  logo: "data/logo.png"
  address: "60 bd Saint-Michel, 75006 Paris"
  siret: ""
  rna: "W751234567"

balance:
  date: "2025-06-01"
  amount: 3200.00

modules:
  transactions: true
  categories: true
  dashboard: true
  invoices: true
  reimbursements: true
  budget: false
  divisions: true
  tiers: true
  attachments: false
  annotations: false
  export: true
  bank_reconciliation: false
  recurring: false
  multi_accounts: false
  audit: false
  forecasting: false
  alerts: false
  tax_receipts: false
  grants: false
  fec_export: false
  multi_users: false
```

Modifiable via l'interface (page Parametres) ou via le skill.

## 8. Interface utilisateur

### 8.1 Layout unique

Identique pour tous les utilisateurs :
- **Sidebar gauche** : navigation generee automatiquement depuis les manifests des modules actifs
- **Zone principale** : contenu de la page/module selectionne
- **Header** : nom de l'entite, solde actuel, notifications (si module alertes actif)

### 8.2 Dashboard personnalisable

- Grille de widgets drag & drop
- Chaque module actif propose ses widgets
- L'utilisateur choisit lesquels afficher, ou les placer, quelle taille
- Layout sauvegarde dans la table `_dashboard`

**Widgets noyau** (toujours disponibles) :
- Solde actuel
- Entrees/Sorties par periode (graphique barres)
- Repartition par categorie (camembert)
- Dernieres transactions

### 8.3 Page Parametres

- **Onglet Modules** : toggles on/off pour chaque module, description, indicateur de dependances
- **Onglet Entite** : nom, type, devise, logo, adresses
- **Onglet Solde** : date et montant de reference
- **Onglet par module** : settings specifiques definis dans `settings_schema` du manifest

## 9. Import de donnees

### 9.1 Import intelligent (via le skill, au setup)

Le skill analyse les fichiers Excel/CSV de l'utilisateur :
- Detecte les colonnes (date, montant, libelle, categorie...)
- Propose un mapping colonnes → champs OpenFlow
- Nettoie les donnees (formats de date, montants, doublons)
- Cree les categories automatiquement
- Importe dans la DB

Ce processus utilise le LLM pour comprendre des structures variees et desordonnees.

### 9.2 Import strict (dans l'app, en fonctionnement)

- Template CSV/Excel telechargeable avec les colonnes attendues
- Validation stricte : format incorrect = rejet avec message d'erreur explicite
- Code deterministe, pas de LLM
- Disponible dans chaque module qui le necessite

## 10. Scripts deterministes (tools/)

### 10.1 `create_module.py <module_id>`

Scaffolde un nouveau module :
- Cree le dossier `backend/modules/<id>/` avec manifest.json, models.py, api.py
- Cree le dossier `frontend/src/modules/<id>/` avec index.tsx, components/, widgets/
- Pre-remplit le manifest avec les valeurs par defaut
- Valide contre le JSON Schema

### 10.2 `check.py`

Verification d'integrite globale :
- Valide tous les manifests contre le JSON Schema
- Verifie que les fichiers declares dans les manifests existent
- Verifie que les dependances sont satisfaites (pas de cycle, pas de manque)
- Detecte les conflits de routes API entre modules
- Detecte les conflits de noms de tables entre modules
- Verifie la coherence DB (tables attendues vs tables presentes)
- Retourne PASS ou FAIL avec details

### 10.3 `migrate.py`

Applique les migrations :
- Backup automatique de `openflow.db` avant toute modification
- Compare versions installees vs versions des manifests
- Execute les migrations manquantes dans l'ordre
- Met a jour la table `_modules`

## 11. Le skill `/openflow`

### 11.1 Mode Init (pas de projet existant)

1. Pose des questions : nom entite, type, devise
2. Propose les modules adaptes au type d'entite
3. Si fichiers Excel existants : analyse LLM + import
4. Genere le projet avec les scripts tools/
5. Lance check.py → validation
6. Lance start.py → ouvre le navigateur

### 11.2 Mode Evolution (projet existant)

1. Lit config.yaml et l'etat des modules
2. Execute la demande : activer/desactiver un module, modifier la config, expliquer une fonctionnalite
3. Utilise les scripts tools/ pour toute modification
4. Lance check.py apres chaque changement
5. Conseille l'utilisateur sur les modules pertinents pour ses besoins

### 11.3 Mode Diagnostic (probleme)

1. Lit la DB, les logs, verifie la coherence
2. Identifie les ecarts ou anomalies
3. Propose et applique la correction
4. Lance check.py pour confirmer la resolution

### 11.4 Mode Creation de module custom

1. Comprend le besoin via questions ciblees
2. Identifie les dependances necessaires
3. Lance create_module.py pour scaffolder
4. Genere la logique metier (models, api, composants React)
5. Lance check.py → verifie l'integration
6. Lance migrate.py → cree les tables
7. Le module custom apparait comme un module natif (`"origin": "custom"`)
8. Le skill memorise ce module pour le maintenir dans les futures conversations

### 11.5 Principes du skill

- Utilise TOUJOURS les scripts tools/ plutot que de modifier manuellement
- Ne modifie JAMAIS la DB directement (passe par les migrations)
- Lance TOUJOURS check.py apres une modification
- Connait la structure du projet par design
- Lit config.yaml pour comprendre l'etat courant

## 12. Catalogue des modules

### 12.1 Noyau (non desactivables)

| Module | Description |
|--------|-------------|
| `transactions` | CRUD, recherche, filtres, tri, edition inline |
| `categories` | Hierarchie parent/enfant, couleurs, icones, drag & drop |
| `dashboard` | Grille widgets personnalisable, widgets noyau (solde, graphiques) |

### 12.2 Standard (activables)

| Module | Description | Dependances |
|--------|-------------|-------------|
| `invoices` | Emission factures/devis PDF, numerotation auto, statuts, conversion devis→facture | transactions, tiers |
| `reimbursements` | Suivi des avances, statuts, vue "qui doit combien" | transactions |
| `budget` | Enveloppes par categorie/division, suivi temps reel, alertes plafond | transactions, categories |
| `divisions` | Sous-groupes (poles, services, projets), bilan par division | transactions |
| `tiers` | Fiches contact, historique, coordonnees | transactions |
| `attachments` | Pieces jointes (scan, photo, PDF) sur les transactions | transactions |
| `annotations` | Notes/commentaires horodates sur les transactions | transactions |
| `export` | Bilans PDF/Excel, rapports filtrables, export CSV | transactions |

### 12.3 Avance (activables)

| Module | Description | Dependances |
|--------|-------------|-------------|
| `bank_reconciliation` | Import releve bancaire, matching auto, marqueur rapproche | transactions |
| `recurring` | Transactions recurrentes, frequences configurables, generation auto | transactions |
| `multi_accounts` | Plusieurs comptes, transferts inter-comptes, solde par compte | transactions |
| `audit` | Journal immuable, tracabilite complete, non modifiable | aucun (core) |
| `forecasting` | Projection cash-flow 1/3/6 mois, scenarios | transactions ; optionnel : recurring, invoices, budget |
| `alerts` | Seuils de solde, echeances, budget epuise, notifications | transactions ; optionnel : invoices, budget |
| `tax_receipts` | Recus fiscaux cerfa pour dons (asso francaise) | tiers |
| `grants` | Suivi subventions, versements, rattachement depenses | transactions, tiers |
| `fec_export` | Fichier des Ecritures Comptables format legal francais | transactions |
| `multi_users` | Roles (admin, tresorier, lecteur), authentification locale | audit |
