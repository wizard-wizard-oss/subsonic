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

## Couches dans chaque édition
L'exploration des labels et collaborations (07/11/2026) est propre au site (`webapp/exploration*`, dépôt et contrôleur).
Elle réutilise `shared/external.JsonFetcher` ; ses appels MusicBrainz, comme ceux des anecdotes des deux éditions,
partagent désormais un régulateur par processus (1,05 seconde entre départs). Aucun module n'a changé de zone.

Dépôts (SQL seulement) → services (règles) → contrôleurs (HTTP seulement), assemblés à **un seul endroit**
(`webapp/app.py` pour le site, `server/app.py` pour le Pi). Détail et règles de code : `docs/CONVENTIONS.md`.

## Où chercher quoi
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
