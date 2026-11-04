# Fonctionnalités : ce qui existe, ce qui n'existe pas

Une fiche par fonctionnalité, écrite pour **savoir ce qu'elle fait de A à Z** sans relire le code : ce qui est
implémenté, où se trouve le code, quels tests la couvrent, et ce qui **n'existe pas** ou n'est **pas vérifié**.
Les deux éditions sont séparées (voir `docs/architecture/`) : les fiches du site sont préfixées « (web) » ci-dessous,
celles du Pi dans `pi/`.

**À mettre à jour dans le même geste que le code** : toute fonctionnalité ajoutée, changée ou retirée change sa fiche.
Dans une fiche, « Pas vérifié » veut dire : non essayé sur le vrai matériel / le vrai serveur (testé seulement avec les
faux Subsonic, mpv et jsdom).

## Site web (édition PC)
| Fiche | Résumé | Interface | Vérifié en vrai |
|---|---|---|---|
| [comptes-et-droits](comptes-et-droits.md) | connexion Subsonic, sessions, droits, réglages, page « Mon compte », photos (Gravatar) | oui | en partie (photos : Chromium) |
| [barre-gauche](barre-gauche.md) | artistes + playlists, modes | oui | oui (liste d'artistes) |
| [bibliotheque](bibliotheque.md) | accueil, artiste, album, albums, recherche, favoris | oui | en partie |
| [notes-et-commentaires](notes-et-commentaires.md) | étoiles, cœur, commentaires d'album | oui | en partie |
| [salon](salon.md) | discussion temps réel | oui | oui (Traefik) |
| [lecteur](lecteur.md) | lecteur, file, raccourcis | oui | jsdom seulement |
| [paroles](paroles.md) | LRCLIB / lyrics.ovh | oui | oui (LRCLIB) |
| [mix-et-radios](mix-et-radios.md) | mix, créateur, radio d'artiste | oui (sauf radio d'un titre) | serveur oui |
| [playlists](playlists.md) | playlists, communautaires, glisser-déposer | oui | non |
| [import-playlists](import-playlists.md) | importer une playlist Deezer, Spotify, Apple Music (+ guide) | oui | lien Deezer oui ; bibliothèque non |
| [ecoute-en-cours](ecoute-en-cours.md) | scrobble, « Écouté en ce moment » | oui | non |
| [musique-ailleurs](musique-ailleurs.md) | YouTube, Jamendo | oui | non (clés) |
| [envoi-fichiers](envoi-fichiers.md) | envoi dans Incoming (fichiers, zip décompressé) + scan | oui | non (pas mis en route) |
| [pochettes](pochettes.md) | crayon sur la pochette d'un album : recherche Last.fm ou adresse, écrite en cover.jpg dans le dossier | oui | non (faux Last.fm et Subsonic) |
| [telechargement](telechargement.md) | zip d'album, titre | oui | oui |
| [actualite](actualite.md) | flux RSS des webzines, « Dans la presse » sur la page artiste | oui | non (flux lus une fois) |
| [nouveautes](nouveautes.md) | page « Nouveautés » qui explique le site aux utilisateurs | oui | jsdom + démo |
| [versions](versions.md) | page « Versions » : historique daté, numéro et pastille près du titre | oui | jsdom + démo |
| [serveur-sans-interface](serveur-sans-interface.md) | marque-pages, file partagée, radios Internet… | **non** | non |

## Pi
Voir [pi/README.md](pi/README.md) : 18 fiches, inventaire d'après le code, rien de vérifié sur le vrai Pi.
