# Importer une playlist de Deezer, Spotify, Apple Music… (site web)

## Ce que ça fait, de A à Z
Page **« Importer une playlist »** (`#/import`, bouton ⬇ dans l'onglet Playlists de la barre de gauche, carte dans
« Nouveautés ») ; droit Subsonic « playlist » requis. Faite le 27/10/2026 (demandée).
1. **Lire la playlist** (`POST /api/import/read`) :
   - **lien Deezer** (playlist publique) : `deezer.com/…/playlist/<id>`, ou lien court de l'application
     (`link.deezer.com/s/…`, `deezer.page.link/…`, seuls liens suivis) ; API publique de Deezer, sans clé, pages de 100 ;
   - **fichier** lu par la page (4 Mo au plus) et envoyé en texte ; format reconnu au contenu : CSV (Exportify pour
     Spotify, TuneMyMusic, Soundiiz… : colonnes titre / artiste / album / durée, virgules, points-virgules ou
     tabulations), XML d'Apple Music / iTunes (la première playlist qui n'est pas la bibliothèque), M3U, texte
     « Artiste - Titre ». 1000 titres au plus.
     **Export de toute la bibliothèque Apple** (plusieurs playlists, 28/10/2026) : la page propose la liste (nom + nombre
     de titres ; les playlists d'Apple comme « Musique » à la fin, jamais la bibliothèque entière ni les dossiers) et
     renvoie le fichier avec `playlist` = rang choisi. Essayé avec un vrai export de 24 playlists (835 titres).
2. **Retrouver chaque titre** (`POST /api/import/match`, lots de 25) : `search3` sur le titre nettoyé (sans
   « (feat. …) », « - Remastered 2011 », « (Radio Edit) »…), puis titre + artiste si rien de sûr. Note de 0 à 1 :
   titre 60 %, artiste 30 % (accents ignorés, « Daft Punk » trouve « Daft Punk, Pharrell Williams »), durée (±3 s),
   album en bonus, −0,2 pour un live à la place de l'original (ou l'inverse). ≥ 0,85 : **Trouvé** ; ≥ 0,6 : **À vérifier**
   (3 propositions au plus) ; sinon **Introuvable**. Pas d'ISRC : le Subsonic d'origine ne les connaît pas.
3. **YouTube pour les introuvables** (`POST /api/import/youtube`, lots de 5), si YouTube est réglé sur le site :
   recherche YouTube Music (sans quota), meilleur résultat gardé si sa note ≥ 0,75 (l'artiste est lu dans le titre
   « Artiste - Titre (Clip officiel) »). Compte dans la limite de 120 recherches par heure et par personne ; limite
   atteinte : arrêt, message, les suivants restent introuvables.
4. **Vérifier** : un menu par titre (titres de la bibliothèque proposés, version YouTube, « Ne pas ajouter ») ; résumé
   « N trouvés · N à vérifier · N sur YouTube · N introuvables » ; nom proposé (celui de la playlist ou du fichier).
5. **Créer** (`POST /api/import/create`) : playlist Subsonic avec les titres de la bibliothèque dans l'ordre, puis
   titres YouTube gardés par le site **à leur place** (`Playlists.create_mixed`) ; la page de la playlist s'ouvre.
   500 titres de la bibliothèque et 500 d'ailleurs au plus.

**Guide pas à pas** (`#/import/guide`, lien en tête de la page) : Deezer, Spotify (Exportify), Apple Music sur Mac / PC,
Apple Music sur iPhone (TuneMyMusic), autres plateformes (TuneMyMusic, Soundiiz, texte), « Et ensuite ? ».

## Où
- `src/pimedia/webapp/import_readers.py` : lecture (Deezer, CSV, Apple, M3U, texte), `ImportFailed`.
- `src/pimedia/webapp/playlist_import.py` : nettoyage, notes, recherche bibliothèque et YouTube, création.
- `src/pimedia/webapp/controllers/imports.py` : routes, tailles des lots, validation.
- `Playlists.create_mixed` (`playlists.py`), entité `ImportedTrack` (`entities.py`).
- Page : `src/web-pc/static/js/import.js`, styles « Importer une playlist » dans `views.css`, textes `webapp.import`.

## Tests
`tests/test_playlist_import.py` (lecteurs, liens Deezer, notes, parcours HTTP complet, limite YouTube),
`tests/e2e_webapp.js` (bouton, guide, lien Deezer simulé, états, création dans l'ordre).

## N'existe pas / pas vérifié
- **Pas essayé contre le vrai Subsonic** : la recherche `search3` du Subsonic d'origine avec « titre artiste » ; les
  notes sont réglées à l'estime, sur des exemples. À regarder sur de vraies playlists.
- Lien Deezer **essayé pour de vrai** (playlist publique, 27/10/2026) ; lien court de l'application : pas essayé.
- Exportify, export Apple Music, TuneMyMusic : formats d'après leur documentation et des exemples, pas sur de vrais
  fichiers.
- Pas d'ISRC (piste écartée pour l'instant : environ 9 % des fichiers en ont dans leurs tags ; une tâche de nuit avec
  Deezer pourrait les compléter).
- Pas de connexion aux comptes Spotify / Apple / Deezer (playlists privées) ; pas d'import de YouTube Music ou Tidal
  en direct (passer par TuneMyMusic ou Soundiiz).
- L'aperçu n'est pas gardé : quitter la page perd le travail.
