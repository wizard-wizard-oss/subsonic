# Lecture et file d'attente (page) (Pi)

## Ce que ça fait
- Barre et plein écran : lecture, précédent/suivant, aléatoire, répétition (0/tout/titre), progression.
- File éditable par glisser-déposer (poignée), « Lire ensuite » / « Ajouter à la file », menu « ⋯ » d'un titre (voir album/artiste,
  radio de ce titre, retirer d'une playlist).
- Écoute signalée à Subsonic : « en cours » au début, « écouté » après la moitié ou 4 min. Mode « sans fin » pour les mix aléatoires.
- **File commune** (écran + téléphones) : la page envoie sa file au serveur à chaque changement (`POST /queue/save`),
  restaurée au démarrage sans lecture automatique ; les demandes des téléphones (« après ce titre » / « à la fin ») sont
  reprises toutes les 1,5 s, un message s'affiche, lecture auto si la file était à l'arrêt. Tables `queue_items`,
  `queue_state`, `queue_requests`.

## Où
`web/static/js/playerui.js`, `player.js`, `controls.js`, `menus.js`, `queue.js` ; `pimedia/server/queue.py`, `controllers/queue.py`, `storage/queue.py`.

## Tests
`tests/e2e_queue.js` (12), `tests/e2e_hifi.js`, `tests/test_queue.py` (7).

## N'existe pas / pas vérifié
- Pas de minuteur d'arrêt pour la musique (seulement pour les podcasts).
- Pas de test jsdom du scrobble Pi, des répétitions/aléatoire ni du glisser-déposer de la file Pi.
