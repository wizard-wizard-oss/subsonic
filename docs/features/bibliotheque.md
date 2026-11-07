# Bibliothèque : accueil, artiste, album, albums, recherche, favoris (site web)

## Ce que ça fait
- **Accueil** (`#/`) : derniers albums, plus écoutés (`frequent`), mieux notés (`highest`), albums commentés récemment.
- **Artiste** (`#/artist/<id>`) : **le dossier de l'artiste** (pas les tags) ; ses albums = ses sous-dossiers (par année,
  puis nom), cœur (étoile posée sur le dossier), « Radio de l'artiste », « Créer un mix à partir de cet artiste »,
  **biographie** (27/10/2026 : Wikipédia en français, sinon Last.fm via Subsonic `getArtistInfo2`, sinon Wikipédia en
  anglais ; photo Wikipédia, lien vers la source, repliée avec « Lire la suite », `GET /api/artist/bio?name=&id=`, gardée
  un jour, `pimedia/webapp/facts.py`), **titres populaires** (5 puis 10, Last.fm via Subsonic, chargés après la page),
  **artistes similaires** (Last.fm).
- **Album** (`#/album/<id>`) : **le dossier de l'album** ; ses titres = ceux du dossier puis de ses dossiers de disques
  (CD1, CD2…), nom de l'album = nom du dossier, artiste = dossier parent. Pochette, année, genre, nombre de titres, durée,
  « Écouté N fois », étoiles, cœur, Lire, Aléatoire, Ajouter à la file, Télécharger (zip), Partager dans le salon, tableau
  des titres (lecture au double-clic, cœur, téléchargement d'un titre, « Ajouter à une playlist »), commentaires.
- **Albums** (`#/albums/<onglet>`) : Nouveaux, Plus écoutés, Mieux notés, Écoutés récemment, Au hasard, Favoris, Par
  décennie, Par genre, De A à Z ; 40 par page, « Afficher plus ».
- **Lecture sur les pochettes (1.7.7)** : dans les grilles de l'accueil (derniers, plus écoutés, mieux notés),
  d'Albums, d'un artiste, de la recherche et des favoris, une petite flèche apparaît au survol en haut à gauche.
  Elle réutilise l'icône `play` et le style `.play-big` du site, à 30 px. La flèche charge l'album puis le lit dans
  l'ordre, sans navigation ; le reste de la carte, dont son nom, reste un lien vers la fiche. Le bouton est distinct
  du lien (aucun bouton imbriqué dans un lien), accessible au clavier et visible sur écran tactile. Il est absent
  sans le droit `stream`, désactivé pendant le chargement, et conserve la file en cas d'erreur. Les lignes compactes
  des albums commentés gardent leur présentation.
- **Recherche** (champ du haut, dès 2 lettres) : artistes, albums, titres, et section « Ailleurs » (voir `musique-ailleurs.md`).
- **Favoris** (`#/favorites`) : albums et titres marqués d'un cœur.

### Dossiers ou tags (`pimedia/webapp/folders.py`)
La bibliothèque est rangée `Artiste/Album/titre` (voir `envoi-fichiers.md`) : la barre des artistes, la page artiste et la
page album suivent ces **dossiers** (`getIndexes`, `getMusicDirectory`). Ainsi « Dälek » n'apparaît qu'une fois même si
des tags disent « Dalek ». Le reste de Subsonic parle en tags (ID3) ; le site fait le lien :
- identifiant de dossier préfixé `f` (`#/artist/f123`, `#/album/f456`) : dans Subsonic d'origine, dossiers et éléments
  ID3 ont des numéros indépendants qui peuvent se croiser ;
- un lien par identifiant ID3 (listes d'albums, recherche, titre, artistes similaires) ouvre la page du dossier
  correspondant (album → dossier de ses titres ; artiste → dossier qui contient le dossier de son premier album) ;
- l'album garde son identifiant ID3 pour ce que Subsonic range sous l'ID3 : commentaires, cœur, note, téléchargement,
  partage, écoutes. L'artiste donne le sien (`id3Id`, celui de son premier titre) pour la radio, le mix et les artistes
  proches ; un dossier sans aucun titre n'a ni radio ni mix.

## Où
Les **labels et collaborations**, accessibles depuis la page album, sont détaillés dans
[`labels-et-collaborations.md`](labels-et-collaborations.md) : éditions, crédits cliquables, catalogues et groupes liés.
Depuis la version 1.7.3, la page artiste propose aussi « Membres et autres projets », avec choix entre homonymes ;
depuis un album, les membres de ses artistes principaux s'ouvrent dans les crédits. Chaque musicien permet de
retrouver ses autres groupes / projets et d'ouvrir leurs fiches musicales (toutes périodes, dates connues affichées).

`pimedia/webapp/library.py`, `folders.py` (pages artiste et album par dossiers), `controllers/library.py` ; page :
`web-pc/static/js/views.js`, `stars.js`.

## Tests
`tests/test_webapp.py`, `tests/test_webapp_folders.py` (pages par dossiers, liens ID3, noms de dossiers, cœur),
`tests/test_webapp_ext.py` (recherche), `tests/e2e_webapp.js` (dont les pochettes : flèche existante, chargement
unique, album complet sans navigation, erreur sans perdre la file, lien sur le nom).
Version 1.7.7 déployée le 07/11/2026 : santé HTTPS et conteneur sains ; version, JavaScript et CSS servis vérifiés.
Les interactions sont validées dans jsdom ; le parcours avec un compte connecté en production reste à regarder.

**Pochette prise dans le dossier du disque** (27/10/2026, demandé : carrés gris sur la page Compilations). Un album
en plusieurs disques (« Disc 1 », « Vol. 1 », « Volume 3 ») n'a souvent son image que dans ces sous-dossiers, et
Subsonic ne la remonte pas au dossier de l'album : 328 albums sur music.foos.fr, dont la plupart des compilations. Sans
pochette, la carte de l'album (page artiste) et la page de l'album prennent celle du premier sous-dossier qui en a une,
sur deux niveaux (`Folders._cover_below`, gardée 10 minutes, 4 appels Subsonic à la fois). Les listes ID3 (Accueil,
Albums) gardent ce que donne Subsonic.

**Restes de macOS cachés** (27/10/2026, demandé) : un dossier `__MACOSX` (créé par le Finder dans un zip, puis copié avec
la musique) et les fichiers `._…` ne sont montrés nulle part : liste des artistes, pages artiste et album, Accueil, page
Albums, recherche, favoris, titres populaires, mix (`library.mac_leftover`, `visible`). Subsonic les garde : sur
music.foos.fr il y en a trois (`Music/__MACOSX`, `Music/Compilations/__MACOSX`, `Music/Incoming/__MACOSX`), à effacer à la
main si on veut aussi les retirer des applis Subsonic. L'envoi de zip les ignorait déjà. Pas fait pour l'édition Pi.

## Piste Discogs (demandée le 07/11/2026, pas implémentée)
- Ajouter sur la page artiste un lien « Voir la discographie sur Discogs ». Lien direct vers une fiche identifiée
  avec fiabilité ; sinon recherche sur Discogs, sans choisir arbitrairement entre homonymes.
- Possibilité ultérieure, à décider : discographie intégrée au site, triée par année, albums / EP / singles /
  participations séparés, rééditions regroupées, rapprochement prudent avec les albums de la bibliothèque.
- « Complète » signifie ici l'ensemble des sorties référencées par Discogs, pas une exhaustivité garantie.
- Accès API authentifié testé le 07/11/2026 ; intégration dans le site non implémentée. Vérifier au moment de
  l'implémentation les conditions d'utilisation, de conservation des données et d'attribution. Ne rien modifier
  dans les fichiers musicaux ni dans Subsonic pour établir ce lien.
- Essai en lecture seule avec la variable locale `DISCOGS_API_KEY` : jeton personnel accepté par `/oauth/identity`,
  puis recherche des labels, profil, catalogue paginé et détails d'une édition. **13 requêtes HTTP 200** ; limite
  annoncée par les réponses : 60 requêtes/minute. Valeur du jeton et identité du compte jamais affichées.
- Labels identifiés au nom exact : On-U Sound (`2409`), Dischord Records (`18955`), Clivage Music (`1126309`).
  Éditions d'échantillon : `25744`, `368211`, `22347544` ; chacune appartient bien au label demandé. Aucun classement
  construit lors de cet essai.
- Champs effectivement présents : notes communautaires (`community.rating.average` / `count`), collection et
  souhaits (`have` / `want`), liste des pistes, liens YouTube dans `videos`. Les liens ont été lus, leur lecture et
  leur correspondance avec chaque piste restent à vérifier. Les notes sont celles d'une édition : regrouper les
  rééditions sera nécessaire pour présenter un classement d'albums.
- La variable n'est pas encore branchée à `WebConfig` ni passée par `compose.yaml` ; aucun changement du site,
  aucune écriture sur Discogs, aucune mise en production lors de cet essai.
- Sources : [aide Discogs](https://support.discogs.com/hc/en-us/articles/360009335353-Information-For-Artists-And-Labels),
  [documentation API](https://www.discogs.com/developers/) (accès automatisé refusé en 403 lors de cette lecture).

## N'existe pas / pas vérifié
- Présentation de la page Albums « provisoire » (pastilles), à refaire en s'inspirant de Spotify/Deezer.
- Pas de page « albums d'un genre » riche, pas de pagination des titres d'une recherche.
- Thème sombre au choix encore à faire (`docs/ETAT.md`, point 3 ter). « Lire juste après » et lecture au survol des pochettes sont disponibles.
- Titres populaires et similaires : vides si Last.fm n'est pas réglé dans Subsonic.
- Les listes d'albums (accueil, page Albums, recherche, favoris) restent celles de Subsonic, par tags : un album aux tags
  mal faits peut y apparaître sous un autre nom que son dossier (un clic ouvre bien le dossier).
- Sur la page artiste, les cartes d'albums n'affichent pas leur nombre de commentaires (ils sont rangés sous l'ID3).
- Pas vérifié contre le vrai Subsonic : identifiants de dossiers réels, temps de réponse de la page artiste (un appel
  par niveau de dossier, gardé 10 min pour le lien artiste ID3 → dossier).
