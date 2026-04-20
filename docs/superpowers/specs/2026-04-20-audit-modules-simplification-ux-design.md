# Audit modules OpenFlow — simplification et UX user-friendly

**Date :** 2026-04-20
**Auteur :** Antonin (trésorier BDA Mines Paris) + Claude Opus 4.7

## Contexte

OpenFlow expose 25 modules backend dont plusieurs sont redondants, non utilisés
ou dépourvus de page React. L'utilisateur (trésorier BDA Mines Paris) n'arrive
pas à distinguer quels modules sont utiles, où ils apparaissent dans l'app, ni
comment les utiliser — on ne sait pas si un module « n'existe pas » ou si on ne
sait pas s'en servir.

Le refactor précédent (spec
`~/.claude/plans/je-veux-que-chaque-eventual-map.md`) a garanti l'invariant
*1 module activé = 1 onglet fonctionnel*, mais la liste de modules reste
encombrée et l'UX ne guide pas l'utilisateur.

Ce spec clôture ce sujet : trancher chaque module individuellement (garder /
supprimer), construire la page manquante pour les modules retenus, et rendre
toute l'app auto-explicative sans documentation externe.

## Objectifs

1. **Liste claire** : ne conserver que les modules utiles pour une asso type
   (BDA Mines Paris) ou une petite entreprise. Supprimer les résidus et
   redondances.
2. **Chaque module activé = 1 onglet fonctionnel** ou une section intégrée
   clairement repérable.
3. **Auto-explicatif** : l'utilisateur comprend chaque module sans aide
   externe — où il apparaît, à quoi il sert, comment commencer.
4. **Cohérence texte** : aucun nom de module cité dans l'UI ne doit être
   orphelin (garde-fou automatique).

## Décisions

### Modules supprimés du codebase (8)

Backend + frontend + tables DB + tests supprimés.

| Module | Raison |
|---|---|
| `alerts` | Pas de page, 0 données, cas d'usage marginal |
| `multi_accounts` | Pas de page, redondant avec Entités pour caisse séparée |
| `divisions` | Pas de page, redondant avec Entités (sous-entités hiérarchiques) |
| `bank_reconciliation` | Redondant avec `smart_import` pour le workflow BDA |
| `forecasting` | Redondant avec Budget pour une asso événementielle |
| `tax_receipts` | BDA non habilité CERFA |
| `grants` | Subventions gérées via transactions + contact tier |
| `recurring` | Aucune dépense récurrente fixe au BDA |

### Modules conservés (17)

#### Noyau (10) — toujours actifs, non désactivables

Les 5 modules « intégrés » sont reclassés en `category: "core"` pour refléter
qu'ils sont fondamentaux (notes, pièces jointes, export, audit, FEC).

| Module | Visible où | Type |
|---|---|---|
| `dashboard` | Onglet sidebar | Page |
| `transactions` | Onglet sidebar | Page |
| `categories` | Onglet sidebar | Page |
| `entities` | Onglet sidebar | Page |
| `system` | Onglet sidebar | Page (remis dans la sidebar) |
| `annotations` | Détail transaction → section Notes | Intégré |
| `attachments` | Détail transaction → section Pièces jointes | Intégré |
| `export` | Transactions → boutons CSV/JSON | Intégré |
| `audit` | Paramètres → Journal d'audit | Intégré |
| `fec_export` | Paramètres → Export FEC | Intégré |

#### Métier (6) — actifs par défaut, désactivables

| Module | Onglet | Rôle |
|---|---|---|
| `budget` | Budget | Enveloppes prévisionnelles, comparaison N vs N-1 |
| `tiers` | Contacts | Carnet adresses sponsors/membres/fournisseurs |
| `reimbursements` | Remboursements | Avances de frais membres |
| `smart_import` | Import | Drop Excel/CSV, création auto des transactions |
| `backup` | Sauvegarde | Export/import ZIP complet |
| `multi_users` | Utilisateurs (footer, admin) | Auth + rôles par entité |

#### Opt-in (1) — désactivé par défaut

| Module | Onglet | Raison opt-in |
|---|---|---|
| `invoices` | Factures & devis | Usage ponctuel (location matos), on l'active quand on en a besoin |

### Sidebar par défaut

10 onglets : Tableau de bord, Transactions, Catégories, Entités, Budget,
Contacts, Remboursements, Import, Sauvegarde, Système. + footer Utilisateurs
(admin) / Paramètres.

