# Envoi de musique et rangement dans la bibliothèque (site web)

## En bref
Une personne qui a le droit Subsonic `upload` envoie uniquement un ZIP d’albums depuis la page « Envoyer ».
Le site décompresse le zip, puis **range aussitôt** chaque album qui respecte la nomenclature à sa place dans la
bibliothèque, chez son artiste. Ce qu'il ne sait pas placer attend dans `Incoming`, pour être rangé à la main. Subsonic
scanne ensuite pour faire apparaître les nouveaux titres.

## Albums uniquement et notifications (1.17)

Les fichiers audio envoyés directement sont refusés côté navigateur et serveur, sans écriture de musique ni
entrée d’historique. Un ZIP contenant des titres à sa racine ou sans dossier artiste est refusé intégralement
avant de placer le moindre album. Les archives valides respectent Artiste/Album/titres, avec les dossiers
de disques existants. Les limites de taille sont fournies au navigateur par le statut du serveur.

Le MP3 de Baston 3000 (envoi 18 de Mnu) a été retiré de la bibliothèque le 27/11/2026 à la demande de
l’utilisateur. Copie de récupération hors musique dans `/data/removed-uploads/upload-18/`, empreinte
SHA-256 vérifiée et scan Subsonic demandé. L’historique d’origine est conservé. Le destinataire est
celui de cet envoi ; le message utilise les [notifications privées](notifications.md).

## Fiabilité du rangement et de l’attribution (1.17)

Le rattrapage isole les erreurs de lecture, de déplacement ou de nettoyage par album et par artiste.
Un refus de droits est journalisé avec le dossier concerné ; les autres albums continuent à être traités.
Les déplacements réussis déclenchent le scan même si le nettoyage d’un dossier vidé échoue.
`IncomingSorterTest` couvre ces trois cas. Aucun droit du disque n’est modifié automatiquement.

Après une correction de tags, le cache des chemins utilisé pour afficher l’auteur est également invalidé :
voir [Tags d’albums](tags-albums.md). L’historique d’envoi reste inchangé.

Diagnostic de production du 27/11/2026 : Baston 3000 est un MP3 seul envoyé par Mnu, à la racine d’Incoming,
avec un artiste et un titre mais sans tag album. Ses droits sont corrects (664, propriétaire du site) ;
le téléchargement individuel via Subsonic répond 200 avec les comptes thomas et Mnu. Subsonic annonce
un album générique « Incoming » avec un titre, mais `getAlbum` n’en renvoie aucune piste et `getSong`
n’expose pas d’`albumId`. La fiche album ne peut donc pas fournir son téléchargement. Il faut compléter
le nom d’album et ranger le fichier sous Artiste/Album pour constituer un véritable album. Aucun déplacement
ni modification de tags de ce titre n’a été effectué pendant ce diagnostic.

## Historique des envois (1.10)
La page « Envoyer » affiche un tableau partagé entre tous les comptes connectés : date, compte connecté,
fichier ou archive, nombre de fichiers reçus et résultat du rangement. Il se recharge à la fin de chaque lot et à
chaque visite. Les envois précédents se chargent par pages de 50, du plus récent au plus ancien.

La migration web 19 ajoute `upload_history` : identifiant, référence au compte, copie de son nom, nom du fichier,
taille reçue, nombres de fichiers gardés/ignorés, albums rangés et éléments restés dans Incoming, date de réception.
L'auteur vient uniquement de la session authentifiée. L'historique reste dans `webapp.db` après redémarrage.
Le dépôt `storage/uploads.py` renvoie des entités `upload_entities.py` ; `Uploads` enregistre après réception réussie
et publie une page via `GET /api/upload/history?before=<id>` (authentification uniquement).
L'attribution est aussi montrée sur les nouveaux albums à l'accueil et dans la fiche album, sans droit d'envoi
ou de téléchargement requis. `upload_albums` relie les dossiers rangés à leur envoi, dans la racine de musique
concernée. `upload_attribution.py` confirme le chemin des titres dans Subsonic (disques CD compris) avant de
montrer un nom, même quand les tags diffèrent des noms de dossiers. Les chemins résolus sont mis en cache
dix minutes ; l'accueil utilise au plus quatre lectures simultanées. Aucune lecture supplémentaire de Subsonic
n'est faite en l'absence d'albums attribués dans cette bibliothèque. Aucun nom n'est déduit des droits ou des dates Subsonic.

