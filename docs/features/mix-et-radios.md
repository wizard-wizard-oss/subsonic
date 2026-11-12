# Mix et radios (site web)

## Ce que ça fait, de A à Z
- Page **Mix** (`#/mix`, lien dans le menu) : 4 mix rapides (au hasard, mes favoris, découverte, nouveautés) lancés d'un clic.
- **Créateur de mix** (porté du Pi) : artiste de départ (cherché, ou venu de la page artiste `#/mix/<id>`), styles de la
  bibliothèque regroupés avec leur nombre de titres, époques (décennies), 30/60/100 titres, favoris d'abord,
  profondeur des artistes proches, ordre chronologique. Boutons **Lancer le mix** et **Enregistrer en playlist** (droit `playlist` : nom
  proposé, playlist Subsonic créée).
- **Profondeur du créateur** (1.7.8) : choix exclusif de **1, 2, 3 ou 4 niveaux**, 4 par défaut. Niveau 1 : proches de
  l'artiste de départ ; niveau 2 : proches de ses proches, etc. La limite vaut pour l'écoute et l'enregistrement,
  et ne s'applique qu'à l'exploration depuis un artiste de départ. La recherche s'arrête plus tôt si elle a déjà assez
  d'artistes ou n'en trouve plus. Le choix reste valable pendant la création du mix ; ouvrir à nouveau la page
  rétablit 4. Le serveur valide un entier de 1 à 4 (`depth`) ; une ancienne page envoyant `wide` garde son comportement
  (false → 1, sinon 4). Depuis la 1.8.3, toutes les sources du créateur respectent le périmètre des artistes,
  les styles et les époques (voir ci-dessous).
- **Radio de l'artiste** (page artiste) : ses titres puis ceux des artistes proches (4 niveaux).
- **Radio de ce titre** (depuis la version 1.7.6) : bouton à l'icône d'ondes au bout des lignes des titres Subsonic
  (album, titres populaires, recherche, favoris et playlists). Le morceau choisi démarre, suivi des titres proches
  renvoyés par `/api/radio/song` ; la nouvelle sélection remplace la file. Sans suggestion Last.fm, le service existant
  essaie le même genre, puis des titres au hasard. Pas de bouton pour les titres d'ailleurs ni sans le droit `stream`.
  Le bouton est désactivé et marqué occupé pendant le chargement ; une erreur est expliquée sans changer la file
  ni la lecture en cours. Le double-clic sur ce bouton ne déclenche pas la lecture de la ligne d'album.
- Tout est calculé **par le serveur du site** (mêmes résultats pour tous) à partir de `getRandomSongs`, `getSimilarSongs2`,
  `getTopSongs`, `getArtistInfo2`, `getGenres` (Last.fm configuré dans Subsonic).

## Où
`pimedia/webapp/mixes.py`, `controllers/mixes.py` (`/api/mix`, `/api/mix/genres`, `/api/mix/build`, `/api/radio/song`,
`/api/radio/artist`) ; page : `web-pc/static/js/mix.js`, bouton radio dans `views.js`. Source d'origine côté Pi :
`web/static/js/mixes.js`, `mixbuilder.js`, `similar.js`.

## Tests
Correction **1.8.3 (09/11/2026)** : avec un artiste de départ, seuls ses titres et ceux des artistes du graphe
borné par `depth` alimentent le créateur. Les titres populaires sont vérifiés par identifiant d’artiste, ou nom
normalisé lorsque l’identifiant manque ; les albums locaux complètent cette source sans Last.fm. Les artistes
absents de la bibliothèque (identifiant `-1`) sont ignorés. `getSimilarSongs2`, dont la profondeur interne n’est
pas contrôlée ici, et le tirage global ne participent plus à ce parcours. Sans artiste, le tirage par styles et
époques reste disponible. Sans style explicite, les genres renseignés des titres du départ servent de filtre ;
si aucun genre n’est renseigné, seul le périmètre d’artistes peut être garanti. Un style choisi remplace ce repère.
Les genres et décennies s’appliquent à toutes les sources ; les favoris restent aussi dans les artistes retenus.
Une sélection insuffisante reste courte. Les limites par artiste et l’espacement utilisent leur identifiant ou
le nom normalisé, pour éviter de traiter des variantes orthographiques comme des artistes distincts.
Depuis `#/mix/<id>`, écoute et sauvegarde attendent le chargement de cet artiste. Une erreur reste visible et
bloque les actions jusqu’au choix manuel d’un autre artiste ; elle ne lance plus un mix sans artiste par défaut.
Le formulaire garde l’identifiant musical `id3Id` renvoyé par la fiche, et non son identifiant de dossier.
Les deux actions sont verrouillées ensemble pendant une construction.

