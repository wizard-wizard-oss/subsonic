# État du projet (à lire en premier dans une nouvelle discussion)

Mis à jour le 27/10/2026. Lire aussi `docs/CONVENTIONS.md` (règles de code) et `README.md` (organisation).
Reprise avec une autre IA : `docs/REPRISE.md` (message à coller, pièges à connaître).
**Ce que fait chaque fonctionnalité, ce qui existe et ce qui manque : `docs/features/`** (site web et Pi) ; **qui est partagé et ce que chaque déploiement embarque : `docs/architecture/`**. À tenir à jour avec le code.

**Pour reprendre** : le projet est dans `sub2/sources/` (le `.env`, caché par le Finder, est à côté de
`compose.yaml`). Tests : `docker compose run --rm tests` (tout, y compris jsdom). Site de test :
`docker compose up -d web` → https://pimedia.localhost (Traefik local, Subsonic = https://music.foos.fr, clé YouTube
réglée, Jamendo vide). Démo : `docker compose --profile demo up -d demo` → https://demo.pimedia.localhost.
Pas de dépôt git pour l'instant. **Déployer** (site et Pi) : `docs/DEPLOIEMENT.md` (`bash deploy/pc/push.sh`, `bash deploy/pi/push.sh`).
**En production depuis le 27/10/2026 : https://music2.foos.fr** (music.foos.fr reste le Subsonic d'origine). Serveur :
compte `subsonic` (sans sudo ; clé SSH du Mac sans phrase de passe `~/.ssh/pimedia_ed25519` depuis le 27/10/2026), code dans
`/home/subsonic/pimedia`, conteneur `pimedia-web-1` sur le réseau `subsonic_default` (compose de Subsonic à la racine du
home, conteneur `subsonic`), `SUBSONIC_URL=http://subsonic:4040`, vhost `/etc/apache2/sites-available/music2.foos.fr.conf`
(l'ancien vhost Navidrome `music2.foos.fr-le-ssl.conf` est désactivé, Navidrome arrêté). Mise à jour :
`bash deploy/pc/push.sh subsonic@music.foos.fr`.
**Prochaine étape conseillée** : la suite du point 3 (« Radio de ce titre », marque-pages, radios Internet), puis la mise en route de l'envoi de fichiers sur le serveur (groupe, `.env`, voir
`docs/DEPLOIEMENT.md`). Faits le 25/10/2026 : page Mix, radio et artistes similaires, file d'attente, playlists (dont
communautaires, glisser-déposer), scrobble et « Écouté en ce moment », envoi de fichiers dans Incoming.
**Incoming débloqué le 27/10/2026** : 551 dossiers d'artistes appartenaient à `root`, le rattrapage échouait sur le
premier (« Permission denied ») et abandonnait tout le passage. Rendus au site (`sudo find <MUSIC_DIR> -mindepth 1
-maxdepth 1 -type d ! -user 1001 -exec chown 1001:100 {} +`) ; ~85 albums rangés à 13h37, scan vérifié. Reste du code
à corriger : un album bloqué ne devrait pas arrêter les autres (Tâche 1 du plan ci-dessous).
**À venir : page « Rangement »** (administrateurs) : ce qui a été rangé et où, ce qui reste dans Incoming et pourquoi,
groupes en double à réunir (orthographe proche ou MusicBrainz, ex. `Osees` / `Thee Oh Sees` / `Thee Oh Sees _ Osees`).
Conception validée : `docs/superpowers/specs/2026-10-27-page-rangement-design.md` ; plan de construction prêt, à lancer
tel quel : `docs/superpowers/plans/2026-10-27-page-rangement.md`.
**Veille de l'ampli (Pi), corrigé le 25/10/2026, À VÉRIFIER SUR LE PI** : mpv (lecture haute fidélité) gardait son flux
ouvert vers le DAC en pause (« corked » mais ouvert) → l'ampli croyait qu'on écoutait. Maintenant `HifiPlayer.release_if_idle`
arrête mpv après 30 s de pause ou de file vide et le relance à la reprise (même seconde, même volume, titre suivant
re-préchargé). Mesure sur le Pi : `python3 diagnostic-ampli.py` (voir `docs/features/pi/veille-ampli-meteo.md`).
**Attention** : `docker compose run --rm tests` ne reconstruit pas l'image (le code y est copié) : lancer
`docker compose build tests` avant, sinon on teste l'ancien code. Idem `docker compose up -d --build web`.
Chemins de code ci-dessous : relatifs à `src/`.

