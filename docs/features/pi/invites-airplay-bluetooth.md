# Invités AirPlay / Bluetooth (passage de main) et installation système (Pi)

## Ce que ça fait
- Passage de main : fondu et pause quand un téléphone se met à jouer (`pactl list sink-inputs`, `playerctl`), reprise quand il
  s'arrête, bandeau « passera après ce titre » (« Maintenant » / « Annuler »), retour au Pi si le téléphone ne démarre pas en 8 s.
- Arbitre audio « le dernier qui démarre gagne » (`AudioArbiter`) : coupe radio, pause du lecteur web, Bluetooth, redémarre shairport.
- Installation : `60-airplay.sh` (shairport-sync), `70-bluetooth.sh` (agent, mpris-proxy), `bt-pairing.sh` (mode appairable 2 min).

## Où
`pimedia/server/guests.py`, `menu/audio.py` ; `web/static/js/guest.js` ; `deploy/pi/system/60-airplay.sh`, `70-bluetooth.sh`, `deploy/pi/bin/bt-pairing.sh`.

## Tests
`tests/test_guests.py` (6), `tests/test_menu.py` (arbitre, familles, Bluetooth), `tests/e2e_music.js`. Aucun test des scripts shell.

## N'existe pas / pas vérifié
- **Tout non vérifié sur matériel réel** (AirPlay, Bluetooth, iPhone/Android).
