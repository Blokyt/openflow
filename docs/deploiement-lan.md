# Déploiement d'OpenFlow sur le réseau local de l'école

OpenFlow se déploie sur une machine du réseau local (pas de VPS, pas de domaine
public, pas de HTTPS). Le trafic circule en HTTP non chiffré : ce mode est
réservé à un réseau local de confiance. Ne jamais exposer ce serveur sur
Internet (pas de redirection de port sur la box).

## 1. Installation sur la machine hôte

```bash
git clone <repo> openflow && cd openflow
python setup.py
```

`setup.py` installe les dépendances, build le frontend, applique les
migrations et crée `config.yaml` depuis `config.example.yaml`.

## 2. Écoute réseau

Dans `config.yaml` :

```yaml
server:
  host: 0.0.0.0   # écoute LAN ; remettre 127.0.0.1 pour un usage local seul
  port: 8000
```

Puis :

```bash
python start.py
```

La bannière affiche l'URL à communiquer aux utilisateurs
(`http://<ip-de-la-machine>:8000`). Un seul worker uvicorn : SQLite (mode WAL,
busy_timeout 5 s) n'accepte qu'un processus écrivain. Ne jamais lancer
plusieurs instances sur la même base.

## 3. Pare-feu Windows

Autoriser le port entrant sur le réseau privé uniquement :

```powershell
netsh advfirewall firewall add rule name="OpenFlow LAN" dir=in action=allow protocol=TCP localport=8000 profile=private
```

## 4. Sécurité intégrée

- Connexion : verrouillage progressif après 5 échecs (délais croissants,
  plafond 30 min), aussi par IP (seuil 15). Journal des connexions dans
  la page Utilisateurs (admin).
- Uploads : seuls les PDF et images (PNG, JPEG, GIF, WebP) sont acceptés,
  vérifiés par le contenu binaire réel, 20 Mo maximum.
- Cookies de session HttpOnly + SameSite=Lax (l'attribut Secure s'active
  automatiquement si l'app passe un jour derrière HTTPS).
- Headers : CSP same-origin, X-Frame-Options DENY, nosniff. Pas de HSTS
  (HTTP volontaire en LAN).

## 5. Sauvegarde quotidienne externe

Configurer la destination (partage réseau, NAS, dossier Drive/OneDrive
monté) dans `config.yaml` :

```yaml
external_backup:
  destination: 'Z:/sauvegardes/openflow'
  retention: 14
```

Tester une fois à la main :

```bash
python tools/backup_externe.py
```

Chaque exécution crée `openflow-<horodatage>/` (base copiée à chaud via
l'API backup SQLite, dossier des justificatifs, config.yaml) puis supprime
les sauvegardes au-delà de `retention`.

Planifier l'exécution quotidienne (invite de commandes ADMINISTRATEUR,
adapter les chemins) :

```powershell
schtasks /Create /TN "OpenFlow sauvegarde externe" /TR "\"C:\chemin\vers\python.exe\" \"C:\chemin\vers\openflow\tools\backup_externe.py\"" /SC DAILY /ST 03:00
```

Vérifier : `schtasks /Run /TN "OpenFlow sauvegarde externe"` puis contrôler
le dossier de destination.

## 6. Restauration

1. Arrêter le serveur.
2. Remplacer `data/openflow.db` par le `openflow.db` de la sauvegarde choisie
   (supprimer aussi `data/openflow.db-wal` et `data/openflow.db-shm` s'ils
   existent).
3. Remplacer le contenu de `data/attachments/` par le dossier `attachments/`
   de la sauvegarde.
4. Relancer `python start.py`.
