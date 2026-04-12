# Auth & Permissions — Design Spec

## Probleme

OpenFlow n'a aucun systeme de connexion. Toute personne accedant a l'URL voit tout. Pour un hebergement serveur avec des sous-clubs (Gastronomine, PapiMamine) qui ont chacun leur tresorier, il faut :
- Authentification (login/password)
- Sessions (deconnexion a la fermeture du navigateur)
- Permissions scopees par entite (tresorier Gastro ne voit que Gastro)

## Decisions

### Auth : Sessions DB + cookie HTTP-only

- Login cree une session en SQLite, retourne un cookie de session (`httponly`, `samesite=Strict`)
- Cookie sans `expires` = disparait a la fermeture du navigateur
- Chaque requete API verifie le cookie → cherche la session en DB → 401 si absente
- Deconnexion = supprime la session en DB → acces coupe immediatement
- Nettoyage automatique des sessions > 24h

### Permissions : role par entite

Pas de role global. Le role depend de l'entite assignee.

```
Table user_entities: user_id, entity_id, role
  role = 'tresorier' | 'lecteur'
```

**Tresorier** sur une entite = lire + ecrire (transactions, factures, budgets, exports) sur cette entite et ses enfants.

**Lecteur** sur une entite = consultation seule sur cette entite et ses enfants.

**Tresorier sur l'entite racine** = admin de fait. Peut gerer les users, la structure d'entites, tout. Pas de role "admin" separe — le pouvoir vient de la position dans l'arbre.

### Exemples

| User | Acces | Resultat |
|------|-------|----------|
| President BDA | tresorier sur BDA (racine) | Voit tout, modifie tout, gere users |
| Tresorier Gastro | tresorier sur Gastronomine | Ecrit sur Gastro et ses enfants |
| President Gastro | lecteur sur Gastronomine | Consulte Gastro seulement |
| Tom multi-clubs | tresorier PapiMamine + lecteur Gastro | Ecrit PapiMamine, lit Gastro |

### Securite

- Mots de passe hashes avec **bcrypt** (remplace SHA-256 actuel)
- Cookie `httponly=True, samesite=Strict, secure=False` (secure=True si HTTPS)
- Token de session = UUID4
- Protection CSRF via SameSite=Strict (suffisant pour app interne)
- Changement de mot de passe invalide toutes les sessions sauf la courante

## Modele de donnees

### Table `sessions` (nouvelle)

```sql
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,          -- UUID4
    user_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
)
```

### Table `user_entities` (nouvelle)

```sql
CREATE TABLE user_entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    entity_id INTEGER NOT NULL,
    role TEXT NOT NULL DEFAULT 'lecteur',
    UNIQUE(user_id, entity_id)
)
```

### Table `users` (existante, modifiee)

- `password_hash` passe de SHA-256 a bcrypt
- Migration : re-hash impossible (one-way), les users devront reset leur mot de passe

## Endpoints

### Auth

- `POST /api/multi_users/login` — body `{username, password}`, cree session, set cookie
- `POST /api/multi_users/logout` — supprime session
- `GET /api/multi_users/me` — retourne user + acces [{entity_id, entity_name, role}]
- `PUT /api/multi_users/me/password` — body `{old_password, new_password}`

### Admin (tresorier racine seulement)

- `GET /api/multi_users/` — liste tous les users (existant)
- `POST /api/multi_users/` — creer user (existant)
- `PUT /api/multi_users/{id}` — modifier user (existant)
- `DELETE /api/multi_users/{id}` — supprimer user (existant)
- `GET /api/multi_users/{id}/entities` — liste acces d'un user
- `POST /api/multi_users/{id}/entities` — assigner entite + role
- `DELETE /api/multi_users/{id}/entities/{entity_id}` — retirer acces

### Middleware

- Intercepte toutes les requetes `/api/*` sauf `/api/multi_users/login`
- Lit le cookie `session_id`, cherche en DB
- Si session invalide → 401
- Stocke `request.state.user` et `request.state.user_entities` pour les endpoints

### Guard par endpoint

Les endpoints entity-scoped verifient :
```python
def require_access(request, entity_id):
    # Verifie que le user a au moins lecteur sur entity_id (ou un parent)

def require_write(request, entity_id):
    # Verifie que le user a tresorier sur entity_id (ou un parent)

def is_root_admin(request):
    # Verifie que le user est tresorier sur l'entite racine
```

## Frontend

### Page login (`/login`)

- Plein ecran, pas de sidebar
- Username + password + bouton "Connexion"
- Erreur si credentials invalides
- Redirect vers `/dashboard` apres login

### Protection des routes

- Si pas de session → redirect vers `/login`
- `GET /api/multi_users/me` au chargement pour verifier la session

### Selecteur d'entites

- Ne montre que les entites auxquelles le user a acces
- Filtre base sur `user_entities`

### Page admin (dans Settings ou page dediee)

- Visible seulement si tresorier racine
- Liste des users avec leurs acces
- Creer/modifier/supprimer users
- Assigner entites + roles par user

### Changement de mot de passe

- Accessible a tous les users connectes
- Ancien mot de passe + nouveau + confirmation

## Ce qui est hors scope

- Registration publique (les users sont crees par l'admin)
- Reset de mot de passe par email (pas d'email, c'est local)
- 2FA
- OAuth / SSO
