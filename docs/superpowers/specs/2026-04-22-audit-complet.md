# Audit OpenFlow — 2026-04-22

**Base :** commit `bc60cd8` sur `feat/budget-evolution` · DB `data/openflow.db` · spreadsheet `../compta BDA.xlsx`.
**Méthode :** (1) script de cohérence `tools/audit_coherence.py`, (2) walkthrough UX via Firefox-MCP (Dashboard, Transactions, Catégories, Entités, Remboursements, Budget, Contacts, Import, Sauvegarde, Système, Utilisateurs, Paramètres).
**Non-objectif :** corriger. Ce document est la source d'entrée pour les plans d'implémentation suivants.

---

## Résumé exécutif

- **Cohérence financière globale : ✅ parfaite.** Totaux Dépenses (9 462,65 €), Recettes (9 755,35 €) et Net (+292,70 €) identiques entre Excel et DB. La confiance dans les chiffres affichés est acquise.
- **Cohérence ligne à ligne : quasi-totale.** 89 appariements / 90 lignes Excel. 1 ligne Excel absente (donnée source incomplète).
- **Trou principal identifié : les remboursements.** 9 écarts (Excel ↔ DB), l'affichage dans Transactions est le point douloureux explicite de l'utilisateur.
- **Autres friction UX : 3 critiques, ~10 mineures.** Voir Section 3.

---

## 1. Écarts de données (Phase 1)

Rapport détaillé : `audit/coherence-diff.md` (gitignored). Extraits ci-dessous.

### 1.1 Totaux — aucun écart

| Source | Dépenses | Recettes | Net |
|---|---|---|---|
| Excel `Suivi` | 9 462,65 | 9 755,35 | +292,70 |
| DB `transactions` | 9 462,65 | 9 755,35 | +292,70 |
| Écart | 0,00 | 0,00 | 0,00 |

### 1.2 Transactions — 1 ligne non importée

| Date | Motif | Catégorie | Cause |
|---|---|---|---|
| 2025-10-04 | `th parrainage` | théâtre | Excel ne renseigne ni Dépense ni Recette → montant ambigu → rejeté à l'import. **Qualité source**, pas un bug OpenFlow. |

### 1.3 Écarts de catégorie — 61 occurrences, toutes bénignes

L'Excel utilise les abréviations informelles (`gastro`, `théâtre`, `créa`, `CCMP`, `banque`, `Général`) ; la DB stocke les noms canoniques (`Nourriture / Buffet`, `Theatre`, `Soiree Crea`, `Projection / Media`, `Frais bancaires`, `Cotisations` / `Parrainage` / `Subventions` / `BALM` / ... selon le motif). **Le smart_import a bien fait son travail de remapping.** Aucun correctif nécessaire côté data ; à noter pour la doc utilisateur.

### 1.4 Écarts de remboursement — 9 occurrences, dont 7 réels

| Code | # | Détail |
|---|---|---|
| `REIMB_NOT_SETTLED` | 2 | Excel dit remboursé, DB en `pending` → `Campagnes liste 1` (Vicente Spada, -601,21 €) et `Campagnes liste 2` (Eugene de Maistre, -600,00 €). Le + probable : l'utilisateur n'a pas (encore) cliqué "Marquer comme remboursé" en DB. |
| `REIMB_MISSING` | 5 | Excel dit remboursé, aucun enregistrement DB : `Cyrano`, `recettes M radio` (×2), `Frais dossier passace`, `remboursement cotiz`. Ces lignes ont-elles été importées sans détection de colonne Remboursé ? |
| `REIMB_EXTRA` | 2 | DB a un rembo créé, Excel ne signale rien : `Cotisation salle ins'` (5 €, Killian Bujon), `Constellation` (500 €, PCV). Probable création manuelle a posteriori. |

→ **Lot "Cohérence rembos"** : revue manuelle ligne par ligne avec l'utilisateur pour réconcilier les 7 entrées.

---

## 2. Bugs fonctionnels (Phase 2)

Sévérité : 🔴 Critique · 🟠 Majeur · 🟡 Mineur · ⚪ Cosmétique

### B1 🟠 Legacy `"Remboursé: non"` persistant dans 5 transactions

**Lieu :** colonne LIBELLÉ de `/transactions`, ex. #85 `remboursement cotiz\n\nRemboursé: non`.
**Cause :** ancienne import Excel a inscrit cette string dans `transactions.description`. Le module `reimbursements` ignore cette string mais le frontend l'affiche.
**Impact :** double système visible côté user ; 5 lignes polluent la colonne.
**Correctif :** (a) nettoyage one-shot du champ description ; (b) migration parsing → création rembo si Remboursé=oui manquant (croise avec REIMB_MISSING ci-dessus).

