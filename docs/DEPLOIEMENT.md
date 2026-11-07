# Déployer le projet

Deux éditions, deux déploiements indépendants : le **site web** (édition PC, sur le serveur) et le **Pi** (station
musicale). Une mise à jour de l'un ne touche jamais l'autre.

| | Site web (PC) | Pi |
|---|---|---|
| Où | le serveur (Docker) | le Raspberry Pi |
| Mise à jour | `bash deploy/pc/push.sh utilisateur@serveur` | `bash deploy/pi/push.sh pi@adresse-du-pi` |
| Premier déploiement | voir « Site web » ci-dessous | `install.sh` (Pi neuf) |
| Retour arrière | remettre l'ancien code, relancer `push.sh` | `ssh pi@… 'bash deploy.sh --rollback'` |
| Données | volume Docker `web-data` (base du site) | `~/.local/share/pi-media/` |

**Avant chaque mise à jour du site avec du nouveau** : ajouter la version en tête de `src/i18n/versions.yaml`
(page « Versions ») ; `push.sh` affiche la version envoyée et le rappelle si elle n'est pas datée du jour.

Les commandes se lancent depuis le dossier `sources/` du projet, sur ton poste.

## Site web (édition PC)

### Premier déploiement
Le site s'installe sous **le même utilisateur que Subsonic** (`music`), dans son dossier personnel : `~music/pimedia`.
Ainsi les fichiers envoyés appartiennent à `music`, comme le reste de la musique. Le site a sa propre base (volume
`pimedia_web-data`) ; il lit la bibliothèque dans Subsonic.

1. Sur le serveur : Docker installé, `music` dans le groupe `docker` (`sudo usermod -aG docker music`, puis se reconnecter).
2. **Joindre Subsonic.** Dans le conteneur du site, `127.0.0.1` est le conteneur lui-même, jamais le serveur :
   - Subsonic dans un conteneur (cas du serveur) : le site rejoint le réseau Docker de Subsonic et l'appelle par son nom.
     Une fois : `docker network create subsonic && docker network connect subsonic <conteneur Subsonic>` (sans
     redémarrage ; si Subsonic est lancé par un `compose.yaml`, y déclarer ce réseau externe pour qu'il le garde quand
     le conteneur est recréé). Dans le `.env` : `COMPOSE_FILE=compose.yaml:compose.subsonic.yaml`,
     `SUBSONIC_NETWORK=subsonic`, `SUBSONIC_URL=http://<conteneur Subsonic>:4040` (port interne du conteneur) ;
   - Subsonic hors Docker, ou port publié sur toutes les interfaces : `SUBSONIC_URL=http://host.docker.internal:4040`.
