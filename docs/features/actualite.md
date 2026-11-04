# Actualité : flux RSS des webzines (site web)

## Ce que ça fait
Page **« Actualité »** (`#/news`, lien dans le menu du haut) : les derniers articles des webzines suivis par le site,
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
- Pas de reconnaissance des artistes de la bibliothèque dans la page Actualité (pastille « parle de … »).
- Noms courts ou communs (« Air », « Justice ») : des articles sans rapport peuvent apparaître sous l'artiste.
- Les articles ne sont jamais effacés (sauf avec leur flux).
- Mowno est derrière Cloudflare : son flux répond aujourd'hui, sa recherche non.
- **Pas vérifié** sur le vrai serveur (lecture toutes les heures dans le conteneur) ; les trois flux de départ ont été
  lus une fois depuis le Mac avec le code du site.
