# Design : Module HelloAsso (suivi des campagnes + rapprochement)

Date : 2026-06-21
Statut : validé en cadrage, en attente de relecture utilisateur avant plan d'implémentation

## 1. Contexte et objectif

Le BDA encaisse ses cotisations, billetteries et dons via HelloAsso (une seule
organisation HelloAsso). Aujourd'hui, rien ne relie HelloAsso à OpenFlow : les
recettes sont saisies à la main, sans moyen de voir d'un coup d'oeil ce qui a
été collecté en ligne par rapport à ce qui est enregistré en compta.

Objectif : un module `helloasso` qui **suit les campagnes/billetteries actives**
et affiche, pour chacune, l'**écart** entre le montant collecté sur HelloAsso et
le montant enregistré dans OpenFlow, avec un bouton pour **créer une transaction
d'ajustement de l'écart en un clic** (avec validation).

Le besoin n'est pas un pointage adhérent par adhérent : c'est un suivi **au
niveau campagne**. La création automatique a été écartée par l'utilisateur, car
les montants collectés évoluent dans le temps (ex : 3 700 € au moment de la
saisie, 4 000 € plus tard), ce qui rend tout calage automatique fragile.

## 2. Décisions de cadrage (entrées utilisateur)

- **Rôle** : suivi par campagne + ajustement en 1 clic (pas de pointage par paiement, pas de création automatique).
- **Structure HelloAsso** : un seul compte (le BDA), donc une seule clé API.
- **Rafraîchissement** : cache local + bouton « Rafraîchir » (consultable hors ligne).
- **Clé API** : stockée dans la config locale (hors versionnement Git).
- **Montant collecté** : on ne compte que la **part qui revient à l'association** (hors contribution volontaire au site HelloAsso), pour que l'écart colle aux sommes réellement reçues.

## 3. Périmètre

### Inclus (V1)
- Connexion API HelloAsso (OAuth2 client_credentials) en lecture.
- Récupération des campagnes (formulaires) et de leurs paiements encaissés.
- Cache local des campagnes et de leur montant collecté.
- Rattachement campagne -> (catégorie + club + contrepartie externe).
- Calcul de l'écart par campagne sur l'exercice en cours.
- Bouton d'ajustement : création d'une transaction d'écart validée par l'utilisateur.

### Exclu (hors V1, évolutions possibles)
- Rapprochement avec le relevé bancaire (virements groupés HelloAsso -> banque).
- Détail adhérent par adhérent (liste nominative des paiements).
- Création automatique de transactions sans validation.
- Gestion de plusieurs organisations HelloAsso.

## 4. Architecture

Module autonome respectant la convention OpenFlow (manifest + api + models +
frontend). Il ne modifie aucune table d'un autre module ; il réutilise l'API
transactions existante pour créer les ajustements.

```
backend/modules/helloasso/
  manifest.json      # id, name, description, help, version, category, menu, api_routes, db_models
  api.py             # router FastAPI : status, sync, campaigns, links, adjust
  client.py          # client HTTP HelloAsso : auth (token + refresh), forms, payments, pagination
  models.py          # migrations SQL (tables de cache + mapping)
frontend/src/modules/helloasso/
  index.tsx          # page principale (tableau de suivi)
  components/        # ligne de campagne, dialog de rattachement, dialog d'ajustement
```

- **Catégorie de module** : `metier` (comme reimbursements, budget, reports).
- **Dépendances de module** : `transactions`, `categories`, `entities` (et `budget` pour les exercices, en dépendance souple).
- **Dépendance Python** : un client HTTP. À l'implémentation, réutiliser `httpx`
  s'il est déjà présent dans `requirements.txt`, sinon l'ajouter (préféré à
  `requests` pour le support timeout/async). Ne pas tirer le SDK officiel
  `helloasso-python` (il ajoute Authlib et ne gère pas le refresh) : un client
  HTTP minimal est suffisant et plus simple à tester.

## 5. Modèle de données

Deux tables, créées par les migrations du module (sqlite3 brut via `get_conn()`).
Montants en **centimes entiers**, cohérent avec la table `transactions`.

### `helloasso_campaigns` (cache de synchronisation)
| colonne | type | rôle |
|---|---|---|
| id | INTEGER PK | identifiant local |
| form_type | TEXT | type HelloAsso (Membership, Event, Donation...) |
| form_slug | TEXT | slug du formulaire HelloAsso |
| title | TEXT | nom affiché de la campagne |
| state | TEXT | état (active / close) |
| collected_cents | INTEGER | part asso collectée sur l'exercice, en centimes |
| currency | TEXT | devise (EUR) |
| last_synced_at | TEXT | horodatage de la dernière synchro |

Unicité logique sur `(form_type, form_slug)`.

