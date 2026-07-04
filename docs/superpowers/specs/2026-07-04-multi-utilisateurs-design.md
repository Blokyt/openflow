# OpenFlow multi-utilisateurs : design

Date : 2026-07-04
Statut : validé par Vicente (brainstorm du 2026-07-04)

## Objectif

Mettre OpenFlow en ligne et le rendre multi-utilisateurs. Aujourd'hui : app locale
mono-utilisateur (FastAPI + SQLite + React servie en statique, zéro auth).

Cas d'usage cibles :

- Le trésorier d'un sous-club (ex : Gastronomine) se connecte et ne voit QUE le
  périmètre de son entité (sous-arbre) : solde réel, transactions, budget,
  remboursements. La mécanique de périmètre par sous-arbre existe déjà côté backend
  (include_children, frontière de flux) et est testée.
- Il peut SOUMETTRE des transactions (pas les valider) : facture PDF via le module
  attachments, commentaire, montant, catégorie. L'admin (trésorier BDA) valide ou
  refuse ; la transaction validée entre dans la compta.
- Il suit ses demandes de remboursement (lecture seule sur son périmètre).
- Des membres ont un accès lecture seule à certains périmètres (transparence).
- L'admin garde tous les droits actuels.

Contraintes :

- Architecture modulaire respectée : modules plug-and-play avec manifests, pas de
  logique inter-modules dans le core (l'auth est une infrastructure transverse au
  même titre que database.py ou balance.py, pas de la logique métier).
- Tout en français, design system existant (PRODUCT.md / DESIGN.md).
- Les 425 tests existants continuent de passer ; chaque capacité arrive avec ses tests.

## Décisions actées

