# Déployer le projet

Correctif 1.27.1 publié le 28/11/2026 après retour immédiat : le menu principal démarre ouvert et garde
sa colonne avec toutes les anciennes préférences ; les suggestions de l’accueil dédoublonnent les albums.
Commit applicatif `3b14bf9`, image `a533827ea7d2`. Tests ciblés et contrôle visuel bureau/mobile ; aucune
nouvelle suite complète à la demande de l’utilisateur. HTTPS et version 1.27.1 vérifiés, conteneur sain,
340 fichiers applicatifs et 88 ressources publiques conformes. Schéma 32 inchangé, intégrité et clés
étrangères valides. Sauvegarde préalable `../pimedia-backups/pre-1.27.1-20261128T132112Z/` et image
`pimedia-web:pre-1.27.1-20261128T132112Z`. Configuration, volumes et fichiers musicaux conservés.

Publication 1.27 du 28/11/2026 : livraison regroupée de l’accueil, de la navigation, des favoris,
des sorties et des playlists. La 1.24.2 publiée hors branche a été préservée, migration 31 comprise ;
l’historique personnel est en migration 32. Sauvegarde cohérente code/configuration/SQLite dans
`../pimedia-backups/pre-1.27-20261128T131348Z/`, image de retour arrière
`pimedia-web:pre-1.27-20261128t131348z`. Migration répétée en conteneur isolé sur la sauvegarde réelle :
38 tables et 73 910 lignes existantes conservées. Les sources du commit `8dface8` ont été copiées
seules, sans écraser le `.env` ni les fichiers Compose du serveur. Image `68ac4ed2e675`, service web
sain, version publique 1.27, schéma 32 intègre et sans clé étrangère orpheline ; 340 fichiers applicatifs
et 88 ressources HTTPS conformes. Aucune nouvelle suite complète à la demande de l’utilisateur.

Publication 1.18 vérifiée le 27/11/2026 sur https://music2.foos.fr : conteneur sain, version publique,
253 fichiers exécutés et 62 ressources HTTPS conformes à la livraison isolée de la 1.17. Menu et pastille
confirmés dans le HTML publié. Aucune migration : schéma 22, intégrité et clés étrangères valides,
notification n° 1 à Mnu conservée. Aucun message supplémentaire envoyé. Sauvegarde code/configuration/SQLite :
`../pimedia-backups/pre-1.18-20261127T005355Z/` ; image précédente `pimedia-web:pre-1.18-20261127t005355z`.
Les dix fichiers applicatifs modifiés ou ajoutés se limitent au menu de compte et à son signal de notification.
Photo visible sur mobile ; notifications et déconnexion retirées de la navigation principale. Copie ciblée de
`src/`, reconstruction du seul service web. Code de production 1.17 comparé à l’instantané avant publication ;
configuration et volume de données conservés. Validation : cinq tests de versions, 58 contrôles du composant
mobile, parcours Notifications/PC/mobile et Chrome à 1440/390/320 px, ainsi que 667×375 en paysage,
clair/sombre ; liens et vraie déconnexion vérifiés sur des comptes de test. Aucun changement backend.
Le retour de code peut conserver la base actuelle et les messages reçus.

Publication 1.17 le 27/11/2026 : notifications administratives privées et refus des fichiers audio seuls.
Livraison isolée issue du code de production 1.16, avec les correctifs de cache d’attribution et de rangement
précédemment préparés en 1.16.1. Copie ciblée de `src/`, puis `docker compose up -d --build web` : configuration,
volumes, documentation distante et autres fichiers préservés. Les 303 fichiers source préexistants avaient
été comparés à l’instantané avant publication ; les 16 fichiers applicatifs modifiés ou ajoutés sont ceux testés.
Migration 22 additive : table notifications indépendante. Répétition sur une copie de la base de production,
contenu des 26 tables existantes conservé. Validation : 154 tests Python et parcours Notifications/PC/mobile ;
Chrome à 1440/390/320 px clair/sombre. En production : 251 fichiers exécutés et 60 ressources HTTPS conformes,
version 1.17, santé HTTP et Docker, intégrité SQLite et clés étrangères valides. Refus MP3 HTTP 400 sans
écriture vérifié. Notification n° 1 envoyée à Mnu via l’API en service, en utilisant une session administrative
temporaire supprimée après l’envoi ; clé de dédoublonnage liée à l’envoi 18. Aucun message envoyé à un autre membre.
Le MP3 de cet envoi a été retiré sur demande ; copie de récupération hors catalogue dans
`/data/removed-uploads/upload-18/`, SHA-256 `3509600ba2224c1095ff55750046911650c431b413787c1e588c72f25462043b`.
Scan Subsonic terminé et disparition de la recherche vérifiée ; ancienne fiche encore lisible par son ID.
Sauvegarde code/configuration/SQLite : `../pimedia-backups/pre-1.17-20261127T002811Z/` ; image précédente :
`pimedia-web:pre-1.17-20261127t002811z`. La migration ajoute une table sans modifier les tables existantes :
l’ancien code peut conserver la base courante ; les notifications y restent stockées sans interface dans
l’ancienne version. Toute restauration complète de SQLite doit préserver les écritures reçues depuis la sauvegarde.

