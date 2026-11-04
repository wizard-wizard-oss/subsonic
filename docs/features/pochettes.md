# Changer la pochette d'un album (site web)

## Ce que ça fait
Comme dans Subsonic V1. Sur la page d'un album, un **crayon** apparaît en bas à droite de la pochette (au survol) pour les
comptes qui ont le droit Subsonic `upload`. Il ouvre « Changer la jaquette » :
- l'artiste et l'album, préremplis et modifiables ;
- **Rechercher sur Last.fm** : une grille de pochettes (l'album exact d'abord, puis les albums de ce nom, ceux du même artiste
  en tête) ; **un clic sur une image l'enregistre** ;
- ou **l'adresse d'une image** collée à la main (+ OK).

L'image est téléchargée **par le serveur**, vérifiée (jpg ou png, 10 Mo au plus, d'après le début du fichier), puis écrite en
`cover.jpg` (ou `cover.png`) dans le dossier de l'album de la musique (`MUSIC_DIR`, monté en écriture). Une pochette
`cover.*` déjà là devient `cover.jpg.bak` (la copie de secours précédente est remplacée) ; elle n'est retirée qu'une fois la
nouvelle bien écrite. **Subsonic n'est pas invité à scanner** (décision du 31/10/2026) ; la page recharge l'image.

## Réglages
`LASTFM_API_KEY` dans le `.env` (clé gratuite, last.fm/api) → `PI_MEDIA_WEB_LASTFM_API_KEY` (`compose.yaml`). Sans clé, la
recherche est désactivée (message dans la fenêtre) ; l'adresse d'image marche toujours. `MUSIC_DIR` doit être réglé.

## Où est le code
- `pimedia/webapp/covers.py` : `Covers` (dossier de l'album, écriture, copie de secours), `LastFmAlbums` (`album.getinfo` +
  `album.search`), `ImageDownloader` (garde-fous).
- `Folders.album_path` (`folders.py`) : chemin « Artiste/Album » lu sur le `path` des titres ou dossiers de disques de Subsonic.
- `controllers/covers.py` ; routes `GET /api/cover/status`, `GET /api/cover/search?artist=&album=`, `POST /api/cover/save`
  `{albumId, url}` (droit `upload`, CSRF). Erreurs : clés `cover.*` (`i18n/fr.yaml`, section `webapp.cover`).
- Interface : `web-pc/static/js/cover.js` (fenêtre), crayon dans `views.js` (`coverWithPencil`), styles dans `views.css`.
- CSP : `img-src` accepte `https://lastfm-img.freetls.fastly.net` (hôte réel des images, vu avec la vraie clé le 31/10/2026) (aperçus des pochettes proposées).

## Sécurité
Le serveur télécharge une adresse donnée par une personne : seules les adresses **http(s) publiques** passent (noms qui
résolvent vers une adresse privée, locale ou de lien local refusés, **redirections comprises**) ; l'écriture reste dans la
racine de la musique (`realpath`), jamais en dehors.

## Tests
`tests/test_webapp_covers.py` (recherche, écriture, copie de secours, droits, CSRF, garde-fous) ; parcours jsdom
(`tests/e2e_webapp.js`, section « pochette »).

## Pas fait / pas vérifié
- Vérifié avec la vraie clé le 31/10/2026 : `album.search` / `album.getinfo` renvoient bien des images (300 px au plus,
  hôte `lastfm-img.freetls.fastly.net`) et le serveur sait télécharger l'une d'elles. Pas vérifié : l'écriture sur le vrai
  Subsonic de prod.
- Que Subsonic affiche aussitôt la nouvelle image sans scan (cache de ses miniatures) n'est pas vérifié.
- Discogs : pas fait (décision : Last.fm seul pour l'instant).
- Une vérification DNS faite avant le téléchargement ne couvre pas un nom qui change de réponse entre les deux.
