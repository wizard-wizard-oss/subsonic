# État du projet (à lire en premier dans une nouvelle discussion)

**Recherche des paroles, 1.9.3 (11/11/2026, publiée sur le site avec la 1.10)** :
« Destinée ; Guy Marchand — AnyMusics » échouait parce que le nom de chaîne était utilisé comme artiste ;
« Delirium (Ma chérie je t'écris...) — Guy Marchand » différait du titre court présent dans LRCLIB.
Les deux recherches ont été reproduites vides sur l'API publique, puis retrouvées sous Guy Marchand / Destinée
et Guy Marchand / Delirium avec paroles synchronisées. Deux régressions HTTP échouent avant la correction.
Fonction pure `lyrics_search_pairs` pour préparer les variantes et `filter_lyrics_candidates` pour vérifier
les noms renvoyés, avec la normalisation commune. La fonction d'envoi HTTP reste inchangée ; mêmes sources,
choix par durée et caches, métadonnées originales prioritaires et affichage conservé. Aucun artiste ni titre
codé en dur dans le code applicatif. Code partagé aux deux éditions ; aucune dépendance déplacée.
Tests unitaires dédiés, régressions HTTP et parcours PC complétés pour les deux cas.
Validation : suite complète de 664 tests Python dans Docker, puis 29 contrôles ciblés du code final,
parcours PC complet avec les deux titres YouTube et leur affichage, recherches réelles via le finder corrigé.
Publié sur les sites web local et de production avec la 1.10 le 12/11/2026 ; aucun déploiement Pi dans cette opération. Voir [Paroles](features/paroles.md).

**Notifications des recommandations, 1.9.2 (10/11/2026, déployées et vérifiées)** :
pastille rouge sur « À écouter » tant que des conseils restent non lus. État persistant par recommandation,
flux SSE existant ciblé sur le destinataire, mise à jour des onglets et rattrapage à la reconnexion ou au retour
sur la page. Les conseils réellement affichés sont acquittés par leur marqueur de livraison : une arrivée
simultanée ou une recommandation supprimée puis recréée ne peut pas être lue par un ancien accusé.
Les conseils existants deviennent non lus lors de la migration 18 ; un envoi identique déjà lu reste lu.
Validation : 650 tests Python, parcours PC et parcours À écouter passent ; Chrome vérifie le vrai SSE entre
deux onglets, les lectures synchronisées et un nouveau conseiller. Noms anglais et textes i18n.
Publication vérifiée sur https://music2.foos.fr : HTTPS et conteneur sains, version publique 1.9.2,
212 fichiers identiques aux sources testées, ressources versionnées et libellé accessible conformes.
SQLite intègre au schéma 18, dix comptes et les marque-pages/conseils existants conservés.
Statut protégé par session et accusé protégé par CSRF ; aucun conseil de production envoyé pour les contrôles.
Sauvegarde cohérente : ../pimedia-backups/pre-1.9.2-20261110T221310Z/ ; image précédente : pimedia-web:pre-1.9.2-20261110t221310z.
Recharger la page (Cmd+Maj+R). Voir [À écouter](features/listen-later.md).


**Recherche d'artistes, 1.9.1 (10/11/2026, déployée et vérifiée)** :
la recherche ne dépend plus uniquement des tags ID3 pour les artistes. Elle complète `search3` avec la liste de
dossiers déjà utilisée par la barre, pour le compte connecté. « gurr » retrouve Gurriers même si les tags sont
absents des résultats ; comparaison commune des noms, exact puis début de nom avant les occurrences internes,
huit résultats et dédoublonnage des tags au profit du dossier. Les albums/titres restent ceux de `search3`.
Le choix manuel d'un départ de mix résout aussi la fiche vers son identifiant musical avant d'activer les actions.
Pas de collecte supplémentaire, scan ni migration. Le contrôle utilisant les jetons de comptes de production
a été refusé par la vérification automatique ; aucune recherche avec ces jetons n'a été exécutée.
Validation : régression reproduite avant correction sur le faux Subsonic ; **642 tests Python et parcours jsdom PC
passent dans Docker sans réseau externe**, dont recherche par saisie, lien vers la fiche et départ de mix résolu
avant toute construction. Neuf tests HTTP dédiés couvrent les variantes, le cache et les périmètres des comptes.
Déployée le 10/11/2026 sur `https://music2.foos.fr` à la demande utilisateur : conteneur sain, HTTPS 200,
version publique 1.9.1, JavaScript servi conforme et ressources munies de leur nouvelle empreinte de cache.
**212 fichiers applicatifs identiques aux sources testées** ; seuls quatre changent depuis la production 1.9.
SQLite intègre au schéma 17 inchangé, dix comptes conservés. Sauvegarde cohérente du code, de la configuration
et de SQLite : `../pimedia-backups/pre-1.9.1-20261110T212712Z/` ; image précédente : `pimedia-web:pre-1.9.1-20261110t212712z`.
Le test connecté de « gurr » est laissé à l’utilisateur, selon sa demande ; aucun jeton de compte utilisé
par les contrôles de déploiement. Recharger la page (Cmd+Maj+R) avant cet essai.
Détails et limites : [Bibliothèque](features/bibliotheque.md).

**Complément de la page Nouveautés (10/11/2026, déployé avec la 1.9)** : menu et page « Actualités » au pluriel.
La présentation du site décrit désormais les discographies et choix Discogs, les crédits et groupes liés, les
sélections et classements des labels avec versions YouTube, les marque-pages et recommandations de « À écouter ».
Les textes du créateur de mix, de l'accueil, de l'import Apple Music, de la file, des pochettes et des données
gardées sur le site sont complétés. Six parties, 34 cartes ; liens vers « À écouter ».
Décision utilisateur : complément éditorial sans nouvelle version, historique `versions.yaml` conservé tel quel.
Publié avec la version 1.9 ; textes publics et JavaScript servis vérifiés après le parcours PC de régression.

**À écouter et recommandations, 1.9 (déployée et vérifiée — 10/11/2026)** :
marque-pages personnels d'artistes et d'albums Subsonic/Discogs, recommandations séparées avec plusieurs
conseillers et destinataire explicite, deux sections sur une même page. Recherche, lecteur, favoris et
playlists existants réutilisés. Migration 17 : listen_later et recommendations.
Aucune synchronisation du catalogue ou rapprochement automatique. Nomenclature en anglais.
Validation locale : 633 tests Python, contrôles ciblés, parcours PC existant et nouveau parcours jsdom,
syntaxe JavaScript et contenu dans Chrome. Le complément Nouveautés a aussi passé 21 tests Python et le parcours PC.
Publication sur https://music2.foos.fr : conteneur sain, HTTPS 200, version publique 1.9,
212 fichiers de l'image identiques aux instantanés testés, nouveaux JavaScript/CSS versionnés et textes conformes.
Base intègre au schéma 17, deux nouvelles tables présentes et dix comptes conservés.
Sauvegarde cohérente du code, de la configuration et de SQLite :
../pimedia-backups/pre-1.9-20261110T202923Z/ depuis le projet distant ; image précédente conservée sous
pimedia-web:pre-1.9-20261110t202923z.
Le parcours interactif avec un compte réel reste à essayer ; aucun favori, marque-page ou conseil réel créé pour les contrôles.
Recharger la page (Cmd+Maj+R), puis ouvrir « À écouter ».
Détails, API, limites : [À écouter](features/listen-later.md).


Mis à jour le 10/11/2026. Lire aussi `docs/CONVENTIONS.md` (règles de code) et `README.md` (organisation).

**Cohérence des mix, 1.8.3 (déployée et vérifiée le 09/11/2026)** : le créateur depuis un artiste abandonne
le remplissage global et les titres proches dont la profondeur interne échappe au choix de la page. Titres
vérifiés par artiste ; albums locaux utilisés sans Last.fm, artistes absents ignorés. Le style renseigné du
départ sert de filtre par défaut ; les genres explicites le remplacent et les décennies filtrent toutes les
sources. Les favoris restent dans les artistes retenus, une sélection peut rester courte. Depuis une fiche,
le chargement de l’artiste précède écoute et sauvegarde ; son identifiant musical est conservé, au lieu de
celui du dossier. Une erreur ne produit plus un mix global silencieux.
Documentation et limites : `docs/features/mix-et-radios.md`. La bibliothèque réelle de Raz Fresco X n’a pas été
interrogée ; les régressions recréent les contaminations rock/métal avec un faux Subsonic.
Validation Docker sans réseau externe : **617 tests Python passent**, syntaxe JavaScript valide et cinq parcours
jsdom vérifiés. Lors du lancement global, le parcours PC a dépassé son attente initiale sur la connexion ; tous
ses cas de mix passaient déjà. Rejoué isolément, il passe entièrement, connexion comprise. Les quatre parcours
Pi passent lors du lancement global.
Publication vérifiée sur `music2.foos.fr` : **202 fichiers applicatifs identiques** aux sources testées,
conteneur sain, HTTPS 200, version publique 1.8.3, JavaScript/CSS et textes du mix conformes. Page sans cache et
JavaScript versionné, création de mix protégée. Base intègre, schéma 16 inchangé. Sauvegarde cohérente du code,
de la configuration et de SQLite ; image précédente conservée : `../pimedia-backups/pre-1.8.3-20261109T115922Z/`.
Recharger la page (Cmd+Maj+R) pour utiliser le nouveau créateur. Le cas réel de Raz Fresco X reste à vérifier.

**Arrêt du classement et précision YouTube, 1.8.2 (déployée et vérifiée)** : arrêt sur le dernier lot terminé sans attendre
le lot réseau suivant ; si aucun lot n’est encore disponible, le premier lot se termine avec un message explicite.
Sélection alimentée disque par disque, écoute et sauvegarde disponibles dès les premiers titres choisis ; choix
conservés pendant les ajouts. Sauvegarde limitée aux titres choisis lors de l’envoi, sans double enregistrement.
Réponses tardives ignorées, reprise au dernier offset confirmé, absence de disque classable expliquée. Bouton
d’arrêt présenté pendant le classement, après le chargement du catalogue. Cache public lu sans attendre un appel
réseau sans rapport en cours. Cas Zmatsutsi : orthographe Discogs « Endless Pavments », vidéo « Endless Pavements »
avec suffixe label/code catalogue ; parseur générique affiné à partir de ces métadonnées, sans artiste ou ID dans
le code applicatif. Cinq pistes réelles de Hooked Up retrouvées via Discogs, un choix chacune, cache confirmé.
La vidéo fournie par l’utilisateur est intitulée Hooked Up ; elle n’est pas attribuée arbitrairement à Endless Pavments.
Validation : **613 tests Python et cinq parcours jsdom passent** dans l’image reconstruite, parcours PC aussi validé
isolément. Attente du rechargement des artistes stabilisée dans le test ; playlist temporaire du nouveau parcours
supprimée après ses assertions. Chrome clair/sombre à 1 440, 390 et 320 px : aperçu focalisé, progression, écoute et
enregistrement disponibles avec le lot réseau et le disque suivants encore bloqués. Cache et cinq correspondances
réelles de Hooked Up vérifiés depuis Docker ; audio réel non vérifié. Sauvegarde cohérente et image de retour arrière :
`../pimedia-backups/pre-1.8.2-20261108T190313Z/`, schéma 16 inchangé. Documentation : `docs/features/decouverte-labels.md`.
Publication vérifiée : 202 fichiers applicatifs identiques aux sources testées, HTTPS sain, version publique 1.8.2,
JavaScript/CSS/textes conformes, routes protégées et base intègre au schéma 16. Cinq correspondances et cache de
Hooked Up confirmés aussi depuis le conteneur déployé, en base temporaire, sans compte réel ou playlist modifiés.
Recharger la page pour charger le nouveau comportement d’arrêt et les règles de recherche.

**Versions YouTube des labels, 1.8.1 (déployée et vérifiée)** : recherche automatique après la priorité bibliothèque,
liens des éditions Discogs vérifiés d’abord, trois correspondances au maximum. Service `YouTubeVersions`, règles
pures dans `youtube_matching.py`, transport `YouTubeSource` et cache/budgets existants réutilisés. Artiste, titre,
version et durée contrôlés ; une réponse vide est préférée aux vidéos sans rapport. Progression visible, cartes
de versions et choix explicite, file de deux recherches abandonnée lors d’un changement de sélection. Aucun
service payant ou classement par IA ajouté. Validation Docker : **608 tests Python et cinq parcours jsdom passent** ;
parcours PC repassé dans l’image finale après les finitions. Chrome clair/sombre à 1 440, 390 et 320 px : chargement
compact visible, choix explicite et cartes sans débordement. API réelle de l’édition Muslim Disco Club fournie :
une correspondance liée pour Djetelina, Sladjana et Kurosava ; aucune attribution arbitraire pour Osjecam. Deuxième
demande servie par le cache, sans nouvel appel YouTube. Sauvegarde cohérente code/configuration/SQLite et image de
retour arrière : `../pimedia-backups/pre-1.8.1-20261108T183148Z/`, base intègre au schéma 16, sans migration nouvelle.
Publication vérifiée sur le site : **202 fichiers applicatifs identiques**, HTTPS sain, version publique 1.8.1,
JavaScript/CSS/textes conformes et nouvelle route POST protégée. Historique 1.8.1 → 1.8 → 1.7.13 ; base intègre,
schéma 16 conservé. Sonde des quatre pistes relancée depuis le conteneur déployé : mêmes trois correspondances et
cache confirmé, aucun compte réel ni playlist modifiés. Écoute audio réelle non vérifiée. Recharger la page.

**Fiches artiste/album Discogs, 1.8 (08/11/2026, déployées et vérifiées)** : variante Raccourcis
validée puis intégrée. Bio sous le nom, visuel indépendant, boutons compacts avec symbole Discogs, accès visibles
en haut ; discographie et membres sous les albums, crédits et labels sous les pistes. Choix de fiche durable
par compte/bibliothèque/artiste canonique, migration 16. « Changer » et « Actualiser » distincts ; actualisation
ciblée et échecs conservant le choix. Providers séparés, nouveaux dépôts/services/entités et petits contrôleurs.
Validation finale Docker : **593 tests Python et les cinq parcours jsdom passent** sur l’image reconstruite.
Chrome clair/sombre à 1 440, 390 et 320 px, persistance après rechargement et actualisation vérifiées. API réelles :
Vitalic identifié, image et premier catalogue de 95 disques regroupés, choix conservé après expiration/réouverture
dans une base temporaire au schéma 16. Attente initiale du test PC stabilisée sans retirer ses assertions.
Décision utilisateur : lot Discogs en **1.8**, retouche des compteurs en **1.7.13** après la 1.7.12.
Le lot a d’abord été mis en ligne et vérifié sous le numéro provisoire 1.7.15 : 198 fichiers applicatifs identiques
aux sources testées, base intègre au schéma 16, ressources et routes protégées vérifiées. L’historique public est
réorganisé selon la décision finale ; les noms des sauvegardes réelles sont conservés. Sauvegarde préalable au schéma 15 :
`../pimedia-backups/pre-1.7.15-20261108T165103Z/`. Fiche et schémas :
`docs/features/decouverte-labels.md`. Navigation globale par labels toujours en brouillon pour plus tard.
Publication finale 1.8 vérifiée : **198 fichiers applicatifs identiques**, HTTPS sain, JavaScript/CSS/textes servis
conformes, nouvelles routes protégées, base intègre au schéma 16. Historique public complet identique au fichier
réorganisé, début **1.8 → 1.7.13 → 1.7.12**. Cinq tests de versions et parcours PC complet repassés sous 1.8,
dont un clic sur le raccourci avant la fin du chargement de l’association, sans redemander l’identité enregistrée.
Sonde API réelle relancée depuis le conteneur déployé, dans une base temporaire, sans compte réel utilisé.
Sauvegarde cohérente complémentaire avant renumérotation : `../pimedia-backups/pre-1.8-20261108T170300Z/`.
Recharger la page ; choisir la fiche une première fois permet sa reprise automatique aux prochaines visites.

**Stockage sans décimales, 1.7.13 (08/11/2026, déployée et vérifiée)** : à la demande utilisateur, le volume de la collection
est arrondi à l’entier pour tenir dans sa carte (« 1 479,69 Gio » devient « 1 480 Gio »). Le test existant est adapté.
Livraison isolée à partir des sources de la 1.7.12 déployée ; le lot Discogs préparé en parallèle et livré ensuite
en 1.8 n’était pas inclus dans cette retouche. Publiée initialement sous le numéro 1.7.14, cette entrée est
renumérotée 1.7.13 à la demande utilisateur ; les références d’exploitation et de sauvegarde ci-dessous sont historiques.
Vérification dans Chrome à 1440, 390 et 320 px : arrondi, zéro, absence de décimales et de débordement corrects.
Le parcours jsdom existant est adapté ; il n’a pas été rejoué pour cette retouche, Docker local étant arrêté.
Déploiement isolé : seuls le composant et la version changent parmi les 190 fichiers applicatifs. Version publique
1.7.14 et JavaScript servis vérifiés, santé interne et HTTPS saines. Sauvegarde de la 1.7.12 avant modification :
`../pimedia-backups/pre-1.7.14-20261108T162954Z/` ; image précédente conservée pour retour arrière.

**Collection en chiffres, 1.7.12 (08/11/2026, déployée et vérifiée)** : l’accueil affiche artistes, albums, chansons,
stockage et heures à partir de `MediaLibraryStatistics` / `LastScanned` dans le fichier de propriétés de Subsonic.
Décision utilisateur : réutiliser les compteurs existants, ne pas parcourir le catalogue par API et ne pas recalculer
à chaque visite ou sur expiration d’un cache. Lecture du fichier en lecture seule, dernier résultat valide conservé,
remplacement uniquement lorsque la date du scan change. Le bloc indique son périmètre global et la date ; masqué
sans source. Montage facultatif `compose.statistics.yaml` et `SUBSONIC_PROPERTIES_FILE`, aucune migration ni écriture
dans Subsonic. Les nouveaux chiffres sont visibles à la prochaine visite de l’accueil.
Source confirmée en lecture seule sur la production : 5 440 artistes, 11 843 albums, 137 315 chansons,
1 587 931 675 620 octets et 33 224 428 secondes ; même source dans la page d’aide de la distribution officielle 6.1.6.
Validation : 577 tests Python passent dans Docker ; quatre parcours Pi passent. Le parcours PC passe isolément
après trois échecs initiaux sur les attentes de connexion dans le lancement complet (instabilité déjà signalée en
1.7.11) ; les quatre contrôles du nouveau bloc passent dans les deux passages. Après la dernière protection contre
une ligne numérique tronquée, les dix tests ciblés passent sur une image reconstruite. Configuration Compose
validée ; rendu Chrome contrôlé à 1440, 390 et 320 px, sans débordement des chiffres, thèmes sombre et clair.
Tests et intégration : `docs/features/bibliotheque.md`.
Déployée sur `https://music2.foos.fr` le 08/11/2026 : sauvegarde cohérente code/configuration/SQLite et image de
retour arrière dans `../pimedia-backups/pre-1.7.12-20261108T161734Z/` depuis le projet distant. Les 190 fichiers
applicatifs correspondent exactement à l’image testée puis au conteneur déployé. Santé interne et HTTPS, version
publique 1.7.12, ressources et textes servis, routes protégées vérifiés ; dix comptes conservés, SQLite intègre,
schéma 15 inchangé. Montage `subsonic.properties` activé en lecture seule dans le `.env` du serveur, configuration
existante conservée ; Subsonic n’a pas été redémarré. Les valeurs du dernier scan sont bien lues : 5 441 artistes,
11 844 albums, 137 323 chansons, 1 588 511 745 837 octets et 33 227 128 secondes. Aucun scan déclenché pour ce déploiement.
Un rechargement forcé du navigateur charge les nouveaux fichiers. Le parcours connecté en production reste à regarder.

**Navigation par labels : brouillon pour plus tard (08/11/2026)**. À la demande utilisateur, conserver la conception
d’un index persistant des labels et des relations albums/labels, avec pages de label (logo, histoire sourcée),
albums locaux, catalogue complémentaire et choix YouTube mémorisés. Fiche : `docs/features/navigation-labels.md`.
Non implémenté ; aucun scan, migration ou déploiement demandé pour ce brouillon.

**Fiches artiste/album Discogs : conception historique du 08/11/2026, réalisée en 1.8 ci-dessus**. Mémoriser durablement
le choix d’identité Discogs de l’artiste local ; proposer « Changer » séparément d’« Actualiser ». Accès compacts
visibles dès le haut des fiches, contenu Discogs sous les albums de l’artiste ou les pistes de l’album, chargé
automatiquement une fois l’identité connue. Comparer ancres et onglets dans une maquette avant réalisation.
État actuel et conception : `docs/features/decouverte-labels.md`. La maquette seule ne modifiait pas le site.
Affinements de la maquette : bio sous le nom, photo à côté, boutons compacts et symbole Discogs. Modèle proposé
documenté : `artist_discogs_links` (compte, bibliothèque, artiste local, identité Discogs, date du choix), séparé
du cache public existant ; schémas de données et d’application dans la fiche. Photos et bio à charger séparément :
le code antérieur ne reprenait que les visuels Wikipédia et conditionnait leur affichage à un texte de biographie.

**Correctif Sub Pop, 1.7.11 (08/11/2026, déployé et vérifié)** : la fiche sélectionnée était Sub Pop Records, société
de droits/licences, distincte du label Sub Pop selon les indications et liens Discogs. Le filtre d’édition rejetait
alors les disques et présentait une sélection « 0 sur 0 ». La page explique désormais cette distinction et propose
le label explicitement lié ; le serveur arrête l’analyse d’une fiche réservée à une société avant de parcourir
son catalogue. Aucun nom/identifiant Sub Pop dans le code applicatif, pas de fusion automatique des identités.
Projection d’identité versionnée pour les caches déjà présents ; profil brut et contacts non conservés.
Sélection vide expliquée sans compteur ni boutons inutilisables ; ancien aperçu retiré au lancement d’une analyse.
Validation Docker : 567 tests Python passent et les cinq parcours jsdom sont validés ; le PC a été rejoué isolément
après trois échecs sur les contrôles initiaux de connexion. Contrôle Chrome du passage société → label et des pistes.
API réelles : marqueur de société et lien Sub Pop vérifiés, catalogue du label préchargé (111 pages, 11 098 entrées).
Un tirage réel de quinze disques propose 28 pistes.
Déployé en production le 08/11/2026 : HTTPS sain, version publique 1.7.11, 187 fichiers applicatifs identiques aux
sources testées, ressources servies et routes protégées vérifiées, base intègre au schéma 15. Distinction société/label
et sélection Sub Pop de 28 pistes confirmées depuis le conteneur déployé, sans compte de bibliothèque utilisé.
Sauvegarde préalable code/configuration/base/image : `../pimedia-backups/pre-1.7.11-20261108T015242Z/` depuis le
projet distant. Les cookies de session sont conservés ; recharger la page pour charger le nouvel écran.
Fiche : `docs/features/decouverte-labels.md`.

**Découverte des labels et Discogs, 1.7.10 (08/11/2026, déployé et vérifié)** : deux modes depuis un label identifié :
tirage varié sans popularité (artistes, disques, décennies, sorties sans note incluses) et Top sourcé (note/votes de
l’édition Discogs représentative, ou auditeurs/écoutes de l’album Last.fm). Rééditions regroupées avant sélection ;
analyse progressive avec périmètre visible. Recherche locale prioritaire, choix explicite des versions YouTube,
écoute et enregistrement par les playlists mixtes existantes.
Discogs est proposé en premier sur les pages album et artiste : crédits d’une édition choisie, labels et musiciens
cliquables, membres/groupes, discographies illustrées avec correspondances locales. MusicBrainz reste en complément.
Services Discogs et Last.fm séparés, services de catalogue/crédits/sélection distincts, petits contrôleurs HTTP ;
SQL dans le dépôt. `DISCOGS_API_KEY` branchée à `WebConfig` et au conteneur, jeton strictement serveur.
Métadonnées publiques projetées, cache 24 h, aucune disponibilité de bibliothèque partagée ; schéma 15 inchangé.
API réelles vérifiées depuis Docker : Clivage Music (19 disques regroupés), notes/votes, découverte, premier lot du
Top puis classement complet des 19 disques, associations de sociétés écartées ; statistiques Last.fm et discographie
de Vitalic. Comparaison réelle : mêmes sept membres de Kyuss ; douze groupes
de Josh Homme chez Discogs contre neuf chez MusicBrainz, avec des liens propres à chacune. L’édition comparée de
« Dissidænce Episode 2 » a sept crédits chez Discogs et aucune relation de crédit chez MusicBrainz.
Validation finale : **562 tests Python et les cinq parcours jsdom passent** dans l’image reconstruite. Contrôle Chrome
en thèmes clair/sombre, nouveaux blocs sans débordement à 390 px. La barre du haut et le lecteur PC existants restent
peu adaptés à cette largeur ; pas de changement de ces composants dans cette livraison.
**Déployé sur le site de production le 08/11/2026** avec `deploy/pc/push.sh` : HTTPS et conteneur sains, version
publique 1.7.10, nouvelles routes authentifiées (401 sans session), JavaScript/CSS/textes servis vérifiés. Les 187
fichiers applicatifs du conteneur correspondent aux sources testées ; base au schéma 15, `quick_check` OK.
Clé Discogs ajoutée au `.env` serveur par SSH, sans affichage ; Last.fm déjà configuré. Depuis la production :
catalogue et notes Discogs, premier lot du Top, compteurs Last.fm, discographie et recherche des crédits validés.
Sauvegarde préalable du code, du `.env`, d’une copie cohérente de SQLite et de l’image précédente :
`../pimedia-backups/pre-1.7.10-20261107T233314Z/` depuis le dossier du projet distant (horodatage UTC).
Fiche complète : `docs/features/decouverte-labels.md`. Écoute audio YouTube réelle et parcours dans un navigateur
connecté à la bibliothèque de production encore à essayer.

**Crédits complets des albums corrigés, préparés en 1.7.9 et déployés avec la 1.7.10** : le filtre MusicBrainz
accepte aussi le crédit complet et ses noms d’usage (« Fennesz + Sakamoto », « Prodigy »), en conservant les
noms canoniques et le choix explicite de l’édition. Trois tests de régression ajoutés ; les 44 tests d’exploration
et d’architecture passent sur les sources refactorisées. Fiche : `docs/features/labels-et-collaborations.md`.

**Mutualisation des comparaisons de noms, préparée en 1.7.9 et déployée avec la 1.7.10** : une seule fonction
`shared.text.normalize` pour l’exploration MusicBrainz, les dossiers Pi et web, les pochettes, les genres et les
raccourcis. Casse, accents, ligatures et ponctuation suivent les mêmes règles ; les textes d’origine sont conservés.
`MusicMetadata` devient `MusicBrainzMetadata` pour nommer sa source. SQL conservé dans le dépôt et entités
MusicBrainz documentées. Les options des mix sont fournies par le serveur à la page ; les parcours utilisent la
profondeur demandée, et les décennies vont jusqu’à la décennie courante. `AGENTS.md` reprend les conventions et
demande explicitement une review de la structure et des duplications, en plus des bugs. Vérification : 531 tests
Python et le parcours jsdom PC passent dans l’image de test locale, sans réseau externe ; 86 tests d’exploration
et de mix repassent après les dernières corrections, ainsi que 56 tests unitaires et d’architecture. Aucun déploiement effectué.

**Revue de portabilité du 07/11/2026** : recherche de chemins personnels, hôtes privés et identifiants d'exemple dans
les 139 fichiers Python et 62 JavaScript de `src/`, plus les scripts de déploiement. Aucun autre chemin personnel
utilisé à l'exécution trouvé dans l'application. Ancien chemin local retiré de `REPRISE.md`, exemple de compte rendu
générique dans l'aide CLI. Règle étendue aux diagnostics temporaires dans `CONVENTIONS.md` ; contrôle des chaînes
Python exécutables ajouté à `tests/test_architecture.py` (documentation et commentaires exclus). Les chemins du
conteneur Pi correspondent à son utilisateur créé par l'image ; les paramètres de l'installation viennent de la
configuration. Les adresses historiques de production dans les notes d'exploitation sont conservées pour la reprise.
Reprise avec une autre IA : `docs/REPRISE.md` (message à coller, pièges à connaître).
**Ce que fait chaque fonctionnalité, ce qui existe et ce qui manque : `docs/features/`** (site web et Pi) ; **qui est partagé et ce que chaque déploiement embarque : `docs/architecture/`**. À tenir à jour avec le code.

**Pour reprendre** : le projet est dans `sub2/sources/` (le `.env`, caché par le Finder, est à côté de
`compose.yaml`). Tests : `docker compose run --rm tests` (tout, y compris jsdom). Site de test :
`docker compose up -d web` → https://pimedia.localhost (Traefik local, Subsonic = https://music.foos.fr, clé YouTube
réglée, Jamendo vide). Démo : `docker compose --profile demo up -d demo` → https://demo.pimedia.localhost.
Dépôt GitHub cloné sur ce poste le 07/11/2026. **Déployer** (site et Pi) : `docs/DEPLOIEMENT.md` (`bash deploy/pc/push.sh`, `bash deploy/pi/push.sh`).
**En production depuis le 27/10/2026 : https://music2.foos.fr** (music.foos.fr reste le Subsonic d'origine). Serveur :
compte `subsonic` (sans sudo ; clé SSH du Mac `~/.ssh/pimedia_ed25519`, accès rétabli et vérifié le 07/11/2026), code dans
`/home/subsonic/pimedia`, conteneur `pimedia-web-1` sur le réseau `subsonic_default` (compose de Subsonic à la racine du
home, conteneur `subsonic`), `SUBSONIC_URL=http://subsonic:4040`, vhost `/etc/apache2/sites-available/music2.foos.fr.conf`
(l'ancien vhost Navidrome `music2.foos.fr-le-ssl.conf` est désactivé, Navidrome arrêté). Mise à jour :
`bash deploy/pc/push.sh subsonic@music.foos.fr`.
**Prochaine étape conseillée** : la suite du point 3 (marque-pages, radios Internet), puis la mise en route de l'envoi de fichiers sur le serveur (groupe, `.env`, voir
`docs/DEPLOIEMENT.md`). Faits le 25/10/2026 : page Mix, radio et artistes similaires, file d'attente, playlists (dont
communautaires, glisser-déposer), scrobble et « Écouté en ce moment », envoi de fichiers dans Incoming.
**Incoming débloqué le 27/10/2026** : 551 dossiers d'artistes appartenaient à `root`, le rattrapage échouait sur le
premier (« Permission denied ») et abandonnait tout le passage. Rendus au site (`sudo find <MUSIC_DIR> -mindepth 1
-maxdepth 1 -type d ! -user 1001 -exec chown 1001:100 {} +`) ; ~85 albums rangés à 13h37, scan vérifié. Reste du code
à corriger : un album bloqué ne devrait pas arrêter les autres (Tâche 1 du plan ci-dessous).
**À venir : page « Rangement »** (administrateurs) : ce qui a été rangé et où, ce qui reste dans Incoming et pourquoi,
groupes en double à réunir (orthographe proche ou MusicBrainz, ex. `Osees` / `Thee Oh Sees` / `Thee Oh Sees _ Osees`).
Conception validée : `docs/superpowers/specs/2026-10-27-page-rangement-design.md` ; plan de construction prêt, à lancer
tel quel : `docs/superpowers/plans/2026-10-27-page-rangement.md`.
**Veille de l'ampli (Pi), corrigé le 25/10/2026, À VÉRIFIER SUR LE PI** : mpv (lecture haute fidélité) gardait son flux
ouvert vers le DAC en pause (« corked » mais ouvert) → l'ampli croyait qu'on écoutait. Maintenant `HifiPlayer.release_if_idle`
arrête mpv après 30 s de pause ou de file vide et le relance à la reprise (même seconde, même volume, titre suivant
re-préchargé). Mesure sur le Pi : `python3 diagnostic-ampli.py` (voir `docs/features/pi/veille-ampli-meteo.md`).
**Attention** : `docker compose run --rm tests` ne reconstruit pas l'image (le code y est copié) : lancer
`docker compose build tests` avant, sinon on teste l'ancien code. Idem `docker compose up -d --build web`.
Chemins de code ci-dessous : relatifs à `src/`.

