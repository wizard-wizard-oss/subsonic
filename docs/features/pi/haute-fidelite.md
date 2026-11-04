# Haute fidélité (mpv) (Pi)

## Ce que ça fait
- mpv piloté par socket IPC JSON, redémarré s'il s'arrête (`MpvConnection`) ; `HifiPlayer` : chargement, préchargement du titre
  suivant sans blanc (gapless), pause, déplacement, volume, arrêt.
- Adresses refusées sauf flux Subsonic `/rest/stream.view`, `/phone-files/` et http(s) publiques.
- La page (`MpvAudio`) imite un `<audio>` ; bascule par le bouton « Haute fidélité : oui/non » de l'accueil (page rechargée).
  **Désactivé par défaut** (`hifi_playback`). Les titres YouTube ne sont pas préchargés.

## Où
`pimedia/server/playback.py`, `controllers/player.py` (`/player/state`, `/player/cmd`) ; `web/static/js/hifi.js`.

## Tests
`tests/test_playback.py` (8, faux mpv `tests/fake_mpv.py`), `tests/e2e_hifi.js` (8).

## N'existe pas / pas vérifié
- **mpv sur le vrai Pi : non vérifié.** La fréquence d'origine envoyée à l'ampli n'est vérifiée que par la ligne de commande dans le test.