| Question | Décision |
|---|---|
| Modèle de rôles | Rôle par (user, entité) avec héritage sur le sous-arbre. Rôles : treasurer, viewer. Admin = flag global sur users. |
| Auth | Sessions cookie côté serveur (HttpOnly + Secure + SameSite=Lax), table sessions, révocation instantanée. |
| Comptes | Création par l'admin + lien d'invitation à usage unique (72 h), transmis manuellement. Zéro infra email. |
| Soumissions | Table à part `transaction_submissions` dans un nouveau module `submissions`. Pas de statut sur la table transactions (`FROM transactions` apparaît dans 15 fichiers backend : un filtre oublié = solde faux). |
| Base de données | SQLite conservé (WAL + busy_timeout, un seul worker uvicorn). Pas de migration Postgres. |
| Hébergement | VPS (Hetzner ou OVH) + Caddy (HTTPS Let's Encrypt automatique) + systemd. |

## Découpage en trois phases

Chaque phase est livrable et testable seule, avec son propre plan d'implémentation :

1. **Phase 1 : auth + comptes + rôles + scoping.** L'app devient multi-utilisateur,
   chacun voit son périmètre, toutes les écritures restent admin.
2. **Phase 2 : module `submissions`.** Workflow soumettre / valider / refuser avec PDF.
3. **Phase 3 : durcissement + déploiement.** Headers de sécurité, audit final des
   endpoints, VPS, HTTPS, domaine, sauvegardes distantes.

## Modèle de données

### Module `users` (nouveau, catégorie noyau)

Manifest + api.py + models.py + frontend, comme tout module.

- `users` : id, email UNIQUE, display_name, password_hash (scrypt via hashlib stdlib,
  zéro dépendance nouvelle), is_admin INTEGER, is_active INTEGER, created_at,
  last_login_at.
- `sessions` : id, token_hash (SHA-256 du token aléatoire 256 bits ; le token en clair
  ne vit que dans le cookie), user_id, created_at, expires_at (30 jours glissants),
  last_seen_at, user_agent.
- `user_entity_roles` : id, user_id, entity_id, role TEXT CHECK(role IN
  ('treasurer','viewer')). Le rôle s'applique à l'entité et tout son sous-arbre.
  Un user peut cumuler plusieurs lignes (trésorier de Gastronomine ET viewer du CCMP).
- `invitations` : id, token_hash, email, is_admin, roles_json (rôles à attribuer à
  l'acceptation), expires_at (72 h), used_at, created_by, created_at.

### Module `submissions` (nouveau, catégorie métier)

- `transaction_submissions` : id, date, label, description, amount (centimes, toujours
  positif, même convention que transactions), category_id, entity_id (entité interne
  du périmètre du soumetteur), counterparty_entity_id (le tiers), direction
  TEXT CHECK(direction IN ('expense','income')), status TEXT CHECK(status IN
  ('pending','approved','rejected','cancelled')), submitted_by (user id),
  reviewed_by, reviewed_at, review_comment, transaction_id (renseigné à
  l'approbation), created_at, updated_at.

À l'approbation, le backend crée une vraie transaction (from/to déduits de
entity_id + counterparty_entity_id + direction) et stocke son id dans la soumission.
Les soldes existants ne peuvent pas être pollués par construction : aucune requête de
balance.py, reports ou direns ne change.

### Module `attachments` (extension)

- Colonne nullable `submission_id` sur `attachments`. Un justificatif est lié soit à
  une transaction, soit à une soumission. À l'approbation, les justificatifs de la
  soumission sont re-liés à la transaction créée (transaction_id renseigné,
  submission_id conservé pour l'historique).

## Enforcement backend

### backend/core/auth.py (infrastructure transverse)

- `get_current_user` : dépendance FastAPI, lit le cookie, vérifie la session
  (token hashé, non expirée), renvoie le user. 401 sinon.
- `require_admin` : 403 si user non admin.
- `get_allowed_entity_ids(user)` : étend les rôles au sous-arbre via la CTE récursive
  existante du module entities. Admin : toutes. Renvoie aussi le rôle effectif par
  entité (treasurer prime sur viewer en cas de chevauchement).

### Deny by default

Dans l'app factory de `main.py` : toute route `/api/*` exige une session, sauf
allowlist explicite (`/api/auth/login`, acceptation d'invitation, health check).
Un futur module est protégé sans action de son auteur.

### Par endpoint

- **Lectures** (dashboard, transactions, budget, reports, reimbursements, entities) :
  le focus entité demandé est intersecté avec le périmètre autorisé, 403 si hors
  périmètre. La mécanique include_children existante est réutilisée telle quelle.
- **Écritures** : `require_admin` sur tout l'existant (transactions, catégories,
  budget, entities, backup, system, direns, helloasso). Exceptions : endpoints du
  module submissions (création par treasurer dans son périmètre, annulation de ses
  propres soumissions pending) et gestion de son propre compte (changement de mot de
  passe).
- **Catégories** : lecture pour tous les connectés (globales), écriture admin.
- **Attachments** : accès conditionné au droit de lecture sur la transaction ou la
  soumission liée (aujourd'hui n'importe quel id se télécharge : fermé en phase 1).
- **Tiers (entités externes)** : lisibles par les connectés (nécessaires pour
  soumettre), écriture admin.

## Frontend

- Page `/login` et page d'acceptation d'invitation (choix du mot de passe), dans le
  design system existant (DESIGN.md), tout en français avec accents.
- `AuthContext` (même pattern que `FiscalYearContext`) : user, rôles, périmètre.
  Garde de routes : non connecté vers /login.
- Sidebar et routes filtrées par rôle :
  - treasurer : Dashboard, Transactions (lecture), Budget, Remboursements,
    « Soumettre une dépense », ses soumissions.
  - viewer : lecture seule (Dashboard, Transactions, Budget, Rapports).
  - admin : tout, plus gestion des utilisateurs et file de validation des
    soumissions avec badge de comptage dans la sidebar.
- Arbre d'entités restreint au sous-arbre autorisé, focus par défaut sur l'entité
  du rôle.
- Aucun nom de module hardcodé : manifest.menu.label et INTEGRATED_LOCATIONS comme
  aujourd'hui (test_ui_text_coherence.py doit rester vert).

## Sécurité

- Cookie HttpOnly + Secure + SameSite=Lax. Anti-CSRF : vérification de l'en-tête
  Origin sur toutes les mutations (même origine garantie, FastAPI sert le build).
- Rate limiting slowapi (backend/core/rate_limit.py existant) durci sur
  /api/auth/login et l'acceptation d'invitation. Verrouillage progressif après
  échecs répétés, journal des connexions.
- Uploads : validation existante (20 Mo, sanitisation du nom, anti-traversal)
  complétée par une liste blanche de types (PDF + images) vérifiée par magic bytes.
- Headers : X-Content-Type-Options, X-Frame-Options, Referrer-Policy, CSP simple.
- Mots de passe : scrypt (hashlib stdlib), paramètres recommandés OWASP.
- Les tokens (sessions, invitations) ne sont jamais stockés en clair.

## Hébergement et exploitation

- SQLite : PRAGMA journal_mode=WAL + busy_timeout=5000 au démarrage, un seul worker
  uvicorn (documenté dans CLAUDE.md à la phase 3). Volumes réels : quelques milliers
  de transactions par an, une dizaine d'utilisateurs.
- VPS Hetzner ou OVH (4 à 6 euros par mois), Caddy en reverse proxy avec HTTPS
  Let's Encrypt automatique, service systemd. Nom de domaine choisi par Vicente.
- Sauvegardes : cron quotidien `sqlite3 .backup` + copie chiffrée hors site (rclone),
  en plus du module backup existant. Le dossier data/attachments est inclus.

## Tests

- conftest.py : la DB template embarque un admin par défaut ; la fixture `client`
  s'authentifie automatiquement en admin. Les 425 tests existants passent quasi
  inchangés. Nouvelles fixtures : `client_as(role, entity)` pour la matrice de
  permissions.
- Phase 1 : cycle login/logout/expiration/révocation, invitations (usage unique,
  expiration, rôles attribués), matrice rôle x endpoint (admin/treasurer/viewer/
  anonyme sur chaque famille de routes), scoping (entité hors périmètre : 403,
  focus intersecté), attachments fermés hors périmètre.
- Phase 2 : workflow complet (soumission, approbation, transaction créée avec
  from/to corrects, justificatif re-lié ; refus avec commentaire ; annulation),
  périmètre de soumission (entité hors rôle : 403),
  test_coherence_submissions.py : aucune soumission pending/rejected/cancelled
  n'affecte jamais un solde, un budget ou un rapport.
- Phase 3 : headers présents, rate limiting effectif, magic bytes uploads.

## Hors périmètre (YAGNI assumé)

- Notifications email (le badge de comptage suffit).
- OAuth / magic link (ajoutables plus tard par-dessus les sessions).
- Permissions fines par capacité (can_manage_budget...) : trois rôles suffisent
  pour 4 sous-clubs.
- Migration Postgres.
- Édition d'une soumission approuvée (on annule et on re-soumet).
