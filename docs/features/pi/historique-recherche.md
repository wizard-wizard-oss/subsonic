# Historique de recherche (Pi)

## Ce que ça fait
- `/ext/history`, table `search_history` (par type musique/podcasts, doublons remontés, limite) ; proposé quand le champ est vide,
  relance au toucher, retrait. Partagé entre musique et podcasts.

## Où
`pimedia/server/controllers/history.py`, `storage/history.py` ; `web/static/js/history.js`.

## Tests
`tests/test_history.py` (4), `tests/e2e_music.js`, `tests/e2e_podcasts.js`.

## N'existe pas / pas vérifié
- **Pas d'historique de lecture** : la table `play_history` existe dans `schema.py` mais aucun code ne l'utilise.
