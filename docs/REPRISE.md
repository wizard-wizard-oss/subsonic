# Reprendre le projet avec une autre IA (ou une nouvelle discussion)

## Message à coller tel quel

> Projet Pi Media Station, dans `/Users/thomasfoos/Documents/perso/sub2/sources` (le reste de `sub2/` est ancien,
> ignore-le). Lis d'abord `docs/ETAT.md`, puis `docs/CONVENTIONS.md` : contexte, décisions et règles de code.
> Subsonic d'origine (pas Navidrome), API Subsonic standard uniquement. Deux éditions séparées (Pi et PC), aucun
> « if serveur ». Je m'occupe surtout de l'édition PC (le site). Interface : s'inspirer de Spotify/Deezer.
> Continue la liste « Reste à faire » d'ETAT.md, en commençant par la prochaine étape conseillée en haut du fichier.
> Avance seul, pose-moi le moins de questions possible, garde tous les tests au vert et dis-moi franchement ce qui
> n'est pas fait ou pas vérifié. Mets ETAT.md à jour au fur et à mesure.

## Les pièges à connaître (déjà rencontrés)

1. **Les tests tournent dans une image Docker où le code est copié.** Toujours :
   `docker compose build tests && docker compose run --rm tests`. Sans le `build`, on teste l'ancien code.
   Pareil pour le site : `docker compose up -d --build web`.
2. Résultat attendu : `Ran 324 tests … OK` puis `Tous les parcours sont OK` (dernière ligne).
3. **Subsonic (music.foos.fr) est lent pour la liste des artistes** : `getArtists` 34 s, `getIndexes` 19 s (la barre
   utilise `getIndexes` depuis le 26/10/2026 : elle suit les dossiers)
   (les autres appels < 2 s). Le site garde cette liste en base et ne la recalcule qu'après un scan.
4. Pour tester contre le vrai Subsonic sans mot de passe : un petit script Python lancé **dans** le conteneur
   (`docker compose exec -T web …`, code dans `/app`, base dans `/data/webapp.db`) qui réutilise le jeton enregistré
   (`users.subsonic_salt`, `users.subsonic_token`). Ne jamais afficher ces valeurs ni la clé YouTube du `.env`.
5. Un seul compte sur le site pour l'instant (thomas, administrateur, tous les droits) : les cas « compte limité »
   ne sont testés qu'avec le faux Subsonic (`tests/fake_subsonic.py`, `roles`).

Appris le 25/10/2026 :
- Les commandes `docker compose` se lancent dans `sources/` (là où est `compose.yaml`), pas dans `sub2/`.
- Les parcours jsdom directement sur macOS échouent par `ECONNRESET` (rafale de connexions refusée) : les lancer dans
  Docker. Les tests Python seuls tournent sans Docker avec PyYAML (`pip install -r tests/requirements.txt`).
- Subsonic (image `gzurowski/subsonic`) : musique montée en lecture seule sur `/var/music`, `startScan` réservé aux
  administrateurs. Le site garde le jeton Subsonic de chaque personne connectée : c'est ce qui permet d'écrire dans la
  playlist d'un autre (communautaires) et de lancer un scan avec un administrateur ; un mot de passe changé rend ce
  jeton inutilisable jusqu'à la prochaine connexion.
- Dans une playlist communautaire un titre n'est ajouté qu'une fois (l'auteur est noté par titre).
- Le site de test local écoute sur `pimedia.localhost` (Traefik) : la barre de gauche déborde si une colonne de grille
  n'est pas `minmax(0, 1fr)` (noms longs) ; vérifier avec des noms très longs.

## Où en est-on (25/10/2026)

Fait aujourd'hui : barre des artistes réparée (liste partagée, gardée en base, comparée à Subsonic toutes les
10 min) et affichée par lettre au fil du défilement ; droits Subsonic appliqués (écouter, télécharger, playlists,
noter et commenter…) ; téléchargement d'album (zip) et de titre ; deux parcours Pi instables corrigés.

Fait ensuite : file d'attente en bas (survol, glisser-déposer), page Mix (générateur du Pi), radio et artistes
similaires sur la page artiste, téléchargement par titre.
Fait ensuite (soir du 25/10/2026) : playlists dans la barre de gauche (onglets Artistes | Playlists, communautaires où le
site écrit avec le jeton du créateur et garde qui a ajouté chaque titre, glisser-déposer), scrobble dans le lecteur et
« Écouté en ce moment » (panneau de droite), envoi de fichiers dans Incoming (à mettre en route sur le serveur),
`docs/DEPLOIEMENT.md` et les scripts `deploy/pc/push.sh` et `deploy/pi/push.sh`.
Prochaine étape conseillée : la suite du point 3 d'ETAT.md (radio d'un titre, marque-pages, radios Internet, photos de
profil). Veille de l'ampli (Pi) : correctif écrit (mpv libéré après 30 s de pause), à valider sur le vrai Pi (ETAT.md).
Décision en attente de l'utilisateur : la correction des tags ID3 (point 3 quater d'ETAT.md).
Le détail, ce qui n'est pas vérifié et tout le reste : `docs/ETAT.md`.
