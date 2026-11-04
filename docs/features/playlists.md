# Playlists, communautaires, glisser-déposer (site web)

## Ce que ça fait, de A à Z
- **Liste** (barre de gauche, onglet Playlists) : *Mes playlists*, *Communautaires* (celles des autres où l'on peut ajouter),
  *Partagées* (publiques des autres, lecture seule). Compteur de titres, filtre, pastille ⚑ pour une communautaire.
- **Créer** : bouton « + » → fenêtre (nom + case « Communautaire »). Un dépôt de titres ou d'album sur « + » crée la
  playlist avec ce contenu.
- **Page d'une playlist** (`#/playlist/<id>`) : nom, créateur, nombre et durée, Lire / Aléatoire / Ajouter à la file ;
  créateur : renommer, supprimer, case « Communautaire ». Colonne **« Ajouté par »** si communautaire ; retirer un titre
  (croix au survol). **Petite pochette de l'album devant chaque titre** (27/10/2026, demandé : utile pour les
  compilations qui mêlent plusieurs albums) ; aussi dans les autres listes de titres de plusieurs albums (recherche,
  favoris, titres populaires d'un artiste), pas sur la page d'un album.
- **Changer l'ordre** (27/10/2026, demandé) : le créateur seul (même d'une communautaire), sur la page de la playlist ;
  glisser une ligne (poignée ⋮⋮) au-dessus ou au-dessous d'une autre, ou Alt + ↑ / ↓ sur la ligne (elle garde le
  focus). Titres Subsonic et d'ailleurs ensemble. Subsonic ne sait pas déplacer : le site retire la fin de la playlist
  à partir du premier titre qui bouge et la remet dans le nouvel ordre, en **un seul `updatePlaylist` envoyé en POST**
  (paramètres dans le corps : une adresse serait trop longue pour une grande playlist). Les titres d'ailleurs gardent
  leur nouvelle place chez le site (`after_songs` + `place`, migration 14). La page envoie l'ordre complet ; si la
  playlist a changé entre-temps (ajout, retrait par quelqu'un d'autre ou une appli), rien n'est touché
  (`playlist.changed`) et la page est relue. Une ligne glissée sur une playlist de la barre y est toujours ajoutée.
- **Ajouter** : glisser un titre (ligne d'un tableau) ou un album (pochette) sur une playlist de la barre ; l'onglet
  Playlists s'ouvre seul pendant le glissé ; ou bouton « Ajouter à une playlist » (icône liste) au survol d'un titre.
- **Communautaire** : une playlist Subsonic du créateur A, rendue **publique** (`updatePlaylist public=true`). Quand B y
  ajoute, le site écrit **avec le jeton de A** (gardé à sa dernière connexion) et note dans sa base que c'est B
  (`playlist_additions`). Un titre n'y est ajouté qu'une fois ; chacun ne retire que ce qu'il a ajouté, A retire tout ;
  seul A change le réglage, renomme ou supprime. Côté Subsonic (applis de téléphone) on voit une playlist normale :
  seule la mention « ajouté par » est perdue.
- **Titres d'ailleurs dans une playlist** (26/10/2026, demandé) : un titre YouTube, SoundCloud ou Jamendo se glisse ou
  s'ajoute (« Ajouter à une playlist ») comme un titre Subsonic, depuis la recherche, les favoris ou une autre playlist.
  Subsonic ne peut pas le garder : le site le range à côté de la playlist (`playlist_ext_tracks`, migration 13), à la
  place qu'il avait (après les N titres Subsonic présents à l'ajout). **Sur le site on voit les deux, mêlés ; dans une
  application Subsonic, seulement les titres Subsonic.** Mêmes droits que pour les titres Subsonic (communautaire :
  chacun retire ce qu'il a ajouté). Colonne Album : la source ; pas de téléchargement. Le compteur de la barre compte
  les deux. Une playlist supprimée sur le site emporte ses titres d'ailleurs.

## Où
`pimedia/webapp/playlists.py`, `storage/community.py`, `controllers/playlists.py`, `schema.py` (migrations 7, 13, 14) ;
page : `web-pc/static/js/playlists.js`, `dnd.js`, `views.js` (`songTable`, pochettes glissables), `dialogs.js` (`newPlaylist`).
Titres d'ailleurs : `storage/ext_favorites.py` (`PlaylistExtRepository`), vérifiés par `ext_favorites.py` (`ExtFavorites.checked`).
Routes : `GET /api/playlists`, `GET /api/playlist`, `POST /api/playlist/create|add|remove|rename|delete|community`,
`POST /api/playlist/add-ext {id, items}`, `POST /api/playlist/remove-ext {id, extIds}`,
`POST /api/playlist/reorder {id, order: [{position} | {extId}]}` (tous les titres, dans le nouvel ordre). Chaque titre Subsonic de
`GET /api/playlist` porte `position` (son rang chez Subsonic, pour le retirer), chaque titre d'ailleurs `extId`.

## Tests
`tests/test_webapp_music.py` (`PlaylistHttpTest`, `CommunityPlaylistTest`), `tests/test_webapp_ext_favorites.py`
(`PlaylistWithExtTracksTest` : place, droits, vérification de ce que la page envoie, ordre mêlé), `tests/e2e_webapp.js`
(onglets, création, glisser-déposer, « ajouté par », retrait, titre SoundCloud glissé puis retiré, ordre changé au
clavier et en glissant, pas de poignée sur la communautaire d'un autre). Ordre : `test_webapp_music.py`
(`test_the_owner_changes_the_order`, titre en double, page périmée, autre personne, envoi en POST). Glisser-déposer essayé aussi dans le navigateur intégré de Claude.

## N'existe pas / pas vérifié
- Pas vérifié contre le vrai Subsonic : le paramètre `public` de `updatePlaylist`.
- Si le créateur change son mot de passe, les ajouts des autres sont refusés (`playlist.owner_unavailable`) jusqu'à sa reconnexion.
- Le créateur doit s'être connecté au site au moins une fois (jeton gardé).
- Changer l'ordre : **pas vérifié contre le vrai Subsonic** (`updatePlaylist` en POST, retrait + remise de la fin) ;
  essayé sur le site de démo, glisser à la souris dans le navigateur intégré de Claude. Réservé au créateur.
- Pas de glisser depuis la file de lecture ni depuis une page artiste.
- Titres d'ailleurs : leur place est approximative si des titres Subsonic placés avant eux sont retirés (ils remontent
  d'autant) ; un ajout fait depuis une application Subsonic ne les déplace pas. Pas de file partagée (`savePlayQueue`)
  avec eux. Une playlist supprimée depuis une application Subsonic laisse ses titres d'ailleurs en base (invisibles).
- Firefox/Safari : glisser-déposer non essayé.