**Profondeur des mix ajoutée le 07/11/2026 (1.7.8, déployée et vérifiée)** : le créateur du site propose 1, 2, 3 ou
4 niveaux d'artistes proches, au lieu du bouton 1 ou 4. Le choix (4 par défaut) fixe la profondeur maximale depuis
l'artiste de départ, pour l'écoute et la playlist. Le serveur valide `depth` ; les anciennes pages envoyant `wide`
restent compatibles. Radio de l'artiste et édition Pi inchangées. Fiche : `docs/features/mix-et-radios.md`.
Validation Docker finale avant déploiement : **525 tests Python et les cinq parcours jsdom passent** dans l'image
reconstruite. La chaîne de cinq artistes vérifie l'arrêt aux quatre profondeurs ; la page vérifie les choix exclusifs,
le lancement à 2 niveaux et la playlist à 3 niveaux.
Déployée sur `music2.foos.fr` le 07/11/2026 : copie ciblée des quatre fichiers applicatifs, reconstruction du seul
conteneur web. HTTPS sain, version publique 1.7.8, libellés disponibles et JavaScript servi identique au fichier testé.
Les quatre fichiers dans le conteneur sont identiques aux sources testées ; base au schéma 15, intégrité OK.
Sauvegarde préalable des quatre fichiers, de la base SQLite et de la référence de l'image 1.7.7 :
`/home/subsonic/pimedia-backups/pre-1.7.8-20261107T221218Z/`. Le parcours connecté contre le vrai Last.fm reste à essayer.

