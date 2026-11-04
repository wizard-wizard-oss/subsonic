# Musique d'ailleurs : Jamendo et YouTube (Pi)

## Ce que ça fait
- Sources désactivées par défaut, activées par clé (jamais renvoyée par `/ext/status`). Section « Ailleurs » de la recherche :
  Jamendo automatique, YouTube sur clic « Chercher aussi sur YouTube ».
- YouTube : chaînes « Topic » en premier, vidéos vérifiées intégrables dans la région, versions originales seulement, vidéo
  refusée mémorisée (`unplayable_videos`) puis autre version, sinon « Lire sur YouTube » ; lecteur officiel en iframe + fenêtre
  youtube.com surgissante avec compte à rebours « Fermeture dans 15 s » et « Garder ouverte ».
- Jamendo : audio direct, ni scrobble ni favori Subsonic. Favoris d'ailleurs (`external_favorites`) dans l'onglet Favoris ;
  playlists locales (`local_playlists`, `playlist_tracks`). Page de réglages des clés.
- Le service (`server/extmusic/`) est **réutilisé par le site web**.

## Où
`pimedia/server/extmusic/`, `controllers/extmusic.py` (`/ext/*`) ; `web/static/js/ext.js`, `engine.js`, `ytpopup.js`.

## Tests
`tests/test_extmusic.py` (28), `tests/e2e_music.js` (~35 contrôles), `tests/test_storage.py`.

## N'existe pas / pas vérifié
- **Pas vérifié avec de vraies clés** : aucun appel réel à Jamendo ni YouTube.
