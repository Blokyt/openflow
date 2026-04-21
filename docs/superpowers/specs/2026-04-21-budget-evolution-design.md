# M1 — Budget évolué : allocation par pôles/clubs avec exercices et comparaison N/N-1

**Date :** 2026-04-21
**Module concerné :** `budget` (refonte)
**Dépendances :** `entities`, `categories`, `transactions`
**Statut :** design validé, à planifier

---

## Contexte et objectifs

Le module `budget` actuel est désactivé et non exploité (table `budgets` vide). Les
besoins exprimés par le trésorier BDA :

- **Allouer des budgets par entité** (pôles, sous-clubs) et optionnellement par
  catégorie (« Gastronomine 2 000 € dont 1 500 € Nourriture »).
- **Définir un exercice budgétaire** avec dates libres (typiquement 1er septembre →
  31 août pour un BDA) et pouvoir en ouvrir plusieurs au fil du temps.
- **Saisir les soldes d'ouverture réels** (relevé bancaire) de chaque entité interne
  au démarrage d'un exercice.
- **Suivre le réalisé** (conso vs alloué, reste, %) et **comparer au même exercice
  N-1** sur le réalisé (pas sur les budgets).
- **Pas de clôture comptable** : les exercices sont des tranches d'affichage, les
  transactions passées restent modifiables.

## Hors scope (volontaire)

