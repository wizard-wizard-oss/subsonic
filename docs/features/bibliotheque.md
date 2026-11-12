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

## Discographies et crédits Discogs (1.7.10)
- Depuis la 1.8 : choix d’artiste Discogs mémorisé par compte, accès compacts visibles en haut et discographie
  automatique sous les albums. Bio sous le nom, visuel indépendant (Discogs, Subsonic, Wikipédia selon identité).
  « Changer » et « Actualiser » distincts. Schéma 16 ; détails et validations dans `decouverte-labels.md`.
- Sur la page artiste : **Voir la discographie Discogs**, choix explicite de l’identité, cartes avec pochettes,
  dates et formats, disques principaux et participations, pagination et rééditions regroupées. Les correspondances
  locales donnent accès à l’album ; une recherche est proposée sinon. Les membres/groupes sont également cliquables.
- Sur l’album : choix d’une édition Discogs, labels et musiciens crédités ; liens vers leurs fiches et discographies.
  Discogs est proposé avant le complément MusicBrainz. Les crédits d’édition et les membres d’un groupe restent distincts.
- Depuis un label : découverte variée ou classement sourcé, priorité à la bibliothèque, versions YouTube choisies,
  écoute et enregistrement de playlists mixtes. Détails : [`decouverte-labels.md`](decouverte-labels.md).
- `DISCOGS_API_KEY` est maintenant branchée à la configuration et au conteneur, strictement côté serveur.
  Métadonnées utiles seulement, cache 24 h ; aucune écriture Discogs, modification de tags ou de fichiers.
- L’essai initial du 07/11/2026 avait validé treize lectures authentifiées ; la 1.7.10 vérifie aussi les services
  réels dans Docker. La couverture dépend de la base communautaire, sans garantie d’exhaustivité. **Déployé et vérifié
  le 08/11/2026** : HTTPS, version et fichiers servis, base intègre ; API Discogs/Last.fm relues depuis la production.
  Lecture audio YouTube réelle et parcours connecté à la bibliothèque de production encore à essayer.

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
