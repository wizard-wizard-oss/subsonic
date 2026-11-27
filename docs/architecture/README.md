# Architecture : trois zones, deux déploiements

Un seul dépôt, deux produits qui tournent sur deux machines différentes, et un socle partagé.

```
src/
├── pimedia/
│   ├── server/   ┐
│   ├── menu/     │ ZONE PI        : station musicale (menu Tk tactile, serveur local, mpv, podcasts…)
│   ├── entities.py, tracks.py,    │ (entities/tracks/paths/cli servent au Pi : le site a ses propres
│   │   paths.py, cli.py           ┘  entités dans webapp/entities.py) + web/, subsonic-web.py, launcher*.py, themes/
│   ├── webapp/   ┐ ZONE WEB       : site multi-utilisateurs (comptes, salon, playlists…)
│   │             ┘                  + web-pc/ , pimedia-web.py
│   ├── shared/                ZONE PARTAGÉE (voulue) : code pur utilisé par les deux (paroles, MusicBrainz…)
│   └── storage/, envfile.py,  SOCLE COMMUN : base SQLite et migrations, lecture du .env, réglages, textes
│       settings.py, i18n.py    (storage/ contient aussi les dépôts propres au Pi : file, historique, podcasts…)
└── i18n/fr.yaml               tous les textes des deux éditions (clés anglaises, section `webapp` pour le site)
```

## Règle d'or du déploiement
- **Sur le Pi : seulement la zone Pi + le partagé.** `deploy/pi/build_archive.py` fabrique l'archive en excluant `webapp/`
  et `web-pc/` (liste `INCLUDED` / `EXCLUDED_DIRS`). Le conteneur d'essai `docker/pi/` installe cette même archive.
- **Sur le serveur web : seulement la zone web + le partagé.** `docker/web/Dockerfile` copie `src/pimedia-web.py`,
  `src/i18n`, `src/pimedia`, `src/web-pc`.
- Les deux se déploient **séparément**, avec leurs propres scripts (voir `docs/DEPLOIEMENT.md`) ; une mise à jour de l'un
  ne touche jamais l'autre. Chaque machine a ses propres données (`~/.local/share/pi-media/` sur le Pi, volume Docker
  `web-data` sur le serveur) et son propre `.env`.

## Ce qui est partagé, vraiment (état au 25/10/2026)
| Quoi | Où | Utilisé par |
|---|---|---|
| Paroles, MusicBrainz, Wikipédia, anecdotes | `pimedia/shared/external.py` | Pi (`server/external.py`), web (`webapp/lyrics.py`) |
| Comparaison des noms musicaux (casse, accents, ligatures, ponctuation) | `pimedia/shared/text.py` | Pi (`server/folders.py`), web (exploration, rangement, pochettes, genres et raccourcis) |
| Base SQLite + migrations (une liste par édition) | `pimedia/storage/database.py` | Pi (`storage/schema.py`), web (`webapp/schema.py`) |
| Lecture du `.env`, réglages typés | `pimedia/envfile.py`, `settings.py` | les deux |
| Textes | `pimedia/i18n.py`, `src/i18n/fr.yaml` | les deux |