### `helloasso_links` (rattachement campagne -> compta)
| colonne | type | rôle |
|---|---|---|
| id | INTEGER PK | identifiant local |
| form_type | TEXT | type HelloAsso |
| form_slug | TEXT | slug du formulaire |
| category_id | INTEGER | catégorie OpenFlow cible |
| from_entity_id | INTEGER | contrepartie externe (ex : Membres BDA) |
| to_entity_id | INTEGER | club interne bénéficiaire |
| created_at | TEXT | horodatage |

Unicité sur `(form_type, form_slug)` : une campagne se rattache à un seul poste.

### Credentials
Stockés dans `config.yaml` (gitignored), section dédiée :
```yaml
helloasso:
  client_id: "..."
  client_secret: "..."
  organization_slug: "bda-ens-paris-saclay"
```
Lecture via `backend/core/config.py`. Aucune clé en clair dans le code ni dans
un fichier versionné. La base `data/openflow.db` étant locale (non versionnée),
le cache des campagnes n'expose pas de secret.

## 6. Intégration API HelloAsso

Base : `https://api.helloasso.com/v5`. Détails confirmés dans la doc officielle
(voir Références).

### Authentification (client_credentials)
- `POST https://api.helloasso.com/oauth2/token` avec `grant_type=client_credentials`, `client_id`, `client_secret`.
- Réponse : `access_token` (valide 30 min / 1800 s), `refresh_token` (30 jours), `token_type=bearer`.
- La clé API générée depuis le back-office de l'organisation embarque
  automatiquement le rôle `OrganizationAdmin` et les privilèges
  `AccessPublicData` + `AccessTransactions` : l'orga accède donc à ses propres
  formulaires et paiements **sans** flux `authorization_code` ni login
  utilisateur. (Le `authorization_code` ne concerne que les prestataires tiers.)