Publication 1.16 le 26/11/2026 : Help est organisé en sept thèmes et 39 guides pas à pas,
avec mises en avant du salon, des paroles synchronisées et des journaux.
Publication le 26/11/2026 depuis une livraison isolée de la production 1.15.2, par
`deploy/pc/push.sh` (empreinte `e01ea663204e`). Seuls les 12 fichiers applicatifs Help
diffèrent de la production précédente. Les 245 fichiers exécutés et 64 ressources HTTPS, dont les
six captures, correspondent à cette livraison. Menu et titre Help, sept thèmes, 39 guides et
117 étapes confirmés par HTTPS. Conteneur sain, configuration et volume de données conservés ;
SQLite intègre au schéma 21, clés étrangères valides. Les recherches et autres écritures reçues
pendant la publication sont conservées. Sauvegarde code/configuration/SQLite :
`../pimedia-backups/pre-1.16-20261126T221729Z/` ; image précédente `pimedia-web:pre-1.16-20261126t221729z`.
Aucune migration. Le retour de code peut conserver la base courante.
Validation de la livraison exacte : 12 groupes Help, parcours PC général, parcours mobile complet
et cinq tests de versions réussis.

Publication 1.15.2 le 26/11/2026 : le menu et le titre de la page d’aide deviennent « Help »,
plus court sur mobile, à la demande de l’utilisateur. Correction de texte sur la 1.15.1, sans tests relancés.
Mise à jour ciblée et reconstruction Docker ; HTTPS confirme le nouveau libellé, la version et la santé du site.
Aucune migration ni modification de configuration. Sauvegarde code/configuration/SQLite :
`../pimedia-backups/pre-1.15.2-20261126T213916Z/` ; image précédente : `pimedia-web:pre-1.15.2-20261126t213916z`.

Publication 1.15.1 le 26/11/2026 : le menu « Nouveautés » et le titre de sa page deviennent
« Découvrir l’application ». Correction de libellé au troisième numéro, publiée sur la version mobile 1.15.
Mise à jour ciblée des textes, de l’historique et du commentaire du composant, puis reconstruction Docker.
Les 235 autres fichiers applicatifs restent identiques à la 1.15 ; aucune migration ni modification de
configuration. HTTPS confirme la version, le menu et le titre ; conteneur sain. Aucune suite de tests
relancée, conformément à la consigne sur les modifications de texte du 26/11/2026.
Sauvegarde cohérente code/configuration/SQLite : `../pimedia-backups/pre-1.15.1-20261126T212908Z/` ;
image précédente : `pimedia-web:pre-1.15.1-20261126t212908z`. Le retour de code peut conserver la base courante.

Publication 1.15 le 26/11/2026 : responsive isolé pour les petits écrans, menu artistes/playlists
et salon en volets ; CSS et JS mobiles dédiés. Navigation PC et moteur YouTube conservés. L’instantané
reprend la production 1.14.2 et ajoute seulement cette évolution ; les travaux de tags et de textes encore
préparés séparément ne sont pas inclus.
Publication le 26/11/2026 depuis l’instantané testé du commit `376064d`, par
`deploy/pc/push.sh`. Version publique 1.15, conteneur sain, 238 fichiers applicatifs et
57 ressources HTTPS conformes. Validation de cet instantané : 58 contrôles mobiles,
parcours complet mobile, parcours PC général et cinq tests de versions. Configuration et volume de données
conservés ; SQLite intègre au schéma 21, clés étrangères valides. Les messages et sessions reçus pendant
la publication sont conservés. Sauvegarde code/configuration/SQLite : `../pimedia-backups/pre-1.15-20261126T212335Z/` ;
image précédente `pimedia-web:pre-1.15-20261126t212335z`. Aucune migration ; le retour de code peut conserver la base courante.