Limites : aucun rattrapage des anciens envois, aucun inventaire piste par piste d'un ZIP, aucun suivi des déplacements
manuels ou automatiques ultérieurs. Le résultat est celui à la réception. Les refus et interruptions ne sont pas
des envois réussis. Disque et SQLite ne forment pas une transaction commune : une panne après écriture du fichier
et avant inscription en base peut laisser un fichier sans historique. Version 1.10 déployée et vérifiée le 12/11/2026 sur le site local et sur https://music2.foos.fr :
conteneurs sains, version publique 1.10, ressources versionnées conformes et SQLite intègre au schéma 19.
Les 12 comptes et les données existantes de production sont conservés ; l’historique démarre vide pour les anciens envois.
Validation globale : 691 tests Python et les six parcours navigateur, dont le parcours À écouter rejoué après correction
d’une attente du DOM. Sauvegarde et image de retour arrière consignées dans docs/ETAT.md.

Validation : `UploadHistoryTest` (attribution, accès, ZIP, échecs, persistance, pagination et envois simultanés) et parcours jsdom PC
(tableau, auteur, résultat et retour sur la page).

## La nomenclature (`pimedia/webapp/library/naming.py`)
La racine de la musique (`MUSIC_DIR`) contient un dossier par artiste et un sous-dossier par album :

```
<racine>/Artiste/Album/titre.flac
<racine>/Artiste/Album/CD1/titre.flac        album en plusieurs disques
<racine>/Artiste/Album/cover.jpg             pochette
<racine>/Incoming/                           ce qui attend d'être rangé à la main
```

- Les nouveaux dossiers d'artistes et d'albums reçoivent **une majuscule à chaque mot** (séparateur : espace ou
  tiret), sans abaisser les autres lettres : « jean-michel jarre » devient « Jean-Michel Jarre », « DJ NaZe »
  reste « DJ NaZe ». Les chiffres, accents et signes sont conservés (« 38 Spesh », « ...Et Après »).
- Un sous-dossier d'album n'est accepté que s'il s'agit d'un **disque** : `CD1`, `CD 2`, `Disc 1`, `Disk 2`, `Disque 3`
  (majuscules indifférentes). « Face A » ou « Bonus » ne le sont pas.
- **Un seul dossier par artiste** : un artiste déjà présent est retrouvé **sans tenir compte des majuscules, des
  accents, des espaces ni de la ponctuation** (« Dalek » rejoint « Dälek », « DJ NaZe » rejoint « DJ Naze »,
  « A.A.Williams » rejoint « A.A. Williams ») ; la recherche précède la mise en majuscules des initiales et le nom
  du dossier existant est gardé, même si sa casse ne suit pas la règle des nouveaux dossiers.
  Depuis la 1.7.9, les ligatures sont également équivalentes (`Œdipe` / `Oedipe`, `æ` / `ae`) via la comparaison
  commune `shared.text.normalize` (utilisée par `LibraryNaming.comparison_key` pour le rangement).
  `LibraryNaming.normalize_artist` et `normalize_album` appliquent la nomenclature aux nouveaux dossiers ;
  `LibraryFiles.find_matching_folder` retrouve les
  dossiers existants en comparant les clés, sans changer leurs noms. AnyASCII 0.3.3 complète les lettres latines
  non décomposables (`ø/o`, `ł/l`, `đ/d`) ; les noms exacts et les clés Unicode natives sont prioritaires.
  Une correspondance ambiguë attend dans Incoming. Les autres alphabets restent en Unicode : les écritures
  arabes ne sont pas transformées en noms latins pour décider automatiquement d’un rangement.
  Le nettoyage des chemins d’envoi reste distinct de cette clé de comparaison.
  Décision du 18/11/2026 : les futurs rapprochements entre alphabets (par exemple arabe/latin) issus d’une
  même translittération seront proposés pour validation explicite, sans fusion ni rangement automatique sur
  cette seule base. La génération et l’interface de ces suggestions ne sont pas encore implémentées.
