# Écoute signalée et « Écouté en ce moment » (site web)

## Ce que ça fait, de A à Z
1. Le lecteur signale chaque titre **de Subsonic** démarré (`POST /api/scrobble {id, submission:false}` → `scrobble`
   « en cours »), si le compte a le droit `scrobble`.
2. Après la moitié du titre (titres de 30 s et plus) ou 4 minutes **réellement écoutées**, il envoie l'écoute comptée
   (`submission:true`). Subsonic la transmet à Last.fm si la personne a relié son compte (Paramètres → Personnel).
3. En haut du **panneau de droite**, au-dessus du salon, la section **« Écouté en ce moment »** (`GET /api/now-playing`,
   `getNowPlaying`) liste chacun, **soi-même en premier** : initiale colorée, titre — artiste, « à l'instant / il y a N
   min », pochette ; un clic ouvre l'album. Relue toutes les 30 s et à chaque titre lancé ; masquée si personne n'écoute.
   Hauteur limitée à 38 % de la colonne, avec ascenseur ; le salon prend le reste.

## Où
`web-pc/static/js/player.js` (`startListen`, `countListen`), `listening.js`, `css/layout.css` ;
serveur : `pimedia/webapp/listening.py`, `controllers/listening.py`.

## Tests
`tests/test_webapp_music.py` (`ListeningHttpTest`), `tests/e2e_webapp.js` (en cours, saut ignoré, comptée une fois, liste).

## N'existe pas / pas vérifié
- Titres YouTube/Jamendo : **non signalés**.
- Photos de profil : initiales colorées seulement.
- Masquée si le salon est fermé (même panneau).
- Pas vérifié sur le vrai Subsonic : `scrobble` et `getNowPlaying`.
