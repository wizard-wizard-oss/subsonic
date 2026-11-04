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
`pimedia/webapp/library.py`, `folders.py` (pages artiste et album par dossiers), `controllers/library.py` ; page :
`web-pc/static/js/views.js`, `stars.js`.

## Tests
`tests/test_webapp.py`, `tests/test_webapp_folders.py` (pages par dossiers, liens ID3, noms de dossiers, cœur),
`tests/test_webapp_ext.py` (recherche), `tests/e2e_webapp.js`.

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

## N'existe pas / pas vérifié
- Présentation de la page Albums « provisoire » (pastilles), à refaire en s'inspirant de Spotify/Deezer.
- Pas de page « albums d'un genre » riche, pas de pagination des titres d'une recherche.
- Boutons absents (liste « à faire » dans `docs/ETAT.md`, point 3 ter) : « Lire juste après », bouton lecture sur la
  pochette au survol, thème sombre au choix.
- Titres populaires et similaires : vides si Last.fm n'est pas réglé dans Subsonic.
- Les listes d'albums (accueil, page Albums, recherche, favoris) restent celles de Subsonic, par tags : un album aux tags
  mal faits peut y apparaître sous un autre nom que son dossier (un clic ouvre bien le dossier).
- Sur la page artiste, les cartes d'albums n'affichent pas leur nombre de commentaires (ils sont rangés sous l'ID3).
- Pas vérifié contre le vrai Subsonic : identifiants de dossiers réels, temps de réponse de la page artiste (un appel
  par niveau de dossier, gardé 10 min pour le lien artiste ID3 → dossier).
