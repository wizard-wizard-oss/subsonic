# Interface web tactile : navigation, accueil, albums, artistes, recherche, clavier (Pi)

## Ce que ça fait
- Onglets Accueil / Albums / Artistes / Favoris / Playlists / Radios / Recherche + bouton « Menu ».
- Accueil : 5 tuiles mix, rangées « Écoutés récemment / Ajoutés récemment / Plus écoutés / À redécouvrir », décennies.
- Albums : 6 tris, défilement infini (40 par page). Artistes : liste par lettre, affichage progressif (80 lignes).
- Pages album et artiste ; artiste : « Radio de l'artiste », « Titres populaires » (`getTopSongs`).
- Recherche `search3` avec suggestions d'artistes dès les premières lettres. Clavier tactile intégré (simple-keyboard),
  touche Coller, effacement par appui long. Défilement tactile.

## Où
`web/index.html`, `web/static/js/tabs.js`, `nav.js`, `components.js`, `search.js`, `keyboard.js`, `touchscroll.js`.

## Tests
`tests/e2e_music.js` (recherche, suggestions, clavier, QR), `tests/e2e_podcasts.js` (clavier).

## N'existe pas / pas vérifié
- La page ne lit pas le thème YAML (couleurs en dur) : `docs/ETAT.md` point 5.
- **Aucun test** dédié aux onglets Accueil/Albums/Artistes/Favoris, à la page artiste ni à « Titres populaires ».