## Contexte
- Raspberry Pi 4, écran tactile 7" 800×480, ampli Advance Paris A10 Classic en USB (son DAC).
- **Serveur de musique : Subsonic d'origine** (pas Navidrome). Tout passe par l'API Subsonic standard (1.16.1).
- Last.fm :
  - **global** = réglage du serveur Subsonic : alimente `getSimilarSongs2`, `getTopSongs`, `getArtistInfo2`
    (radios, artistes proches, titres populaires) ;
  - **par personne** = chacun relie son compte dans Subsonic, « Paramètres → Personnel » ; le site doit
    seulement envoyer `scrobble`.
- YouTube : **pas de clé par personne** (la clé ne change ni les résultats ni la pub : seulement le quota).
  Lecture YouTube : lecteur officiel ou fenêtre youtube.com. Tout les moyens sont bon pour réduire le quota **Recherche** : un moyen non officiel, sans clé ni quota (ex. ytmusicapi), est autorisé (décision du 27/10/2026).
- L'utilisateur veut : peu de questions, avancer seul, honnêteté sur ce qui n'est pas fait ou pas vérifié.

## Deux éditions, séparées (aucun `if serveur`)
1. **Pi** (un utilisateur) : `subsonic-web.py`, `pimedia/server/`, `pimedia/menu/` (menu Tk), `web/`.
   Déploiement : `python3 deploy/pi/build_archive.py` → `dist/` (install.sh pour un Pi neuf, deploy.sh pour les
   mises à jour, migration.sh). L'archive Pi n'embarque pas l'édition PC.
2. **PC** (plusieurs utilisateurs, souris/clavier) : `pimedia-web.py`, `pimedia/webapp/`, `web-pc/`.
   Données : `~/.local/share/pimedia-web/` (`.env` avec SUBSONIC_URL, `webapp.db`). Service, Apache et nginx : `deploy/pc/`.
   **Docker** (`compose.yaml`, images dans `docker/`) : `docker compose up -d web` (site sur 127.0.0.1:8200,
   données dans le volume `web-data`), `docker compose run --rm tests` (tous les tests),
   `docker compose --profile demo up demo` (bibliothèque inventée, port 8300).
   **Édition Pi en conteneur, pour l'essayer sur le Mac** (26/10/2026) : `docker compose --profile pi up -d --build pi`
   (vrai Subsonic : `SUBSONIC_URL`, `PI_SUBSONIC_USER`/`PI_SUBSONIC_PASS` du `.env`, port 8399, `https://pi.pimedia.localhost`)
   ou `--profile pi-demo up -d --build pi-demo` (faux Subsonic, port 8499). Image `docker/pi/` : l'archive de
   `build_archive.py` installée par `deploy.sh` au démarrage (mode `PI_MEDIA_SERVICE=direct`, sans systemd), vrai mpv
   avec sortie nulle ; `bash docker/pi/push.sh` répète une mise à jour. Page web seulement : ni menu Tk, ni écran,
   ni son, ni Bluetooth, ni AirPlay, ni bouton Éteindre. Détails : `docs/DEPLOIEMENT.md`.
   Réglages par machine dans `.env` (modèle `.env.example`). Test local : Traefik (`compose.traefik.yaml`,
   `https://pimedia.localhost`, vérifié : page, connexion, salon en temps réel). Prod : Apache → 127.0.0.1:port
   (`deploy/pc/apache-exemple.conf`, non vérifié).

## Édition PC : fait et testé
- Connexion avec son compte Subsonic (jeton seulement), sessions, CSRF, limitation des essais.
- Barre des artistes à gauche : fixe / au survol / masquée, largeur, filtre, index, artiste en cours.
- Accueil (derniers albums, mieux notés du site, albums commentés), artiste, album, recherche, favoris.
- Étoiles 1–5 **lues et écrites dans Subsonic** (rien en base locale, migration 3) : comme l'exige Subsonic d'origine,
  la note va sur le **dossier** de l'album (`parent` de ses titres ; album en plusieurs disques : dossier parent),
  `userRating` / `averageRating` (moyenne de tous les comptes) lus par `getMusicDirectory`. Mieux notés :
  `getAlbumList type=highest`. Cœur (`star`/`unstar`).