**Essai API Discogs du 07/11/2026** : `DISCOGS_API_KEY` présente dans le `.env` local et reconnue comme jeton
personnel. Treize lectures HTTP 200 : authentification, recherche et catalogues d'On-U Sound, Dischord Records et
Clivage Music, puis une édition de chaque label. Notes / nombre de votes, pistes et liens YouTube récupérés ; aucune
lecture vidéo ni sélection « Top » validée. Jeton et identité non affichés. État historique de cet essai :
l’intégration est désormais déployée et vérifiée en 1.7.10.
Détails et points à traiter (regroupement des éditions, conservation des données) : `docs/features/bibliotheque.md`.

**Lecture au survol des pochettes ajoutée le 07/11/2026 (1.7.7, déployée et vérifiée)** : petite flèche en haut
à gauche des pochettes, reprise de l'icône et du bouton lecture existants. Depuis l'accueil et les autres grilles,
la flèche lance l'album sans navigation ; le reste de la carte ouvre la fiche. Fiche : `docs/features/bibliotheque.md`.
Validation : 519 tests Python passent ; les cinq parcours jsdom passent, avec reprises isolées du PC (attente initiale
de connexion) et de la haute fidélité Pi (démarrage). Les contrôles des deux nouvelles fonctions passent.
Déployée sur `music2.foos.fr` : copie ciblée des cinq fichiers d'interface, reconstruction du seul conteneur web.
Santé HTTPS 200, version publique 1.7.7, JavaScript et CSS servis identiques aux sources testées, conteneur sain.
Aucun changement de schéma. Sauvegarde des cinq fichiers précédents et référence de l'image 1.7.5 :
`/home/subsonic/pimedia-backups/pre-1.7.7-20261107T181450Z/`. Le parcours connecté sur le vrai serveur reste à regarder.

