# Barre de gauche : artistes et playlists (site web)

## Ce que ça fait, de A à Z
- Deux onglets, **Artistes | Playlists** (l'onglet choisi est gardé dans les réglages, `sidebar_tab`).
- **Artistes** : les **dossiers d'artistes** de la bibliothèque (`getIndexes`), pas les tags : un seul « Dälek » même si
  des titres disent « Dalek » (voir `bibliotheque.md`, « Dossiers ou tags »). Le dossier `Incoming` n'y figure pas. Index
  par lettre cliquable, filtre sans accents (Entrée ouvre le premier), artiste en cours surligné (aussi depuis un album).
  Affichage paresseux par lettre (milliers d'artistes). Subsonic met ~19 s à calculer la liste : le site la garde **une
  pour tout le site** en base (`artist_indexes`), la compare à Subsonic toutes les 10 min (`getIndexes ifModifiedSince`)
  et prévient les pages ouvertes par un événement temps réel `artists` après un scan.
- **Raccourcis épinglés** en haut de l'onglet Artistes, au-dessus du filtre : des dossiers de la racine réglés dans le
  `.env` (`SHORTCUT_FOLDERS`, par défaut `Compilations` : le dossier qui regroupe les compilations, rangé
  `Compilations/Album/titre`). Retrouvés sans tenir compte des majuscules ; un nom absent de la bibliothèque n'affiche
  rien ; le dossier reste aussi à sa lettre. Surligné quand on est sur sa page.
- **Playlists** : sections Mes playlists / Communautaires / Partagées, filtre, bouton « + », nombre de titres, pastille ⚑
  pour une communautaire. Détail dans `playlists.md`.
- Modes : fixe, au survol du bord gauche (la barre sort et rentre), masquée ; largeur réglable ; raccourci A ou bouton ☰.
- Pendant un glisser-déposer, l'onglet Playlists s'ouvre tout seul, et la barre « au survol » sort.

## Où
`web-pc/static/js/sidebar.js` (`ArtistSidebar`), `playlists.js` (`PlaylistPanel`), `dnd.js`, `css/layout.css` ;
serveur : `pimedia/webapp/artist_index.py` (liste et raccourcis), `storage/artist_index.py`, `controllers/library.py`
(`/api/artists` : `index` et `shortcuts`), `config.py` (`shortcut_folders`).

## Tests
`tests/test_webapp_artist_index.py` (dont le raccourci Compilations), `tests/e2e_webapp.js` (barre, raccourci, onglets,
filtre, rechargement).

## N'existe pas / pas vérifié
- Pas de pagination côté Subsonic pour `getIndexes` (API standard) : la liste complète est chargée d'un coup.
- Plus de nombre d'albums par artiste (et plus de réglage pour l'afficher) : `getIndexes` ne le donne pas, et le compter
  demanderait un appel par artiste.
- Pas vérifié sur music.foos.fr depuis le passage aux dossiers (26/10/2026) : temps réel de `getIndexes`, liste rebâtie
  au premier démarrage (migration 8).
- Mode « masquée » : aucune cible pour déposer (il faut le menu « Ajouter à une playlist »).
- Si le salon est fermé, rien ne change dans la barre (le panneau de droite est séparé).