### B2 🟠 Doublons contacts « Josephine Peronne / Joséphine Peronne / Joséphinne Peronne »

**Lieu :** `/tiers`, 3 variantes du même nom.
**Cause :** smart_import n'a pas normalisé les accents/fautes de frappe avant création contact.
**Impact :** la personne apparaît 3 fois dans la liste "Qui doit combien ?" ; sommes par personne faussées.
**Correctif :** (a) one-shot : fusion manuelle assistée (détection similarité par Levenshtein) ; (b) ajouter une étape de déduplication pendant l'import (UI de review "ce nom ressemble à…").

### B3 🟠 Affichage remboursement dans Transactions — plusieurs problèmes combinés

**Lieu :** colonne LIBELLÉ de `/transactions`, 52 lignes sur 89.
**Observations :**
- Le libellé et le nom du payeur sont mélangés dans la même cellule : `Campagnes liste 2\n↩ Eugene de Maistre`.
- Aucune distinction visuelle entre `pending` et `reimbursed` — l'utilisateur ne sait pas au premier coup d'œil s'il reste à rembourser.
- L'icône `↩` (retour arrière) est sémantiquement ambiguë : désigne-t-elle "tx à rembourser" ou "tx de remboursement" ? Les deux cas existent et sont rendus identiquement.
- Pas de filtre par statut rembo (voir B5).
- La colonne LIBELLÉ mélange donc 3 sources : label propre, rembo `↩ Nom`, et legacy `Remboursé: non` (B1).

**Correctif (à chiffrer en brainstorming) :** options envisageables :
1. Colonne dédiée **"Rembo"** avec chip `⏳ Nom` (pending) / `✓ Nom` (remboursé) / vide, triable et filtrable.
2. Plus radical : séparer la vue en 2 onglets `Toutes / Avances ouvertes`.
3. Enrichir le détail (eye icon) au lieu du tableau, garder le tableau propre.

### B4 🟡 Route `/multi_users` retourne le Dashboard silencieusement

**Cause :** redirect fallback `<Route path="*">` attrape cette URL. Le bon lien sidebar pointe vers `/multi-users` (tiret). La confusion est plausible.
**Correctif :** alias de route ou 404 explicite.

### B5 🟡 Filtres Transactions incomplets

**Lieu :** `/transactions` header.
**Filtres disponibles :** Texte, Du, Au, Catégorie.
**Manquants :** Entité (from/to), Statut rembo, Min/Max montant.
**Correctif :** ajouter au moins **Entité** et **Statut rembo** (cohérent avec B3).

### B6 🟡 Tri des colonnes partiel

**Lieu :** `/transactions`.
**Observations :** en-tête DATE montre une flèche `↓` (tri actif), autres colonnes non cliquables.
**Correctif :** activer tri sur Montant et Catégorie.

### B7 🟡 Date/Solde de référence affichés sans formatage monétaire

**Lieu :** `/settings` → Entité → Solde de référence affiche `24646.15`.
**Ailleurs dans l'app :** `24 646,15 €` (format fr-FR).
**Correctif :** utiliser `utils/format.ts::eur` (ajouté lors du refactor budget).

### B8 🟡 Intégrité code perpétuellement rouge pendant le dev

**Lieu :** `/system` → "14 fichier(s) différent(s) du snapshot".
**Cause :** le snapshot pristine n'est pas régénéré à chaque release ; les commits de dev ressortent en rouge.
**Correctif (léger) :** bouton "Mettre à jour" existe déjà → documenter dans CLAUDE.md quand l'appeler. Ou masquer l'alerte quand le diff est < X fichiers.

### B9 🟡 Le fichier temporaire `smart_import_temp/*.xlsx` traîne

**Lieu :** `/system` → "TEMPORAIRE 38.1 KB · 1 fichier(s) import en attente".
**Cause :** pas de nettoyage après import réussi.
**Correctif :** supprimer le fichier temp en fin d'import (ou TTL 1h).

### B10 ⚪ 13 sessions actives pour 1 utilisateur

**Lieu :** `/backup` → "Sessions 13".
**Cause :** pas de purge des sessions expirées côté DB.
**Correctif :** job de ménage au démarrage de l'app ou à chaque login réussi.

### B11 ⚪ Journal d'audit quasi-vide

**Lieu :** `/settings` → Journal d'audit, 2 entrées malgré des dizaines de CRUD récents.
**Cause :** module `audit` n'est pas câblé aux modules récents (budget, rembos, imports).
**Correctif :** ajouter hooks dans les endpoints mutants de chaque module, ou logger via un middleware.

---

## 3. Frictions UX (Phase 2)