**Radio de ce titre ajoutée le 07/11/2026 (1.7.6, livrée avec la 1.7.7)** : bouton d'ondes dans les listes de
morceaux Subsonic, avec le droit `stream`. Réutilise `/api/radio/song` : morceau choisi en premier, titres proches,
repli même style puis hasard si Last.fm ne propose rien. Titres d'ailleurs exclus. Bouton occupé pendant le chargement ;
en cas d'erreur, file et lecture conservées. Fiche : `docs/features/mix-et-radios.md`.
Validation Docker sur les sources courantes : 9 tests ciblés (radios et versions), syntaxe JavaScript et parcours
jsdom PC complet passent. Aucun changement de base ; livrée en production avec la 1.7.7, vérifiée ci-dessus.

**Accents et ponctuation des envois corrigés le 07/11/2026 (1.7.5)** : deux problèmes à l'extraction des ZIP :
le nettoyage remplaçait `$` par `_` (`Mon$rock` → `Mon_rock`) et un nom UTF-8 sans marqueur était lu en CP437
(`Na\u0301n Fiero` → `Na╠ün Fiero` → `Na_ün Fiero`). Les noms UTF-8 non déclarés sont maintenant reconnus quand
ils sont valides ; les anciens ZIP CP437, les accents combinés et la ponctuation sont conservés. La normalisation
reste réservée aux comparaisons de `layout.py`, qui garde le nom du dossier existant. Régression reproduite avec
l'ancien code ; 58 tests d'envoi, rangement et versions et le parcours jsdom PC passent dans Docker. Correctif
déployé sur `music2.foos.fr` (1.7.5), santé HTTP 200 et ZIP problématique vérifié dans un dossier temporaire du
conteneur de production. Dossier existant renommé en `BigDaddyChop, Mon$rock & Nán Fiero` : ses deux albums
(`Medalla`, `Medalla II`) et leurs 22 fichiers sont conservés à l'identique ; scan Subsonic lancé. Sauvegarde du
code précédent : `/home/subsonic/pimedia-accents-backup-20261107-4ljjbgz5` ; manifeste du renommage dans
`/data/accents-repair-20261107-4ljjbgz5.json`. Fiche : `docs/features/envoi-fichiers.md`.

## Contexte
- Raspberry Pi 4, écran tactile 7" 800×480, ampli Advance Paris A10 Classic en USB (son DAC).
- **Serveur de musique : Subsonic d'origine** (pas Navidrome). Tout passe par l'API Subsonic standard (1.16.1).
- Last.fm :
  - **global** = réglage du serveur Subsonic : alimente `getSimilarSongs2`, `getTopSongs`, `getArtistInfo2`
    (radios, artistes proches, titres populaires) ;
  - **par personne** = chacun relie son compte dans Subsonic, « Paramètres → Personnel » ; le site doit
    seulement envoyer `scrobble`.