Publication 1.14.2 le 26/11/2026 : correctif de priorité des biographies, Last.fm via l'API Subsonic avant
Wikipédia français puis anglais, depuis l'instantané du commit dédié `81f5d3f`, par `deploy/pc/push.sh`.
Le code et la note de version de ce correctif sont les seules différences applicatives avec la production
précédente. Validation initiale : 30 tests Python ciblés et parcours jsdom PC général ; 12 tests biographies/versions
passent aussi sur l'instantané isolé. En production : version publique 1.14.2, 234 fichiers applicatifs conformes,
conteneur sain, aucune erreur de démarrage ; biographie du groupe Jungle et lien Last.fm vérifiés sur la route réelle.
SQLite reste au schéma 21, intègre, avec clés étrangères valides et comptages métier conservés. Configuration
inchangée, aucune nouvelle dépendance déclarée. Sauvegarde code/configuration/SQLite :
`../pimedia-backups/pre-1.14.2-20261126T211022Z/` ; image précédente
`pimedia-web:pre-1.14.2-20261126t211022z`. Le retour arrière peut conserver la base actuelle.

Publication 1.14 le 22/11/2026 : commentaires privés des recommandations, depuis l'instantané testé du
commit `68ba21a`, par `deploy/pc/push.sh`. Version mineure pour cette nouvelle possibilité, conformément
à la nomenclature confirmée par l'utilisateur ; troisième numéro réservé aux corrections de bugs. Une simple
renumérotation ne justifie pas de relancer la suite complète : contrôle ciblé de l'historique des versions.
Le correctif de tags préparé séparément n'est pas inclus.
Migration web 21 : fils de commentaires, archivage et curseurs de lecture des deux participants. Répétition
sur une copie de sauvegarde : valeurs des 25 tables existantes, identifiants et marqueurs de lecture conservés.
Sauvegarde cohérente code/configuration/SQLite : `../pimedia-backups/pre-1.14-20261122T210559Z/` ;
image précédente `pimedia-web:pre-1.14-20261122t210559z`. Configuration et dépendances conservées.
Validation de l'instantané : 869 tests Python et quatre parcours jsdom PC. En production : version publique
1.14, 234 fichiers applicatifs et 53 ressources HTTPS conformes, conteneur sain, SQLite intègre au schéma 21,
clés étrangères et données métier conservées. Les contrôles de session/CSRF ne créent aucun commentaire réel.
Attention au retour vers une ancienne image : l'unicité des conseils est maintenant partielle (conseils actifs).
Le code 1.13 ne peut pas être remis seul sur ce schéma. Préparer un retour code/base cohérent en tenant compte
des écritures reçues depuis la sauvegarde ; ne pas restaurer aveuglément l'ancienne base.

Publication 1.13 le 21/11/2026 : recommandations de morceaux avec lecture groupée et retrait individuel,
depuis l'instantané testé du commit `da9edc6`, par `deploy/pc/push.sh`. Migration web 20 : les tables
`listen_later` et `recommendations` acceptent les morceaux Subsonic. Reconstruction transactionnelle,
identifiants et marqueurs de lecture conservés ; répétée sur une copie de la sauvegarde avant publication.
Sauvegarde cohérente code/configuration/SQLite : `../pimedia-backups/pre-1.13-20261121T174551Z/` ; image
précédente `pimedia-web:pre-1.13-20261121t174551z`. Aucun nouveau réglage ni dépendance ; `.env` inchangé.
Validation : 853 tests Python et trois parcours jsdom PC, Chrome à deux comptes avec SSE et six rendus.
En production : version publique 1.13, 231 fichiers applicatifs et 52 ressources HTTPS conformes,
conteneur sain sans erreur de démarrage. SQLite intègre au schéma 20, clés étrangères valides et données
métier conservées ; contrôles de session et CSRF réussis sans écriture de données utilisateur.
Le retour de code utilise l'image conservée ; toute restauration SQLite doit tenir compte des écritures
reçues depuis la sauvegarde. Les commits restent locaux, séparés par évolution ; aucun push Git.