| # | Module | Friction | Proposition |
|---|---|---|---|
| F1 | Dashboard | Bannière "Explorer les modules" réapparaît à chaque chargement ; X ne persiste pas. | Persister dismiss dans `localStorage` avec opt-in "ne plus afficher". |
| F2 | Dashboard | "Dernières transactions" tronquées verticalement sur petit viewport. | Lignes fixées (overflow hidden sur libellé trop long) ; tooltip au survol. |
| F3 | Transactions | Bouton "Toutes catégories" coupé sur viewport ≤ 800 px. | Layout responsive : filtres en 2 lignes ou collapsable. |
| F4 | Transactions | Tableau en `overflow-hidden` : la colonne MONTANT disparaît sur viewport < 978 px. | Scroll horizontal OU colonnes prioritaires en responsive. |
| F5 | Transactions | Confirmation delete inline sans undo. | Banner "Annuler" après delete (5 s). |
| F6 | Catégories | Pas de compteur de transactions ni de total € par catégorie. | Ajouter colonnes dans la vue arbre. |
| F7 | Catégories | Impossible de renommer ou supprimer une catégorie depuis la liste (il faut passer par un endpoint ?). | Boutons `✏` `🗑` sur chaque feuille, avec confirmation. |
| F8 | Contacts | Titre "Contacts & Tiers" vs sidebar "Contacts" vs URL `/tiers`. | Unifier sur **Contacts** partout (incluant la route). |
| F9 | Contacts | Pas de colonne "Total avancé", "Nb transactions", "Dernière activité". | Enrichir la vue liste ; utile pour identifier les membres inactifs. |
| F10 | Entités | Pas de bouton "éditer" sur les enfants (seul le solde propre a ✏). | Icone éditer sur chaque nœud de l'arbre. |
| F11 | Budget | Sélecteur d'exercice tronqué en top-right ("26-2027 (actif)" coupé). | Agrandir ou simplifier le label. |
| F12 | Wizard Budget | Backdrop click ferme le modal même après step 1 complété (orphan fiscal year). | **Déjà corrigé** dans `bc60cd8`. |
| F13 | Sidebar | Pas de badge budget tant que l'exercice est futur (Sept 2026) — OK mais confusion possible. | À documenter (tooltip ?). |
| F14 | Global | Pas de raccourci clavier (`/` pour search, `N` pour new, `Esc` pour fermer modal). | Phase ultérieure. |
| F15 | Global | Pas de mode clair (seulement sombre). | Basse priorité. |
| F16 | Global | Aucun tooltip au hover sur les badges colorés d'entités — l'utilisateur doit deviner la couleur. | Ajouter `title` avec le nom complet. |

---

## 4. Découpage proposé en lots

Chaque lot = un futur brainstorming → spec → writing-plans → implémentation. Ordre recommandé par valeur/risque :

### Lot A — Réconciliation remboursements (B1 + B3 + partie 1.4)

**Objectif :** que la colonne "remboursement" dans `/transactions` soit **lisible, triable, filtrable**, et que les 7 écarts de la section 1.4 soient résolus.
**Inclus :**
- Nettoyer les 5 `Remboursé: non` résiduels dans `description`.
- Brainstorm sur l'affichage (B3 options 1/2/3).
- Ajouter filtre statut rembo dans les filtres Transactions (B5).
- Fusionner les 7 incohérences Excel/DB (ou 9 selon interprétation) avec revue utilisateur.

**Gain :** le point douloureux n°1 disparaît.

### Lot B — Contacts (B2 + F8 + F9)

**Objectif :** dédup, clarification nommage, enrichissement.
- Fusion interactive des doublons.
- Renommage URL `/tiers` → `/contacts`.
- Colonnes "Total avancé", "Nb tx".

### Lot C — Filtres & tri Transactions (B5 + B6 + F3 + F4)

**Objectif :** rendre la liste des 89 transactions vraiment exploitable.

### Lot D — Catégories enrichies (F6 + F7)

**Objectif :** totaux par catégorie + édition inline.

### Lot E — Ménage système (B9 + B10 + B11)

**Objectif :** hygiène DB (sessions, temp files, audit trail).

### Lot F — Corrections ponctuelles (B4 + B7 + B8 + F1 + F11 + F16)

**Objectif :** ramasser les petits bugs/cosmétique. Peut être un seul PR.

---

## 5. Livrables

- `tools/audit_coherence.py` — outil réexécutable (commit)
- `audit/coherence-diff.md` — rapport détaillé (gitignored, contient données privées)
- `docs/superpowers/specs/2026-04-22-audit-complet.md` — ce document (commit)
- `docs/superpowers/specs/2026-04-22-audit-complet-design.md` — méthodologie (déjà commit)

## 6. Prochaine étape

Revue de cette synthèse par l'utilisateur → choix du premier lot → brainstorming du lot choisi → writing-plans → exécution subagent-driven-development.