3. Créer `~music/pimedia/.env` à partir de `.env.example` (l'exemple explique chaque réglage). En plus de l'étape 2 :
   - `WEB_SECURE_COOKIE=true` (site en HTTPS, sinon la connexion échoue) et `WEB_TRUST_PROXY=true` (derrière Apache) ;
   - `APP_UID` / `APP_GID` : ceux de `music` (`id music`) ;
   - `MUSIC_DIR` : la racine de la musique (celle que Subsonic voit), pour la page « Envoyer » et le rangement ;
   - `SUBSONIC_PUBLIC_URL` : l'adresse de Subsonic pour les personnes (ex. `https://music.foos.fr`) quand
     `SUBSONIC_URL` est interne : bouton « Ouvrir mes réglages Subsonic » (Last.fm) de la page « Mon compte ».
4. Lancer `bash deploy/pc/push.sh music@serveur` depuis ton poste. Vérifier, sur le serveur, dans `~/pimedia` :
   ```bash
   curl -s 127.0.0.1:8200/health
   docker compose exec web python3 -c "import urllib.request as u, os; print(u.urlopen(os.environ['PI_MEDIA_WEB_SUBSONIC_URL'] + '/rest/ping.view').status)"
   ```
   La seconde vérifie que le conteneur joint Subsonic (200 attendu ; sinon revoir l'étape 2).
5. Apache en HTTPS devant (le site écoute sur `127.0.0.1:8200`) : `deploy/pc/apache-exemple.conf` (redirection HTTP,
   certificat Let's Encrypt, salon sans tampon, envois de 2 Go ; les commandes sont en tête du fichier). nginx :
   `deploy/pc/nginx-exemple.conf`.
6. Se connecter une fois avec un compte **administrateur** de Subsonic (nécessaire au scan après un envoi de musique).

Déjà installé sous un autre utilisateur ? Le volume des données (`pimedia_web-data`) appartient à l'ancien uid ; après le
premier `push.sh` sous `music`, le lui donner une fois :
```bash
ssh music@serveur 'cd pimedia && docker compose down && docker run --rm -v pimedia_web-data:/data alpine chown -R "$(id -u):$(id -g)" /data && docker compose up -d web'
```

### Mise à jour
```bash
bash deploy/pc/push.sh utilisateur@serveur
```
Le script copie le code (sans toucher au `.env` du serveur ni aux données), puis relance
`docker compose up -d --build web`. Les migrations de la base s'appliquent toutes seules au démarrage.
Les dossiers `.git`, `.idea` et `.vscode` sont exclus : les métadonnées du dépôt et de l'éditeur ne sont pas déployées
et les éventuelles configurations déjà présentes sur le serveur sont préservées.
La reconstruction installe aussi les nouvelles dépendances de `requirements.txt` (ex. `ytmusicapi`, 27/10/2026).

### Vérifier, lire le journal
```bash
ssh utilisateur@serveur 'cd pimedia && docker compose ps web && docker compose logs --tail 50 web'
```
Le site répond sur `/health` (`curl -s https://domaine/health` → `{"ok": true}` ; pas `curl -I` : le site ne gère pas
`HEAD`). Après une mise à jour, recharger la page en forçant (Cmd+Maj+R).

### Pièges rencontrés au premier déploiement
- **503 d'Apache alors que `127.0.0.1:8200/health` répond** : un autre vhost porte le même nom (ex. un ancien
  `<domaine>-le-ssl.conf` créé par `certbot --apache`) et passe avant. `sudo apache2ctl -S | grep <domaine>` ne doit
  montrer qu'une ligne par port ; le journal (`/var/log/apache2/error.log`) dit vers quel port Apache essaie d'aller.
  Retirer le lien en trop dans `sites-enabled/`, puis `configtest` et `reload`.
- **« Incoming : rangement impossible (Permission denied) » dans le journal** : des dossiers de `Incoming` appartiennent
  à un autre compte (root après un `sudo cp` ou un `scp root@…`). Déplacer un dossier demande d'avoir le droit d'écrire
  dessus : `sudo chown -R <utilisateur de Subsonic>:<groupe> <MUSIC_DIR>/Incoming`.
- **Ce qui est déjà dans `Incoming` est rangé aussi** (album bien nommé, inchangé depuis `INCOMING_WAIT_HOURS`) : mettre
  `INCOMING_WAIT_HOURS=0` pour ne ranger que les envois du site.

### Mémoire
Le site est limité à `WEB_MEM_LIMIT` (512m par défaut) : s'il dépasse, seul son conteneur est relancé. Le plus gros
consommateur reste Subsonic (Java), surtout pendant un scan : le limiter aussi dans **son** `compose.yaml` (sur le
serveur, pas dans ce dépôt), avec une limite du conteneur un peu au-dessus de la mémoire donnée à Java :
```yaml
    mem_limit: 1g
    environment:
      SUBSONIC_MAX_MEMORY: 512   # Mo pour Java ; vérifier que l'image le prend en compte (docker exec subsonic ps aux)
```
Contrôle : `docker stats --no-stream`.

### Sans Docker
Service systemd utilisateur : `deploy/pc/pimedia-web.service` (le fichier explique l'installation).

### Envoi de musique et rangement (facultatif)
Le site range les envois dans la bibliothèque : un zip est décompressé, chaque album bien nommé (`Artiste/Album/titre`)
part aussitôt chez son artiste, le reste attend dans `<MUSIC_DIR>/Incoming/`. Fonctionnement détaillé, exemples et
règles : `docs/features/envoi-fichiers.md`. Ce qui a été rangé automatiquement est noté dans `docker compose logs web`.

- `MUSIC_DIR` = la racine de la musique sur l'hôte, celle que Subsonic monte en lecture seule sur `/var/music` (image
  `gzurowski/subsonic`), ex. `/media/090c1ace-…/Music`. Le site la monte en écriture sur `/music` : il y crée des dossiers
  d'artistes et d'albums, et `Incoming` s'il manque ; il n'écrase et n'efface jamais rien dans la bibliothèque.
  Vide : `datas/Music` à côté de `compose.yaml` (test en local : `mkdir -p datas/Music`).
- `INCOMING_WAIT_HOURS` (1) : un album corrigé à la main dans `Incoming/Artiste/Album` est rangé après ce délai sans
  changement (0 = jamais).
- Le conteneur tourne sous l'uid/gid de `music` (`APP_UID`, `APP_GID`, appliqués à la construction de l'image) : il a
  les mêmes droits que `music` sur la musique, sans groupe à créer. Fichiers `664`, dossiers `775`.
- Taille : 300 Mo par fichier audio, 2 Go par zip (4 Go une fois décompressé). Le proxy doit laisser passer ces envois :
  `deploy/pc/nginx-exemple.conf` et `apache-exemple.conf` ont un bloc `/api/upload` pour cela (sinon refus « 413 »).
- Le scan (`startScan`) est réservé aux administrateurs de Subsonic : le site le lance avec le compte de la personne si elle
  est administratrice, sinon avec un administrateur qui s'est déjà connecté au site. **Un administrateur doit donc s'être
  connecté une fois au site** ; sans cela, les fichiers sont bien rangés mais n'apparaissent qu'au prochain scan de Subsonic.
- Si le site ne peut pas écrire, la page « Envoyer » le dit.

## Pi

### Mise à jour d'un Pi déjà installé
```bash
bash deploy/pi/push.sh pi@adresse-du-pi
```
Le script fabrique l'archive (`dist/pi-media-<date>.tar.gz`), l'envoie avec `deploy.sh` et l'installe. Les trois dernières
versions sont gardées sur le Pi ; les données (`.env`, base) ne sont jamais touchées.

### Retour arrière, état
```bash
ssh pi@adresse-du-pi 'bash deploy.sh --rollback'
ssh pi@adresse-du-pi 'bash deploy.sh --status'
```

### Pi neuf
Prérequis : Raspberry Pi OS 64 bits avec bureau, connexion automatique, accès Internet.
1. `python3 deploy/pi/build_archive.py` : crée `dist/` (archive, `install.sh`, `deploy.sh`, `migration.sh`).
2. Copier ces fichiers sur le Pi, dans un même dossier.
3. Sur le Pi : `bash install.sh` (paquets, AirPlay, Bluetooth, démarrage automatique, puis l'application ; les réglages
   manquants — adresse Subsonic, compte — sont demandés).
4. Une étape seule peut être refaite : `bash install.sh --etape airplay` (autres : paquets, applis, reglages, bureau, son,
   bluetooth, autorisations).

Ensuite, seules les mises à jour (`push.sh` ou `deploy.sh`) sont nécessaires.

### Essayer l'édition Pi sur le poste (Docker, sans le Pi)
Pour voir la page web du Pi et répéter une mise à jour sur le Mac avant de l'envoyer sur le vrai Pi.

| Subsonic | Commande | Adresse |
|---|---|---|
| le vrai (`.env`) | `docker compose --profile pi up -d --build pi` | `http://127.0.0.1:8399` (Traefik : `https://pi.pimedia.localhost`) |
| faux, de démonstration | `docker compose --profile pi-demo up -d --build pi-demo` | `http://127.0.0.1:8499` (Traefik : `https://pi-demo.pimedia.localhost`) |

- **Comme sur le Pi** : l'image `docker/pi/` est une Debian bookworm (comme Raspberry Pi OS 64 bits) avec l'utilisateur
  `pi` et les paquets que demande `deploy.sh` (python3, python3-yaml, mpv, curl). L'archive y est fabriquée par
  `deploy/pi/build_archive.py` (version = date et heure **UTC** de la construction) et installée au démarrage du conteneur
  par `deploy.sh` : `releases/`, lien `current`, `.env` et base dans le volume (`pi-data`, ou `pi-demo-data`).
  Au redémarrage, une version déjà installée n'est pas réinstallée : `deploy.sh --start` relance la version active.
- **Sans systemd** dans le conteneur : `deploy.sh` lance le serveur lui-même (`PI_MEDIA_SERVICE=direct`, réglé dans
  l'image ; journal dans `~/.local/share/pi-media/server.log`, affiché par `docker compose logs pi`). Sur le vrai Pi,
  cette variable n'existe pas : rien ne change (service `subsonic-web` de systemd).
- **Vrai Subsonic** : adresse `SUBSONIC_URL` du `.env` (ou `PI_SUBSONIC_URL` si elle diffère), compte du Pi
  `PI_SUBSONIC_USER` / `PI_SUBSONIC_PASS` (modèle : `.env.example`). Vides : la page affiche « Serveur non configuré » ;
  les saisir une fois dans le conteneur, gardés dans le volume :
  `docker compose exec -it pi bash /opt/pi-media/deploy.sh --configure`.
- **Faux Subsonic** : service `pi-subsonic` (image des tests, `tests/demo_subsonic.py`, bibliothèque inventée de la
  démonstration PC, compte `alice`), lancé tout seul avec `pi-demo`.
- **Son** : le vrai mpv, avec une sortie audio nulle (`ao=null` dans `~/.config/mpv/mpv.conf` de l'image) : la lecture
  haute fidélité avance comme sur le Pi, sans rien jouer. Dans le navigateur, le son est celui du Mac.
- **Pas dans le conteneur** : menu tactile Tk, écran (veille, luminosité), sortie audio et volume du système, Bluetooth,
  AirPlay, bouton Éteindre. La saisie depuis le téléphone démarre mais son port (8100) n'est pas ouvert hors du conteneur.

Répéter une mise à jour, comme `push.sh` mais vers le conteneur (qui doit tourner) :
```bash
bash docker/pi/push.sh                                # ou : bash docker/pi/push.sh pi-demo
docker compose exec pi bash /opt/pi-media/deploy.sh --status
docker compose exec pi bash /opt/pi-media/deploy.sh --rollback
```
`docker/pi/push.sh` fabrique l'archive sur le Mac, la copie avec `deploy.sh` dans le dossier de `pi`, puis lance
`deploy.sh` (vérification `/health`, retour automatique en cas d'échec). Reconstruire l'image (`up -d --build pi`) installe
aussi la nouvelle version par-dessus l'ancienne au démarrage.

Repartir de zéro (versions et données du Pi de test seulement ; **pas** `docker compose down -v`, qui effacerait aussi
le volume du site) :
```bash
docker compose --profile pi rm -sf pi && docker volume rm pimedia_pi-data
```

## Avant de déployer

Lancer tous les tests (unitaires et parcours navigateur simulé) :
```bash
docker compose build tests && docker compose run --rm tests
```
`docker compose run --rm tests` ne reconstruit pas l'image tout seul : sans le `build`, on teste l'ancien code.

## Ce qui n'a pas été vérifié sur le vrai matériel
Voir `docs/ETAT.md` (section « Non vérifié ») : le site contre le vrai Subsonic, `install.sh` sur un Pi neuf, le bouton
Éteindre, AirPlay, mpv sur le Pi.
