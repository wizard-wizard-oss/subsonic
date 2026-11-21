# Modifier les tags d'un album (site web, 1.11)

## Style en premier (1.11.1)

L'ouverture montre d'abord « Style de l'album ». Les autres informations et les pistes restent dans un volet
replié. Discogs est proposé en premier s'il est configuré ; MusicBrainz reste sélectionnable. Les éditions
s'affichent en cartes visibles : titre, artiste, date, pays, support, pochette Discogs et styles disponibles.
Les titres/artistes exacts et l'année locale améliorent l'ordre des résultats, sans sélection automatique.
Les nombres de pistes inconnus ne sont pas affichés comme zéro.

L'édition choisie montre ses styles et genres ; « Utiliser ce style pour l'album » ne modifie que le genre du
brouillon des pistes modifiables, sans exiger leur correspondance. L'aperçu et l'enregistrement restent
explicites. Aucun style fourni : message clair, valeur existante conservée et saisie manuelle possible.
L'import détaillé exige une correspondance uniquement pour les champs propres aux pistes (titre, artiste
de piste, numéro, disque), pas pour les informations communes d'album.

MusicBrainz peut porter les genres sur le groupe d'éditions : le client consulte ce groupe avec son cache et
son régulateur lorsqu'aucun genre utilisable n'a été trouvé. Une panne de ce complément conserve les pistes
déjà obtenues. Aucun genre d'artiste n'est attribué implicitement à un album.

Cas réel lu sans écriture : Trentemøller/Trentemøller (2026), dix pistes sans genre. Discogs propose les
éditions 39001571 et 39001217 (13/11/2026), genre Rock, styles Shoegaze, Indie Rock et Post-Punk. Ces choix sont
exposés sans reprendre Electronic des anciens albums. Le diagnostic n'a modifié ni musique ni comptes ; le
client fournisseur a utilisé un cache temporaire en mémoire.
Validation : 221 tests Python ciblés et les quatre parcours PC passent ; Chrome vérifié à 768/390/320 px,
sans débordement ni erreur JavaScript. Pas de nouveau stockage SQL, droit `coverArt` inchangé.

## Parcours

Le bouton « Modifier les informations » utilise le droit Subsonic `coverArt`, « Modifier pochettes et tags ».
Le compte n'a pas besoin d'être administrateur. Ce droit est vérifié dans l'interface et sur chaque route serveur.
Navigation, titre et artiste de l'en-tête restent ceux des dossiers. Aucun fichier audio ni dossier n'est renommé
ou déplacé. L'éditeur distingue artiste d'album et artistes des pistes ; il expose aussi album, titre, année,
style, numéro de piste et disque. Une valeur commune peut être appliquée à toutes les pistes, à une sélection
ou aux seules valeurs manquantes. Un champ commun vide n'efface rien ; l'effacement est explicite.

Chaque action prépare un brouillon. L'aperçu est validé par le serveur avant « Enregistrer dans les fichiers ».
Le brouillon reste disponible après erreur ; quitter avec des changements demande confirmation. La fermeture
de session détruit l'éditeur. Le suivi distingue écriture des fichiers et réindexation Subsonic ; réessayer le
suivi ne réécrit pas les fichiers. Les artistes invités sont conservés lorsqu'on change seulement l'artiste d'album.

## MusicBrainz ou Discogs

Une seule source est choisie ; les critères artiste/album sont modifiables. Les éditions gardent date, pays,
support et nombre de pistes lorsqu'ils existent. L'import est sélectif et montre les correspondances entre
pistes locales et proposées. Pour les champs propres aux pistes, une correspondance explicite et unique
est exigée en cas de nombre différent ; l'import du style en est indépendant.
Le rapprochement utilise titres normalisés, numéros/disques et durées proches (trois secondes). Aucun appariement
par ordre ou simple nombre égal de pistes ; une ambiguïté reste à choisir manuellement.
Les positions vinyle ne deviennent pas arbitrairement des numéros ; le style personnel reste conservé tant
que son import n'est pas sélectionné. Une proposition rejoint le brouillon manuel sans enregistrer.

MusicBrainz fonctionne sans clé pour la consultation ; Discogs utilise `DISCOGS_API_KEY` existant. Les clients
dédiés gardent leur transport, cache, régulation et gestion des erreurs. Aucune fusion automatique des sources.

## Données et accès

Subsonic fournit l'album accessible au compte, ses pistes, identifiants et chemins. Le serveur confirme chaque
fichier dans ce périmètre ; le navigateur ne transmet jamais un chemin disque. L'inspection ciblée des seuls
fichiers de l'album complète les champs absents de l'API et contrôle la fraîcheur avant écriture. Si l'index
diffère, l'éditeur le signale et montre les valeurs réelles qui seront remplacées. Les autres vues et les mix
continuent de consulter l'API Subsonic. Aucun inventaire disque global, catalogue SQL, historique de valeurs de
tags en base ou migration SQLite n'est ajouté.

Authentification et droit `coverArt` sont exigés ; les POST demandent aussi CSRF. Le serveur valide champs,
limites et révision des fichiers. Un changement externe donne un conflit. Limites communes : 500 pistes,
500 caractères par champ, numéros de 1 à 999, années de 1000 à 9999. Les liens symboliques, liens physiques
multiples et sorties du périmètre sont refusés. Les formats non modifiables restent en lecture seule.

## Écriture et reprise