- Écoutes « Écouté N fois » (`playCount` des albums ID3), accueil « Les plus écoutés » (`frequent`).
- Page **Albums** (`/api/albums`, `/api/genres`) : Nouveaux (en premier, voulu), Plus écoutés, Mieux notés, Écoutés
  récemment, Au hasard, Favoris, Par décennie, Par genre (pastilles avec nombre d'albums), De A à Z ; 40 par page,
  « Afficher plus ». Présentation provisoire (pastilles) : à refaire plus tard en s'inspirant de Spotify/Deezer.
- **Droits Subsonic** (25/10/2026) : lus par `getUser` à la connexion puis à chaque page (`/api/me`, 0,1 s) ; un
  changement fait dans Subsonic s'applique sans se reconnecter, et si Subsonic ne répond pas on garde les derniers
  connus (colonne `users.roles`, migration 6). Appliqués côté serveur (`Guard.reader/writer(..., right=)`, erreur
  `auth.missing_right`) et côté page (`App.can`). `stream` : écouter ; `download` : **télécharger** un album (zip fait
  par Subsonic du dossier de l'album, `/api/download?album=`, bouton sur la page album) ou un titre
  (`/api/download?song=`, icône au survol de chaque ligne des listes de titres) ; `playlist` : créer/modifier/supprimer des playlists ;
  `comment` : étoiles et commentaires d'album (le salon reste libre) ; `admin` : modérer le salon. Réglages : liste
  « Votre compte Subsonic permet de… ». Réservés aux fonctions à venir : `coverArt` (pochettes et **tags ID3**),
  `upload` (envoi de fichiers), `share` (liens publics `createShare`), `settings` (lien Last.fm). Sans objet sur le
  site : `podcast`, `jukebox`, `videoConversion`. Vérifié sur music.foos.fr : droits lus, zip d'album reçu
  (« Made In Chicago.zip »). Pas vérifié : un compte non administrateur réel, un gros album complet derrière Traefik.
- Le chat (salon, commentaires) reste dans la base du site (`webapp.db`), volontairement séparé du chat Subsonic.
- Salon global temps réel (SSE) : réponses, @mentions + notification, réactions, modification, suppression
  (auteur ou admin Subsonic), partage d'album, recherche, mentions, non-lus, « écrit… », en ligne, anti-spam.
- Commentaires sous chaque album. Lecteur (file, raccourcis clavier), réglages par utilisateur, icônes SVG.
- Tests : `python3 -m unittest discover -s tests -t .` (458 OK le 27/10/2026 dans Docker, PyYAML requis : `requirements.txt`) ;
  tous les parcours jsdom : `python3 -m tests.run_e2e [chemin/jsdom]` (5 parcours OK, dont 52 contrôles PC).
  Le plus simple : `docker compose run --rm tests` (tout, avec Node et jsdom). `e2e_hifi` et `e2e_queue` (Pi)
  échouaient souvent sur machine chargée (« queue is not defined ») : ils attendaient 2,5 s fixes que la page soit
  chargée ; ils attendent maintenant qu'elle soit prête (15 s au plus).
- Captures : `python3 -m tests.demo_webapp` (bibliothèque inventée) + Playwright/Chromium.

## Édition PC : routes serveur (25/10/2026) — certaines ont maintenant leur interface (voir `docs/features/`)
Routes testées (unitaires + HTTP, `tests/test_webapp_music.py`, faux Subsonic complet `FakeSubsonicFull`) :
- Mix : `GET /api/mix?kind=random|favorites|discover|newest[&genre=]`, `GET /api/radio/song?id=`,
  `GET /api/radio/artist?id=&name=` (4 niveaux d'artistes proches), `GET /api/mix/genres` (styles regroupés),
  `POST /api/mix/build` (styles, décennies, artiste de départ, favoris, chronologique, nom proposé).
  Sans Last.fm : radio d'un titre → même style ; radio d'artiste → erreur `mix.no_lastfm`.
- Playlists : `GET /api/playlists`, `GET /api/playlist?id=`, `POST /api/playlist/create|add|remove|rename|delete|community`
  (`create` accepte `community`, `add` renvoie `{added}`). Communautaires : tables `community_playlists` et
  `playlist_additions` (migration 7).
- Pochette d'un album : `GET /api/cover/status`, `GET /api/cover/search`, `POST /api/cover/save` (droit `upload`, `LASTFM_API_KEY`, voir `features/pochettes.md`).
- Envoi de fichiers : `GET /api/upload/status`, `POST /api/upload?name=` (corps brut), `POST /api/upload/finish` (droit `upload`).
- Écoute : `POST /api/scrobble {id, submission}`, `GET /api/now-playing`, `GET /api/bookmarks`,
  `POST /api/bookmark/save|delete`, `GET /api/play-queue`, `POST /api/play-queue/save`.
- Photos : `GET /api/avatar?user=` (site, sinon Subsonic, sinon 404 → initiale), `GET /api/avatars`,
  `POST /api/avatar/upload` (300 Ko, PNG/JPEG/WebP vérifiés aux octets), `POST /api/avatar/delete`.
- Radios Internet : `GET /api/radios`, `GET /api/radios/stream?id=` (seules les adresses de la liste Subsonic).
- Titres populaires d'un artiste : `GET /api/artist/top?name=` (getTopSongs, Last.fm), gardé une heure ; section
  « Titres populaires » sur la page artiste (5, puis 10), chargée après la page. **Seule partie avec interface.**
- **Paroles** (avec interface) : `GET /api/lyrics?artist=&title=&album=&duration=`, directement LRCLIB (synchronisées)
  puis lyrics.ovh, **sans Subsonic** (décision : l'externe non essentiel ne passe pas par Subsonic), gardées un jour.
  Bouton micro du lecteur ou touche L : panneau à droite à la place du salon, ligne chantée en surbrillance au
  milieu ; paroles simples : défilement estimé. Vérifié contre le vrai LRCLIB depuis le conteneur.
- **Musique d'ailleurs** (avec interface) : Jamendo et YouTube, UNE clé par source dans le `.env` du site
  (`EXT_JAMENDO_ID`, `EXT_YOUTUBE_KEY`, `EXT_YOUTUBE_REGION`, passés par `compose.yaml`), jamais renvoyées à la page.
  Service du Pi réutilisé (`server/extmusic/`) : chaînes « Topic » d'abord, vidéos lisibles vérifiées, versions
  originales seulement. Routes : `GET /api/ext/status`, `GET /api/ext/search?src=&q=`, `POST /api/ext/alternative`,
  `POST /api/ext/unplayable`, `POST /api/ext/played`. Quota YouTube partagé (~100 recherches/jour) : YouTube
  proposé **seulement si Subsonic n'a ni titre ni album** pour la recherche, et seulement sur clic ; recherches
  gardées **90 jours en base** (migration 4, `ext_searches`), partagées entre tous ; 120 par personne et par heure.
  **Recherche par YouTube Music** (`ytmusicapi`, 27/10/2026) : sans quota ; repli sur l'API officielle limité à 20
  recherches par heure pour tout le site. Voir `docs/features/musique-ailleurs.md`.
- **Importer une playlist** (27/10/2026, demandé) : page `#/import` + guide `#/import/guide` ; lien Deezer, CSV
  (Spotify par Exportify, TuneMyMusic…), XML Apple Music, M3U, texte ; rapprochement par le texte avec `search3`
  (pas d'ISRC), introuvables cherchés sur YouTube Music, aperçu avec un choix par titre, playlist mixte créée dans
  l'ordre. **Pas essayé contre le vrai Subsonic.** Voir `docs/features/import-playlists.md`.
- **1.3 (28/10/2026)** : choix de la playlist dans un export de toute la bibliothèque Apple ; vidéos YouTube refusées
  (code 150, labels) : une seule autre version par titre, plus de cascade d'échecs. Voir les deux fiches.
  Vidéos (`youtube_videos`) : refus gardé avec le code d'erreur YouTube, réessayée après 90 jours ; lectures
  réussies comptées → en tête des résultats avec « déjà lue ici », et une lecture efface un refus. Page : section « Ailleurs » de la recherche ;
  moteur de lecture `engine.js` (audio ou lecteur officiel YouTube dans une petite fenêtre vidéo visible) ; vidéo
  refusée → autre version sûre, sinon « Ouvrir sur YouTube » et titre suivant. Politique de sécurité de la page :
  seuls youtube.com (script, cadre), i.ytimg.com et *.jamendo.com sont ajoutés. **Pas vérifié avec de vraies clés.**
- Erreurs précises renvoyées comme clés de texte (`mix.*`, `playlist.*`, `avatar.*`).
- Défauts trouvés par ces tests et corrigés : réponse Subsonic vide `{}` (sans Last.fm) transformée en titre
  fantôme « ? » ; styles sans titre proposés ; « jamais deux titres du même artiste à la suite » pas garanti.

## Reste à faire (dans l'ordre)
1. ~~Brancher les modules~~ et 2. ~~faux Subsonic complet + tests~~ : faits le 25/10/2026 (voir plus haut).
~~Barre des artistes vide~~ : **réglé le 25/10/2026**. Cause : `getArtists` met **34 s** à répondre sur
music.foos.fr (5 424 artistes ; calcul côté Subsonic, premier octet à 34 s, `getIndexes` 19 s, les autres appels
< 2 s) et le client coupait à 20 s → `subsonic.unreachable`. Correctif : délai par appel (`SLOW_TIMEOUT` = 180 s,
`pimedia/webapp/subsonic.py`) et **une liste pour tout le site** (`pimedia/webapp/artist_index.py`, table
`artist_indexes`, migration 5) : calculée une fois, gardée en base (survit aux redémarrages), servie à tous tout de
suite. Au démarrage du site puis toutes les 10 min, comparaison avec Subsonic par `getIndexes ifModifiedSince`
(0,1 s si rien n'a changé) ; après un scan, recalcul (34 s, en arrière-plan) et, si la liste a changé, événement
temps réel `artists` : les barres ouvertes se rechargent sans attente. Préchauffage avec un compte connu
(administrateur d'abord). Une liste par ensemble de dossiers de musique visibles (`getMusicFolders`) : un compte
limité par Subsonic à certains dossiers a la sienne. **Vérifié sur music.foos.fr** : liste prête 34 s après le
démarrage, pas recalculée au redémarrage suivant. Barre : « Chargement des artistes… » (seulement si rien en base),
« Réessayer » en cas d'échec, affichage paresseux par lettre (`IntersectionObserver`, tout d'un coup sans lui).
L'API Subsonic standard n'a pas de pagination pour `getArtists` : impossible de la charger par morceaux chez Subsonic.
(Depuis le 26/10/2026 la barre suit les dossiers : `getIndexes`, 19 s, même principe de liste gardée en base.)
3. Interface. **Fait le 25/10/2026** : page **Mix** (`#/mix`, `web-pc/static/js/mix.js`, lien dans le menu) avec
   4 mix rapides (au hasard, favoris, découverte, nouveautés) et le **créateur de mix du Pi** (artiste de départ
   cherché ou venu de la page artiste `#/mix/<id>`, styles avec nombre de titres, époques, 30/60/100 titres, favoris
   d'abord, proches de proches, chronologique ; « Lancer le mix », « Enregistrer en playlist » si droit `playlist`) ;
   page artiste : **« Radio de l'artiste »**, « Créer un mix à partir de cet artiste », section **« Artistes
   similaires »** (`GET /api/artist/similar?id=`, getArtistInfo2, gardé une heure, vide sans Last.fm). Vérifié sur
   music.foos.fr côté serveur (15 similaires de Depeche Mode en 0,7 s, 1 124 styles, mix de 30 titres en 5,6 s,
   radio de 100 titres en 6,1 s) ; interface testée dans jsdom seulement.
   **Playlists, fait le 25/10/2026** : onglets **Artistes | Playlists** dans la barre de gauche (`web-pc/static/js/playlists.js`,
   réglage `sidebar_tab`) ; sections Mes playlists / Communautaires / Partagées ; page `#/playlist/<id>` ; création
   (« + », nom + case Communautaire) ; **glisser-déposer** (`dnd.js`) d'un titre ou d'un album sur une playlist
   (ou sur « + » pour en créer une), l'onglet Playlists s'ouvre tout seul pendant le glissé ; bouton « Ajouter à une
   playlist » au survol de chaque titre. **Communautaire** : playlist Subsonic de son créateur, rendue publique ; quand
   un autre y ajoute, le site écrit avec le jeton du créateur (gardé à sa dernière connexion) et note qui a ajouté
   chaque titre (`community_playlists`, `playlist_additions`, migration 7) — Subsonic ne garde pas l'auteur. Un titre
   n'y est ajouté qu'une fois ; chacun ne retire que ce qu'il a ajouté, le créateur retire tout. Si le créateur
   change son mot de passe, les ajouts des autres sont refusés (`playlist.owner_unavailable`) jusqu'à sa reconnexion.
   Testé avec le faux Subsonic et jsdom, **pas vérifié contre le vrai Subsonic** (paramètre `public` de `updatePlaylist`).
   **Écoute, fait le 25/10/2026** : le lecteur signale chaque titre de Subsonic (`/api/scrobble`, « en cours » au
   démarrage, « écoutée » après la moitié du titre ou 4 min réellement écoutées, un saut en avant ne compte pas) ;
   section **Écouté en ce moment** en haut du panneau de droite, au-dessus du salon, comme dans Subsonic
   (`web-pc/static/js/listening.js`, `getNowPlaying`, relu toutes les 30 s) : chacun, soi-même en premier, avec la pochette.
   **Page « Mon compte », faite le 27/10/2026** (demandée) : photo de profil (image envoyée, **copie de Gravatar**, ou
   celle de Subsonic par `getAvatar`), affichage, droits, bouton vers les réglages Subsonic (Last.fm, mot de passe :
   `SUBSONIC_PUBLIC_URL`, **à ajouter au `.env` de prod**), import d'un lien YouTube/SoundCloud ; photos en haut, dans le
   salon et « Écouté en ce moment ». Réglages rapides (roue dentée) gardés. Voir `docs/features/comptes-et-droits.md`.
   Connexion aux comptes YouTube/SoundCloud : **pas faite** (OAuth, voir la fiche).
   **Reste** : page radios Internet, Marque-pages (reprendre à la position) ; bouton « Radio de ce titre ».
3 bis. **YouTube et Jamendo** : faits le 25/10/2026 (voir « Musique d'ailleurs » plus haut). **Favoris d'ailleurs et
   SoundCloud, faits le 26/10/2026** (demandés) : favoris par personne (`ext_favorites`, migration 12), ajout par cœur
   ou par **lien collé** (vidéo ou playlist YouTube publique/non répertoriée, titre SoundCloud par oEmbed sans clé),
   lecteur officiel SoundCloud ; **titres d'ailleurs dans les playlists Subsonic** (`playlist_ext_tracks`, migration 13) :
   décision de l'utilisateur, le site montre les deux mêlés, les applications Subsonic seulement les titres Subsonic
   (pas de faux fichiers dans la bibliothèque). Fiches : `docs/features/musique-ailleurs.md`, `playlists.md`.
   **Pas vérifié avec les vrais YouTube et SoundCloud.** Pas fait : « J'aime » privés (il faudrait relier le compte
   Google), playlists SoundCloud, fenêtre youtube.com avec compte à rebours comme sur le Pi (`web/static/js/ytpopup.js`).
3 bis bis. **Page « Nouveautés »** (27/10/2026, demandée) : `#/whatsnew`, explique aux utilisateurs, sur un ton léger,
   tout ce que le site fait en plus de Subsonic (fiche `docs/features/nouveautes.md`). À tenir à jour avec les fonctionnalités.
3 bis ter. **Page « Versions »** (27/10/2026, demandée) : `#/versions`, historique daté version par version, numéro
   `v1.1` et pastille à côté du titre du site ; à compléter à chaque version mineure ou majeure dans
   `src/i18n/versions.yaml` avant de déployer (fiche `docs/features/versions.md`). **Version 1.1 pas encore déployée**
   (avec le rangement qui ignore espaces et ponctuation : « A.A.Williams » = « A.A. Williams »).
3 ter. **Retours de test du 25/10/2026 (interface, à faire)** — s'inspirer de Spotify / Deezer :
   - salon : pouvoir le fermer ou régler sa largeur pour laisser plus de place aux albums ;
   - ~~lecteur agrandi au survol~~ et ~~file d'attente en bas~~ : **faits le 25/10/2026** (`web-pc/static/js/queue.js`).
     Survol du lecteur : bande album · année · genre · format · position ; la souris reste 0,7 s : file sur toute
     la largeur (comme Subsonic : titre, album, artiste, durée, genre, année, format, « N titres • durée »),
     « Vider la suite », « Annuler » (20 niveaux), glisser-déposer (poignée ⋮⋮) ou Alt+↑/↓, Entrée, Suppr.
     Fermeture : clic ailleurs, souris repartie au-dessus (0,6 s), Échap, bouton ☰. Testé dans jsdom seulement ;
   - album : bouton « Lire juste après » en plus de « Lire » et « Ajouter à la file » ;
   - pochettes : petit bouton lecture au survol, en haut à gauche, qui lance l'album sans l'ouvrir ; clic sur
     le titre = ouvrir l'album ;
   - thème sombre au choix dans les réglages (aujourd'hui il suit le système) ;
   - page Albums : présentation provisoire (pastilles) à revoir ;
   - ~~envoi de fichiers~~ : **fait le 25/10/2026**. L'API Subsonic n'a pas d'envoi : page `#/upload` (lien « Envoyer »,
     droit Subsonic `upload`), fichiers audio envoyés un par un (corps brut, 300 Mo au plus, mp3/flac/m4a/aac/ogg/opus/wav/aiff)
     puis `startScan`. **Revu le 26/10/2026** (décisions de l'utilisateur) : le site tourne sous l'utilisateur de Subsonic
     (`music`, `APP_UID`/`APP_GID`), `MUSIC_DIR` = racine de la musique (montée en écriture ; `datas/Music` en local) ; un
     zip est décompressé et chaque album `Artiste/Album/titre` (majuscule au début, disques `CD1`…) part **aussitôt** chez
     son artiste (retrouvé sans majuscules ni accents : un seul dossier par artiste), dossiers en trop ignorés ; le reste
     attend dans `Incoming` ; jamais d'écrasement ; rattrapage d'Incoming corrigé à la main (`INCOMING_WAIT_HOURS`) ;
     barres de progression par fichier et pour le lot ; proxy : bloc `/api/upload` (avant, 1 Mo bloquait tout). Fiche
     complète avec exemples : `docs/features/envoi-fichiers.md`. **Pas vérifié sur le vrai serveur.**
   - **Barre des artistes, page artiste et page album par dossiers : fait le 26/10/2026** (demandé par l'utilisateur) :
     `getIndexes` + `getMusicDirectory` au lieu de `getArtists`/`getArtist`/`getAlbum` ; identifiants de dossier préfixés
     `f` ; liens ID3 ramenés au dossier ; commentaires, notes, cœur d'album, téléchargement restent sur l'ID3 ; radio et
     mix par l'ID3 du premier titre ; `Incoming` caché ; plus de nombre d'albums dans la barre (réglage retiré) ;
     migration 8 (liste recalculée). Détail : `docs/features/bibliotheque.md`. **Pas vérifié sur le vrai Subsonic.**
   - Raccourci **Compilations** en haut de la barre des artistes (26/10/2026) : dossiers réglés par `SHORTCUT_FOLDERS`
     dans le `.env` (`docs/features/barre-gauche.md`).
3 quater. **Corriger les tags ID3** (demandé le 25/10/2026, à préciser) : l'API Subsonic standard ne sait pas
   écrire les tags. Il faudrait que le site accède aux fichiers (déjà possible depuis le 26/10/2026 : `MUSIC_DIR` monté en écriture sur `/music`, sous l'utilisateur `music` ; dossier de musique de Subsonic monté dans le
   conteneur, en écriture), les modifie (bibliothèque Python `mutagen`), puis demande `startScan`. À décider : qui a
   le droit (proposé : le droit Subsonic `coverArt`, « modifier pochettes et tags », déjà lu par le site), quoi
   corriger (titre, artiste, album, année, genre, n°, pochette ?),
   album entier ou titre par titre, et suggestions MusicBrainz (`shared/external.py` le sait déjà) ou saisie à la main.
   **Actualité** (fait le 26/10/2026, voir `docs/features/actualite.md`) : page `#/news`, flux de webzines ajoutés par
   chacun et partagés, lus toutes les heures, articles gardés ; chacun décoche les flux qu'il ne veut pas voir (pour
   lui seul) ; « Dans la presse » sur la page artiste. Plus tard, éventuellement : recherche dans les archives des
   webzines (API WordPress) et Google Actualités.
4. Sauvegarde distante (demandée) : Forgejo à la maison + copie automatique vers Codeberg pour le code ;
   restic ou borg chiffré, chaque nuit, pour les données (`.env`, bases) — jamais sur Codeberg.
5. Plus tard : thème lu par la page web (variables CSS `--theme-*`), templates.
6. **À la fin (décidé le 27/10/2026) : fermer Subsonic au public.** Seul le site parle à Subsonic, en interne
   (`SUBSONIC_URL=http://subsonic:4040`). D'ici là, Subsonic reste public, deux adresses : `SUBSONIC_URL` interne et
   `SUBSONIC_PUBLIC_URL=https://music.foos.fr` (bouton « Ouvrir mes réglages Subsonic »). Avant de fermer :
   - **relais de l'API Subsonic par le site** (`/rest/...` relayé vers Subsonic) pour que les applis Subsonic du
     téléphone continuent de marcher, et pour une future API téléphone propre au site ;
   - **mot de passe dans le site** (`changePassword` de l'API, puis jeton du site mis à jour) ;
   - **Last.fm par personne** : l'API Subsonic ne permet pas de relier un compte Last.fm → soit l'admin le fait dans
     Subsonic, soit le site envoie lui-même les écoutes à Last.fm (clé du site, chacun autorise une fois) ;
   - `SUBSONIC_PUBLIC_URL` vide → aujourd'hui elle retombe sur `SUBSONIC_URL` (lien cassé si interne) : changer pour
     « vide = pas de bouton » (`config.py`, `controllers/profile.py`).

## Décisions (25/10/2026)
- Le Pi est à part (local, à la maison) : on n'y touche pas, pas de socle commun à construire pour l'instant.
- Le site PC lit tout depuis Subsonic (notes, écoutes, favoris, playlists, marque-pages) ; seuls le chat, les
  comptes du site et les réglages sont dans `webapp.db`. Mixes calculés par le serveur du site (mêmes pour tous).
- Interface : s'inspirer de Spotify/Deezer plutôt que de l'interface Subsonic.
- **Code commun** : `src/pimedia/shared/` contient les classes pures utilisées par les deux éditions (pour l'instant
  `external.py` : paroles, MusicBrainz, Wikipédia, anecdotes). Règle vérifiée par `tests/test_architecture.py` :
  `shared` n'importe ni le Pi ni le site, le Pi n'importe jamais le site. Pas de dépôt séparé (inutile tant que
  tout est dans le même dépôt). À déplacer ensuite dans `shared` : client Subsonic (deux versions aujourd'hui),
  serveur HTTP (`server/transport.py`, `webfiles.py`, encore importés par le site depuis le Pi), entités communes.
- Proposé, pas tranché : ranger l'édition PC en couches hexagonales (domain / application / infrastructure /
  interfaces).

## Non vérifié sur le vrai matériel / vrai serveur
Barre des artistes paresseuse avec 5 424 artistes dans un vrai navigateur (testée seulement dans jsdom).
**À tester sur music.foos.fr** (Subsonic 1.16.1 confirmé par `ping`) : notes posées sur le dossier de l'album et
moyenne relue ; album en plusieurs disques ; « Mieux notés » (`highest`) relié aux albums ID3 par le premier titre du
dossier ; écoutes ; listes par décennie et par genre.
Édition PC contre le vrai Subsonic ; nouveau menu Tk sur le Pi ; install.sh sur un Pi neuf ; bouton Éteindre ;
AirPlay (sortie PulseAudio) ; mpv sur le Pi.