## Nouvelle page « Factures & devis » (InvoicesView)

Fichier : `frontend/src/modules/invoices/InvoicesView.tsx`.

### Fonctionnalités

- **Onglets Devis / Factures** en haut de la page
- **Numérotation auto** : `DEV-2026-001`, `FAC-2026-001` (préfixe + année + compteur par année)
- **Table** : numéro, date, client (picker sur module `tiers`), montant HT,
  TVA, TTC, statut, actions
- **Création** : modal avec **lignes dynamiques** (description + quantité +
  prix unitaire), calcul live des totaux HT / TVA / TTC
- **Statuts** :
  - Devis : `brouillon`, `envoyé`, `accepté`, `refusé`
  - Facture : `brouillon`, `envoyée`, `payée`, `annulée`
- **Conversion devis → facture** : bouton sur un devis accepté, crée la
  facture liée avec mêmes lignes
- **Export PDF** : bouton download → `GET /api/invoices/{id}/pdf` (nouveau
  endpoint backend, template HTML→PDF via `weasyprint` ou équivalent)
- **Lien transaction** : une facture `payée` peut être associée à une
  transaction existante (champ `transaction_id` optionnel)

### Gestion TVA (asso ET entreprise)

Nouveau champ `vat_enabled: bool` dans `config.yaml > entity`.

- **Off (défaut, BDA asso loi 1901)** : pas de colonne TVA, mention auto
  en pied de facture « TVA non applicable, art. 293 B du CGI »
- **On (entreprise ou asso assujettie)** : colonne TVA par ligne (taux
  20 % / 10 % / 5,5 % / 2,1 %), totaux HT / TVA / TTC distincts

Toggle dans *Paramètres → Entité → « Assujetti à la TVA »*.

### API backend

API CRUD existante (`backend/modules/invoices/api.py`) conservée. Ajout d'un
endpoint :

```
GET /api/invoices/{id}/pdf
→ Response: application/pdf
```

Template HTML simple dans `backend/modules/invoices/templates/invoice.html`,
rendu avec Jinja2 + `weasyprint` (ou `pdfkit`).

## UX user-friendly (B + C)

### Paramètres → Modules (option B)

Chaque carte module affiche :

1. **Nom + toggle actif**
2. **📍 Où ça apparaît** — dérivé automatiquement :
   - Si `manifest.menu` existe → « Barre latérale → {menu.label} »
   - Sinon lookup dans `INTEGRATED_LOCATIONS` (table dans `frontend/src/routes.tsx`)
3. **À quoi ça sert** — lu depuis `manifest.help`
4. **Exemple concret** — nouveau champ `manifest.example` (1-2 lignes)
5. **Bouton « Voir en action → »** — si module actif, lien vers la page ou
   ancre vers la section intégrée

Table `INTEGRATED_LOCATIONS` à maintenir dans `frontend/src/routes.tsx` :

```ts
export const INTEGRATED_LOCATIONS: Record<string, string> = {
  annotations: "Détail d'une transaction → section Notes",
  attachments: "Détail d'une transaction → section Pièces jointes",
  export: "Page Transactions → boutons CSV/JSON en haut",
  audit: "Paramètres → section Journal d'audit",
  fec_export: "Paramètres → section Export FEC",
};
```

### Empty states parlants (option C)

Nouveau composant partagé `frontend/src/core/EmptyState.tsx` :

```tsx
<EmptyState
  moduleId="reimbursements"
  icon={RotateCcw}
  examples={[
    "Marie a avancé 45 € de courses → en attente",
    "Paul a avancé 120 € pour la soirée → remboursé",
  ]}
  ctaLabel="Créer le premier remboursement"
  onCta={openCreate}
/>
```

Le composant :
- Lit `name` et `help` depuis le manifest du module
- Affiche : icône colorée + titre « Aucun {name} pour l'instant » + `help` +
  liste d'exemples + bouton CTA
- Disparaît dès que le composant parent a ≥ 1 élément
- Max 6 lignes de texte (règle UI)

Intégré dans : `BudgetManager`, `TiersList`, `ReimbursementManager`,
`InvoicesView`.

### Encart Dashboard dynamique

Dans `frontend/src/core/Dashboard.tsx`, ajout d'un composant
`<ModuleDiscoveryHint />` :