- **Rien n'est jamais écrasé** : un album déjà présent chez l'artiste (même nom, aux mêmes détails près) n'est
  pas rangé, il attend dans Incoming.
- La seule correction automatique des noms est la mise en majuscules des initiales des nouveaux dossiers.
  Les accents et la ponctuation (`Mon$rock`, `[Deluxe]`, `!!!`) sont conservés. La simplification des noms sert
  uniquement à retrouver un artiste ou un album déjà présent ; elle ne renomme jamais le dossier existant.
  Aucune recherche de l'orthographe officielle sur un service externe et aucune modification des tags audio.
- **Compilations** : le dossier `Compilations` se range comme un artiste (`Compilations/Album/titre`) : un zip
  `Compilations/Mon album/…` rejoint le dossier existant. Il a un raccourci en haut de la barre (`barre-gauche.md`).

## Ce qui se passe, de A à Z
1. Le lien **« Envoyer »** (ou **« Envois »** sans droit `upload`) est accessible à tous les comptes connectés.
   L'historique est commun ; le formulaire reste réservé aux comptes qui peuvent envoyer et à une racine accessible.
2. Page `#/upload` : on glisse des albums **ZIP** (2 Go au plus), ou clic pour choisir. Les formats audio
   mp3, flac, m4a, aac, ogg, oga, opus, wav, aiff et aif restent acceptés à l’intérieur (300 Mo par titre).
   Les fichiers audio seuls, formats inconnus et tailles refusées sont expliqués tout de suite.
3. **Barres de progression** : une par fichier (l'envoi, puis une barre animée « Décompression et rangement… » pendant que
   le serveur travaille : il ne dit pas où il en est), et une pour le lot entier (« Fichier 2 sur 5 — 40 % », puis
   « Terminé »). Un fichier à la fois.
4. Le serveur reçoit le corps brut (`POST /api/upload?name=`) dans un fichier caché unique d'Incoming (`.nom.<identifiant>.part`). Les publications sont sérialisées pour que deux envois simultanés ne se mélangent pas.
5. **Zip** : décompressé dans un dossier caché d'Incoming. Seuls les fichiers audio et les images jpg/png sont gardés (pas
   `__MACOSX`, `.DS_Store`, textes, playlists…). Noms nettoyés : rien ne peut sortir d'Incoming (`../`, chemins absolus,
   `C:\`). Seuls les caractères de contrôle et les caractères interdits (`<>:"|?*`) sont remplacés ; accents et
   ponctuation sont gardés. Les noms UTF-8 sont aussi reconnus dans les ZIP qui ont oublié leur marqueur d'encodage,
   sans perdre les accents combinés ; les anciens noms CP437 restent pris en charge. 4 Go décompressés au plus,
   300 Mo par titre. Zip abîmé, chiffré, ou sans aucun titre : refusé, rien ne reste.
6. **Rangement immédiat** : chaque dossier qui contient des titres est un album (le dossier au-dessus pour un dossier de
   disque) ; le dossier qui contient l'album est l'artiste. L'artiste existant est recherché avec la comparaison commune.
   Les initiales des mots du nouvel album et, si nécessaire, du nouvel artiste sont mises en majuscules, puis l'album
   est déplacé d'un coup dans `<racine>/Artiste/Album` (Subsonic n'en voit jamais une moitié).
7. **Ce qui reste** rejoint Incoming tel qu’il était organisé dans le ZIP (fusionné avec les dossiers déjà là,
   sans écrasement : « titre (2).flac »). Si un titre est à la racine du ZIP ou dans un album sans artiste,
   toute l’archive est refusée avant placement. Le ZIP temporaire est effacé.
8. **Titre seul** (pas de ZIP) : refusé avant réception avec le message expliquant la règle des albums.
9. La page affiche le résultat de chaque fichier : « Décompressé : 12 fichiers — rangé dans Converge/Jane Doe — à ranger à
   la main dans Incoming : … ».
