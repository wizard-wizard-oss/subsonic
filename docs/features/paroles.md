# Paroles et anecdotes (site web)

## Ce que ça fait
Bouton micro du lecteur ou touche L : panneau à droite **à la place du salon**. `GET /api/lyrics?artist=&title=&album=&duration=`
interroge LRCLIB (paroles synchronisées) puis lyrics.ovh, **sans passer par Subsonic** (décision : l'externe non essentiel
ne passe pas par Subsonic). Résultat gardé un jour. Paroles synchronisées : ligne chantée en surbrillance au milieu ;
paroles simples : défilement estimé.

**Anecdotes** (27/10/2026, comme sur le Pi) : cadre au-dessus des paroles, qui change toutes les 14 s (ou au clic) :
sortie de l'album (MusicBrainz), la chanson (Wikipédia), l'artiste (biographie Last.fm via Subsonic), photo Wikipédia.
`GET /api/facts?artist=&title=&album=&artistId=`, classe commune `FactsBuilder`, gardées un jour. Caché s'il n'y a rien. Photos : `upload.wikimedia.org` et `thumb.wikimedia.org` (hôte renvoyé par l'API Wikipédia depuis fin 2026 ; constaté le 31/10/2026) ajoutés à la politique de sécurité (`img-src`).

## Où
`pimedia/webapp/lyrics.py`, `facts.py`, `controllers/lyrics.py`, `controllers/facts.py`, `pimedia/shared/external.py` ; page : `web-pc/static/js/lyrics.js`.

## Tests
`tests/test_webapp_music.py` (faux LRCLIB / lyrics.ovh, faux Wikipédia / MusicBrainz : `FakeInfoSites`), `tests/e2e_webapp.js`, vérifié une fois contre le vrai LRCLIB depuis le conteneur.

## N'existe pas / pas vérifié
- Pas de saisie ni de correction manuelle des paroles ; pas d'autre source.
- Paroles simples : défilement estimé seulement (pas de synchronisation réelle).
