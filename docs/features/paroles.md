# Paroles et anecdotes (site web)

## Ce que ça fait
Bouton micro du lecteur ou touche L : panneau à droite **à la place du salon**. `GET /api/lyrics?artist=&title=&album=&duration=`
interroge LRCLIB (paroles synchronisées) puis lyrics.ovh, **sans passer par Subsonic** (décision : l'externe non essentiel
ne passe pas par Subsonic). Résultat gardé un jour. Paroles synchronisées : ligne chantée en surbrillance au milieu ;
paroles simples : défilement estimé.

**Titres YouTube (1.9.3, 11/11/2026)** : préparation des requêtes par la fonction pure
`lyrics_search_pairs`, séparée de l'envoi HTTP. Les métadonnées originales sont essayées en premier,
puis les variantes nettoyées, les crédits artiste/titre séparés par `;`, un tiret espacé ou `|` dans les deux
ordres, et le titre sans sous-titre final entre parenthèses ou crochets. Ainsi, « Destinée ; Guy Marchand »
de la chaîne AnyMusics retrouve Guy Marchand / Destinée, et « Delirium (Ma chérie je t'écris...) » retrouve
Delirium. Les titres affichés, la file et les favoris ne sont pas réécrits. `filter_lyrics_candidates`
écarte les autres artistes et titres voisins renvoyés par LRCLIB ; les comparaisons utilisent
`shared.text.normalize`. LRCLIB, lyrics.ovh, le choix par durée et le cache existants sont réutilisés.

**Anecdotes** (27/10/2026, comme sur le Pi) : cadre au-dessus des paroles, qui change toutes les 14 s (ou au clic) :
sortie de l'album (MusicBrainz), la chanson (Wikipédia), l'artiste (biographie Last.fm via Subsonic), photo Wikipédia.
`GET /api/facts?artist=&title=&album=&artistId=`, classe commune `FactsBuilder`, gardées un jour. Caché s'il n'y a rien. Photos : `upload.wikimedia.org` et `thumb.wikimedia.org` (hôte renvoyé par l'API Wikipédia depuis fin 2026 ; constaté le 31/10/2026) ajoutés à la politique de sécurité (`img-src`).

## Où
`pimedia/webapp/lyrics.py`, `facts.py`, `controllers/lyrics.py`, `controllers/facts.py`, `pimedia/shared/external.py` ; page : `web-pc/static/js/lyrics.js`.

## Tests
`tests/test_lyrics.py` (fonctions pures, homonymes et titres voisins, priorité des métadonnées originales,
durée, repli lyrics.ovh), `tests/test_webapp_music.py` (HTTP et cache des deux cas Guy Marchand,
faux LRCLIB / lyrics.ovh, faux Wikipédia / MusicBrainz : `FakeInfoSites`), `tests/e2e_webapp.js`
(affichage des deux titres YouTube et paroles). Réponses publiques LRCLIB vérifiées le 11/11/2026 :
recherches originales vides, paroles synchronisées disponibles pour les deux titres courts avec Guy Marchand.

## N'existe pas / pas vérifié
- Pas de saisie ni de correction manuelle des paroles ; pas d'autre source.
- Paroles simples : défilement estimé seulement (pas de synchronisation réelle).
- Pas de reconnaissance audio : les recherches restent fondées sur le titre et l'artiste ; un crédit absent
  des métadonnées et du titre YouTube ne peut pas être déduit.