- YouTube : **pas de clé par personne** (la clé ne change ni les résultats ni la pub : seulement le quota).
  Lecture YouTube : lecteur officiel ou fenêtre youtube.com. Tout les moyens sont bon pour réduire le quota **Recherche** : un moyen non officiel, sans clé ni quota (ex. ytmusicapi), est autorisé (décision du 27/10/2026).
- L'utilisateur veut : peu de questions, avancer seul, honnêteté sur ce qui n'est pas fait ou pas vérifié.

## Deux éditions, séparées (aucun `if serveur`)
1. **Pi** (un utilisateur) : `subsonic-web.py`, `pimedia/server/`, `pimedia/menu/` (menu Tk), `web/`.
   Déploiement : `python3 deploy/pi/build_archive.py` → `dist/` (install.sh pour un Pi neuf, deploy.sh pour les
   mises à jour, migration.sh). L'archive Pi n'embarque pas l'édition PC.
2. **PC** (plusieurs utilisateurs, souris/clavier) : `pimedia-web.py`, `pimedia/webapp/`, `web-pc/`.
   Données : `~/.local/share/pimedia-web/` (`.env` avec SUBSONIC_URL, `webapp.db`). Service, Apache et nginx : `deploy/pc/`.
   **Docker** (`compose.yaml`, images dans `docker/`) : `docker compose up -d web` (site sur 127.0.0.1:8200,
   données dans le volume `web-data`), `docker compose run --rm tests` (tous les tests),
   `docker compose --profile demo up demo` (bibliothèque inventée, port 8300).
   **Édition Pi en conteneur, pour l'essayer sur le Mac** (26/10/2026) : `docker compose --profile pi up -d --build pi`
   (vrai Subsonic : `SUBSONIC_URL`, `PI_SUBSONIC_USER`/`PI_SUBSONIC_PASS` du `.env`, port 8399, `https://pi.pimedia.localhost`)
   ou `--profile pi-demo up -d --build pi-demo` (faux Subsonic, port 8499). Image `docker/pi/` : l'archive de
   `build_archive.py` installée par `deploy.sh` au démarrage (mode `PI_MEDIA_SERVICE=direct`, sans systemd), vrai mpv
   avec sortie nulle ; `bash docker/pi/push.sh` répète une mise à jour. Page web seulement : ni menu Tk, ni écran,
   ni son, ni Bluetooth, ni AirPlay, ni bouton Éteindre. Détails : `docs/DEPLOIEMENT.md`.
   Réglages par machine dans `.env` (modèle `.env.example`). Test local : Traefik (`compose.traefik.yaml`,
   `https://pimedia.localhost`, vérifié : page, connexion, salon en temps réel). Prod : Apache → 127.0.0.1:port
   (`deploy/pc/apache-exemple.conf`, non vérifié).

## Édition PC : fait et testé
- Connexion avec son compte Subsonic (jeton seulement), sessions, CSRF, limitation des essais.
- Barre des artistes à gauche : fixe / au survol / masquée, largeur, filtre, index, artiste en cours.
- Accueil (derniers albums, mieux notés du site, albums commentés), artiste, album, recherche, favoris.
- Étoiles 1–5 **lues et écrites dans Subsonic** (rien en base locale, migration 3) : comme l'exige Subsonic d'origine,
  la note va sur le **dossier** de l'album (`parent` de ses titres ; album en plusieurs disques : dossier parent),
  `userRating` / `averageRating` (moyenne de tous les comptes) lus par `getMusicDirectory`. Mieux notés :
  `getAlbumList type=highest`. Cœur (`star`/`unstar`).
