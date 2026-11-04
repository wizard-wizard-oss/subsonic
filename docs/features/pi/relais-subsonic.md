# Relais Subsonic, cache et classement par dossiers (Pi)

## Ce que ça fait
- Relais `/rest/*` : le serveur local ajoute lui-même les identifiants Subsonic (la page n'a jamais le mot de passe), flux avec `Range`.
- Cache disque JSON + pochettes, durée de vie par appel, invalidé après étoile / playlist / scrobble ; vidage `/cache/refresh` et
  `/cache/clear` (appui long 1,5 s sur « Actualiser »).
- Détection de nouveaux albums et préchauffage (`watcher.py`).
- Mode « dossiers » : traduit l'API ID3 en parcours par dossiers (bouton « Classement » de l'accueil).
- Sans configuration : message « lancez set-subsonic.sh ».

## Où
`pimedia/server/controllers/library.py`, `upstream.py`, `api.py`, `cache.py`, `policy.py`, `watcher.py`, `folders.py`.

## Tests
`tests/test_pi_mode.py` (24), `tests/test_units.py`, `tests/test_architecture.py`.

## N'existe pas / pas vérifié
- Pas de notes 1-5, pas de téléchargement d'album, pas de commentaires (ça, c'est le site web).
- Jamais essayé contre le vrai serveur Subsonic.
