# Playlists (Subsonic et locales) et favoris (Pi)

## Ce que ça fait
- Onglet Playlists : playlists locales (titres d'ailleurs) et playlists Subsonic (créer, ajouter par la feuille « Ajouter à une
  playlist », retirer, lire). Une playlist Subsonic refuse les titres d'ailleurs.
- Cœur : `star`/`unstar` Subsonic pour la bibliothèque, cœur local pour Jamendo/YouTube.

## Où
`web/static/js/menus.js`, `tabs.js` ; `pimedia/storage/playlists.py`.

## Tests
`tests/test_extmusic.py` (playlists locales, favoris), `tests/test_pi_mode.py` (cache des favoris).

## N'existe pas / pas vérifié
- Pas de playlist communautaire (c'est le site web : `../playlists.md`), pas de renommage ni de suppression de playlist Subsonic dans l'interface du Pi, pas d'étoiles 1-5.
- Pas de test jsdom des playlists Subsonic.
