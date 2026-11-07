# Envoi de musique et rangement dans la bibliothèque (site web)

## En bref
Une personne qui a le droit Subsonic `upload` envoie un zip d'albums (ou des titres seuls) depuis la page « Envoyer ».
Le site décompresse le zip, puis **range aussitôt** chaque album qui respecte la nomenclature à sa place dans la
bibliothèque, chez son artiste. Ce qu'il ne sait pas placer attend dans `Incoming`, pour être rangé à la main. Subsonic
scanne ensuite pour faire apparaître les nouveaux titres.

## La nomenclature (`pimedia/webapp/layout.py`)
La racine de la musique (`MUSIC_DIR`) contient un dossier par artiste et un sous-dossier par album :

```
<racine>/Artiste/Album/titre.flac
<racine>/Artiste/Album/CD1/titre.flac        album en plusieurs disques
<racine>/Artiste/Album/cover.jpg             pochette
<racine>/Incoming/                           ce qui attend d'être rangé à la main
```

- L'artiste et l'album **commencent par une majuscule** (ou un chiffre, un signe : « 38 Spesh », « ...Et Après »).
- Un sous-dossier d'album n'est accepté que s'il s'agit d'un **disque** : `CD1`, `CD 2`, `Disc 1`, `Disk 2`, `Disque 3`
  (majuscules indifférentes). « Face A » ou « Bonus » ne le sont pas.
- **Un seul dossier par artiste** : un artiste déjà présent est retrouvé **sans tenir compte des majuscules, des
  accents, des espaces ni de la ponctuation** (« Dalek » rejoint « Dälek », « DJ NaZe » rejoint « DJ Naze »,
  « A.A.Williams » rejoint « A.A. Williams ») ; le nom du dossier existant est gardé.
- **Rien n'est jamais écrasé** : un album déjà présent chez l'artiste (même nom, aux mêmes détails près) n'est
  pas rangé, il attend dans Incoming.
- Aucun nom n'est corrigé automatiquement (pas de majuscule ajoutée, pas d'accent retiré).
- Les noms de dossiers restent ceux d'origine : les accents et la ponctuation (`Mon$rock`, `[Deluxe]`, `!!!`) sont
  conservés. La simplification des noms sert uniquement à retrouver un artiste ou un album déjà présent ; elle ne
  renomme jamais le dossier existant.
- **Compilations** : le dossier `Compilations` se range comme un artiste (`Compilations/Album/titre`) : un zip
  `Compilations/Mon album/…` rejoint le dossier existant. Il a un raccourci en haut de la barre (`barre-gauche.md`).

## Ce qui se passe, de A à Z
1. Le lien **« Envoyer »** (menu du haut) apparaît si le compte a le droit Subsonic `upload` et que le site peut écrire dans
   la racine de la musique.
2. Page `#/upload` : on glisse des fichiers (ou clic pour choisir). Formats : **zip** (2 Go au plus), mp3, flac, m4a, aac,
   ogg, oga, opus, wav, aiff, aif (300 Mo au plus). Un format ou une taille refusés sont expliqués tout de suite.
3. **Barres de progression** : une par fichier (l'envoi, puis une barre animée « Décompression et rangement… » pendant que
   le serveur travaille : il ne dit pas où il en est), et une pour le lot entier (« Fichier 2 sur 5 — 40 % », puis
   « Terminé »). Un fichier à la fois.
4. Le serveur reçoit le corps brut (`POST /api/upload?name=`) dans un fichier caché d'Incoming (`.nom.part`).
5. **Zip** : décompressé dans un dossier caché d'Incoming. Seuls les fichiers audio et les images jpg/png sont gardés (pas
   `__MACOSX`, `.DS_Store`, textes, playlists…). Noms nettoyés : rien ne peut sortir d'Incoming (`../`, chemins absolus,
   `C:\`). Seuls les caractères de contrôle et les caractères interdits (`<>:"|?*`) sont remplacés ; accents et
   ponctuation sont gardés. Les noms UTF-8 sont aussi reconnus dans les ZIP qui ont oublié leur marqueur d'encodage,
   sans perdre les accents combinés ; les anciens noms CP437 restent pris en charge. 4 Go décompressés au plus,
   300 Mo par titre. Zip abîmé, chiffré, ou sans aucun titre : refusé, rien ne reste.
