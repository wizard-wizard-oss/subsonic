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

### Ce que ça fait
- **Sources** d’un compte (table `release_sources`) : styles (nom exact du catalogue MusicBrainz), labels et artistes
  (MBID), proches (« découvertes », MBID). Origine : `manual` (ajoutée par la personne), `trends` (d’après ses
  favoris), `discovery` (proche Last.fm, avec « proche de X »). Une source retirée est **masquée**, pas effacée :
  le calcul suivant ne la remet pas ; l’ajouter à la main la réactive.
- **Tendances**, recalculées à chaque synchronisation, à partir de signaux **propres au compte** seulement :
  favoris Subsonic (`getStarred2` : artistes, albums, morceaux) et marque-pages « À écouter ». La liste « plus
  écoutés » de Subsonic est commune au serveur : elle n’est pas utilisée. Artistes (30 au plus, MBID de Subsonic
  ou recherche MusicBrainz au nom exact), labels des albums favoris (lien album ↔ label gardé dans `album_labels`,
  « rien trouvé » compris : un album n’est cherché qu’une fois), styles dominants du profil de tags (5 au plus).
- **Découvertes** : `artist.getSimilar` de Last.fm (pas `getArtistInfo2` de Subsonic, limité à la bibliothèque),
  proches absents de la bibliothèque et des artistes déjà suivis, 5 par artiste, 60 par compte. Interrupteur dans
  « ⚙ Mes sources » ; sans clé Last.fm, ni pastille ni interrupteur.
- **Tri selon les goûts** : profil de tags pondérés par compte (`radar_profiles`) ; une carte est classée par
  cosinus entre ses tags MusicBrainz et ce profil, puis par date.
- **Page** : pastilles Tout · chaque style · Labels · Mes artistes · ✨ Découvertes, avec leur nombre ; chaque carte
  dit pourquoi elle est là ; « Ouvrir l’album » quand l’album est déjà dans la bibliothèque (rapprochement fait par
  le serveur, gardé 5 min). Changer de pastille ou de semaine remplace la grille seulement. 48 cartes par page.
- **Hors période** (plus de 14 jours en arrière, plus de 60 jours en avant) : la page le dit et propose la
  consultation « un style à la fois » (l’ancienne vue, requête MusicBrainz à la demande, cache 1 h).

### Synchronisation de fond
- Fil lancé par `app.run()` (`ReleaseSync.run`) : au démarrage si la dernière synchronisation complète date de plus
  de 24 h, puis chaque nuit à 4 h. **La mise en production lance donc la première synchronisation.**
- Elle recalcule les tendances de chaque compte, puis interroge l’**union dédoublonnée** des sources de tous les
  comptes, des plus anciennes aux plus récentes : un style = une requête par semaine de la fenêtre (2 pages de 100
  au plus) ; un label = ses éditions de la fenêtre, puis une requête groupée `rgid:` pour ne garder que les
  nouveautés (pas les rééditions) ; les artistes et proches = requêtes groupées par 20 (`arid:`).
- Une panne garde les sorties déjà en base et note l’échec (`radar_sync.failed_at`). Les sorties plus vieilles que
  30 jours sont purgées.
- Ajouter une source la synchronise tout de suite ; « ↻ » relance tendances et sources du compte, une fois toutes
  les 10 min (refus : 429 `weekly.refresh_too_soon`).
- Toutes les valeurs (fenêtre, plafonds, délais) sont dans `webapp/weekly_releases/limits.py`.

### Où
Paquet `webapp/weekly_releases/` : `radar.py` (service de la page et des sources), `trends.py`, `taste.py`,
`sync.py`, `entities.py`, `limits.py`, `assembly.py` (câblage) ; `service.py` (consultation par style).
Dépôts : `storage/release_radar.py`, `storage/weekly_releases.py`. Migration 29. Requêtes : classe `MusicBrainz`
(`groups_by_artists`, `label_groups`, `release_label`, `search_labels`, `artist_tags`) et `LastFm.similar_artists`.
Page : `web-pc/static/js/weekly-radar.js`, `weekly-sources.js`, `weekly-releases.js` (vue par style).
Routes : `GET /api/news/releases/radar?monday=&filter=&offset=`, `GET …/sources`, `POST …/sources/add
{kind, identity, name}`, `POST …/sources/hide {id}`, `POST …/discoveries {enabled}`, `GET …/search?kind=label|artist&q=`,
`POST …/refresh` ; et toujours `GET /api/news/releases`, `GET …/genres`, `POST …/follow`.

### Tests
`tests/test_release_radar_storage.py` (dont migration 29 depuis une base remplie), `test_musicbrainz_radar.py`,
`test_lastfm_similar.py`, `test_release_trends.py`, `test_release_sync.py`, `test_release_radar_service.py`,
`test_weekly_releases.py` (routes, session, CSRF, 429) ; parcours jsdom `e2e_weekly_radar.js` et
`e2e_weekly_releases.js`.

### N’existe pas / pas vérifié
- Pas de partie communauté (« ce que suivent les autres ») ni de projets parallèles via les relations MusicBrainz.
- Pas d’historique d’écoute par compte (le site ne garde pas les écoutes).
- **Pas vérifié** sur le vrai serveur : durée de la première synchronisation, part des proches Last.fm avec MBID.
