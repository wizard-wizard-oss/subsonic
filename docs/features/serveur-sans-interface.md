# Branché côté serveur, SANS interface (site web)

Ces fonctions ont leurs routes, leur service et leurs tests, mais **aucun bouton ni page** ne les utilise encore.

| Fonction | Routes | Ce qui manque |
|---|---|---|
| **Marque-pages** | `GET /api/bookmarks`, `POST /api/bookmark/save\|delete` | page « Marque-pages » pour reprendre à la position (les applis de téléphone en créent) |
| **File d'attente partagée** | `GET /api/play-queue`, `POST /api/play-queue/save` | reprendre la file d'une appli, sauvegarder la sienne |
| **Radios Internet** | `GET /api/radios`, `GET /api/radios/stream?id=` (seules les adresses de la liste Subsonic) | page radios |
| **Radio d'un titre** | `GET /api/radio/song?id=` | bouton « Radio de ce titre » |

Photos de profil et lien Last.fm : faits le 27/10/2026, page « Mon compte » (voir `comptes-et-droits.md`).

Code : `pimedia/webapp/listening.py`, `radios.py`, `mixes.py`, `controllers/listening.py`, `controllers/profile.py`.
Tests : `tests/test_webapp_music.py`.
