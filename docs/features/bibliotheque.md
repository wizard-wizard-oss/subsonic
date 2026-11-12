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
- **À écouter** : marque-pages et recommandations d’artistes/albums, indépendants des cœurs. Boutons sur les fiches ; voir [listen-later](listen-later.md).

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

## Recherche des artistes (1.9.1, déployée le 10/11/2026)

Le champ de recherche retrouve les artistes de la **même liste de dossiers que la barre latérale**, en complément
des résultats `search3` de Subsonic. Une partie du nom suffit : « gurr » retrouve « Gurriers » même lorsque
`search3` ne renvoie aucun artiste. Casse, accents, ligatures, espaces et ponctuation utilisent la comparaison
commune `pimedia.shared.text.normalize` ; le nom affiché conserve son orthographe.

Les noms exacts passent avant les débuts de noms, puis les autres occurrences ; huit artistes au maximum.
Un résultat des tags portant le même nom normalisé qu'un dossier trouvé est remplacé par ce dossier, dont le lien
ouvre directement la fiche artiste. Les artistes connus seulement par leurs tags restent proposés.

La liste persistante existante est réutilisée avec les dossiers visibles du compte connecté : aucune nouvelle
collecte du catalogue ni scan Subsonic. Incoming et les restes macOS sont exclus comme dans la barre latérale.
Si cette liste est indisponible, les résultats des tags restent utilisables. Les albums et les titres continuent
de venir de `search3`, avec les limites existantes (12 albums et 30 titres). Pas de correction des fautes de frappe.

Code : `webapp/library.py` (`search`, `_search_artists`), dépendance `artist_indexes` assemblée dans `app.py`.
Tests : `tests/test_webapp_search.py` (Gurriers sans résultat ID3, variantes de noms, classement, doublons, tags seuls,
cache, périmètres des comptes, exclusions, indisponibilité de l'index, albums/titres/requête vide),
`tests/e2e_webapp.js` (saisie du nom partiel sans accent puis ouverture du dossier artiste).
Validation : 642 tests Python et parcours jsdom PC passent. Déploiement du 10/11/2026 vérifié en HTTPS :
version publique 1.9.1, 212 fichiers applicatifs identiques aux sources testées, JavaScript servi conforme,
base intègre au schéma 17 inchangé. Sauvegarde et image précédente conservées (voir `docs/ETAT.md`).
Le cas Gurriers est reproduit sur le faux Subsonic ; le test connecté en production est laissé à l’utilisateur.

## Collection en chiffres (1.7.12)

L’accueil présente cinq indicateurs : artistes, albums, chansons, stockage en Gio (octets / 1024³, arrondi à l’entier
depuis 1.7.13, sans décimales : « 1 479,69 » devient « 1 480 ») et heures
de musique (secondes / 3600, partie entière), avec la date du dernier scan et un bloc adapté aux petits écrans.
Le périmètre affiché est **la collection du serveur**, comme les statistiques de la page d’aide Subsonic,
indépendamment des dossiers accessibles à chaque compte. Aucune liste de fichiers ou information de compte n’est exposée.

Les valeurs viennent directement de `MediaLibraryStatistics` et `LastScanned` dans `subsonic.properties`, que Subsonic
enregistre après son scan. Aucun parcours REST, comptage SQL, lecture des fichiers musicaux ou nouveau scan n’est lancé
par le site. Ce fichier est déjà le cache persistant : inutile de recopier les chiffres en base. Le lecteur garde
le dernier résultat valide en mémoire, ne relit le fichier que s’il change et ne remplace les compteurs que si la date
du scan change. Une visite ou un réglage Subsonic sans nouveau scan ne les recalcule jamais.

Activation facultative : `compose.statistics.yaml` monte le seul fichier de propriétés en lecture seule, son chemin
sur l’hôte étant réglé par `SUBSONIC_PROPERTIES_FILE`. Hors Docker : `PI_MEDIA_WEB_SUBSONIC_STATISTICS_FILE`.
Sans source réglée ou lisible, le bloc est masqué sans faux zéros. Une sauvegarde temporairement incomplète ou une
disparition du fichier conserve le dernier résultat valide déjà lu ; sa date reste visible. Seuls six nombres sont
renvoyés dans `/api/home`, jamais le contenu des autres propriétés ni le chemin du fichier.

La prochaine visite de l’accueil prend le résultat du nouveau scan ; pas de mise à jour automatique d’une page restée
ouverte. Pas de migration, de minuterie, d’identifiants supplémentaires ni de changement de Subsonic.

Code : `webapp/library_statistics.py`, entité `LibraryStatistics` dans `entities.py`, assemblage dans `app.py`,
`controllers/library.py` ; composant `web-pc/static/js/library-statistics.js` et sa feuille CSS.
Tests : `tests/test_library_statistics.py` (format natif, cache, changement de scan, redémarrage, source absente ou
incomplète, remplacement de fichier, HTTP authentifié et absence de collecte/secrets), `tests/e2e_webapp.js`
(placement, cinq indicateurs, nombres français, conversion et date, source absente).
Vérification en lecture seule sur la production le 08/11/2026 : format et cinq compteurs confirmés, ainsi que
leur utilisation par la page d’aide dans la distribution officielle Subsonic 6.1.6.
Validation Docker : 577 tests Python passent ; parcours PC validé après reprise isolée des attentes de connexion,
puis dix tests des statistiques rejoués après la dernière protection contre une ligne tronquée. Rendu Chrome vérifié
en sombre et clair, largeurs 1440, 390 et 320 px, sans débordement des chiffres. Configuration Compose validée.
**Déployé et vérifié le 08/11/2026** : version publique 1.7.12, HTTPS et conteneur sains, montage en lecture seule,
190 fichiers applicatifs identiques aux sources testées, JavaScript/CSS/textes publics à jour, SQLite intègre au
schéma 15 et dix comptes conservés. Valeurs du dernier scan confirmées depuis le conteneur : 5 441 artistes,
11 844 albums, 137 323 chansons, 1 588 511 745 837 octets, 33 227 128 secondes. Aucun nouveau scan ni redémarrage
Subsonic pour cette mise à jour. Sauvegarde préalable et retour arrière décrits dans `docs/ETAT.md`.
Le parcours dans un navigateur connecté à la production n’a pas été rejoué ; rendu Chrome et parcours jsdom validés.

**Retouche 1.7.13 déployée le 08/11/2026** : stockage arrondi à l’entier, sans décimales, pour tenir dans sa carte.
Initialement publiée en 1.7.14, elle est renumérotée 1.7.13 dans l’historique à la demande utilisateur.
Arrondi et absence de débordement vérifiés directement dans Chrome à 1440, 390 et 320 px ; le parcours jsdom existant
est adapté, sans nouvelle exécution pour cette retouche (Docker local arrêté). Version publique et JavaScript servis
vérifiés, santé interne et HTTPS saines ; sauvegarde et image de retour arrière conservées.

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
