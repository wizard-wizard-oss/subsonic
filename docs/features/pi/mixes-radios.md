# Mixes, radios et créateur de mix (page) (Pi)

## Ce que ça fait
- Mix aléatoire, favoris (Subsonic + d'ailleurs), Découverte (6 albums au hasard), Derniers ajouts, par décennie, par genre.
- « Radio de ce titre » (`getSimilarSongs2`, sinon même genre, sinon aléatoire) et « Radio de l'artiste » (artistes proches sur 4 niveaux).
- Créateur de mix : styles regroupés, décennies, artiste de départ, favoris d'abord, 30/60/100 titres, « Lancer » ou
  « Enregistrer en playlist » (nom proposé). Calculs dans la page, appels Subsonic directs (le site web, lui, les fait côté serveur).

## Où
`web/static/js/mixes.js`, `mixbuilder.js`, `similar.js`, `tabs.js`.

## Tests
**Aucun test** du code Pi (les tests de mix de `tests/test_webapp_music.py` concernent le site web).

## N'existe pas / pas vérifié
- Sans Last.fm côté Subsonic : message « Pas de données Last.fm ».
- Contrôle « chronologique » du créateur : non vérifié dans le code (inventaire incomplet).