- Limite : 20 access_tokens valides simultanés par clé. Le client garde un token
  en mémoire et le rafraîchit via `refresh_token` quand il expire (le SDK ne le
  fait pas tout seul : on l'implémente).

### Endpoints lus
- `GET /organizations/{slug}/forms` : liste des campagnes/formulaires. Pagination `pageSize` (défaut 20) + `continuationToken`.
- `GET /organizations/{slug}/payments` : paiements de l'organisation (filtrables par date). Même pagination.
- `GET /organizations/{slug}/forms/{formType}/{formSlug}/payments` : paiements d'un formulaire donné (alternative ciblée).

### Calcul du montant collecté (part asso)
- On récupère les paiements de l'exercice en cours et on agrège par campagne.
- On ne retient que les paiements **encaissés** (état autorisé) ; les remboursés / refusés sont exclus.
- On exclut la **contribution volontaire au site HelloAsso** pour ne garder que
  la part revenant à l'association.
- Point à valider sur le swagger lors de l'implémentation : le champ exact
  donnant la part nette asso (ventilation par `items` / `shares` du paiement vs
  montant brut). La décision de design est fixée (part nette) ; seul le champ
  source reste à confirmer techniquement.

## 7. Flux de synchronisation

1. L'utilisateur ouvre la page HelloAsso ou clique « Rafraîchir ».
2. Le backend obtient/rafraîchit le token, appelle `forms` (toutes les pages) et `payments` de l'exercice (toutes les pages).
3. Il agrège la part asso encaissée par campagne, met à jour `helloasso_campaigns` (upsert sur `form_type`+`form_slug`, `last_synced_at`).
4. La page lit le cache, calcule l'enregistré et l'écart, et affiche le tableau.

La synchro est explicite (pas de tâche de fond, pas de cron) : adapté à une app
locale lancée à la demande.

## 8. Rattachement et calcul de l'écart

- **Rattachement** : l'utilisateur associe chaque campagne à `category_id` + `to_entity_id` (club) + `from_entity_id` (contrepartie externe). Persisté dans `helloasso_links`.
- **Enregistré** : somme des transactions de la catégorie rattachée, vers le club rattaché, sur l'exercice en cours.
  - Convention OpenFlow : une recette est une transaction dont `to_entity_id` est l'entité interne bénéficiaire.
  - `enregistre_cents = SUM(transactions.amount) WHERE category_id = link.category_id AND to_entity_id = link.to_entity_id AND date BETWEEN exercice.debut AND exercice.fin`.
  - Bornes d'exercice issues du module `budget` (`fiscal_years`) ; exercice courant par défaut, sélection possible via le `FiscalYearContext` du front.
- **Écart** : `ecart_cents = collected_cents - enregistre_cents`.
- Campagne sans rattachement : affichée « à rattacher », sans calcul d'écart.

Note sur les collisions : si deux campagnes pointaient vers la même
catégorie + club, leurs « enregistrés » se confondraient. La granularité
actuelle des catégories du BDA (une par évènement/pôle) rend ce cas rare ; il
sera traité par affinage (sous-catégorie dédiée) si nécessaire, pas en V1.

## 9. Écran « HelloAsso »

Tableau, une ligne par campagne :

| Campagne | Type | Statut | Collecté (HelloAsso) | Enregistré (compta) | Écart | Action |
|---|---|---|---|---|---|---|

- Tri par écart décroissant (les campagnes à régulariser remontent).
- Filtre rapide : actives / toutes.
- En tête : bouton « Rafraîchir » + date de dernière synchro + sélecteur d'exercice.
- Ligne non rattachée : badge « à rattacher » + bouton « Rattacher » (ouvre un dialog catégorie/club/contrepartie).
- Ligne rattachée avec écart non nul : bouton « Ajuster ».
- Ligne rattachée à l'équilibre : coche verte, pas d'action.
- Widget dashboard (optionnel V1) : nombre de campagnes avec écart à régulariser.

## 10. Ajustement en un clic

- L'utilisateur clique « Ajuster » sur une campagne.
- Un dialog récapitule la transaction qui sera créée :
  - date = aujourd'hui,
  - libellé = « Ajustement HelloAsso, <titre campagne> »,
  - montant = valeur absolue de l'écart (centimes),
  - catégorie / club / contrepartie = ceux du rattachement,
  - sens : écart positif (collecté > enregistré) => recette (`from` externe -> `to` club) ; écart négatif => régularisation inverse.
- À la validation, création via l'API transactions existante (`POST /api/transactions/`).
- Au rafraîchissement suivant, l'enregistré inclut l'ajustement et l'écart retombe à zéro (auto-cohérent).

## 11. Endpoints du module (backend)

- `GET /api/helloasso/status` : config présente ?, dernière synchro, nombre de campagnes en cache.
- `POST /api/helloasso/sync` : déclenche la synchro (forms + payments), met à jour le cache, renvoie les campagnes.
- `GET /api/helloasso/campaigns?fiscal_year_id=...` : cache + enregistré + écart calculés.
- `GET /api/helloasso/links` / `PUT /api/helloasso/links` : lecture / écriture du rattachement d'une campagne.
- `POST /api/helloasso/campaigns/{form_type}/{form_slug}/adjust` : crée la transaction d'ajustement (après confirmation côté front).

## 12. Gestion des erreurs

- **Config absente** : la page affiche un onboarding « Configure ta clé API HelloAsso » ; les endpoints renvoient 409/400 explicite.
- **Token expiré (401)** : refresh automatique ; en cas d'échec, message « reconnecte ta clé ».
- **Droits insuffisants (403)** : message « clé invalide ou privilèges manquants, régénère ta clé depuis HelloAsso ».
- **Réseau / HelloAsso indisponible** : on sert le dernier cache avec un bandeau « dernière synchro le <date> » ; pas d'écran vide.
- **Rate limit (429)** : backoff court + message ; la synchro reste relançable.
- **Campagne non rattachée** : pas d'écart calculé, badge « à rattacher ».
- **Écart négatif** : on propose une régularisation inverse (sortie), jamais d'écriture silencieuse.

## 13. Tests (obligatoires, avant de considérer la feature terminée)

Conformément aux règles du projet (chaque endpoint et comportement métier testé,
DB isolée par test). Les appels HelloAsso sont mockés (pas d'appel réseau réel).

- **client.py** : récupération de token, refresh à expiration, pagination (`continuationToken`), agrégation part asso (exclusion contribution HelloAsso et remboursés).
- **sync** : forms + payments mockés -> cache correct (upsert, montants, état).
- **calcul écart** : collecté vs enregistré sur l'exercice (cas nominal, hors exercice exclu, campagne non rattachée).
- **links** : CRUD du rattachement, unicité par campagne.
- **adjust** : 201 et transaction correcte (montant, catégorie, club, sens) ; 400 si campagne non rattachée ; 409/400 si config absente ; écart négatif -> sens inversé.
- **cohérence** : après `adjust`, un nouveau calcul d'écart renvoie zéro.
- **erreurs** : 401/403/429/réseau gérés sans planter, cache servi en repli.

## 14. Points à valider lors de l'implémentation

- Présence de `httpx` dans `requirements.txt` (sinon l'ajouter).
- Champ exact de l'API donnant la part nette revenant à l'asso (ventilation du paiement).
- Format précis de `form_type` / `form_slug` renvoyé par `forms` vs présent sur les `payments` (pour l'agrégation par campagne).
- Mécanisme retenu pour les bornes d'exercice si le module `budget` est désactivé (repli sur année civile).

## 15. Références

- Authentification HelloAsso : https://dev.helloasso.com/docs/getting-started
- Privilèges et rôles : https://dev.helloasso.com/docs/privil%C3%A8ges-et-r%C3%B4les
- SDK Python officiel (référence d'endpoints) : https://github.com/HelloAsso/helloasso-python
- Endpoint paiements par formulaire : https://dev.helloasso.com/reference/get_organizations-organizationslug-forms-formtype-formslug-payments
