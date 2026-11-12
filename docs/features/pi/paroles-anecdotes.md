# Paroles et anecdotes (Pi)

## Ce que ça fait
- `/info/lyrics`, `/info/facts`, `/info/genres` : LRCLIB (synchronisé si possible), lyrics.ovh, puis Subsonic `getLyrics` ; anecdotes
  (MusicBrainz, Wikipédia, biographie Subsonic) ; cache serveur définitif si non vide, retenté après 24 h si vide.
- Plein écran : paroles synchronisées, cadre « anecdotes » qui tourne toutes les 14 s. Paroles affichées = pas d'écran de veille
  (`/control/awake` toutes les 15 s).
- Recherche partagée (11/11/2026) : fonctions pures `lyrics_search_pairs` et `filter_lyrics_candidates` ;
  priorité au titre/artiste d'origine, variantes pour les crédits artiste/titre ajoutés aux vidéos et les
  sous-titres finaux entre parenthèses ou crochets. Le filtre LRCLIB vérifie les noms avec
  `shared.text.normalize`. Transport HTTP et noms affichés conservés.

## Où
`pimedia/server/controllers/library.py` (`InfoController`), `pimedia/shared/external.py`, `server/external.py` ; `web/static/js/lyrics.js`.

## Tests
Aucun test de `/info/*` ni de `lyrics.js` côté Pi ; `tests/test_pi_mode.py` (`test_awake_flag`).
`tests/test_lyrics.py` vérifie la préparation, le filtre et les sources du code partagé ; le site web
teste aussi les deux cas Guy Marchand par HTTP et dans son parcours jsdom.

## N'existe pas / pas vérifié
- Non vérifié dans les tests Pi.
