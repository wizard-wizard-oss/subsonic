"""Édition PC : site pour plusieurs utilisateurs d'un même serveur Subsonic (grand écran, souris, clavier).

Indépendante de l'édition Pi (pimedia/server) : elle partage seulement le socle (pimedia/storage/database.py,
pimedia/envfile.py, pimedia/i18n.py, la couche HTTP pimedia/server/transport.py).

storage/      tables (en anglais) et dépôts qui renvoient des entités (entities.py)
accounts.py   connexion par compte Subsonic, sessions, limitation des essais
subsonic.py   appels Subsonic au nom de l'utilisateur connecté
library.py    artistes, albums, recherche (+ notes et commentaires du site)
ratings.py    étoiles 1 à 5 (envoyées à Subsonic) et moyenne du site
chat.py       salon global et commentaires d'albums ; events.py : temps réel (SSE), présence, « écrit… »
controllers/  traduction HTTP <-> services, rien d'autre ; app.py assemble le tout
"""
