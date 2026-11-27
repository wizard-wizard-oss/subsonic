# Actualités : flux RSS des webzines (site web)

## Ce que ça fait
Page **« Actualités »** (`#/news`, lien dans le menu du haut) : les derniers articles des webzines suivis par le site,
du plus récent au plus ancien, 40 par page avec « Afficher plus ». Pour chaque article : titre (lien vers le webzine,
nouvel onglet), webzine, date, début du résumé (280 caractères, sans HTML). **Le site ne montre que des liens** :
l'article se lit chez le webzine ; ni image ni contenu copié.

- **Filtre par webzine** : une pastille par flux (`#/news/<id>`), avec le nombre d'articles gardés et ⚠ si la
  dernière lecture a échoué.
- **Ajouter un flux** : n'importe qui colle l'adresse d'un flux RSS / Atom **ou d'un site** (`noisemag.net`) : le site
  cherche alors le flux annoncé par la page (`<link rel="alternate" type="application/rss+xml">`, celui des articles
  avant celui des commentaires). Le flux est lu tout de suite. **Un flux ajouté sert à tout le monde.** 200 flux au plus.
- **Chacun choisit ce qu'il voit** : case à cocher sur chaque pastille. Par défaut tout est coché ; un flux décoché
  est masqué **pour soi seulement** (dans « Tout » et dans « Dans la presse »), il reste suivi pour les autres et se
  consulte toujours en cliquant sa pastille. Table `news_hidden_feeds` (personne, flux).
- **Retirer un flux** (×) : l'admin Subsonic, ou la personne qui l'a ajouté ; les flux de départ, l'admin seulement.
  Ses articles gardés sont oubliés.
- **Lecture toutes les heures** par le serveur ; **chaque article est gardé** (titre, lien, date, début du résumé) :
  un flux ne contient que ses 10 à 20 derniers articles, la base se remplit avec le temps.
- **Page d'un artiste** : section **« Dans la presse »** sous les albums (8 articles au plus) : les articles gardés dont
  le **titre** contient le nom de l'artiste, en mots entiers, sans accents ni ponctuation (« Fontaines D.C. » ne trouve
  pas « Les Fontainesques », « Bjork » trouve « Björk »). Rien d'affiché si aucun article ne le cite.
- Flux de départ (migration 10, Inrocks changé par la 11) : **Les Inrocks – Musique** (rubrique seulement), Mowno,
  New Noise (vérifiés lisibles le 26/10/2026).