Publication 1.12 le 20/11/2026 : instantané de la 1.11.1 avec les colonnes configurables, sans les changements
de progression des tags 1.11.3 préparés séparément. 148 tests Python et les deux parcours PC principaux
rejoués sur cet instantané, publication par `deploy/pc/push.sh`. Les 231 fichiers applicatifs et 52 ressources
HTTPS sont conformes ; version publique 1.12, conteneur sain et aucun marqueur d’erreur de démarrage.
Sauvegarde code/configuration/données avec copie SQLite cohérente :
`../pimedia-backups/pre-1.12-20261119T230713Z/`, image précédente `pimedia-web:pre-1.12-20261119t230713z`.
SQLite reste intègre au schéma 19, données conservées. Aucun changement d’infrastructure ni tag réel écrit.

L'éditeur de tags 1.11, publié le 18/11/2026, ajoute Mutagen 1.47.0
aux dépendances PC ; reconstruire l'image lors d'une mise à jour. Il réutilise `MUSIC_DIR` monté en
écriture et le volume de données existants, sous le même UID/GID que la musique. Les sauvegardes techniques
restent hors de la musique dans `<data_dir>/audio-tag-backups` (24 h, huit lots, 4 Gio pour les lots terminés).
Prévoir l'espace pour les originaux et les copies temporaires. Aucun nouveau volume, réglage obligatoire ni
migration SQL. Discogs réutilise son jeton configuré ; MusicBrainz n'exige pas de clé pour la consultation.
Le comportement du vrai Subsonic après regroupement des tags d'album/artiste, notamment les liens,
commentaires et favoris, reste à vérifier sur une copie. Voir [Tags d'albums](features/tags-albums.md).

Publication 1.11 : instantané figé du code testé, 230 fichiers applicatifs conformes dans le conteneur,
HTTPS et note de version vérifiés. Le droit d'édition est `coverArt`, sans exiger `admin` ; le scan réutilise
un administrateur connu valide. Sauvegarde préalable code/configuration/données avec copie SQLite cohérente :
`../pimedia-backups/pre-1.11-20261117T234433Z/`. Image précédente conservée :
`pimedia-web:pre-1.11-20261117t234433z`. SQLite reste au schéma 19, intègre, et les données sont conservées.
Aucun enregistrement de tags ni test d'écriture sur la musique de production pendant les contrôles.

Publication 1.11.1 le 18/11/2026 : style en premier et résultats d'éditions en cartes. L'image est reconstruite
depuis l'instantané testé ; les 230 fichiers applicatifs et les JS/CSS publics sont conformes, la santé HTTPS,
le conteneur et la note publique vérifiés. Sauvegarde préalable code/configuration/données avec copie SQLite
cohérente : `../pimedia-backups/pre-1.11.1-20261118T000805Z/`. Image 1.11 conservée sous
`pimedia-web:pre-1.11.1-20261118t000805z`. Schéma 19, intégrité et données métier inchangés ; aucun tag réel écrit.

Publication 1.12.1 le 20/11/2026 : progression de la préparation et de l’enregistrement des tags, puis
suivi distinct de l’actualisation. Numérotation corrigée après publication de la 1.12 ; instantané basé
sur cette version, colonnes des morceaux conservées. Déploiement par `deploy/pc/push.sh` après 116 tests
Python et deux parcours PC sur l’instantané exact. Les 231 fichiers applicatifs et 52 ressources publiques
sont conformes ; santé HTTPS, version publique et conteneur sain vérifiés, aucune erreur de démarrage.
SQLite intègre au schéma 19, données métier conservées. Sauvegarde préalable :
`../pimedia-backups/pre-1.12.1-20261120T190256Z/`, image `pimedia-web:pre-1.12.1-20261120t190256z`.
Aucun tag réel modifié. Accès SSH de déploiement : compte `subsonic` sur l’hôte du projet, avec la clé
existante et vérification stricte de l’identité d’hôte ; ne pas utiliser les comptes music ou thomas.

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

### Compteurs de la bibliothèque (facultatif, 1.7.12)

Le site peut lire les statistiques que Subsonic a déjà enregistrées après son scan. Monter son fichier
`subsonic.properties` en lecture seule avec `compose.statistics.yaml`, en plus des fichiers Compose habituels :

```dotenv
COMPOSE_FILE=compose.yaml:compose.subsonic.yaml:compose.statistics.yaml
SUBSONIC_PROPERTIES_FILE=/chemin/des/donnees/subsonic.properties
```

Le chemin désigne **le fichier existant sur l’hôte Docker**, lisible par l’utilisateur du conteneur web.
Le montage refuse de créer un dossier si ce fichier manque. Ne pas changer les permissions de la configuration
Subsonic pour l’exposer publiquement. Le navigateur ne reçoit que les compteurs et la date du scan.
Le fichier n’est ni copié dans l’image ni servi par HTTP, et le site ne le modifie jamais.
Subsonic conserve déjà ces chiffres entre les redémarrages : aucune nouvelle base, tâche planifiée ou clé API.
L’accueil prend les nouveaux chiffres lors de sa prochaine ouverture après un scan terminé.

Hors Docker, régler `PI_MEDIA_WEB_SUBSONIC_STATISTICS_FILE` sur le fichier lisible en lecture seule.
Sans cette option, le reste du site fonctionne et le bloc des compteurs reste masqué. Si le fichier monté est
remplacé manuellement par renommage (restauration de sauvegarde), recréer le conteneur web pour renouveler ce
montage de fichier. Les sauvegardes ordinaires de Subsonic mettent à jour le fichier en place.

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
La version 1.7.10 ajoute `DISCOGS_API_KEY` au `.env` et son passage à `PI_MEDIA_WEB_DISCOGS_API_KEY` dans le conteneur
web. Jeton personnel Discogs, facultatif et strictement côté serveur ; ne pas le copier dans une commande ou un journal.
`LASTFM_API_KEY` active les critères auditeurs/écoutes des albums en plus des pochettes. Après réglage,
reconstruire/recréer le conteneur web pour charger la configuration. Aucun changement de schéma.

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

La 1.10.3 regroupe les accès du site dans `pimedia/webapp/library/` et ajoute `anyascii==0.3.3` aux dépendances PC.
Publiée le 18/11/2026 sur https://music2.foos.fr depuis l’archive du commit `c52cf40`, par `deploy/pc/push.sh`.
Sauvegarde cohérente code/configuration/SQLite : `../pimedia-backups/pre-1.10.3-20261117T231434Z` ;
image précédente : `pimedia-web:pre-1.10.3-20261117t231434z`. Aucun changement de schéma (19), de configuration ni des dépendances Pi.
Les 219 fichiers applicatifs, AnyASCII et la santé HTTPS sont vérifiés ; SQLite est intègre et ses comptages conservés.
Le rangement automatique d’Incoming a placé l’album Trentemøller ; dix fichiers identiques avant/après et indexation
Subsonic confirmés après scan. La note 1.10.3 est datée du 18/11/2026. PR différée ; recharger avec Cmd+Maj+R.
Pour une mise à jour ultérieure, envoyer l’arbre complet : le déplacement des modules nécessite la suppression
des anciens chemins, assurée par le script habituel. Le code partagé et le Pi restent sans dépendance à AnyASCII.


La 1.10.2 remplace les écoutes par le style sur les cartes d’albums, sauf dans « Plus écoutés » ; la fiche
album garde les écoutes. Aucun changement de schéma, de configuration ou de dépendance.
Publiée le 17/11/2026 sur https://music2.foos.fr par `deploy/pc/push.sh`, après 71 tests Python ciblés,
344 contrôles du parcours PC jsdom et rendu Chrome (grilles normale/compacte, 1440/390/320 px).
Sauvegarde cohérente code/configuration/SQLite : `../pimedia-backups/pre-1.10.2-20261117T202115Z` ;
image précédente : `pimedia-web:pre-1.10.2-20261117t202115z`.
SSH utilise la clé déjà prévue par le projet avec `UseKeychain=yes`, sans modifier la configuration SSH.
Le conteneur et HTTPS sont sains ; version 1.10.2, 216 fichiers applicatifs et ressources publiques vérifiés.
JavaScript/CSS servis avec l’empreinte `a94804d512`. SQLite reste au schéma 19, intègre ; comptes et
données existantes conservés. Aucun compte ou jeton utilisateur utilisé pour ces vérifications.
La suite complète, les autres parcours et la navigation connectée en production n’ont pas été rejoués.
Recharger avec Cmd+Maj+R.

La 1.10.1 ne change ni le schéma ni la configuration. Elle relie le lecteur aux routes existantes de file
Subsonic et ajoute une copie locale par compte. Publiée le 12/11/2026 sur https://music2.foos.fr après
694 tests Python et les sept parcours jsdom ; les deux parcours PC ont été rejoués sur le code final.
Sauvegarde cohérente du code, de la configuration et de SQLite : `../pimedia-backups/pre-1.10.1-20261112T200913Z`.
Image précédente conservée : `pimedia-web:pre-1.10.1-20261112t200913z`. Publication par `deploy/pc/push.sh`,
sans modifier le `.env` ni les volumes. Le conteneur est sain ; les 216 fichiers applicatifs correspondent
aux sources testées. HTTPS, version, scripts versionnés et connexion publique dans jsdom vérifiés ;
les routes de file exigent session et CSRF. SQLite reste au schéma 19, intègre, avec les compteurs inchangés.
Aucun compte ni file de production utilisé pour les tests connectés. Recharger la page avec Cmd+Maj+R.

La 1.10 ajoute la migration web 19 : `upload_history` et `upload_albums`, pour attribuer les nouveaux envois
au compte connecté et afficher l’auteur sur les albums. Aucun nouveau réglage d’environnement.
L’historique est initialement vide : les anciens envois ne peuvent pas être attribués rétroactivement.
Sauvegarder SQLite via son API de backup, archiver code/configuration et conserver l’image précédente.
Publication du 12/11/2026 : sauvegarde ../pimedia-backups/pre-1.10-20261112T180315Z/ et image
`pimedia-web:pre-1.10-20261112t180315z`. Migration répétée sur copie sans réseau, puis schéma 19 et intégrité
vérifiés en production ; 12 comptes et les données existantes conservés. Les tables sont additives :
un retour à l’image précédente peut garder la base actuelle et ses tables inutilisées.
Les sites local et production servent la 1.10, avec 215 fichiers applicatifs identiques à l’instantané testé.
Local : service en HTTP sur 127.0.0.1:8200, démarré avec `docker compose -f compose.yaml up -d --no-build web`
pour conserver le réseau existant ; le réseau externe Traefik `proxy` est absent de cet environnement.
Validation finale : 691 tests Python et six parcours jsdom ; points de départ historiques des tests de migration
figés, attente du DOM À écouter corrigée puis parcours rejoué.

La 1.9.2 ajoute la migration web 18 : marqueurs de conseils non lus et index par destinataire.
Les conseils existants sont initialisés comme non lus ; aucune nouvelle variable ni tâche périodique.
Sauvegarder SQLite et conserver l’image précédente avant publication.
Publication du 10/11/2026 : sauvegarde cohérente dans ../pimedia-backups/pre-1.9.2-20261110T221310Z/, image pimedia-web:pre-1.9.2-20261110t221310z. Schéma 18 et intégrité vérifiés après publication.

La 1.9 ajoute la migration web 17 (listen_later et recommendations), appliquée au démarrage.
Sauvegarde cohérente avant publication : code/configuration archivés, SQLite copié par l'API backup,
image précédente conservée sous une étiquette dédiée. Aucun nouveau réglage d'environnement.
Le 10/11/2026, sauvegarde dans ../pimedia-backups/pre-1.9-20261110T202923Z/ depuis le projet distant,
image pimedia-web:pre-1.9-20261110t202923z ; schéma 17 et intégrité vérifiés après publication.
Les deux tables sont additives ; un retour à l'image précédente peut conserver la base actuelle et ses nouvelles
tables inutilisées. Une restauration de la sauvegarde SQLite doit tenir compte des écritures intervenues depuis.

La 1.8 ajoute la migration web 16 (`artist_discogs_links`), appliquée au démarrage. Sauvegarder la base de façon
cohérente et conserver l’image précédente avant mise à jour. Le `.env` et le montage facultatif des statistiques
restent ceux du serveur ; aucune nouvelle variable et aucun changement de l’édition Pi pour les fiches Discogs.

Lancer tous les tests (unitaires et parcours navigateur simulé) :
```bash
docker compose build tests && docker compose run --rm tests
```
`docker compose run --rm tests` ne reconstruit pas l'image tout seul : sans le `build`, on teste l'ancien code.

## Ce qui n'a pas été vérifié sur le vrai matériel
Voir `docs/ETAT.md` (section « Non vérifié ») : le site contre le vrai Subsonic, `install.sh` sur un Pi neuf, le bouton
Éteindre, AirPlay, mpv sur le Pi.