- Pas de workflow de validation / soumission (couvert par le futur chantier M10).
- Pas de verrou comptable sur les transactions d'un exercice passé.
- Pas de prévision automatique, pas de ML.
- Pas de rapprochement bancaire (explicitement écarté par l'utilisateur).

---

## Contraintes de cohérence avec le projet

Les règles OpenFlow doivent être respectées :

- **Modularité** : toute logique reste dans `backend/modules/budget/` (api.py,
  models.py, manifest.json) et `frontend/src/modules/budget/`. Pas de logique
  cross-module hardcodée dans le core.
- **`from_entity_id` / `to_entity_id`** : toujours non-null sur les transactions
  (règle déjà enforcée depuis le bug #1 d'avril 2026).
- **Calcul de solde centralisé** : les fonctions dans `backend/core/balance.py`
  sont étendues, pas dupliquées. Nouvelle fonction
  `compute_entity_balance_for_period(conn, entity_id, start, end, opening)` réutilisant
  les patterns existants.
- **Migrations versionnées** : `backend/modules/budget/models.py` passe de 1.1.0 à
  1.2.0 avec les nouvelles tables. L'ancienne table `budgets` est dropée (vide en
  base). `tools/migrate.py` orchestre.
- **Manifest source de vérité** : mise à jour du nom / help / version / dashboard_widgets
  dans `manifest.json`. `tools/check.py` doit passer après modification.
- **Noms d'UI** : pas de chaîne hardcodée dans les composants React — tout passe par
  `manifest.name`, `manifest.menu.label`, etc.

---

## Modèle de données

### Nouvelles tables (migration `1.2.0`)

```sql
DROP TABLE IF EXISTS budgets;  -- table 1.0.0 vide, inutilisée

CREATE TABLE fiscal_years (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,      -- ex "2025-2026"
  start_date TEXT NOT NULL,       -- ex "2025-09-01"
  end_date TEXT NOT NULL,         -- ex "2026-08-31"
  is_current INTEGER DEFAULT 0,   -- un seul à 1 à la fois (enforce API-side)
  notes TEXT DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE fiscal_year_opening_balances (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  fiscal_year_id INTEGER NOT NULL,
  entity_id INTEGER NOT NULL,
  amount REAL NOT NULL,
  source TEXT DEFAULT '',         -- ex "Relevé CE IDF au 2025-08-31"
  notes TEXT DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE (fiscal_year_id, entity_id)
);

CREATE TABLE budget_allocations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  fiscal_year_id INTEGER NOT NULL,
  entity_id INTEGER NOT NULL,
  category_id INTEGER,            -- NULL = enveloppe globale de l'entité
  amount REAL NOT NULL,
  notes TEXT DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE (fiscal_year_id, entity_id, category_id)
);
```

**Règles métier :**

- `category_id IS NULL` dans une allocation = budget global de l'entité pour
  l'exercice. `category_id IS NOT NULL` = budget détaillé.
- **Cohérence non stricte** : la somme des détails peut dépasser ou être inférieure
  au global. Un warning UI non bloquant le signale.
- `is_current = 1` sur un seul exercice à la fois. Le bascule est atomique
  (transaction SQL : UPDATE fiscal_years SET is_current=0; UPDATE … SET is_current=1
  WHERE id=?).
- Table `entity_balance_refs` existante **conservée** : fallback pour la période
  antérieure au premier exercice (pas de migration destructive).

### Impact sur les autres modules

- `backend/core/balance.py` : ajout de `compute_entity_balance_for_period()` sans
  casser les fonctions existantes.
- `backend/modules/dashboard/api.py` : le widget Dashboard « Solde actuel » continue
  d'utiliser `compute_consolidated_balance`. Un nouveau widget « Budget » est ajouté
  (cf. section Dashboard).
- Aucune modification des tables `transactions`, `entities`, `categories`.

---

## API endpoints

Tous les endpoints sont sous `/api/budget/`.

### Exercices

- `GET /api/budget/fiscal-years` → liste ordre desc par `start_date`
- `POST /api/budget/fiscal-years` → crée un exercice (body : name, start_date, end_date, notes). Si `is_current=true`, bascule automatiquement.
- `PUT /api/budget/fiscal-years/{id}` → modifie (dont `is_current`)
- `DELETE /api/budget/fiscal-years/{id}` → supprime ; le handler API supprime
  explicitement les `opening_balances` et `allocations` associés (cascade
  applicative, car `PRAGMA foreign_keys` est OFF dans OpenFlow).
- `GET /api/budget/fiscal-years/current` → renvoie l'exercice marqué current, ou 404 si aucun

### Soldes d'ouverture

- `GET /api/budget/fiscal-years/{id}/opening-balances` → liste pour l'exercice
- `PUT /api/budget/fiscal-years/{id}/opening-balances` → upsert en masse (body : liste de `{entity_id, amount, source, notes}`) — remplace toutes les valeurs existantes pour cet exercice
- `GET /api/budget/fiscal-years/{id}/suggested-opening` → renvoie pour chaque entité interne le solde calculé à `start_date - 1` (pré-remplissage du wizard)

### Allocations

- `GET /api/budget/fiscal-years/{id}/allocations` → liste pour l'exercice
- `POST /api/budget/fiscal-years/{id}/allocations` → crée (body : entity_id, category_id?, amount, notes)
- `PUT /api/budget/allocations/{id}` → modifie
- `DELETE /api/budget/allocations/{id}`

### Vue consolidée (calcul du réalisé)

- `GET /api/budget/view?fiscal_year_id={id}` → vue composite :
  ```json
  {
    "fiscal_year": { "id", "name", "start_date", "end_date" },
    "previous_fiscal_year_id": 3,  // ou null si pas de N-1
    "entities": [
      {
        "entity_id": 1,
        "entity_name": "BDA",
        "opening_balance": 26000.0,
        "allocated_total": 30000.0,
        "realized_total": 9462.65,
        "realized_n_minus_1": 8200.10,
        "variation_pct": 15.4,
        "categories": [
          {
            "category_id": 3,
            "category_name": "Nourriture",
            "allocated": 5000.0,
            "realized": 904.63,
            "realized_n_minus_1": 820.0,
            "variation_pct": 10.3,
            "percent_consumed": 18.1
          }
        ]
      }
    ],
    "totals": { "allocated": 30000.0, "realized": 9462.65, "remaining": 20537.35 }
  }
  ```

### Validation API

- `is_current = 1` garanti unique : service de création/modif exécute une transaction
  `UPDATE fiscal_years SET is_current=0 WHERE id != ?` avant de fixer le nouveau.
- Dates cohérentes : `start_date < end_date`. Chevauchement entre exercices
  **toléré explicitement** (cohérent avec la règle « exercices = tranches
  d'affichage, pas de verrou »).
- Allocation : entity existe ET category existe (si non-null), sinon 400.
- Opening balance : entity existe ET type = `internal` (externes refusées, 400).

---

## UI — page `/budget` refondue

Trois onglets, sélecteur d'exercice en haut à droite (par défaut = `is_current`).

### Onglet 1 — Vue d'ensemble (par défaut)

Tableau avec une ligne par entité interne. Colonnes :

| Entité | Ouverture | Alloué | Réalisé | Reste | % consommé | N-1 (abs) | Variation % |
|--------|-----------|--------|---------|-------|-----------|-----------|-------------|

- Cellule `% consommé` : barre de progression colorée (vert < 70 %, ambre < 95 %, rouge ≥ 95 %).
- Cellule `Variation %` : couleur (vert baisse vs N-1 sur les dépenses, rouge hausse ; inversé pour recettes).
- Ligne expandable → affiche les lignes détaillées par catégorie si des allocations `category_id IS NOT NULL` existent pour cette entité.
- Footer : « Total consolidé » agrégeant les entités internes.
- Si aucun exercice N-1 détecté (première année), les colonnes N-1 sont masquées.

### Onglet 2 — Allocation

- Tableau éditable inline : (entité, catégorie optionnelle) → montant.
- Bouton « + Ligne » → choix entité + catégorie (ou laisser vide pour global).
- Validation côté client : entité obligatoire, montant > 0.
- Warning banner non bloquant si `somme(allocations catégorisées d'une entité) > allocation globale de cette entité`.
- Bouton « Copier depuis l'exercice précédent » → copie toutes les allocations (modifiable ensuite).

### Onglet 3 — Exercices

- Liste des exercices (desc par `start_date`).
- Indicateur « Actif » sur celui marqué `is_current`.
- Bouton « Nouvel exercice » → wizard 3 étapes (cf. ci-dessous).
- Action « Définir comme actif » sur chaque ligne.
- Action « Supprimer » avec confirmation (cascade sur allocations + opening_balances).

### Wizard « Nouvel exercice »

**Étape 1 — Informations**
- Nom (default : dérivé des dates, ex « 2026-2027 »)
- Date de début (default : 1er septembre de l'année en cours)
- Date de fin (default : 31 août de l'année suivante)
- Case à cocher « Définir comme exercice actif » (cochée par défaut)

**Étape 2 — Soldes d'ouverture**
- Tableau listant toutes les entités internes.
- Colonnes : Entité | Solde suggéré (= `compute_entity_balance` à `start_date - 1`) | Solde réel | Source.
- Bouton « Utiliser le solde suggéré » par ligne (copie la valeur).
- Le solde réel est **obligatoire**, la source facultative (mais encouragée : tooltip explicatif).

**Étape 3 — Allocations (optionnel)**
- Toggle « Copier les allocations de l'exercice précédent » (on par défaut si un exercice N-1 existe).
- Résumé final : nombre d'entités avec opening balance saisi, nombre d'allocations copiées.
- Bouton « Créer l'exercice ».

### Widget Dashboard « Budget »

- Compact : barre globale (% consommé du budget consolidé) + reste € + « Top 3 dépassements » (entités avec % consommé le plus élevé).
- Lien « Voir le détail » → `/budget`.
- Manifest : `dashboard_widgets: [{ id: "budget_overview", component: "widgets/BudgetOverview.tsx", default_visible: true, size: "half" }]`.

### Sidebar

- L'entrée existante « Budget » reste telle quelle (manifest `menu.label`).
- Badge « ! » (style badge existant) si au moins une entité est en dépassement sur l'exercice courant. Compteur = nombre d'entités en dépassement.

### Page `/entities`

- Dans le panneau détail d'une entité interne, le bloc « Solde de référence » (qui utilise `entity_balance_refs`) est remplacé par « Solde d'ouverture — {exercice actif} » (valeur issue de `fiscal_year_opening_balances`).
- Lien « Voir tous les exercices » → redirige vers `/budget?tab=exercices`.
- Si aucun exercice n'existe → fallback sur le bloc legacy + bouton « Créer le premier exercice ».

---

## Data flow — calcul du réalisé

```
Client appelle GET /api/budget/view?fiscal_year_id=X

Backend :
  1. Charge fiscal_years[X] → start_date, end_date
  2. Détecte fiscal_year N-1 : celui avec start_date le plus proche de X.start_date - 365j (± 31j)
  3. Pour chaque entity interne :
       a. opening = fiscal_year_opening_balances[X, entity] ?? 0
       b. allocations = budget_allocations WHERE fiscal_year_id=X AND entity_id=entity
       c. realized_per_category = SELECT category_id, SUM(amount_signed)
           FROM transactions t
           WHERE date BETWEEN start_date AND end_date
             AND (from_entity_id = entity OR to_entity_id = entity)
           GROUP BY category_id
          (amount_signed = +amount si to=entity, -amount si from=entity)
       d. Pareil pour N-1 si trouvé, sinon 0
       e. Assemble la ligne { opening, allocated_total, realized_total,
                              realized_n_minus_1, categories: [...] }
  4. Renvoie la structure JSON
```

**Optimisation** : l'endpoint `view` fait une requête SQL unique par entité (pas de N+1). Pour un BDA typique (< 10 entités internes), acceptable. Optimisable plus tard avec un CTE global.

---

## Edge cases

1. **Pas d'exercice du tout** : l'app continue de fonctionner avec `entity_balance_refs` (legacy). La page budget affiche une invite « Créer un premier exercice ».
2. **Pas d'exercice N-1** (première année) : colonnes N-1 masquées, pas d'erreur.
3. **Transaction hors de tout exercice** : exclue du calcul budget. Pas signalée (trop bruité pour un message).
4. **Entité créée en cours d'exercice** : pas d'opening balance → 0 par défaut, tooltip « À compléter dans les soldes d'ouverture ».
5. **Catégorie supprimée alors qu'une allocation la référence** : allocation conservée, affichée « — Catégorie supprimée — » (italique grisé), éditable pour réassigner.
6. **Entité supprimée** : le handler de suppression d'entité (module `entities`) est étendu pour supprimer explicitement les allocations et opening_balances associés. Cascade applicative (pas DB) — cohérent avec `PRAGMA foreign_keys OFF`.
7. **Allocation dupliquée** (même triplet) : bloquée par l'index `UNIQUE`, erreur 400 explicite (« Une allocation existe déjà pour cette entité et cette catégorie dans cet exercice »).
8. **Changement d'exercice actif** : tous les composants qui lisent « l'exercice courant » (dashboard, widget, filtres tx) se rechargent. Trigger via `EntityContext`-like pattern : un hook global `useFiscalYear()` qui expose `currentFiscalYear` et `setCurrentFiscalYear(id)`.
9. **`is_current=1` multiple** (bug ou import malformé) : le service API prend le plus récent et corrige silencieusement au prochain write.

---

## Tests

### Backend (module budget)

Fichier : `tests/backend/test_budget.py`

- `test_fiscal_year_crud` : create, list, update, delete + `name UNIQUE`.
- `test_fiscal_year_is_current_unique` : créer 2 exercices `is_current=true`, vérifier qu'un seul l'est.
- `test_fiscal_year_current_endpoint` : renvoie l'actif ou 404.
- `test_opening_balance_upsert` : PUT en masse, unicité par (year, entity), refus sur entité externe.
- `test_suggested_opening` : renvoie le solde calculé à `start_date - 1`.
- `test_allocation_crud` : CRUD + UNIQUE (year, entity, category).
- `test_allocation_category_nullable` : deux allocations pour la même entité (une globale, une catégorisée) coexistent.
- `test_view_realized` : alloc + tx dans la période → realized correct ; tx hors période → exclue.
- `test_view_n_minus_1_matching` : deux exercices consécutifs → variation calculée.
- `test_view_no_previous_year` : un seul exercice → `previous_fiscal_year_id = null`.
- `test_view_category_deleted` : allocation référence une catégorie supprimée → ne crashe pas.
- `test_entity_delete_cascades` : supprimer une entité → allocations et opening_balances associés disparaissent.

### Cohérence cross-module

Fichier : `tests/backend/test_coherence_budget.py`

- `test_budget_view_matches_entity_balance` : pour un exercice, `opening + realized_total == compute_entity_balance_for_period(entity)` à l'entité près.
- `test_dashboard_widget_reads_current_fiscal_year` : après création d'un exercice `is_current`, le widget renvoie bien les chiffres de cet exercice.

### Frontend

- `cd frontend && npm run build` passe sans erreur TypeScript.
- Validation manuelle Firefox-MCP :
  - Wizard d'ouverture fonctionne
  - Onglet 1 affiche les chiffres attendus
  - Onglet 2 permet d'éditer/supprimer une allocation
  - Widget dashboard apparaît
  - Badge sidebar apparaît quand dépassement

### Migration

- `tools/migrate.py` applique 1.2.0 proprement sur une base existante (backup auto cf. bug #5).
- `tools/check.py` passe après modification du manifest.

---

## Manifest — mise à jour

```json
{
  "id": "budget",
  "name": "Budget & Exercices",
  "description": "Allocations budgétaires par entité et catégorie, suivi du réalisé et comparaison inter-exercices",
  "help": "Définis des exercices budgétaires (ex: année universitaire), alloue un budget par pôle/club et par catégorie, suis le réalisé en temps réel et compare à l'exercice précédent.",
  "version": "1.2.0",
  "origin": "builtin",
  "category": "standard",
  "dependencies": ["entities", "categories", "transactions"],
  "menu": { "label": "Budget", "icon": "piggy-bank", "position": 15 },
  "api_routes": ["api.py"],
  "db_models": ["models.py"],
  "dashboard_widgets": [
    {
      "id": "budget_overview",
      "name": "Budget en cours",
      "component": "widgets/BudgetOverview.tsx",
      "default_visible": true,
      "size": "half"
    }
  ],
  "settings_schema": {},
  "example": "Je définis l'exercice 2025-2026 (sept→août), j'alloue 2 000 € à Gastronomine dont 1 500 € Nourriture, et je vois en temps réel que 40 % a été consommé vs 55 % l'an dernier à la même date."
}
```

---

## Livrables attendus

Cette refonte sera ensuite découpée en un plan d'implémentation via `writing-plans`.
Liste prévisionnelle des livrables :

1. Migration 1.2.0 + nettoyage table `budgets` legacy
2. `backend/modules/budget/api.py` refondu (6 groupes d'endpoints)
3. Extension de `backend/core/balance.py` avec `compute_entity_balance_for_period`
4. Manifest mis à jour + check.py PASS
5. Page `/budget` refondue (3 onglets) + wizard
6. Widget Dashboard `BudgetOverview.tsx`
7. Intégration badge sidebar (compteur dépassements)
8. Adaptation page `/entities` (bloc solde d'ouverture)
9. Hook global `useFiscalYear()`
10. Tests backend + coherence (liste ci-dessus)
11. Validation E2E via Firefox-MCP
12. Mise à jour `CLAUDE.md` (nouveau concept d'exercice, fiscal_year_opening_balances)
