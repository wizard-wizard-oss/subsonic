# Saisie et envoi depuis le téléphone (QR code) (Pi)

## Ce que ça fait
- Serveur séparé `0.0.0.0:8100` (désactivable `PHONE_REMOTE=false`) : page `/tel`, QR code affiché par l'écran avec un code qui change
  à chaque affichage ; 10 mauvais codes par minute → verrou 1 min.
- Le texte tapé arrive dans la recherche du Pi (+ suggestions d'artistes) ; ajout de titres à la file ; liens partagés YouTube /
  Deezer / Apple Music / Spotify résolus (oEmbed/API publiques) puis cherchés dans la bibliothèque puis sur YouTube.
- **Envoi de fichier audio** (mp3, flac, m4a, aac, ogg, opus, wav, aiff ; 300 Mo ; 2 Go au total ; purge à 7 jours), servi
  à `/phone-files/<id>` avec `Range`, lisible par mpv. Le fichier **n'entre pas dans la bibliothèque Subsonic**.

## Où
`pimedia/server/remote.py`, `links.py`, `phone_files.py` ; `web/telephone.html`, `telephone.js`, `static/js/remote.js`.

## Tests
`tests/test_remote.py` (8), `tests/test_phone_adds.py` (13), `tests/e2e_music.js`, `e2e_queue.js`.

## N'existe pas / pas vérifié
- **Non vérifié** : QR scanné par un vrai téléphone sur le réseau local ; vrais liens Spotify/Deezer/Apple (faux HTTP en test).