6. **Rangement immédiat** : chaque dossier qui contient des titres est un album (le dossier au-dessus pour un dossier de
   disque) ; le dossier qui contient l'album est l'artiste. Si la nomenclature est respectée, l'album est déplacé d'un coup
   dans `<racine>/Artiste/Album` (Subsonic n'en voit jamais une moitié), le dossier de l'artiste étant créé s'il n'existe pas.
7. **Ce qui reste** rejoint Incoming tel qu'il était organisé dans le zip (fusionné avec les dossiers déjà là, jamais
   d'écrasement : « titre (2).flac »). Des titres à la racine du zip sont réunis dans un dossier au nom du zip. Le zip est
   effacé.
8. **Titre seul** (pas de zip) : il n'a ni artiste ni album, il attend à la racine d'Incoming.
9. La page affiche le résultat de chaque fichier : « Décompressé : 12 fichiers — rangé dans Converge/Jane Doe — à ranger à
   la main dans Incoming : … ».
10. En fin de lot (`POST /api/upload/finish`), le site lance `startScan` : avec le compte de la personne, sinon avec un
    administrateur connu du site (jusqu'à 3). Le scan est réservé aux administrateurs de Subsonic.
11. **Rattrapage d'Incoming** (`pimedia/webapp/incoming.py`, toutes les 10 minutes) : un album corrigé à la main sur place,
    en `Incoming/Artiste/Album`, est rangé de la même façon une fois resté `INCOMING_WAIT_HOURS` heures sans changement
    (1 par défaut ; 0 = jamais), puis Subsonic scanne (avec un administrateur connu du site). Le dossier d'artiste vidé
    quitte Incoming. Ce qui a été rangé est écrit dans le journal du conteneur.

## Exemples
Bibliothèque de départ : `Dälek/Absence/`, `Converge/Axe to Fall/`.

| Contenu du zip | Résultat | Pourquoi |
|---|---|---|
| `Converge/Jane Doe/01.flac` | `<racine>/Converge/Jane Doe/` | artiste existant, nouvel album |
| `Dalek/Precipice/01.flac` | `<racine>/Dälek/Precipice/` | même artiste, accents et majuscules mis à part |
| `Chat Pile/God's Country/01.flac` | `<racine>/Chat Pile/God's Country/` | nouvel artiste : dossier créé |
| `Converge/Jane Doe/CD1/…`, `…/CD2/…` | `<racine>/Converge/Jane Doe/CD1/…` | album en plusieurs disques |
| `Mes envois/Chat Pile/Cool World/01.flac` | `<racine>/Chat Pile/Cool World/` | dossier en trop autour, ignoré |
| `Converge/Jane Doe/…` + `Dälek/Precipice/…` | les deux rangés | chaque album est traité à part |
| `Converge/axe to fall/01.flac` | `Incoming/Converge/axe to fall/` | album déjà présent |
| `converge/Jane Doe/01.flac` | `Incoming/converge/Jane Doe/` | pas de majuscule |
| `Converge/Live/Face A/01.flac` | `Incoming/Converge/Live/Face A/` | « Face A » n'est pas un disque, et « Converge » est un artiste connu : doute |
| `Jane Doe/01.flac` | `Incoming/Jane Doe/` | album sans artiste |
| `01.flac` à la racine de `Jane Doe.zip` | `Incoming/Jane Doe/01.flac` | idem |
| un mp3 envoyé seul | `Incoming/titre.mp3` | idem |

**Dossiers en trop** : un dossier au-dessus de l'artiste est ignoré seulement s'il ne contient rien d'autre que le suivant
et ne porte pas le nom d'un artiste de la bibliothèque. Sans cette règle, `Converge/Live/Face A` passerait pour l'artiste
« Live ». Dans le doute, l'album attend dans Incoming.

## Installation
L'API Subsonic n'a **pas d'envoi de fichiers** : le site écrit directement dans le dossier de musique.
- `MUSIC_DIR` (`.env`) = la racine de la musique sur l'hôte, celle que Subsonic (image `gzurowski/subsonic`) monte en
  lecture seule sur `/var/music`. Le site la monte en écriture sur `/music`. Vide : `datas/Music` à côté de `compose.yaml`
  (test en local).
- Le site tourne sous **le même utilisateur que Subsonic** (`music`) : `APP_UID` / `APP_GID` (`id music`), appliqués à la
  construction de l'image. Fichiers `664`, dossiers `775`.
- `INCOMING_NAME` (`Incoming` par défaut, créé s'il manque), `INCOMING_WAIT_HOURS` (1).
- Le proxy doit laisser passer 2 Go sur `/api/upload` (blocs prêts dans `deploy/pc/nginx-exemple.conf` et
  `apache-exemple.conf`). Détails : `docs/DEPLOIEMENT.md`.

## Où est le code
- `pimedia/webapp/layout.py` : nomenclature (`is_disc`, `capitalised`, `normalised`, `tracks_fit`, `find_albums`) et
  `MusicTree.place` (ranger un album chez son artiste).
- `pimedia/webapp/uploads.py` : réception, décompression, rangement des albums du zip, scan.
- `pimedia/webapp/incoming.py` : rattrapage d'Incoming (tâche lancée par `app.py`).
- `pimedia/webapp/controllers/uploads.py`, `controllers/base.py` (`raw_writer`), `config.py` (`music_dir`, `incoming_name`,
  `incoming_wait_hours`).
- Page : `web-pc/static/js/upload.js`, styles `web-pc/static/css/views.css` (`.upload-*`), textes `i18n/fr.yaml`
  (`upload`).
- `compose.yaml`, `docker/web/Dockerfile`, `.env.example`, `deploy/pc/*-exemple.conf`.

## Tests
- `tests/test_incoming.py` : nomenclature, rangement, artiste retrouvé (accents, majuscules), jamais d'écrasement,
  rattrapage d'Incoming et son délai.
- `tests/test_webapp_upload.py` : envoi HTTP, droits, refus, zip (rangement immédiat, dossiers en trop, cas laissés dans
  Incoming, chemins piégés, zip abîmé), scan ; conservation des accents et de la ponctuation, UTF-8 sans marqueur,
  accents combinés, anciens ZIP CP437 et rapprochement sans renommer un dossier existant.
- `tests/e2e_webapp.js` : page, refus, titres seuls « à ranger », zip rangé chez l'artiste, barre du lot, scan.

## N'existe pas / pas vérifié
- En service sur `music2.foos.fr` ; correctif 1.7.5 déployé et vérifié le 07/11/2026 : santé HTTP 200, ZIP UTF-8 sans
  marqueur extrait avec accents et ponctuation conservés dans un dossier temporaire du conteneur de production.
- Vérifié sur le vrai disque : renommage du dossier `BigDaddyChop, Mon_rock & Na_ün Fiero` en
  `BigDaddyChop, Mon$rock & Nán Fiero`, deux albums et 22 fichiers conservés à l'identique, `startScan` lancé.
- Pas vérifié : un zip de 2 Go derrière le vrai proxy.
- Tests lancés sur macOS et dans Docker (Linux) ; sur macOS le disque ignore les majuscules (« converge » et « Converge »
  sont le même dossier), pas sur le serveur.
- Pas de progression réelle du traitement côté serveur (barre animée seulement) ; pas de reprise d'un envoi coupé.
- Les tags ID3 ne sont ni lus ni corrigés : seuls les noms de dossiers comptent (`docs/ETAT.md` point 3 quater).
- Aucun quota par personne ni contrôle de l'espace disque.
