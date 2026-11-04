# Radios Internet (Pi)

## Ce que ça fait
- Page web, onglet Radios : liste `getInternetRadioStations` de Subsonic, lecture par la page.
- Menu Tk : 9 radios **codées en dur** (FIP, France Inter/Musique/Culture, TSF Jazz, Radio Paradise (+FLAC), SomaFM, KEXP) jouées
  par un mpv séparé, bouton Arrêter, détection d'une radio coupée (« interrompue »).

## Où
`pimedia/menu/stations.py`, `menu/players.py` ; `web/static/js/tabs.js`.

## Tests
`tests/test_menu.py` (radio, neuf stations, bouton Arrêter), `tests/test_playback.py`.

## N'existe pas / pas vérifié
- Pas d'édition des radios du menu dans l'interface (adresses dans le code, elles peuvent devenir obsolètes).
- Pas de test jsdom de l'onglet Radios.
