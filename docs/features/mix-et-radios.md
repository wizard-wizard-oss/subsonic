# Mix et radios (site web)

## Ce que ça fait, de A à Z
- Page **Mix** (`#/mix`, lien dans le menu) : 4 mix rapides (au hasard, mes favoris, découverte, nouveautés) lancés d'un clic.
- **Créateur de mix** (porté du Pi) : artiste de départ (cherché, ou venu de la page artiste `#/mix/<id>`), styles de la
  bibliothèque regroupés avec leur nombre de titres, époques (décennies), 30/60/100 titres, favoris d'abord,
  profondeur des artistes proches, ordre chronologique. Boutons **Lancer le mix** et **Enregistrer en playlist** (droit `playlist` : nom
  proposé, playlist Subsonic créée).
- **Profondeur du créateur** (1.7.8) : choix exclusif de **1, 2, 3 ou 4 niveaux**, 4 par défaut. Niveau 1 : proches de
  l'artiste de départ ; niveau 2 : proches de ses proches, etc. La limite vaut pour l'écoute et l'enregistrement,
  et ne s'applique qu'à l'exploration depuis un artiste de départ. La recherche s'arrête plus tôt si elle a déjà assez
  d'artistes ou n'en trouve plus. Le choix reste valable pendant la création du mix ; ouvrir à nouveau la page
  rétablit 4. Le serveur valide un entier de 1 à 4 (`depth`) ; une ancienne page envoyant `wide` garde son comportement
  (false → 1, sinon 4). Les autres sources du mix (titres proches Last.fm, styles, époques, favoris) gardent leur rôle.
- **Radio de l'artiste** (page artiste) : ses titres puis ceux des artistes proches (4 niveaux).
- **Radio de ce titre** (depuis la version 1.7.6) : bouton à l'icône d'ondes au bout des lignes des titres Subsonic
  (album, titres populaires, recherche, favoris et playlists). Le morceau choisi démarre, suivi des titres proches
  renvoyés par `/api/radio/song` ; la nouvelle sélection remplace la file. Sans suggestion Last.fm, le service existant
  essaie le même genre, puis des titres au hasard. Pas de bouton pour les titres d'ailleurs ni sans le droit `stream`.
  Le bouton est désactivé et marqué occupé pendant le chargement ; une erreur est expliquée sans changer la file
  ni la lecture en cours. Le double-clic sur ce bouton ne déclenche pas la lecture de la ligne d'album.
- Tout est calculé **par le serveur du site** (mêmes résultats pour tous) à partir de `getRandomSongs`, `getSimilarSongs2`,
  `getTopSongs`, `getArtistInfo2`, `getGenres` (Last.fm configuré dans Subsonic).

## Où
`pimedia/webapp/mixes.py`, `controllers/mixes.py` (`/api/mix`, `/api/mix/genres`, `/api/mix/build`, `/api/radio/song`,
`/api/radio/artist`) ; page : `web-pc/static/js/mix.js`, bouton radio dans `views.js`. Source d'origine côté Pi :
`web/static/js/mixes.js`, `mixbuilder.js`, `similar.js`.

## Tests
`tests/test_webapp_music.py` (unitaires + HTTP, `FakeSubsonicFull`, dont validation de profondeur, compatibilité `wide`,
chaîne de cinq artistes vérifiant l'arrêt à chacun des quatre niveaux, radio d'un titre avec / sans Last.fm),
`tests/e2e_webapp.js` (mix rapide, créateur, choix exclusif et accessible des quatre profondeurs, transmission à l'écoute
et à l'enregistrement ; radio d'un titre : morceau de départ, voisins sans doublon,
chargement unique, erreur sans perdre la file, droit d'écoute et exclusion des titres d'ailleurs).
Vérifié sur music.foos.fr côté serveur (mix de 30 titres en 5,6 s, radio de 100 titres en 6,1 s).
Profondeur 1.7.8 vérifiée dans Docker le 07/11/2026 : 52 tests Python (`test_webapp_music`, `test_versions`),
syntaxe JavaScript du composant et du parcours, puis parcours jsdom PC complet, tous passent.

## N'existe pas / pas vérifié
- Le choix de profondeur 1.7.8 n'est pas encore déployé ni vérifié contre le vrai Last.fm. La radio de l'artiste
  et le créateur de l'édition Pi gardent leur comportement actuel.
- Le bouton « Radio de ce titre » est déployé avec la version 1.7.7 le 07/11/2026 (HTTPS, version et fichiers servis vérifiés). Ses interactions sont vérifiées avec le faux Subsonic et jsdom, pas dans un navigateur connecté au serveur de production.
- Sans Last.fm : radio d'un titre → même style ; radio d'artiste → erreur `mix.no_lastfm`.
- Pas de mix sauvegardé « vivant » (une playlist enregistrée est figée).