## Ce qui est partagé « de fait » : le site importe du code rangé côté Pi
Le site réutilise des modules qui vivent dans `pimedia/server/` (la zone Pi) :
`server/transport.py` (serveur HTTP, routeur, `Reply` ; `BodyReader` : un corps de requête non lu, par exemple refusé
en 401/403, est vidé avant la réponse, sinon la requête suivante sur la même connexion HTTP/1.1 était lue de travers —
corrigé le 27/10/2026, test `KeepAliveTest`), `server/webfiles.py` (fichiers statiques), `server/upstream.py`
(`make_token` Subsonic), `server/constants.py` (`API_VERSION`), `server/podcasts/directories.py` (`JsonHttp`),
`server/extmusic/` (sources YouTube/Jamendo, service), `server/podcasts/feeds.py` et `relevance.py` (lecture protégée
des flux et mots sans accents, pour l'Actualité). **Conséquence : l'image Docker du site embarque tout `src/pimedia`,
donc aussi le code Pi-seulement (`menu/`, le reste de `server/`)**, qui n'y sert à rien. Inversement le Pi n'importe jamais
le site.

**Cible** (pas encore faite, listée dans `docs/ETAT.md`) : déplacer ces modules dans `pimedia/shared/` (client Subsonic —
il en existe deux versions —, serveur HTTP, entités communes, sources de musique d'ailleurs) pour que chaque déploiement
n'embarque que sa zone + le partagé, et que le Dockerfile du site puisse ne plus copier `menu/` ni les contrôleurs du Pi.

## Règles vérifiées par les tests (`tests/test_architecture.py`)
1. `shared/` n'importe **ni** `server`, **ni** `webapp`, **ni** `menu`.
2. Le Pi (`server/`, `menu/`) n'importe **jamais** `webapp`.
3. Rien n'empêche encore `webapp` d'importer `server` (c'est le « partagé de fait » ci-dessus) : à resserrer quand le
   déplacement vers `shared/` sera fait.
4. Les services de `webapp/` n'importent jamais `controllers/` (erreurs de droits : `webapp/errors.py`).
5. Chaque adresse d'API externe n'est appelée que par sa classe (MusicBrainz, Deezer, Spotify, Last.fm, Discogs, iTunes).
6. Pas d'`urllib.request` hors du transport `shared/providers/http.py` dans `shared/` et `webapp/` (exceptions déclarées :
   le client Subsonic et le flux audio des radios).
7. `tests/test_code_size.py` : 40 lignes par fonction et 300 par fichier dans `webapp/` et `shared/` ; les exceptions
   existantes sont figées et ne peuvent que diminuer. `tests/test_webapp_routes.py` fige la table des routes.

## Services externes (remise à plat du 27/11/2026)
- Socle commun dans `shared/providers/` : `http.py` (seul transport, adresses publiques vérifiées), `cache.py` et
  `metadata.py` (`PublicMetadata` : cache par préfixe, cadence par service, une reprise, copie de moins de 30 jours servie
  pendant une panne, jamais pour un rafraîchissement demandé ni pour une entité supprimée).
- Une classe par service : `shared/providers/` pour ceux des deux éditions (MusicBrainz, Wikipédia, paroles, Deezer,
  Spotify), `webapp/providers/` pour ceux du site seul (Discogs, Last.fm, Gravatar).
- YouTube garde ses transports pour l'instant (`JsonHttp`, YouTube Music ; décision du 27/11). iTunes, PodcastIndex et
  Jamendo passent par le transport commun (`json_get` garde leurs erreurs `DirectoryError`).

## Couches dans chaque édition
L'exploration des labels et collaborations est propre au site (`webapp/exploration*`) ; toutes ses requêtes passent par
la classe `shared/providers/musicbrainz`, qui garde aussi la cadence (1,05 seconde entre départs).
Les fonctionnalités récentes sont rangées en paquets (`webapp/tags/`, `notifications/`, `recommendations/`,
`listen_later/`, `weekly_releases/`) ; chaque contrôleur déclare ses routes (`routes()`), `app.py` assemble seulement.

Dépôts (SQL seulement) → services (règles) → contrôleurs (HTTP seulement), assemblés à **un seul endroit**
(`webapp/app.py` pour le site, `server/app.py` pour le Pi). Détail et règles de code : `docs/CONVENTIONS.md`.

## Où chercher quoi

### Accès à la bibliothèque du site

Le package `pimedia/webapp/library/` regroupe le noyau d’accès à la bibliothèque. Le transport Subsonic reste dans
`webapp/subsonic.py`, le SQL dans les dépôts `webapp/storage/`, et les contrôleurs HTTP dans `webapp/controllers/`.

| Module | Responsabilité |
|---|---|
| `catalog.py` — `Library` | Consultation du catalogue par l’API Subsonic : albums, titres, recherche et données propres au site. |
| `folders.py` — `Folders` | Navigation par dossiers via Subsonic et résolution des identifiants de dossiers/ID3. |
| `artists.py` — `ArtistIndexes` | Index des artistes et raccourcis, avec le dépôt et les événements existants. |
| `statistics.py` — `SubsonicStatistics` | Lecture limitée aux compteurs déjà calculés par Subsonic. |
| `files.py` — `LibraryFiles` | Arborescence, recherche des dossiers existants et placement des albums sur le disque. |
| `incoming.py` — `IncomingSorter` | Albums en attente, délai sans modification, rangement puis demande de scan. |
| `naming.py` — `LibraryNaming` | Noms conformes pour les nouveaux artistes/albums et clés de comparaison déléguées à `shared.text.normalize`. |
| `cache.py` — `TtlCache` | Cache mémoire réutilisé par les accès Subsonic et les services consommateurs. |

`Uploads` reçoit et décompresse les fichiers puis appelle `LibraryFiles`, comme `IncomingSorter`. Tous deux utilisent
donc le même placement et la même politique de nommage. Les fonctionnalités telles que les pochettes et les
playlists restent dans leurs services et consomment ces accès. `app.py` assemble les objets, dont la politique de
nommage injectable dans `LibraryFiles`. Les sous-modules s’importent explicitement ; `__init__.py` reste descriptif.
Aucun déplacement de zone Pi/web/shared ni modification de base. AnyASCII 0.3.3 est une dépendance PC utilisée
uniquement par `LibraryNaming` pour les lettres latines ; le partagé et le Pi restent sans cette dépendance.

### Autres fonctionnalités

- Affichage mobile (1.15) : `web-pc/static/js/mobile/bootstrap.js` assemble un adaptateur de navigation selon
  l’écran et la session. `navigation.js` réutilise les artistes, playlists, routes et fil du salon existants,
  avec restauration à la sortie du mode mobile. CSS conditionnelles dans `static/css/mobile/` ; aucune règle
  métier, donnée ou route dupliquée, aucun changement du moteur YouTube ni de l’édition Pi.

- Tags d'albums (1.11) : `album_tags.py` organise l'édition ; entités/limites dans
  `tag_entities.py`, seul `audio_tags.py` écrit les fichiers. `tag_sources.py` appelle le fournisseur choisi.
  `MusicBrainzMetadata` est extrait d'`exploration.py` vers `musicbrainz.py` ; le réexport conserve les imports
  existants et l'assemblage injecte la même instance dans exploration/tags. Discogs conserve son client et ses
  projections typées enrichies. Régulation/cache existants réutilisés ; aucun déplacement Pi/web/shared ni
  copie SQL des tags. `library_scan.py` mutualise les scans envois/corrections. Contrôleur et JS/CSS dédiés.

- Commentaires des recommandations (1.14) : entité RecommendationComment et projections typées dans
  recommendation_entities.py, SQL dans storage/recommendation_comments.py (insertion commune à l'envoi initial),
  règles de participants/validation dans Recommendations, contrôleur existant et un composant JS de fil pour les
  conseils reçus, envoyés et archivés. Migration web 21 ; EventHub/LiveEvents et protection CSRF réutilisés.
  Les discussions restent privées et indépendantes du salon et des commentaires publics d'albums ; aucune
  dépendance vers le Pi ou nouveau catalogue musical.
- Pastille À écouter (1.9.2) : Recommendations publie dans EventHub vers le seul destinataire ; le composant existant utilise LiveEvents, sans nouvelle connexion SSE. Les accusés de lecture passent par le dépôt et le contrôleur existants.
- À écouter et recommandations (1.9) : résolution commune dans webapp/listening_targets.py, règles dans listen_later.py et recommendations.py, entités et dépôts SQL dédiés. Contrôleur commun, assemblage app.py. Zone web uniquement ; recherche et lecture existantes réutilisées.
- Versions YouTube des labels (1.8.1) : `webapp/youtube_versions.py` orchestre les liens puis la recherche ;
  `youtube_matching.py` porte les règles pures de pertinence. `ExternalMusic` réutilise `server/extmusic/YouTubeSource`,
  les budgets et le dépôt de vidéos commun aux favoris. Parseur de liens mutualisé dans `webapp/external_links.py` ;
  adaptation HTTP dans le contrôleur Discogs, assemblage `app.py`. Aucun nouveau service externe ou déplacement de zone.
- Associations Discogs (1.8) : `webapp/artist_discogs.py`, entités `artist_entities.py`, SQL dans
  `storage/artist_links.py` (migration 16). Visuels indépendants dans `artist_portraits.py`, cache public existant
  conservé séparément. Petits contrôleurs Discogs/Facts, assemblage `app.py` ; aucune dépendance nouvelle côté Pi.
- Découverte et discographies (1.7.10) : fournisseurs séparés `webapp/discogs.py` et `webapp/lastfm.py`, objets typés ;
  transport/cache dans `music_metadata.py`, SQL dans `storage/exploration.py`. Services de catalogue, crédits et
  sélection dans `discogs_catalogs.py`, `discogs_exploration.py` et `label_discovery.py` ; contrôleur limité au HTTP.
  Assemblage dans `app.py`, aucun déplacement vers le Pi ou `shared/`.
- Fonctionnalités, ce qui existe / n'existe pas : `docs/features/` (une fiche par fonctionnalité).
- Où en est-on, décisions : `docs/ETAT.md`. Reprise par une autre IA : `docs/REPRISE.md`.
- Déployer : `docs/DEPLOIEMENT.md`.

- Notifications de service (1.17) : entités/limites dans `notification_entities.py`, SQL dans
  `storage/notifications.py`, règles dans `notifications.py`, adaptation HTTP dans `controllers/notifications.py`.
  Assemblage dans `app.py`, migration web 22, diffusion ciblée par EventHub/LiveEvents existants. Composant
  `static/js/notifications.js` et styles propres, navigation mobile existante réutilisée. Aucune dépendance
  externe ni couplage avec les auteurs d’envois ou l’édition Pi.

### Sorties de la semaine · édition web

Actualités charge la vue `weekly-releases.js` pour `#/news/releases`. Help ouvre cette vue depuis le guide presse. Le navigateur envoie le lundi sélectionné et le genre au contrôleur `controllers/weekly_releases.py`. Le service `weekly_releases.py` valide le genre et calcule le dimanche. Le client `musicbrainz.py` interroge MusicBrainz, réutilise le cache public et convertit les réponses en entités de `weekly_release_entities.py`. Le service conserve les sorties datées dans la semaine. La recherche d’une semaine est rafraîchie après une heure.

Pour suivre ou quitter un style, le contrôleur transmet l’utilisateur authentifié au même service. Seul `storage/weekly_releases.py` lit et écrit les abonnements dans `release_subscriptions` (migration 23). La vue interroge séparément le contrôleur d’exploration existant pour identifier les albums accessibles sur Subsonic. Les dépendances sont assemblées dans `app.py`.