- Adresse d'une **rubrique** collée (`lesinrocks.com/musique/`) : le flux de la rubrique est préféré à celui du site.
- Flux lus avec indulgence : RSS 0.9x / 1.0 / 2.0 et Atom ; préfixes non déclarés (« media: » de WordPress, cas des
  Inrocks) retirés avant relecture ; résumé « Cet article … est apparu en premier sur … » effacé ; seuls les liens
  `http(s)` gardés. Sécurité : mêmes protections que les podcasts (`FeedFetcher` : pas d'adresse locale ou privée, même
  après redirection, 6 Mo au plus, pas d'entités XML).

## Où
`pimedia/webapp/news.py` (lecture des flux, recherche du flux d'un site, service), `storage/news.py`,
`controllers/news.py`, entités `NewsFeed` / `NewsArticle`, migration 10 (`news_feeds`, `news_articles`, `news_hidden_feeds`) ; réutilise
`server/podcasts/feeds.py` (`FeedFetcher`, dates) et `server/podcasts/relevance.py` (`normalize`).
Page : `web-pc/static/js/news.js` (page et section « Dans la presse », appelée par `views.js`), styles dans `views.css`.
Routes : `GET /api/news[?feed=&beforeDate=&beforeId=]`, `GET /api/news/feeds`, `GET /api/news/artist?name=`,
`POST /api/news/feed/add {address}`, `POST /api/news/feed/show {id, shown}`, `POST /api/news/feed/remove {id}`.
**Édition web seulement** : le Pi ne s'en sert pas.

## Tests
`tests/test_webapp_news.py` (faux sites : RSS WordPress, Atom, page qui annonce son flux), `tests/e2e_webapp.js`
(parcours : ajout d'un site, liens, « déjà suivi », flux décoché puis recoché, « Dans la presse », retrait).

## N'existe pas / pas vérifié
- Pas de recherche dans les archives des webzines (API WordPress `wp-json/wp/v2/posts?search=`, recherche en RSS
  `?s=…&feed=rss2`) ni de Google Actualités : seulement ce qui passe dans les flux depuis leur ajout.
- Pas de reconnaissance des artistes de la bibliothèque dans la page Actualités (pastille « parle de … »).
- Noms courts ou communs (« Air », « Justice ») : des articles sans rapport peuvent apparaître sous l'artiste.
- Les articles ne sont jamais effacés (sauf avec leur flux).
- Mowno est derrière Cloudflare : son flux répond aujourd'hui, sa recherche non.
- **Pas vérifié** sur le vrai serveur (lecture toutes les heures dans le conteneur) ; les trois flux de départ ont été
  lus une fois depuis le Mac avec le code du site.

## Sorties de la semaine : le radar

Dans l’édition web, l’onglet `#/news/releases` ouvre le **radar** du compte : les albums et EP dont la première
sortie tombe dans la semaine (lundi → dimanche, date locale du lecteur), pour **tout ce que la personne suit**.
Conception : `docs/superpowers/specs/2026-11-27-radar-sorties-design.md` ; plan : `docs/superpowers/plans/2026-11-27-radar-sorties.md`.

### Ce que ça fait (version 2, 1.24)
- **Sources** d’un compte (table `release_sources`) : styles (nom exact du catalogue MusicBrainz), labels et artistes
  (MBID). Origine : `manual` (ajoutée par la personne) ou `trends` (d’après ses favoris). Une source retirée est
  **masquée**, pas effacée : le calcul suivant ne la remet pas ; l’ajouter à la main la réactive.
- **Tendances**, recalculées à chaque synchronisation, d’après les **favoris seulement** (`getStarred2` : artistes,
  albums, morceaux) :
  - artistes (30 au plus ; MBID de Subsonic, sinon recherche MusicBrainz au nom exact, gardée dans
    `artist_resolutions` ; un nom introuvable ou porté par plusieurs artistes est recherché de nouveau après 30 jours) ;
  - labels des albums favoris (lien album ↔ label gardé dans `album_labels`, « rien trouvé » compris) ;
  - **styles dominants** : les 3 premiers tags du catalogue de chaque artiste, lus par lots de 20 artistes en une
    requête ; un style porté par moins de 3 artistes est écarté ; les 5 premiers sont proposés.
  - **Sans favori** : styles génériques calculés de la même façon sur les albums les plus écoutés du sub
    (`getAlbumList2 type=frequent`, liste commune au serveur) ; la page le dit (`radar_profiles.basis = 'site'`).
- **Page** : pastilles Tout · chaque style · Labels · Mes artistes, avec leur nombre ; chaque carte dit pourquoi elle est
  là ; cartes par date puis titre ; « Ouvrir l’album » quand l’album est déjà dans la bibliothèque (rapprochement
  serveur, gardé 5 min). 48 cartes par page. Pochette Cover Art Archive : miniature 250 px, sinon l’image d’origine
  (archive.org ne fabrique pas tout de suite les miniatures des sorties récentes), sinon pochette vide. Avant cela, la
  pochette connue du serveur : l'image exacte de l'édition qui en a une (ListenBrainz `caa_release_mbid`/`caa_id`), sinon
  celle de Last.fm (`album.getinfo`, artiste et titre exacts), cherchée une fois par sortie pendant la synchronisation
  (300 au plus par passage, colonnes `radar_releases.cover` et `cover_checked_at`, migration 31).
- **« Écouter l’album »** (sortie absente de la bibliothèque) : `#/listen/<artiste>/<titre>` cherche l’album lui-même
  dans YouTube Music (même recherche sans clé que le reste du site, `YouTubeMusicSearch.album` : titre et artiste
  égaux après normalisation, puis ses morceaux lisibles ici), route `GET /api/ext/album?artist=&title=` ; introuvable :
  lien vers la recherche habituelle (`web-pc/static/js/weekly-listen.js`).
- **« Autour de… »** : on choisit un de ses artistes ; Last.fm donne ses proches (une requête) ; on cherche leurs
  sorties parmi celles de ListenBrainz déjà en base (MBID quand Last.fm le donne, sinon nom normalisé).
- **Fenêtre** : 90 jours en arrière, 60 en avant, synchronisés. Les semaines de plus de 14 jours ne sont relues
  qu’une fois par semaine (`radar_sync.past_synced_at`) ; ListenBrainz est lu par tranches de 30 jours.
- **Plus ancien que 90 jours** : la semaine est cherchée à la demande pour les sources du compte (`ReleaseSync.sync_week` :
  une requête par style et par label, une ListenBrainz), puis gardée un jour (`radar_runs`, `week:<compte>:<lundi>`).
- **Plus de 60 jours en avant** : consultation « un style à la fois ».

### Synchronisation de fond
- Fil lancé par `app.run()` (`ReleaseSync.run`) : au démarrage si la dernière synchronisation complète date de plus
  de 24 h, puis chaque nuit à 4 h (heure du conteneur, UTC) ; vérification toutes les 5 min.
- Ordre : sources déjà suivies (styles, labels), puis **ListenBrainz** (`explore/fresh-releases`, deux requêtes pour
  tout le site : 14 jours avant, 60 après, albums et EP, gardés avec leurs artistes crédités dans
  `radar_release_artists`), puis tendances de chaque compte, puis sources nouvelles. Un style = une requête
  MusicBrainz par semaine de la fenêtre ; un label = ses éditions de la fenêtre puis une requête groupée `rgid:` pour
  ne garder que les nouveautés.
- **Pas de cache de 7 jours pour le radar** : ListenBrainz est lu en direct ; ce que le radar garde est dans ses tables.
- Une panne garde les sorties déjà en base, note l’échec (`radar_sync.failed_at`) et sa raison dans le journal ; la
  source est réessayée 10 min plus tard (vérification toutes les 5 min). Une panne pendant les tendances n’en retire aucune. Sorties de plus de 30 jours
  purgées.
- Ajouter une source la synchronise tout de suite ; « ↻ » relance ListenBrainz, les tendances et les sources du
  compte, une fois toutes les 10 min (refus : 429 `weekly.refresh_too_soon`). Une seule file de travail, sans doublon.
- Valeurs (fenêtre, seuils, délais) : `webapp/weekly_releases/limits.py`.

### Où
Paquet `webapp/weekly_releases/` : `radar.py` (page, « Autour de… », sources), `trends.py`, `sync.py`, `entities.py`,
`limits.py`, `assembly.py` (câblage) ; `service.py` (consultation par style). Dépôts : `storage/release_radar.py`,
`storage/weekly_releases.py`. Migrations 29 et 30. Requêtes : `MusicBrainz` (`label_groups`, `release_label`,
`search_labels`, `artists_tags`, `weekly_groups`), `webapp/providers/listenbrainz.py`, `LastFm.similar_artists`.
Page : `web-pc/static/js/weekly-radar.js`, `weekly-sources.js`, `weekly-releases.js` (vue par style, pochettes).
Routes : `GET /api/news/releases/radar?monday=&filter=&offset=`, `GET …/around?name=&mbid=&monday=&offset=`,
`GET …/sources`, `POST …/sources/add {kind, identity, name}`, `POST …/sources/hide {id}`,
`GET …/search?kind=label|artist&q=`, `POST …/refresh` ; et toujours `GET /api/news/releases`, `GET …/genres`,
`POST …/follow`.

### Tests
`tests/test_release_radar_storage.py` (dont migration 29 depuis une base remplie), `test_musicbrainz_radar.py`,
`test_lastfm_similar.py`, `test_listenbrainz.py`, `test_release_trends.py`, `test_release_sync.py`, `test_release_radar_service.py`,
`test_weekly_releases.py` (routes, session, CSRF, 429) ; parcours jsdom `e2e_weekly_radar.js` et
`e2e_weekly_releases.js`.

### N’existe pas / pas vérifié
- Pas de partie communauté (« ce que suivent les autres ») ni de projets parallèles via les relations MusicBrainz.
- « Autour de… » depuis la page d’un artiste : pas encore (seulement depuis le radar).
- ListenBrainz date les éditions : une réédition d’un artiste suivi peut apparaître dans « Mes artistes ».
- Pas d’historique d’écoute par compte (le site ne garde pas les écoutes).
- **Pas vérifié** sur le vrai serveur : durée de la première synchronisation, part des proches Last.fm avec MBID.