- Écoutes « Écouté N fois » (`playCount` des albums ID3), accueil « Les plus écoutés » (`frequent`).
- Page **Albums** (`/api/albums`, `/api/genres`) : Nouveaux (en premier, voulu), Plus écoutés, Mieux notés, Écoutés
  récemment, Au hasard, Favoris, Par décennie, Par genre (pastilles avec nombre d'albums), De A à Z ; 40 par page,
  « Afficher plus ». Présentation provisoire (pastilles) : à refaire plus tard en s'inspirant de Spotify/Deezer.
- **Droits Subsonic** (25/10/2026) : lus par `getUser` à la connexion puis à chaque page (`/api/me`, 0,1 s) ; un
  changement fait dans Subsonic s'applique sans se reconnecter, et si Subsonic ne répond pas on garde les derniers
  connus (colonne `users.roles`, migration 6). Appliqués côté serveur (`Guard.reader/writer(..., right=)`, erreur
  `auth.missing_right`) et côté page (`App.can`). `stream` : écouter ; `download` : **télécharger** un album (zip fait
  par Subsonic du dossier de l'album, `/api/download?album=`, bouton sur la page album) ou un titre
  (`/api/download?song=`, icône au survol de chaque ligne des listes de titres) ; `playlist` : créer/modifier/supprimer des playlists ;
  `comment` : étoiles et commentaires d'album (le salon reste libre) ; `admin` : modérer le salon. Réglages : liste
  « Votre compte Subsonic permet de… ». Réservés aux fonctions à venir : `coverArt` (pochettes et **tags ID3**),
  `upload` (envoi de fichiers), `share` (liens publics `createShare`), `settings` (lien Last.fm). Sans objet sur le
  site : `podcast`, `jukebox`, `videoConversion`. Vérifié sur music.foos.fr : droits lus, zip d'album reçu
  (« Made In Chicago.zip »). Pas vérifié : un compte non administrateur réel, un gros album complet derrière Traefik.
- Le chat (salon, commentaires) reste dans la base du site (`webapp.db`), volontairement séparé du chat Subsonic.
- Salon global temps réel (SSE) : réponses, @mentions + notification, réactions, modification, suppression
  (auteur ou admin Subsonic), partage d'album, recherche, mentions, non-lus, « écrit… », en ligne, anti-spam.
- Commentaires sous chaque album. Lecteur (file, raccourcis clavier), réglages par utilisateur, icônes SVG.
- Tests : `python3 -m unittest discover -s tests -t .` (458 OK le 27/10/2026 dans Docker, PyYAML requis : `requirements.txt`) ;
  tous les parcours jsdom : `python3 -m tests.run_e2e [chemin/jsdom]` (5 parcours OK, dont 52 contrôles PC).
  Le plus simple : `docker compose run --rm tests` (tout, avec Node et jsdom). `e2e_hifi` et `e2e_queue` (Pi)
  échouaient souvent sur machine chargée (« queue is not defined ») : ils attendaient 2,5 s fixes que la page soit
  chargée ; ils attendent maintenant qu'elle soit prête (15 s au plus).
- Captures : `python3 -m tests.demo_webapp` (bibliothèque inventée) + Playwright/Chromium.

## Édition PC : routes serveur (25/10/2026) — certaines ont maintenant leur interface (voir `docs/features/`)
Routes testées (unitaires + HTTP, `tests/test_webapp_music.py`, faux Subsonic complet `FakeSubsonicFull`) :
- Mix : `GET /api/mix?kind=random|favorites|discover|newest[&genre=]`, `GET /api/radio/song?id=`,
  `GET /api/radio/artist?id=&name=` (4 niveaux d'artistes proches), `GET /api/mix/genres` (styles regroupés),
  `POST /api/mix/build` (styles, décennies, artiste de départ, favoris, chronologique, nom proposé).
  Sans Last.fm : radio d'un titre → même style ; radio d'artiste → erreur `mix.no_lastfm`.
- Playlists : `GET /api/playlists`, `GET /api/playlist?id=`, `POST /api/playlist/create|add|remove|rename|delete|community`
  (`create` accepte `community`, `add` renvoie `{added}`). Communautaires : tables `community_playlists` et
  `playlist_additions` (migration 7).
- Pochette d'un album : `GET /api/cover/status`, `GET /api/cover/search`, `POST /api/cover/save` (droit `upload`, `LASTFM_API_KEY`, voir `features/pochettes.md`).
- Envoi de fichiers : `GET /api/upload/status`, `POST /api/upload?name=` (corps brut), `POST /api/upload/finish` (droit `upload`).
- Écoute : `POST /api/scrobble {id, submission}`, `GET /api/now-playing`, `GET /api/bookmarks`,
  `POST /api/bookmark/save|delete`, `GET /api/play-queue`, `POST /api/play-queue/save`.
- Photos : `GET /api/avatar?user=` (site, sinon Subsonic, sinon 404 → initiale), `GET /api/avatars`,
  `POST /api/avatar/upload` (300 Ko, PNG/JPEG/WebP vérifiés aux octets), `POST /api/avatar/delete`.
- Radios Internet : `GET /api/radios`, `GET /api/radios/stream?id=` (seules les adresses de la liste Subsonic).
- Titres populaires d'un artiste : `GET /api/artist/top?name=` (getTopSongs, Last.fm), gardé une heure ; section
  « Titres populaires » sur la page artiste (5, puis 10), chargée après la page. **Seule partie avec interface.**
- **Paroles** (avec interface) : `GET /api/lyrics?artist=&title=&album=&duration=`, directement LRCLIB (synchronisées)
  puis lyrics.ovh, **sans Subsonic** (décision : l'externe non essentiel ne passe pas par Subsonic), gardées un jour.
  Bouton micro du lecteur ou touche L : panneau à droite à la place du salon, ligne chantée en surbrillance au
  milieu ; paroles simples : défilement estimé. Vérifié contre le vrai LRCLIB depuis le conteneur.
- **Musique d'ailleurs** (avec interface) : Jamendo et YouTube, UNE clé par source dans le `.env` du site
  (`EXT_JAMENDO_ID`, `EXT_YOUTUBE_KEY`, `EXT_YOUTUBE_REGION`, passés par `compose.yaml`), jamais renvoyées à la page.
  Service du Pi réutilisé (`server/extmusic/`) : chaînes « Topic » d'abord, vidéos lisibles vérifiées, versions
  originales seulement. Routes : `GET /api/ext/status`, `GET /api/ext/search?src=&q=`, `POST /api/ext/alternative`,
  `POST /api/ext/unplayable`, `POST /api/ext/played`. Quota YouTube partagé (~100 recherches/jour) : YouTube
  proposé **seulement si Subsonic n'a ni titre ni album** pour la recherche, et seulement sur clic ; recherches
  gardées **90 jours en base** (migration 4, `ext_searches`), partagées entre tous ; 120 par personne et par heure.
  **Recherche par YouTube Music** (`ytmusicapi`, 27/10/2026) : sans quota ; repli sur l'API officielle limité à 20
  recherches par heure pour tout le site. Voir `docs/features/musique-ailleurs.md`.
- **Importer une playlist** (27/10/2026, demandé) : page `#/import` + guide `#/import/guide` ; lien Deezer, CSV
  (Spotify par Exportify, TuneMyMusic…), XML Apple Music, M3U, texte ; rapprochement par le texte avec `search3`
  (pas d'ISRC), introuvables cherchés sur YouTube Music, aperçu avec un choix par titre, playlist mixte créée dans
  l'ordre. **Pas essayé contre le vrai Subsonic.** Voir `docs/features/import-playlists.md`.
- **1.3 (28/10/2026)** : choix de la playlist dans un export de toute la bibliothèque Apple ; vidéos YouTube refusées
  (code 150, labels) : une seule autre version par titre, plus de cascade d'échecs. Voir les deux fiches.
  Vidéos (`youtube_videos`) : refus gardé avec le code d'erreur YouTube, réessayée après 90 jours ; lectures
  réussies comptées → en tête des résultats avec « déjà lue ici », et une lecture efface un refus. Page : section « Ailleurs » de la recherche ;
  moteur de lecture `engine.js` (audio ou lecteur officiel YouTube dans une petite fenêtre vidéo visible) ; vidéo
  refusée → autre version sûre, sinon « Ouvrir sur YouTube » et titre suivant. Politique de sécurité de la page :
  seuls youtube.com (script, cadre), i.ytimg.com et *.jamendo.com sont ajoutés. **Pas vérifié avec de vraies clés.**
- Erreurs précises renvoyées comme clés de texte (`mix.*`, `playlist.*`, `avatar.*`).
- Défauts trouvés par ces tests et corrigés : réponse Subsonic vide `{}` (sans Last.fm) transformée en titre
  fantôme « ? » ; styles sans titre proposés ; « jamais deux titres du même artiste à la suite » pas garanti.

## Reste à faire (dans l'ordre)
1. ~~Brancher les modules~~ et 2. ~~faux Subsonic complet + tests~~ : faits le 25/10/2026 (voir plus haut).
~~Barre des artistes vide~~ : **réglé le 25/10/2026**. Cause : `getArtists` met **34 s** à répondre sur
music.foos.fr (5 424 artistes ; calcul côté Subsonic, premier octet à 34 s, `getIndexes` 19 s, les autres appels
< 2 s) et le client coupait à 20 s → `subsonic.unreachable`. Correctif : délai par appel (`SLOW_TIMEOUT` = 180 s,
`pimedia/webapp/subsonic.py`) et **une liste pour tout le site** (`pimedia/webapp/artist_index.py`, table
`artist_indexes`, migration 5) : calculée une fois, gardée en base (survit aux redémarrages), servie à tous tout de
suite. Au démarrage du site puis toutes les 10 min, comparaison avec Subsonic par `getIndexes ifModifiedSince`
(0,1 s si rien n'a changé) ; après un scan, recalcul (34 s, en arrière-plan) et, si la liste a changé, événement
temps réel `artists` : les barres ouvertes se rechargent sans attente. Préchauffage avec un compte connu
(administrateur d'abord). Une liste par ensemble de dossiers de musique visibles (`getMusicFolders`) : un compte
limité par Subsonic à certains dossiers a la sienne. **Vérifié sur music.foos.fr** : liste prête 34 s après le
démarrage, pas recalculée au redémarrage suivant. Barre : « Chargement des artistes… » (seulement si rien en base),
« Réessayer » en cas d'échec, affichage paresseux par lettre (`IntersectionObserver`, tout d'un coup sans lui).
L'API Subsonic standard n'a pas de pagination pour `getArtists` : impossible de la charger par morceaux chez Subsonic.
(Depuis le 26/10/2026 la barre suit les dossiers : `getIndexes`, 19 s, même principe de liste gardée en base.)
3. Interface. **Fait le 25/10/2026** : page **Mix** (`#/mix`, `web-pc/static/js/mix.js`, lien dans le menu) avec
   4 mix rapides (au hasard, favoris, découverte, nouveautés) et le **créateur de mix du Pi** (artiste de départ
   cherché ou venu de la page artiste `#/mix/<id>`, styles avec nombre de titres, époques, 30/60/100 titres, favoris
   d'abord, proches de proches, chronologique ; « Lancer le mix », « Enregistrer en playlist » si droit `playlist`) ;
   page artiste : **« Radio de l'artiste »**, « Créer un mix à partir de cet artiste », section **« Artistes
   similaires »** (`GET /api/artist/similar?id=`, getArtistInfo2, gardé une heure, vide sans Last.fm). Vérifié sur
   music.foos.fr côté serveur (15 similaires de Depeche Mode en 0,7 s, 1 124 styles, mix de 30 titres en 5,6 s,
   radio de 100 titres en 6,1 s) ; interface testée dans jsdom seulement.
   **Playlists, fait le 25/10/2026** : onglets **Artistes | Playlists** dans la barre de gauche (`web-pc/static/js/playlists.js`,
   réglage `sidebar_tab`) ; sections Mes playlists / Communautaires / Partagées ; page `#/playlist/<id>` ; création
   (« + », nom + case Communautaire) ; **glisser-déposer** (`dnd.js`) d'un titre ou d'un album sur une playlist
   (ou sur « + » pour en créer une), l'onglet Playlists s'ouvre tout seul pendant le glissé ; bouton « Ajouter à une
   playlist » au survol de chaque titre. **Communautaire** : playlist Subsonic de son créateur, rendue publique ; quand
   un autre y ajoute, le site écrit avec le jeton du créateur (gardé à sa dernière connexion) et note qui a ajouté
   chaque titre (`community_playlists`, `playlist_additions`, migration 7) — Subsonic ne garde pas l'auteur. Un titre
   n'y est ajouté qu'une fois ; chacun ne retire que ce qu'il a ajouté, le créateur retire tout. Si le créateur
   change son mot de passe, les ajouts des autres sont refusés (`playlist.owner_unavailable`) jusqu'à sa reconnexion.
   Testé avec le faux Subsonic et jsdom, **pas vérifié contre le vrai Subsonic** (paramètre `public` de `updatePlaylist`).
   **Écoute, fait le 25/10/2026** : le lecteur signale chaque titre de Subsonic (`/api/scrobble`, « en cours » au
   démarrage, « écoutée » après la moitié du titre ou 4 min réellement écoutées, un saut en avant ne compte pas) ;
   section **Écouté en ce moment** en haut du panneau de droite, au-dessus du salon, comme dans Subsonic
   (`web-pc/static/js/listening.js`, `getNowPlaying`, relu toutes les 30 s) : chacun, soi-même en premier, avec la pochette.
   **Page « Mon compte », faite le 27/10/2026** (demandée) : photo de profil (image envoyée, **copie de Gravatar**, ou
   celle de Subsonic par `getAvatar`), affichage, droits, bouton vers les réglages Subsonic (Last.fm, mot de passe :
   `SUBSONIC_PUBLIC_URL`, **à ajouter au `.env` de prod**), import d'un lien YouTube/SoundCloud ; photos en haut, dans le
   salon et « Écouté en ce moment ». Réglages rapides (roue dentée) gardés. Voir `docs/features/comptes-et-droits.md`.
   Connexion aux comptes YouTube/SoundCloud : **pas faite** (OAuth, voir la fiche).
   **Reste** : page radios Internet, Marque-pages (reprendre à la position). Bouton « Radio de ce titre » ajouté en 1.7.6.
3 bis. **YouTube et Jamendo** : faits le 25/10/2026 (voir « Musique d'ailleurs » plus haut). **Favoris d'ailleurs et
   SoundCloud, faits le 26/10/2026** (demandés) : favoris par personne (`ext_favorites`, migration 12), ajout par cœur
   ou par **lien collé** (vidéo ou playlist YouTube publique/non répertoriée, titre SoundCloud par oEmbed sans clé),
   lecteur officiel SoundCloud ; **titres d'ailleurs dans les playlists Subsonic** (`playlist_ext_tracks`, migration 13) :
   décision de l'utilisateur, le site montre les deux mêlés, les applications Subsonic seulement les titres Subsonic
   (pas de faux fichiers dans la bibliothèque). Fiches : `docs/features/musique-ailleurs.md`, `playlists.md`.
   **Pas vérifié avec les vrais YouTube et SoundCloud.** Pas fait : « J'aime » privés (il faudrait relier le compte
   Google), playlists SoundCloud, fenêtre youtube.com avec compte à rebours comme sur le Pi (`web/static/js/ytpopup.js`).
3 bis bis. **Page « Nouveautés »** (27/10/2026, demandée) : `#/whatsnew`, explique aux utilisateurs, sur un ton léger,
   tout ce que le site fait en plus de Subsonic (fiche `docs/features/nouveautes.md`). À tenir à jour avec les fonctionnalités.
3 bis ter. **Page « Versions »** (27/10/2026, demandée) : `#/versions`, historique daté version par version, numéro
   `v1.1` et pastille à côté du titre du site ; à compléter à chaque version mineure ou majeure dans
   `src/i18n/versions.yaml` avant de déployer (fiche `docs/features/versions.md`). **Version 1.1 pas encore déployée**
   (avec le rangement qui ignore espaces et ponctuation : « A.A.Williams » = « A.A. Williams »).
3 ter. **Retours de test du 25/10/2026 (interface, à faire)** — s'inspirer de Spotify / Deezer :
   - salon : pouvoir le fermer ou régler sa largeur pour laisser plus de place aux albums ;
   - ~~lecteur agrandi au survol~~ et ~~file d'attente en bas~~ : **faits le 25/10/2026** (`web-pc/static/js/queue.js`).
     Survol du lecteur : bande album · année · genre · format · position ; la souris reste 0,7 s : file sur toute
     la largeur (comme Subsonic : titre, album, artiste, durée, genre, année, format, « N titres • durée »),
     « Vider la suite », « Annuler » (20 niveaux), glisser-déposer (poignée ⋮⋮) ou Alt+↑/↓, Entrée, Suppr.
     Fermeture : clic ailleurs, souris repartie au-dessus (0,6 s), Échap, bouton ☰. Testé dans jsdom seulement ;
   - album : bouton « Lire juste après » en plus de « Lire » et « Ajouter à la file » ;
   - ~~pochettes : petit bouton lecture au survol, en haut à gauche~~ : **fait en 1.7.7** depuis l'accueil,
     Albums, artiste, recherche et favoris ; le nom et le reste de la carte ouvrent toujours la fiche ;
   - thème sombre au choix dans les réglages (aujourd'hui il suit le système) ;
   - page Albums : présentation provisoire (pastilles) à revoir ;
   - ~~envoi de fichiers~~ : **fait le 25/10/2026**. L'API Subsonic n'a pas d'envoi : page `#/upload` (lien « Envoyer »,
     droit Subsonic `upload`), fichiers audio envoyés un par un (corps brut, 300 Mo au plus, mp3/flac/m4a/aac/ogg/opus/wav/aiff)
     puis `startScan`. **Revu le 26/10/2026** (décisions de l'utilisateur) : le site tourne sous l'utilisateur de Subsonic
     (`music`, `APP_UID`/`APP_GID`), `MUSIC_DIR` = racine de la musique (montée en écriture ; `datas/Music` en local) ; un
     zip est décompressé et chaque album `Artiste/Album/titre` (majuscule au début, disques `CD1`…) part **aussitôt** chez
     son artiste (retrouvé sans majuscules ni accents : un seul dossier par artiste), dossiers en trop ignorés ; le reste
     attend dans `Incoming` ; jamais d'écrasement ; rattrapage d'Incoming corrigé à la main (`INCOMING_WAIT_HOURS`) ;
     barres de progression par fichier et pour le lot ; proxy : bloc `/api/upload` (avant, 1 Mo bloquait tout). Fiche
     complète avec exemples : `docs/features/envoi-fichiers.md`. **Pas vérifié sur le vrai serveur.**
   - **Barre des artistes, page artiste et page album par dossiers : fait le 26/10/2026** (demandé par l'utilisateur) :
     `getIndexes` + `getMusicDirectory` au lieu de `getArtists`/`getArtist`/`getAlbum` ; identifiants de dossier préfixés
     `f` ; liens ID3 ramenés au dossier ; commentaires, notes, cœur d'album, téléchargement restent sur l'ID3 ; radio et
     mix par l'ID3 du premier titre ; `Incoming` caché ; plus de nombre d'albums dans la barre (réglage retiré) ;
     migration 8 (liste recalculée). Détail : `docs/features/bibliotheque.md`. **Pas vérifié sur le vrai Subsonic.**
   - Raccourci **Compilations** en haut de la barre des artistes (26/10/2026) : dossiers réglés par `SHORTCUT_FOLDERS`
     dans le `.env` (`docs/features/barre-gauche.md`).
3 quater. **Corriger les tags ID3** (demandé le 25/10/2026, à préciser) : l'API Subsonic standard ne sait pas
   écrire les tags. Il faudrait que le site accède aux fichiers (déjà possible depuis le 26/10/2026 : `MUSIC_DIR` monté en écriture sur `/music`, sous l'utilisateur `music` ; dossier de musique de Subsonic monté dans le
   conteneur, en écriture), les modifie (bibliothèque Python `mutagen`), puis demande `startScan`. À décider : qui a
   le droit (proposé : le droit Subsonic `coverArt`, « modifier pochettes et tags », déjà lu par le site), quoi
   corriger (titre, artiste, album, année, genre, n°, pochette ?),
   album entier ou titre par titre, et suggestions MusicBrainz (`shared/external.py` le sait déjà) ou saisie à la main.
   **Actualité** (fait le 26/10/2026, voir `docs/features/actualite.md`) : page `#/news`, flux de webzines ajoutés par
   chacun et partagés, lus toutes les heures, articles gardés ; chacun décoche les flux qu'il ne veut pas voir (pour
   lui seul) ; « Dans la presse » sur la page artiste. Plus tard, éventuellement : recherche dans les archives des
   webzines (API WordPress) et Google Actualités.
4. Sauvegarde distante (demandée) : Forgejo à la maison + copie automatique vers Codeberg pour le code ;
   restic ou borg chiffré, chaque nuit, pour les données (`.env`, bases) — jamais sur Codeberg.
5. Plus tard : thème lu par la page web (variables CSS `--theme-*`), templates.
6. **À la fin (décidé le 27/10/2026) : fermer Subsonic au public.** Seul le site parle à Subsonic, en interne
   (`SUBSONIC_URL=http://subsonic:4040`). D'ici là, Subsonic reste public, deux adresses : `SUBSONIC_URL` interne et
   `SUBSONIC_PUBLIC_URL=https://music.foos.fr` (bouton « Ouvrir mes réglages Subsonic »). Avant de fermer :
   - **relais de l'API Subsonic par le site** (`/rest/...` relayé vers Subsonic) pour que les applis Subsonic du
     téléphone continuent de marcher, et pour une future API téléphone propre au site ;
   - **mot de passe dans le site** (`changePassword` de l'API, puis jeton du site mis à jour) ;
   - **Last.fm par personne** : l'API Subsonic ne permet pas de relier un compte Last.fm → soit l'admin le fait dans
     Subsonic, soit le site envoie lui-même les écoutes à Last.fm (clé du site, chacun autorise une fois) ;
   - `SUBSONIC_PUBLIC_URL` vide → aujourd'hui elle retombe sur `SUBSONIC_URL` (lien cassé si interne) : changer pour
     « vide = pas de bouton » (`config.py`, `controllers/profile.py`).

## Version 1.7.4 : membres visibles directement (07/11/2026)
- Demande utilisateur : supprimer le clic supplémentaire pour afficher les membres dans les participations.
  Après le choix de l'édition d'un album, les relations de chaque artiste principal se chargent directement.
  Le bouton par musicien pour ses autres groupes / projets reste dépliable. Aucun changement d'API ni de base.
- Parcours jsdom existant adapté à l'affichage automatique ; suites non relancées selon la demande utilisateur.
  Syntaxe JavaScript et historique valides. **1.7.4 déployée le 07/11/2026** : HTTPS et conteneur sains, version
  publique et JavaScript servi vérifiés (bouton intermédiaire absent). Le parcours connecté reste à regarder en
  production. Sauvegarde du code et de l'image précédents :
  `/home/subsonic/pimedia-backups/pre-1.7.4-20261107T141821Z/` ; pas de changement de base.

## Version 1.7.3 : membres et autres projets (07/11/2026)
- Décision utilisateur : cette livraison reste une évolution des labels / collaborations, donc **1.7.3** à la suite
  de 1.7.1 et 1.7.2. Le numéro 1.8, brièvement publié, est retiré de l'historique public. Les évolutions de cette
  fonctionnalité restent dans la série 1.7.x (règle ajoutée à CONVENTIONS.md et à la fiche Versions).
- Finition visuelle rapide demandée : cartes avec initiales en médaillon, hiérarchie des noms / dates, projets en
  pastilles, couleurs du thème, adaptation mobile et réduction des animations. Aucun appel réseau ni règle métier
  d'exploration ajouté pour cette finition. Contrôle de syntaxe / YAML uniquement ; pas de relance des suites de
  tests à la demande explicite de l'utilisateur. Les compteurs de tests ci-dessous concernent la version fonctionnelle
  précédant cette finition. **1.7.3 déployée et vérifiée le 07/11/2026** : historique public renuméroté (sans entrée
  1.8), fichiers visuels servis, HTTPS sain. Code et image précédents conservés dans
  `/home/subsonic/pimedia-backups/pre-1.7.3-20261107T111208Z/` ; pas de changement de base.
- Demande : suivre les musiciens d'un groupe vers les autres groupes où ils jouent (exemple public Kyuss).
- Ajouté : bloc sur la page artiste (choix explicite des homonymes) et dans les crédits d'album ; cartes des membres,
  périodes regroupées, bouton « Autres groupes et projets », liens vers les fiches musicales. Même présentation sur
  la fiche musicale du groupe. Relations personnelles exclues, composition toutes périodes distincte des crédits
  d'un album. Chargement au clic, un seul appel de relations par membre, cache et reprise 1.7.2 conservés.
- API authentifiée : `/api/explore/artists?name=`, `/api/explore/connections?id=`. Pas de nouvelle migration.
- Vérification de la source réelle : Kyuss a sept membres renseignés ; Josh Homme mène notamment à Queens of the
  Stone Age, Desert Sessions, Eagles of Death Metal, Them Crooked Vultures. Les homonymes de Kyuss sont conservés
  au choix. **511 tests Python passent**, dont 36 ciblés, et le nouveau parcours PC est validé. Les quatre parcours
  Pi passent également ; le préchargement haute fidélité a nécessité un rejeu isolé après son échec intermittent connu.
- Livraison fonctionnelle initiale brièvement numérotée **1.8**, déployée et vérifiée le 07/11/2026 avant sa
  renumérotation en **1.7.3** : HTTPS sain, conteneur sain, nouvelles routes authentifiées (401 sans session),
  intégrité de la base OK, schéma 15 inchangé.
  Depuis le conteneur, les sept membres de Kyuss et leurs liens musicaux ont été chargés en cache ; pour Josh Homme,
  huit autres groupes / projets sont référencés. Contrôle sur ces seules métadonnées publiques, sans compte ni jeton
  de production. Sauvegarde préalable : `/home/subsonic/pimedia-backups/pre-1.8-20261107T092702Z/`
  (code 1.7.2, référence de l'image et base SQLite vérifiée, schéma 15).

## Correctif 1.7.2 : interruptions MusicBrainz (07/11/2026)
- Signalement utilisateur : message d'indisponibilité dès l'ouverture des crédits. L'API répond aux sondes publiques,
  le site est sain ; le code ne tentait qu'un appel et un échec bloquait ensuite toutes les URL non présentes en cache
  pendant une minute. Ce défaut de gestion est corrigé ; aucune panne permanente de MusicBrainz n'est affirmée.
- Une reprise automatique bornée pour les erreurs temporaires, respect de `Retry-After`, délai limité à l'URL en
  échec, données de moins de 30 jours en secours avec un avertissement. Cache public uniquement, jamais de
  disponibilité de fichiers ou d'identité de compte partagée. Diagnostics limités au type d'entité et au statut HTTP.
- 30 tests ciblés passent, dont reprise 503, isolement des URL, `Retry-After`, âge du cache, panne HTTP et indicateur
  de données anciennes. **505 tests Python et les cinq parcours jsdom passent** dans l'image reconstruite.
- **Version 1.7.2 déployée et vérifiée le 07/11/2026** : HTTPS sain, version publique 1.7.2, conteneur sain,
  intégrité de la base OK. Les métadonnées publiques fournies pour Vitalic / Dissidaence Episode 2 ont été chargées
  dans le cache persistant de production : édition et crédits, catalogue Clivage Music (25 éditions, première page),
  fiche Vitalic (45 sorties et participations chargées). Aucun compte, jeton ni fichier de la bibliothèque utilisé
  pour ce préchargement. Sauvegarde préalable :
  `/home/subsonic/pimedia-backups/pre-1.7.2-20261107T012921Z/` (code 1.7.1, référence de l'image, base SQLite
  dont l'intégrité est vérifiée ; schéma 15, inchangé par le correctif).

## Correctif 1.7.1 : ligatures des titres et artistes (07/11/2026)
- Signalement utilisateur : « Dissidaence Episode 2 » de Vitalic affichait « Aucune édition trouvée ».
  Reproduction avec l'API publique : elle renvoie « Dissidænce Episode 2 », ensuite écarté par notre filtre parce
  que NFKD ne transforme pas `æ` en `ae`.
- Correction limitée aux métadonnées de l'exploration : `æ` / `ae`, `œ` / `oe` reconnus comme équivalents, y compris
  dans les résultats locaux. Aucun changement des règles de rangement ou des fichiers. L'épisode 1 et le coffret
  « 1 & 2 » restent exclus. Trois tests de non-régression ajoutés (unitaires et HTTP).
- Version 1.7.1 ajoutée à l'historique. **497 tests Python et les cinq parcours jsdom passent** dans l'image
  reconstruite. Cas réel vérifié avec les seules métadonnées fournies : édition retrouvée, label Clivage Music.
- Sauvegarde préalable de la 1.7 : `/home/subsonic/pimedia-backups/pre-1.7.1-20261107T011416Z/` (code, image,
  base SQLite dont l'intégrité est vérifiée, schéma 15).
- **Version 1.7.1 déployée et vérifiée en production le 07/11/2026** : HTTPS sain, version publique 1.7.1,
  conteneur sain, base au schéma 15 et intégrité OK. Depuis le conteneur, le titre et l'artiste fournis retrouvent
  l'édition « Dissidænce Episode 2 » et le label Clivage Music, sans utiliser de compte ni de jeton de production.

## Labels et collaborations (07/11/2026, version 1.7)
- Implémenté côté PC : depuis l'album, choix explicite d'une édition MusicBrainz, labels et crédits cliquables,
  catalogue d'un label, sorties et participations d'une personne, membres et groupes liés, recherche des disques
  dans la bibliothèque avec le compte courant. Cache SQLite partagé pour les seules métadonnées publiques,
  migration 15 ; régulation commune des appels MusicBrainz, erreurs et reprises sans bloquer les titres locaux.
- Aucun compte ni clé supplémentaire nécessaire pour MusicBrainz. Discogs est désormais branché dans la 1.7.10.
- Vérification Docker finale : **494 tests Python OK**, parcours PC et les quatre parcours Pi validés ; le parcours
  Pi haute fidélité a eu un échec intermittent de préchargement, puis est passé entièrement au rejeu isolé.
- **Version 1.7 déployée en production le 07/11/2026** : https://music2.foos.fr. Accès SSH rétabli avec
  `~/.ssh/pimedia_ed25519`. Code 1.6, base SQLite (schéma 14, intégrité vérifiée) et référence de l'image sauvegardés
  dans `/home/subsonic/pimedia-backups/pre-1.7-20261107T010615Z/` avant la mise à jour.
- Contrôles après déploiement : conteneur sain, base au schéma **15**, `quick_check` OK, HTTPS `/health` OK,
  `/api/versions` annonce **1.7**, nouveau module JS servi, routes d'exploration protégées (401 sans session),
  aucune trace d'exception au démarrage. Depuis le conteneur de production, exemple public fixe ABBA / Arrival :
  33 éditions, 49 crédits et catalogue Atlantic (25 éditions) chargés. Aucun jeton de compte de production utilisé
  pour ce contrôle ; pas de vérification dans un vrai navigateur connecté à la bibliothèque.
- Tests unitaires, HTTP et parcours jsdom ajoutés. Essai réel depuis le poste : 33 éditions d'Arrival / ABBA, crédits,
  membres et sorties chargés ; catalogue du label Polar validé (25 éditions). API intermittente (503 rencontrés).
  Pas encore essayé dans un vrai navigateur contre la production.
  Détails et limites : `docs/features/labels-et-collaborations.md`.
- Le plan historique de la page Rangement réserve les migrations 15–17 : la 15 est désormais utilisée ici ;
  renuméroter ses migrations à la suite du schéma en vigueur lors de son implémentation.

## Discogs sur la page artiste : intégré en 1.7.10
Demande du 07/11/2026 réalisée : bouton ouvrant la discographie dans le site, identité au choix, pochettes, années,
formats et participations, rééditions regroupées et repères de bibliothèque. Les membres, groupes et crédits
d’album permettent de poursuivre l’exploration dans Discogs. Fiche : `docs/features/decouverte-labels.md`.
La couverture dépend des contributions à Discogs ; pas de garantie d’exhaustivité. Déployé en production le 08/11/2026.

## Décisions (25/10/2026)
- Le Pi est à part (local, à la maison) : on n'y touche pas, pas de socle commun à construire pour l'instant.
- Le site PC lit tout depuis Subsonic (notes, écoutes, favoris, playlists, marque-pages) ; seuls le chat, les
  comptes du site et les réglages sont dans `webapp.db`. Mixes calculés par le serveur du site (mêmes pour tous).
- Interface : s'inspirer de Spotify/Deezer plutôt que de l'interface Subsonic.
- **Code commun** : `src/pimedia/shared/` contient les classes pures utilisées par les deux éditions (pour l'instant
  `external.py` : paroles, MusicBrainz, Wikipédia, anecdotes). Règle vérifiée par `tests/test_architecture.py` :
  `shared` n'importe ni le Pi ni le site, le Pi n'importe jamais le site. Pas de dépôt séparé (inutile tant que
  tout est dans le même dépôt). À déplacer ensuite dans `shared` : client Subsonic (deux versions aujourd'hui),
  serveur HTTP (`server/transport.py`, `webfiles.py`, encore importés par le site depuis le Pi), entités communes.
- Proposé, pas tranché : ranger l'édition PC en couches hexagonales (domain / application / infrastructure /
  interfaces).

## Non vérifié sur le vrai matériel / vrai serveur
Barre des artistes paresseuse avec 5 424 artistes dans un vrai navigateur (testée seulement dans jsdom).
**À tester sur music.foos.fr** (Subsonic 1.16.1 confirmé par `ping`) : notes posées sur le dossier de l'album et
moyenne relue ; album en plusieurs disques ; « Mieux notés » (`highest`) relié aux albums ID3 par le premier titre du
dossier ; écoutes ; listes par décennie et par genre.
Édition PC contre le vrai Subsonic ; nouveau menu Tk sur le Pi ; install.sh sur un Pi neuf ; bouton Éteindre ;
AirPlay (sortie PulseAudio) ; mpv sur le Pi.