- Lit la config via `/api/config` → trouve modules où
  `category != "core"` ET `active == false` ET `menu != null` (donc a une
  page exploitable)
- Si la liste est non vide : affiche un encart avec les noms lus des
  manifests + lien `[Paramètres →]`
- Dismissible : état dans `localStorage` (`openflow.dashboardHintDismissed`)
- Se re-affiche si un nouveau module désactivé avec page apparaît

## Garde-fous

### 1. Invariant 1 module activé = 1 onglet fonctionnel

Déjà en place :
- `tools/check.py` : échoue si un manifest a `menu` mais pas de frontend
- `Sidebar.tsx` : filtre `MODULE_IDS_WITH_ROUTE` pour masquer les ghosts

### 2. Cohérence texte UI → manifests

**Nouveau test** : `tests/test_ui_text_coherence.py`.

- **Charge la liste des manifests présents** : `backend/modules/*/manifest.json` → set des `id` + `name` actuels
- **Charge la liste noire des modules récemment supprimés** (constante en tête
  du test, à jour à chaque cleanup) : `REMOVED_MODULES = {"alerts", "multi_accounts", "divisions", "bank_reconciliation", "forecasting", "tax_receipts", "grants", "recurring"}`
- Scan `frontend/src/` (`*.tsx`, `*.ts`) **sauf** `routes.tsx`
- Pour chaque fichier, regex restrictive : les noms de modules supprimés
  **uniquement entre guillemets** (strings JSX ou TS) ou dans des commentaires.
  Exclu : commentaires de code `//` explicites marqués `// audit-ignore`
- Échoue si une occurrence d'un module supprimé apparaît
- Ne pas matcher les mots communs (« export », « alerts ») si ambigus →
  matcher uniquement sur les ids exacts avec boundaries (ex:
  `/\balert_rules\b|\bforecasting\b/`)

**Exclusions** : `routes.tsx` (peut citer les modules pour le mapping),
`INTEGRATED_LOCATIONS` (string keys = ids légitimes).

Le test fait tomber CI si quelqu'un ajoute « Reçus fiscaux » dans un composant
après suppression du module.

### 3. Manifest → source de vérité

Règle : **aucun nom de module ne doit être hardcodé dans un composant React**.
Toutes les références passent par :
- `manifest.name` (lu via `/api/modules` ou `/api/modules/all`)
- `manifest.help` (description longue)
- `manifest.example` (nouveau)
- `manifest.menu.label`
- `INTEGRATED_LOCATIONS` (seul endroit avec chaînes hardcodées pour les
  modules sans menu)

## Plan d'implémentation

1. **Suppression des 8 modules morts** (1h)
   - `rm -rf backend/modules/{alerts,multi_accounts,divisions,bank_reconciliation,forecasting,tax_receipts,grants,recurring}`
   - `rm -rf frontend/src/modules/{bank_reconciliation,forecasting,tax_receipts,grants,recurring}`
   - Migration DB : `DROP TABLE alert_rules, accounts, divisions, bank_statements, grants, tax_receipts, recurring_transactions`
   - Retirer entrées `routes.tsx`
   - Nettoyer `config.yaml` + `config.example.yaml`
   - Supprimer tests `test_coherence_*.py` référençant ces modules
   - `check.py` + `pytest` doivent passer

2. **Reclasser 5 intégrés en core** (30 min)
   - Patch manifests : `annotations`, `attachments`, `export`, `audit`,
     `fec_export` → `"category": "core"`
   - Dans `Settings.tsx`, `CORE_MODULE_IDS` devient dynamique : `modules.filter(m => m.category === "core").map(m => m.id)`
   - Toggle disabled avec badge « Toujours actif » pour tous les modules core

3. **Remettre `system` dans la sidebar** (5 min)
   - Re-ajouter `"menu": {"label": "Système", "icon": "activity", "position": 20}` dans `backend/modules/system/manifest.json`

4. **Nouveau champ `example` dans les manifests** (30 min)
   - Ajouter au schema `tools/schemas/manifest.schema.json`
   - Patcher les 17 manifests restants avec un exemple concret d'usage
   - `check.py` warn si `example` absent

