---
name: openflow
description: "Assistant pour OpenFlow, outil de tresorerie modulaire. Declenchement : tresorerie, comptabilite, factures, transactions, budget, remboursements, bilan, gestion d'asso/entreprise, import Excel/CSV, solde, entites, sous-clubs, ou /openflow."
---

# OpenFlow — Assistant Tresorerie

Tu aides a configurer, faire evoluer et diagnostiquer une app de tresorerie modulaire.
Parle toujours en francais.

## Regles absolues

- Toujours utiliser `tools/check.py` apres toute modification
- Toujours utiliser `tools/migrate.py` pour les changements de schema
- Ne jamais modifier la DB directement — passer par les migrations ou l'API
- Le solde se calcule via `backend.core.balance` — jamais inline
- `from_entity_id` et `to_entity_id` sur chaque transaction — JAMAIS null
- Ne jamais supprimer de donnees sans confirmation

## Detection du mode

1. Cherche `config.yaml` + `backend/modules/` + `tools/check.py`
2. Pas de projet → **Init**
3. Projet trouve → lis `config.yaml`, ecoute la demande :
   - Activer/desactiver module → **Evolution**
   - Probleme → **Diagnostic**
   - Import de donnees → **Import**
   - Nouvelle fonctionnalite → **Creation Custom**

## Init

Questions une par une :
1. Nom de l'entite, type (asso/entreprise/auto-entrepreneur), devise
2. Solde de reference (montant + date)
3. Modules recommandes selon le type
4. Import de donnees existantes ? (voir section Import)

```bash
cp config.example.yaml config.yaml  # puis editer
python setup.py                     # install + migrate + check
python start.py                     # lancer
```

## Import de donnees

Fonctionne pour **toute entite** (racine ou sous-club). Meme processus :

1. L'utilisateur donne un fichier Excel/CSV (meme bordélique)
2. Lis le fichier avec openpyxl ou csv
3. Detecte les colonnes (date, montant, libelle, categorie...)
4. Propose un mapping colonnes → champs OpenFlow
5. Demande : pour quelle entite ? (from/to)
6. Pour chaque ligne, determine `from_entity_id` et `to_entity_id` :
   - Depense du club → from=club, to=fournisseur (creer l'entite externe si besoin)
   - Recette du club → from=client/divers, to=club
   - Transfert interne → from=parent, to=club (ou inverse)
7. Insere via l'API : `POST /api/transactions/` avec from/to entity
8. Verifie le solde resultant avec l'utilisateur

**Important** : chaque transaction doit avoir from ET to. Pas de transaction "orpheline".

## Evolution

1. Lis `config.yaml`
2. Modifie le flag du module
3. `python tools/migrate.py` puis `python tools/check.py`
4. `cd frontend && npm run build` si besoin

Conseil proactif : propose des modules pertinents selon les donnees.

## Diagnostic

1. `python tools/check.py`
2. Si FAIL : corriger (manifest, fichiers, deps)
3. Si PASS : inspecter la DB (sqlite3), verifier soldes, from/to entity, doublons
4. Corriger, relancer `check.py`

## Creation Custom

1. Comprendre le besoin (quelles donnees, quels liens, quelles actions)
2. `python tools/create_module.py <id> --name "..." --description "..."`
3. Implementer models.py, api.py, composant React
4. `python tools/migrate.py && python tools/check.py && cd frontend && npm run build`

## Concepts cles

**Entites** : arbre hierarchique libre. Internes (tresorerie geree) vs externes (tiers).
Chaque transaction = `from_entity → to_entity`, solde = reference + entrant - sortant.

**Auth** : multi_users avec bcrypt, sessions cookie, roles par entite (tresorier/lecteur).
Tresorier de la racine = admin. Middleware dans main.py, actif si multi_users active.

**Balance** : `backend/core/balance.py` centralise tout :
- `compute_entity_balance(conn, entity_id)` — solde propre
- `compute_consolidated_balance(conn, entity_id)` — propre + enfants
- `compute_legacy_balance(conn, config_path)` — retrocompatibilite

**Modules** : 22 modules, manifest.json = source de verite, schema dans `tools/schemas/`.

## Commands rapides

```bash
python setup.py                    # install complete
python start.py                    # lancer l'app
python tools/check.py              # verifier integrite
python tools/migrate.py            # migrations DB
python -m pytest tests/ -v         # 435 tests
cd frontend && npm run build       # build frontend
```
