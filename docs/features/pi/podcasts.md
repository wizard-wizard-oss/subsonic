# Podcasts (Pi)

## Ce que ça fait
- Page `/podcasts` : annuaires iTunes (sans clé) et Podcast Index (clé facultative, Réglages ou `set-podcastindex.sh`), thèmes,
  recherche, fiche avec épisodes, « Dans le même genre », abonnements, masquer, reprise de lecture, marquer lu / oublier.
- Lecture RSS protégée (adresses privées refusées, XML sans entités, cache 30 min, valeur périmée servie si panne réseau).
- Filtre « français seulement » activé par défaut (langue par Podcast Index ou lue dans le flux). Lecteur : reprise, ±15/30 s,
  vitesse, minuteur d'arrêt, historique de recherche.

## Où
`pimedia/server/podcasts/`, `controllers/podcasts.py` (`/podcast-api/*`) ; `web/podcasts.html`, `web/static/js/pod-*.js`. Tables `podcast_subscriptions`, `hidden_podcasts`, `episode_progress`.

## Tests
`tests/test_podcasts.py` (36), `tests/test_podcast_language.py` (8), `tests/e2e_podcasts.js` (41).

## N'existe pas / pas vérifié
- **Non vérifié** avec les vrais annuaires et flux (faux annuaires), ni Podcast Index avec une vraie clé.
