# Paroles et anecdotes (Pi)

## Ce que ça fait
- `/info/lyrics`, `/info/facts`, `/info/genres` : LRCLIB (synchronisé si possible), lyrics.ovh, puis Subsonic `getLyrics` ; anecdotes
  (MusicBrainz, Wikipédia, biographie Subsonic) ; cache serveur définitif si non vide, retenté après 24 h si vide.
- Plein écran : paroles synchronisées, cadre « anecdotes » qui tourne toutes les 14 s. Paroles affichées = pas d'écran de veille
  (`/control/awake` toutes les 15 s).

## Où
`pimedia/server/controllers/library.py` (`InfoController`), `pimedia/shared/external.py`, `server/external.py` ; `web/static/js/lyrics.js`.

## Tests
Aucun test de `/info/*` ni de `lyrics.js` côté Pi ; `tests/test_pi_mode.py` (`test_awake_flag`). Le code partagé est testé par le site web.

## N'existe pas / pas vérifié
- Non vérifié dans les tests Pi.
