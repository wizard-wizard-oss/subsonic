# Mix et radios (site web)

## Ce que ça fait, de A à Z
- Page **Mix** (`#/mix`, lien dans le menu) : 4 mix rapides (au hasard, mes favoris, découverte, nouveautés) lancés d'un clic.
- **Créateur de mix** (porté du Pi) : artiste de départ (cherché, ou venu de la page artiste `#/mix/<id>`), styles de la
  bibliothèque regroupés avec leur nombre de titres, époques (décennies), 30/60/100 titres, favoris d'abord, « proches
  de proches », ordre chronologique. Boutons **Lancer le mix** et **Enregistrer en playlist** (droit `playlist` : nom
  proposé, playlist Subsonic créée).
- **Radio de l'artiste** (page artiste) : ses titres puis ceux des artistes proches (4 niveaux).
- Tout est calculé **par le serveur du site** (mêmes résultats pour tous) à partir de `getRandomSongs`, `getSimilarSongs2`,
  `getTopSongs`, `getArtistInfo2`, `getGenres` (Last.fm configuré dans Subsonic).

## Où
`pimedia/webapp/mixes.py`, `controllers/mixes.py` (`/api/mix`, `/api/mix/genres`, `/api/mix/build`, `/api/radio/song`,
`/api/radio/artist`) ; page : `web-pc/static/js/mix.js`, bouton radio dans `views.js`. Source d'origine côté Pi :
`web/static/js/mixes.js`, `mixbuilder.js`, `similar.js`.

## Tests
`tests/test_webapp_music.py` (unitaires + HTTP, `FakeSubsonicFull`), `tests/e2e_webapp.js` (mix rapide, créateur, enregistrement).
Vérifié sur music.foos.fr côté serveur (mix de 30 titres en 5,6 s, radio de 100 titres en 6,1 s).

## N'existe pas / pas vérifié
- **« Radio de ce titre »** : la route existe (`/api/radio/song`), **aucun bouton** dans la page.
- Sans Last.fm : radio d'un titre → même style ; radio d'artiste → erreur `mix.no_lastfm`.
- Pas de mix sauvegardé « vivant » (une playlist enregistrée est figée).
