# Téléchargement d'albums et de titres (site web)

## Ce que ça fait
Droit Subsonic `download`. Bouton **Télécharger** sur la page album : zip fait par Subsonic du dossier de l'album
(`/api/download?album=`, album en plusieurs disques : le dossier qui les contient). Icône au survol de chaque ligne de titre
(`/api/download?song=`). Le flux est relayé par le site.

## Où
`pimedia/webapp/controllers/library.py` (`download`), `views.js`.

## Tests
`tests/test_webapp_roles.py` (zip d'album, titre, entrées invalides). Vérifié sur music.foos.fr : zip « Made In Chicago.zip ».

## N'existe pas / pas vérifié
- Pas de téléchargement d'une playlist ni d'un artiste. Pas vérifié : un gros album complet derrière Traefik.