5. **Construire InvoicesView.tsx** (4h)
   - Toggle TVA dans config (`vat_enabled`) + endpoint backend
   - Page React : onglets, table, modal création, conversion devis→facture
   - Endpoint backend `GET /api/invoices/{id}/pdf` (template HTML + Jinja2 + weasyprint)
   - Ajout route dans `routes.tsx` + manifest `menu`
   - Test smoke : créer devis → convertir → télécharger PDF

6. **Composant EmptyState** (2h)
   - Fichier `frontend/src/core/EmptyState.tsx`
   - Intégration dans BudgetManager, TiersList, ReimbursementManager, InvoicesView

7. **Refonte Paramètres → Modules** (2h)
   - Réécrire `renderModuleRow` pour afficher badge 📍, description, exemple,
     bouton « Voir en action »
   - Utiliser `INTEGRATED_LOCATIONS` pour les modules sans menu

8. **Encart Dashboard dynamique** (30 min)
   - Composant `<ModuleDiscoveryHint />` dans `Dashboard.tsx`
   - localStorage pour dismiss

9. **Test cohérence UI** (1h)
   - `tests/test_ui_text_coherence.py`
   - CI passe sur nouveau set

**Total : ~11h**

## Fichiers critiques à modifier

- `backend/modules/*/manifest.json` — ajout `example`, reclassement `category`
- `tools/schemas/manifest.schema.json` — nouveau champ `example`
- `tools/check.py` — warning si `example` absent
- `frontend/src/routes.tsx` — retrait routes modules supprimés, ajout
  `INTEGRATED_LOCATIONS`, `InvoicesView`
- `frontend/src/core/Settings.tsx` — refonte `renderModuleRow`, `CORE_MODULE_IDS` dynamique
- `frontend/src/core/Dashboard.tsx` — ajout `ModuleDiscoveryHint`
- `frontend/src/core/EmptyState.tsx` — **nouveau**
- `frontend/src/modules/invoices/InvoicesView.tsx` — **nouveau**
- `backend/modules/invoices/api.py` — ajout endpoint PDF
- `backend/modules/invoices/templates/invoice.html` — **nouveau**
- `config.yaml` + `config.example.yaml` — retrait modules supprimés, ajout
  `vat_enabled`
- `backend/core/config.py` — ajout champ `vat_enabled: bool = False` dans
  dataclass Entity
- `requirements.txt` — ajout `weasyprint` (ou alternative `pdfkit` + `wkhtmltopdf`)
- `tests/test_ui_text_coherence.py` — **nouveau**

## Fichiers à supprimer

- `backend/modules/{alerts,multi_accounts,divisions,bank_reconciliation,forecasting,tax_receipts,grants,recurring}/` (dossiers entiers)
- `frontend/src/modules/{bank_reconciliation,forecasting,tax_receipts,grants,recurring}/` (dossiers entiers)
- Tests référençant ces modules dans `tests/`

## Vérification end-to-end

Après implémentation, smoke test manuel :

1. `python tools/check.py` → PASS
2. `python -m pytest tests/ -v` → tous verts
3. `cd frontend && npm run build` → OK
4. `python start.py`, naviguer vers `/settings` :
   - Modules groupés par Noyau / Métier / Opt-in
   - Chaque carte affiche 📍 « Où ça apparaît » cohérent
   - Les modules core ont badge « Toujours actif »
5. Aller sur `/reimbursements` (activé) → empty state avec exemples + CTA
6. Aller sur `/dashboard` → voir encart « Tu n'as pas activé Factures & devis »
7. Toggle `invoices` on → onglet apparaît dans sidebar → clic → page vide avec
   empty state + CTA « Créer le premier devis »
8. Créer un devis 3 lignes → TTC correct → convertir en facture → télécharger PDF
9. Dans Paramètres, toggle « Assujetti à la TVA » on → vérifier que le PDF
   suivant a la colonne TVA et pas de mention 293 B

## Risques et migrations

- **Aucune donnée utilisateur perdue** — les 8 tables supprimées ont 0 ligne
  en DB BDA (vérifié)
- **Pas de migration nécessaire** pour les données existantes : transactions,
  entities, categories, contacts (tiers), users, annotations/attachments
  vides, audit vide
- **Tests à supprimer** — impossible de conserver `test_bank_reconciliation.py`
  etc. après suppression des modules. Check que les tests restants ne
  dépendent pas implicitement de ces modules
- **Rollback** : en cas de pépin, git revert. La DB locale a une sauvegarde
  auto créée par `migrate.py` avant toute migration