Mutagen 1.47.0 écrit les formats vérifiés : MP3 ID3v2.3/v2.4, FLAC, M4A/MP4, Ogg Vorbis, Opus, WAV et AIFF.
AAC brut et les autres formats non reconnus restent en lecture seule. L'audio n'est pas réencodé. Les champs
non modifiés, pochettes, tags inconnus et ReplayGain sont conservés. Une valeur modifiée remplace le champ
correspondant par le texte choisi ; les autres valeurs multiples restent intactes. Les dates détaillées et
totaux de pistes/disques sont conservés lors d'une correction de l'année ou du numéro.

Toutes les copies sont préparées et relues avant publication, puis les révisions revérifiées. Le remplacement
est atomique par fichier ; une erreur au milieu du lot déclenche une restauration conservatrice. Les originaux
et un manifeste technique sans valeurs de tags sont gardés hors musique dans `<data_dir>/audio-tag-backups`.
La rétention des lots terminés est bornée à 24 heures, huit lots et 4 Gio, avec purge lors des opérations et
de la reprise. Les lots inachevés sont récupérés au
démarrage. Une restauration n'écrase jamais un fichier modifié extérieurement après sa publication. Une
récupération non résolue désactive l'édition, conserve les sauvegardes et laisse le site consultable.
Ces sauvegardes techniques ne constituent pas un historique utilisateur.

Les opérations et leur progression restent en mémoire une heure au maximum (32 résultats, deux opérations
actives au plus). Un même album ne peut pas être enregistré simultanément. Le suivi peut disparaître après
redémarrage ; les fichiers et la récupération technique en sont indépendants.

## Réindexation

Le service partagé avec les envois demande `startScan` pour le lot entier. Les cycles attendent un éventuel
scan précédent avant d'en lancer un nouveau. `getScanStatus` est suivi avec un délai borné ; les champs exposés
sont ensuite relus via `getSong`. Les caches sont invalidés et la fiche se recharge après confirmation.
L'artiste d'album absent de l'API standard donne une vérification partielle explicitement signalée : ce champ
est vérifié dans les fichiers. Un scan refusé ou non confirmé conserve les fichiers enregistrés et donne un
avertissement distinct.

## Code et tests

- Entités/limites : `webapp/tag_entities.py` ; service : `album_tags.py` ; écrivain unique : `audio_tags.py`.
- Fournisseurs : `discogs.py`, `musicbrainz.py` ; adaptation commune : `tag_sources.py`.
- HTTP : `controllers/tags.py` ; assemblage `app.py` ; scan `library_scan.py`, partagé avec `Uploads`.
- Interface : `web-pc/static/js/album-tags.js`, `static/css/album-tags.css`, entrée `views.js`, textes `webapp.tags`.
- `tests/test_audio_tags.py` : fixtures de chaque format, intégrité audio, préservation, conflits, chemins,
  échecs de publication, restauration et récupération après interruption.
- `tests/test_album_tags.py` : routes, droits/CSRF, API locale et vrais fichiers temporaires, aperçu sans écriture,
  sauvegarde, sélection, conflits, échecs, scan et absence de stockage SQL des tags.
- `tests/test_tag_sources.py`, `tests/test_tag_matching.py`, `tests/test_library_scan.py` : sources indépendantes,
  rapprochements conservateurs et cycles de scan.
- `tests/e2e_album_tags.js` : brouillon, valeurs mixtes, invités, groupes, fermeture/session, correspondances,
  import, aperçu, écriture unique, progression et erreurs. Enregistré dans `tests/run_e2e.py`.

## Limites et vérifications restantes

Validation locale du 18/11/2026 : suite complète de 787 tests Python, puis 82 tests ciblés après ajout des règles
de correspondance et des derniers cas HTTP, tous verts. Les huit parcours jsdom passent. Les échecs initiaux
de chargement de ressources des parcours Pi venaient du backlog TCP du harness local ; le même réglage que
le harness PC (128 connexions en attente) corrige ce problème sans changer le produit Pi. Rendu Chrome vérifié
en clair/sombre, sur ordinateur et à 768/390/320 px. `git diff --check` passe. Python 3.12.14 avec dépendances
isolées ; Docker local indisponible. Les tests n'ont appelé aucune source externe réelle ni modifié la production.

Le droit `coverArt` et le repli du scan pour un compte non administrateur sont couverts par 114 tests ciblés
scanner/routes/envois et le parcours jsdom complet sous un compte non administrateur autorisé. Un compte
administrateur sans droit d'édition est également refusé.

Publication vérifiée le 18/11/2026 sur https://music2.foos.fr : version et note 1.11 publiques, JS/CSS conformes,
230 fichiers applicatifs identiques à l'instantané testé, Mutagen 1.47.0, conteneur sain, aucune erreur de démarrage.
SQLite reste intègre au schéma 19 et les données existantes sont conservées. Sauvegarde préalable :
`../pimedia-backups/pre-1.11-20261117T234433Z/`, image précédente conservée. Les contrôles après publication
n'ont lancé aucun enregistrement de tags sur la musique réelle ni créé de compte/session.

Les écritures sont vérifiées sur de petites fixtures représentatives,
pas sur une copie de bibliothèque réelle ni toutes les variantes historiques de tags. Les sources externes
et Subsonic sont simulés dans les tests ; aucune musique de production n'a été modifiée.
Corriger album/artiste d'album peut changer les regroupements et identifiants ID3 Subsonic. Un changement
détecté est signalé ; aucune migration automatique des commentaires, favoris ou liens n'est promise. La
conservation des associations reste à vérifier sur une copie. Pas de reconnaissance
acoustique, traitement de collection entière, renommage ni historique d'annulation utilisateur.