10. En fin de lot (`POST /api/upload/finish`), le site lance `startScan` : avec le compte de la personne, sinon avec un
    administrateur connu du site (jusqu'à 3). Le scan est réservé aux administrateurs de Subsonic.
11. **Rattrapage d'Incoming** (`pimedia/webapp/library/incoming.py`, toutes les 10 minutes) : un album corrigé à la main sur place,
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
| `converge/jane doe/01.flac` | `<racine>/Converge/Jane Doe/` | artiste existant conservé, initiales de l'album mises en majuscules |
| `jean-michel jarre/nouvel album/01.flac` | `<racine>/Jean-Michel Jarre/Nouvel Album/` | nouvel artiste et album : majuscule à chaque mot |
| `Converge/Live/Face A/01.flac` | `Incoming/Converge/Live/Face A/` | « Face A » n'est pas un disque, et « Converge » est un artiste connu : doute |
| `Jane Doe/01.flac` | ZIP refusé | album sans dossier artiste |
| `01.flac` à la racine de `Jane Doe.zip` | `Incoming/Jane Doe/01.flac` | idem |
| un MP3 envoyé seul | refusé | seuls les albums en ZIP sont autorisés |

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
- `pimedia/webapp/library/naming.py` : `LibraryNaming`, règles de noms d’artistes et d’albums, et clés de comparaison
  déléguées à la normalisation Unicode commune.
- `pimedia/webapp/library/files.py` : accès aux fichiers (`is_disc`, `tracks_fit`, `find_albums`) et
  `LibraryFiles.place` (ranger un album chez son artiste).
- `pimedia/webapp/uploads.py` : réception, décompression, rangement des albums du zip, scan.
- `pimedia/webapp/library/incoming.py` : rattrapage d'Incoming (tâche lancée par `app.py`).
- `pimedia/webapp/controllers/uploads.py`, `controllers/base.py` (`raw_writer`), `config.py` (`music_dir`, `incoming_name`,
  `incoming_wait_hours`).
- Page : `web-pc/static/js/upload.js`, styles `web-pc/static/css/views.css` (`.upload-*`), textes `i18n/fr.yaml`
  (`upload`).
- `compose.yaml`, `docker/web/Dockerfile`, `.env.example`, `deploy/pc/*-exemple.conf`.

## Tests

Correctif 1.10.3 préparé localement le 17/11/2026 : les 725 tests Python complets et les trois parcours PC jsdom
(389 contrôles) passent sous Python 3.12.14 et jsdom 25.0.1. Docker local indisponible. AnyASCII 0.3.3 est testé
comme dépendance PC ; les clés natives, les ambiguïtés et les destinations déjà occupées sont couvertes.
Version 1.10.3 publiée le 18/11/2026 sur https://music2.foos.fr depuis le commit `c52cf40` ; les 219 fichiers
applicatifs et AnyASCII 0.3.3 sont vérifiés. Le rattrapage a placé automatiquement `Trentemøller/Trentemøller` :
dix MP3, 104194801 octets et empreintes SHA-256 identiques. Scan terminé et dix titres au nouveau chemin vérifiés
par l’API Subsonic ; l’album apparaît aussi dans les nouveautés. La recherche ID3 (`search3`) ne le renvoie pas
encore lors du contrôle après scan, point laissé à examiner séparément. Sauvegarde et image de retour arrière
consignées dans `docs/DEPLOIEMENT.md`.

- `tests/test_library_naming.py` : initiales, caractères latins non décomposables, arabe, autres alphabets et signes conservés.
- `tests/test_incoming.py` : nomenclature, rangement, artiste retrouvé (accents, casse reçue quelconque),
  initiales des nouveaux artistes et albums, jamais d'écrasement,
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
- L'envoi et le rangement ne modifient pas les tags audio : seuls les noms de dossiers comptent. La correction
  est une action distincte dans [l'éditeur de tags d'album](tags-albums.md), avec le droit « Modifier pochettes et tags ».
- Aucun quota par personne ni contrôle de l'espace disque.
