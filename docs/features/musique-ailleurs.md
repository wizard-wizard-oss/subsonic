# Musique d'ailleurs : YouTube, Jamendo et SoundCloud (site web)

## Ce que ça fait
Section **« Ailleurs »** de la recherche : résultats Jamendo (identifiant client gratuit) tout de suite, YouTube (clé
« YouTube Data API v3 ») sur un clic, proposé même quand la bibliothèque a trouvé quelque chose, **une clé par source pour tout le site** (`EXT_JAMENDO_ID`, `EXT_YOUTUBE_KEY` dans le `.env`). Recherches gardées
en base (`ext_searches`), partagées : Jamendo 90 jours ; YouTube **sans limite**, mais seulement la liste des vidéos, leurs
titres, chaînes et durées étant dans `youtube_videos` et **relus tous les 30 jours** (règle de YouTube : `videos.list`,
1 unité de quota pour 50 vidéos, tâche toutes les heures) ; vidéo supprimée, privée ou devenue illisible : oubliée.
**Vidéos déjà trouvées** (par n'importe qui) proposées tout de suite dans la recherche, sans quota (`/api/ext/known`,
début de mot, les plus lues d'abord). 120 recherches YouTube par personne et par heure. Vidéos : refus gardé avec le code d'erreur
YouTube (réessayée après 90 jours), lectures réussies comptées (« déjà lue ici », en tête). Lecture : audio Jamendo, ou
**lecteur officiel YouTube**, vidéo en haut du panneau de droite (ouvert pour elle, salon ou paroles en dessous) ; vidéo refusée → autre version sûre, sinon « Ouvrir
sur YouTube » et titre suivant. Politique de sécurité de la page : seuls youtube.com, i.ytimg.com et *.jamendo.com sont ajoutés.
**Lecture YouTube sans contournement** (ni bloqueur de pub ni téléchargement). La **recherche** passe par un moyen non officiel, sans clé ni quota (décision du 27/10/2026).

**Recherche par YouTube Music** (27/10/2026) : `server/extmusic/ytmusic.py`, bibliothèque `ytmusicapi` (dans
`requirements.txt`, délai de 10 s). Une recherche « titres » puis une « vidéos » (6 places gardées aux vidéos),
20 résultats au plus : titre, artistes (sans les faux artistes « 1,9 Md lectures »), album, durée ; vignette
`i.ytimg.com/vi/<id>/mqdefault.jpg` (les pochettes de YouTube Music sont sur googleusercontent.com, refusé par la page).
Aucun quota ; les vidéos restent vérifiées par `videos.list` (1 unité pour 50) avant d'être proposées. Si YouTube Music
échoue (bibliothèque absente, format changé, réseau), `YouTubeSource` se rabat sur l'API officielle (100 unités),
**limitée à 20 recherches par heure pour tout le site** (`OFFICIAL_SEARCHES_PER_HOUR`). La limite par personne
(120/h) reste, pour que YouTube ne bloque pas l'adresse du serveur. Le Pi a le même code, mais sans `ytmusicapi`
installé il utilise l'API officielle comme avant.

**Favoris d'ailleurs, propres à chacun** (26/10/2026) : cœur sur chaque titre d'ailleurs (recherche, favoris, playlists),
et section **« D'ailleurs »** de la page Favoris (« Tout lire ») où l'on **colle un lien** (même champ sur la page
« Mon compte », partie « Importer depuis YouTube ou SoundCloud », `ExtMusic.linkForm`) :
- vidéo YouTube (`watch?v=`, `youtu.be/`, `music.youtube.com`, `shorts/`, `embed/`) : vérifiée lisible ici ;
- **playlist YouTube** (`playlist?list=`) publique ou non répertoriée : jusqu'à 500 vidéos, dans son ordre
  (`playlistItems.list`, 1 unité de quota par 50, puis `videos.list` pour celles que le site ne connaît pas) ; celles
  qui ne se liraient pas ici sont comptées et signalées. **« J'aime » (`LL`, `LM`) et « À regarder plus tard » sont
  privées** : refus expliqué (il faudrait relier le compte Google, pas fait). Les « Mix » (`RD…`) aussi. Un lien
  `watch?v=…&list=…` désigne la vidéo seule (convention de YouTube) ;
- **titre SoundCloud** (`soundcloud.com/artiste/titre`, `m.`, `on.soundcloud.com`) : décrit par l'oEmbed public de
  SoundCloud, **sans clé** ; joué par le **lecteur officiel SoundCloud** (widget, dans la fenêtre vidéo, un cadre par
  titre ; position et durée par son API). Titre refusé → « Ouvrir sur SoundCloud » et titre suivant. Playlists et
  profils SoundCloud refusés (`ext.soundcloud_not_track`).
Une vidéo YouTube en favori ne garde que son identifiant : titre et chaîne restent dans `youtube_videos`, relus tous
les 30 jours ; une vidéo oubliée là disparaît des favoris. 30 ajouts par lien par personne et par heure, 5 000 favoris
au plus. Les titres d'ailleurs vont aussi **dans les playlists Subsonic** (voir `playlists.md`).

## Où
`pimedia/webapp/extmusic.py`, `ext_favorites.py` (liens, oEmbed SoundCloud, vérification de ce que la page envoie),
`controllers/extmusic.py`, `storage/youtube.py`, `storage/ext_favorites.py` (migration 12, `ext_favorites`) ; réutilise
`pimedia/server/extmusic/` (sources, service ; `YouTubeSource.playlist_video_ids` ajouté pour le site) ; page :
`web-pc/static/js/ext.js`, `engine.js` (YouTube, SoundCloud), `views.js` (section de la page Favoris).
Routes en plus : `GET /api/ext/favorites`, `POST /api/ext/favorite {item, on}`, `POST /api/ext/link {link}`.
Politique de sécurité : `w.soundcloud.com` (script et cadre) et `*.sndcdn.com` (pochettes) ajoutés.

## Tests
`tests/test_webapp_ext.py`, `tests/test_ytmusic.py` (YouTube Music simulé, repli), `tests/test_webapp_ext_favorites.py` (liens, oEmbed, import de playlist, cœur, droits,
quota), `tests/test_extmusic.py`, `tests/e2e_webapp.js` (cœur, liens collés, faux lecteur SoundCloud).

## N'existe pas / pas vérifié
- **Pas vérifié avec de vraies clés.** YouTube Music essayé pour de vrai depuis le Mac le 27/10/2026 (20 résultats en
  1,3 s) et **depuis le serveur de production** le 28/10/2026, dans le conteneur (20 résultats). Risque restant :
  blocage de son adresse par YouTube si les recherches sont trop nombreuses.
- YouTube Music : non officiel, peut casser quand YouTube change (repli automatique sur l'API officielle).
- **Vidéos refusées (28/10/2026)** : essai dans un vrai navigateur, certaines vidéos de labels (ex. Rick Astley,
  « Acid Tracks » de Phuture) sont refusées par le lecteur intégré avec le code 150 (intégration interdite par le
  propriétaire), même quand `videos.list` les dit intégrables ; d'autres se lisent. Ce n'est pas la configuration du
  site (pas d'erreur 153 ; changer `Referrer-Policy` ou `youtube-nocookie.com` → `youtube.com` n'y change rien).
  Correctif : une seule autre version par titre (`replaces` dans `player.js`), puis titre suivant ; les codes qui ne
  tiennent pas à la vidéo (2, 5, 153, YouTube injoignable) ne la marquent plus refusée pour tout le site et ne lancent
  pas de recherche (`NOT_THE_VIDEO`, `extmusic.py`). Essai fait depuis 127.0.0.1 : pas vérifié sur music2.foos.fr.
- SoundCloud : **oEmbed vérifié pour de vrai** le 26/10/2026 (titre, artiste, pochette, numéro du titre bien lus) ; le
  **lecteur officiel n'a pas été essayé dans un vrai navigateur** (seulement un faux dans jsdom).
  Les liens courts `on.soundcloud.com` ne sont pas vérifiés (oEmbed les suit peut-être).
- Pas de connexion à un compte YouTube ou SoundCloud : les « J'aime » privés ne s'importent pas.
- Import de playlist YouTube : pas vérifié avec la vraie API (refus d'une playlist privée reconnu par « Not Found » /
  « Forbidden » dans l'erreur).
- Favoris d'ailleurs : pas visibles dans les applications Subsonic (gardés par le site seulement).
- Pas de fenêtre youtube.com avec compte à rebours comme sur le Pi (`web/static/js/ytpopup.js`).
- Titres d'ailleurs : pas d'écoute signalée.