Régressions couvertes par les tests HTTP : départ « Raz Fresco X », suggestions et titres populaires pollués par
du rock/métal, arrêt à chaque profondeur, filtre automatique du style, styles et décennies explicites, favoris
sans rapport, artiste absent et lecture des albums locaux sans Last.fm. Le parcours jsdom couvre l’attente et
l’échec du départ depuis la fiche, puis la récupération par un choix manuel. Pas de vérification contre la
bibliothèque réelle de Raz Fresco X.
Validation : 617 tests Python et syntaxe JavaScript passent dans Docker sans réseau externe. Les quatre parcours
Pi passent ; le parcours PC passe intégralement après relance isolée, à la suite d’un dépassement de son attente
initiale de connexion lors du lancement global (les cas de mix y passaient déjà).
Déployée le 09/11/2026 sur `music2.foos.fr` : conteneur sain, HTTPS 200, version publique 1.8.3, les 202 fichiers
applicatifs identiques aux sources testées et textes/JavaScript servis conformes. Création de mix protégée,
base intègre au schéma 16 inchangé, sauvegarde cohérente et image précédente conservées. Recharger la page
(Cmd+Maj+R). Le mix réel de Raz Fresco X n’a pas été exécuté avec un compte de production.

Depuis la 1.7.9, les genres utilisent `shared.text.normalize`, comme les autres comparaisons de noms musicaux.
Les profondeurs et tailles sont définies une seule fois dans `mixes.py` ; `/api/mix/genres` transmet aussi les options
et leurs valeurs initiales à la page. Les décennies sont calculées jusqu’à la décennie courante à partir de celles de
la bibliothèque. La collecte des titres parcourt les niveaux demandés sans énumérer quatre listes en dur.
Vérification locale 1.7.9 : 531 tests Python et parcours jsdom PC passent ; le parcours modifie les options de la
réponse serveur pour vérifier qu’elles pilotent bien les choix et les valeurs initiales du formulaire. Non déployé.

`tests/test_webapp_music.py` (unitaires + HTTP, `FakeSubsonicFull`, dont validation de profondeur, compatibilité `wide`,
chaîne de cinq artistes vérifiant l'arrêt à chacun des quatre niveaux, radio d'un titre avec / sans Last.fm),
`tests/e2e_webapp.js` (mix rapide, créateur, choix exclusif et accessible des quatre profondeurs, transmission à l'écoute
et à l'enregistrement ; radio d'un titre : morceau de départ, voisins sans doublon,
chargement unique, erreur sans perdre la file, droit d'écoute et exclusion des titres d'ailleurs).
Vérifié sur music.foos.fr côté serveur (mix de 30 titres en 5,6 s, radio de 100 titres en 6,1 s).
Profondeur 1.7.8 vérifiée dans Docker le 07/11/2026 : 52 tests Python ciblés (`test_webapp_music`, `test_versions`),
syntaxe JavaScript du composant et du parcours, puis parcours jsdom PC complet, tous passent.
Validation finale avant déploiement : 525 tests Python et les cinq parcours jsdom passent dans l'image reconstruite.
Version 1.7.8 déployée le 07/11/2026 sur `music2.foos.fr` : santé HTTPS, numéro public, libellés et JavaScript servis
vérifiés ; les quatre fichiers du conteneur correspondent aux sources testées, intégrité de la base OK (schéma 15).

## N'existe pas / pas vérifié
- Le choix de profondeur 1.7.8 est déployé ; son parcours dans un navigateur connecté contre le vrai Last.fm reste
  à vérifier. La radio de l'artiste et le créateur de l'édition Pi gardent leur comportement actuel.
- Le bouton « Radio de ce titre » est déployé avec la version 1.7.7 le 07/11/2026 (HTTPS, version et fichiers servis vérifiés). Ses interactions sont vérifiées avec le faux Subsonic et jsdom, pas dans un navigateur connecté au serveur de production.
- Sans Last.fm : radio d'un titre → même style ; radio d'artiste → erreur `mix.no_lastfm`.
- Pas de mix sauvegardé « vivant » (une playlist enregistrée est figée).
