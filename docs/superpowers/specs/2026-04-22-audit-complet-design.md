# Audit OpenFlow 2026-04-22 — Méthodologie

**Objectif :** produire une punch list exhaustive et triagée couvrant cohérence des données (vs spreadsheet BDA), bugs fonctionnels, et frictions UX. Cette synthèse servira d'entrée à plusieurs plans d'implémentation ciblés (un lot = un plan).

**Non-objectif :** corriger. L'audit est en lecture seule sauf pour l'outil de cohérence (qui reste utile en exploitation).

---

## Contexte

- Spreadsheet de référence : `../compta BDA.xlsx` — 13 feuilles. `Suivi` (91 lignes) = vue consolidée ; un tableau croisé dynamique affiche les totaux ; 10 feuilles par pôle (théâtre, banque, créa, CCMP, gastro, classique, Salle ins, Comédie, PapiMaMine, ciné).
- État OpenFlow : 89 transactions en DB, 52 remboursements (48 remboursés + 4 pending), BDA 26 355 €.
- Audit précédent `../REPORT.md` (2026-04-20) a identifié 6 bugs + 17 frictions. Commit `e9feac8` en a corrigé une partie. Cet audit recouvre les changements depuis et ce qui restait.
- Point douloureux explicite signalé par l'utilisateur : **l'affichage des remboursements dans la liste Transactions**.

---

## Phase 1 — Cohérence données (script `tools/audit_coherence.py`)

Script Python one-shot, idempotent, produit un rapport Markdown.

**Entrées :**
- `../compta BDA.xlsx` (ouvrir avec `openpyxl`, encoding CP1252 pour les noms de feuilles)
- `data/openflow.db`

**Comparaisons :**
1. **Transactions manquantes** — lignes présentes dans `Suivi` (ou feuilles par pôle) absentes d'OpenFlow, et vice versa. Appariement par tuple `(date, montant, motif-fuzzy)`.
2. **Écarts sur transactions appariées** — différences de montant, catégorie, payeur, statut remboursé.
3. **Cohérence statut remboursement** — pour chaque ligne Excel avec `Remboursé=oui`, vérifier qu'un `reimbursements` row correspondant existe en DB avec `status='reimbursed'`.
4. **Totaux globaux** — comparer les totaux du tableau croisé dynamique aux sommes `/api/dashboard/summary`.

**Sortie :** `audit/coherence-diff.md` avec sections :
- Transactions manquantes (Excel → OpenFlow)
- Transactions orphelines (OpenFlow → Excel)
- Écarts sur transactions appariées
- Écarts de remboursement
- Écarts de totaux

## Phase 2 — Walkthrough UX via Firefox-MCP

Parcours de chaque route `/` avec screenshot à chaque étape clé. **Priorité** : l'affichage remboursements dans `/transactions` — lisibilité, séparation visuelle, actions disponibles.

**Modules à parcourir dans cet ordre :**
Dashboard, Transactions (priorité rembos), Entités, Catégories, Remboursements, Budget, Import, Sauvegarde, Système, Utilisateurs, Paramètres.

Pour chaque module, checker :
- Rendu initial (vide, rempli, état chargement)
- Actions CRUD (create/edit/delete) sur un item
- Filtres / tri / recherche
- États d'erreur (champ obligatoire, format invalide)
- Cohérence visuelle (alignements, espacement, hiérarchie typographique)
- Accessibilité basique (focus visible, escape, tab order)

Sortie : liste brute d'observations par module (fichier markdown).

## Phase 3 — Synthèse

Consolider dans `docs/superpowers/specs/2026-04-22-audit-complet.md` :

1. **Écarts de données** (phase 1)
2. **Bugs fonctionnels** (phase 2) avec sévérité Critique/Majeur/Mineur/Cosmétique
3. **Frictions UX** classées par module
4. **Proposition de découpage en lots** — chaque lot = une intention unifiée. Ex : "Lot A — Corrections remboursements", "Lot B — Enrichissement Transactions (filtres, affichage)", etc.

## Phase 4 — Revue + triage (avec utilisateur)

Utilisateur lit la synthèse, coche/élague/ajoute. Puis par lot : brainstorm → spec → writing-plans → implémentation.

---

## Deliverables

- `tools/audit_coherence.py` (commit)
- `audit/coherence-diff.md` (gitignore — contient données privées)
- `docs/superpowers/specs/2026-04-22-audit-complet.md` (commit)
