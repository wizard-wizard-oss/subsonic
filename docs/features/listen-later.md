# À écouter : artistes, albums, morceaux et recommandations (site web)

## Fonctionnement

- Page #/listen-later dans la navigation et les réglages rapides : trois onglets (Reçues, Marque-pages,
  Envoyées), filtre artistes/albums/morceaux ; voir « Refonte pochettes (1.20) » plus bas.
- Bouton marque-page sur les fiches artiste/album Subsonic, la fiche artiste Discogs et les cartes des catalogues
  Discogs existants. Le bouton indique son état ; un second clic retire l'entrée personnelle.
- « Conseiller à quelqu’un » aux mêmes endroits et dans la liste personnelle : choix d'un autre compte déjà
  connecté au site, avec un commentaire initial facultatif. Le conseil arrive dans les recommandations,
  sans créer de marque-page. Les deux participants peuvent ensuite poursuivre leur échange privé.
- Depuis la 1.13, le même bouton sur les lignes de morceaux Subsonic (album, titres populaires, recherche,
  favoris et playlists) envoie le titre précis. Le double-clic sur ce bouton ne lance pas l'album.
- Les morceaux reçus forment une liste avec titre, artiste et conseillers. « Tout écouter » charge les morceaux
  dans l'ordre affiché et les enchaîne dans le lecteur habituel ; le bouton d'une ligne commence à ce morceau
  dans la même liste. Les métadonnées actuelles sont relues via Subsonic avant de remplacer la file.
- La croix de chaque ligne retire ce morceau des recommandations, pour tous ses conseillers. Les autres conseils,
  un éventuel marque-page du morceau et la lecture en cours restent indépendants. Le marque-page permet de
  conserver le morceau ; sa carte propose ensuite « Écouter le morceau ».
- Plusieurs personnes peuvent conseiller la même référence : une carte regroupe tous leurs noms.
  Une même personne ne crée pas deux conseils identiques pour le même destinataire.
- Une recommandation peut être gardée comme marque-page. Les deux cartes peuvent coexister et se retirent
  indépendamment. Retirer une recommandation archive tous les conseils reçus pour cette référence ; leurs
  commentaires restent accessibles dans les recommandations archivées et dans les envois de chaque conseiller.
- Les artistes/albums Subsonic ouvrent les fiches existantes ; le nom d'un morceau gardé ouvre la recherche.
  L'artiste Discogs ouvre sa fiche dans le site ;
  l'album Discogs ouvre l'édition retenue sur Discogs.
- « Rechercher pour écouter » ouvre la recherche actuelle préremplie : bibliothèque, vidéos YouTube déjà connues
  et recherche YouTube sur demande. Lecteur, favoris et playlists existants prennent ensuite le relais.
- Ajouter ou retirer un marque-page ne modifie aucun favori Subsonic ou YouTube.
- Images manquantes : icône de remplacement. Textes français dans i18n/fr.yaml et nomenclature anglaise.

## Refonte « pochettes » (1.20)

- Trois onglets (`listen-later-tabs.js`) : Reçues (par défaut), Marque-pages, Envoyées (+ archivées). L'onglet choisi
  est gardé tant que l'on reste sur la page ; une nouvelle visite rouvre Reçues. La pastille rouge de l'onglet
  Reçues compte les conseils nouveaux ou à commentaires non lus et n'apparaît que si un autre onglet est ouvert.
  Les conseils ne sont accusés comme lus qu'à l'ouverture de l'onglet Reçues.
- Artistes et albums : tuiles en grille avec la pochette (`image_ref`), badge de type, point rouge « nouveau »,
  avatars des conseillers, flèche de lecture (album Subsonic, radio de l'artiste Subsonic, morceau). Les cartes
  Discogs gardent « Rechercher pour écouter » : rien à lire directement. Morceaux : liste avec petite pochette.
- Commentaires : `RecommendationComments.group()` affiche l'aperçu du fil le plus récent (non lu d'abord, puis avec
  message, puis le plus récent), la bulle avec son compteur et « Voir tous les conseillers » pour les autres fils.
  Le fil se déplie en place (`mount`) ; la fenêtre ne sert plus qu'à l'ouverture depuis la notification ou après
  un envoi. Plusieurs fils peuvent être dépliés ; l'actualisation temps réel les met à jour sans redessiner la page.
- Pas de changement de données, de routes ni de migration. Les conseils YouTube restent hors périmètre.

## Données

Migration 17 dans webapp/schema.py, ajoutée à la suite des migrations existantes :

| Table | Colonnes |
|---|---|
| listen_later | id, user_id, kind, source, library_key, source_id, title, artist, image_ref, created_at |
| recommendations | id, sender_id, recipient_id, kind, source, library_key, source_id, title, artist, image_ref, created_at |

kind : artist, album ou song ; source : subsonic ou discogs. Les morceaux sont limités à Subsonic.
Folders ramène les références Subsonic aux dossiers : un ajout depuis l'ID3 ou depuis un dossier donne la même
entrée. library_key réutilise l'identité de serveur calculée par ArtistDiscogsLinks. Les entrées d'un ancien
serveur restent conservées ; seules celles du serveur configuré et celles de Discogs sont affichées.
Un morceau garde son identifiant Subsonic propre ; il ne se confond ni avec son album, ni avec un autre titre.

Pour Discogs : identifiant d'artiste, ou identifiant de l'édition déjà utilisée par la carte (editions[0]).
Deux éditions restent deux références distinctes. Les descriptions sont résolues par les services côté serveur.

Unicité des marque-pages par propriétaire et référence complète ; des conseils par émetteur, destinataire et
référence complète tant que le conseil est actif. Un nouvel ajout identique conserve la date initiale et
le commentaire déjà envoyé ; après archivage, un nouvel envoi crée un autre fil. Les clés étrangères nettoient les
entrées à la suppression du compte correspondant.

Les descriptions conservées permettent d'afficher et retirer une entrée sans rappeler les sources.
Aucun catalogue complet importé, cron, rapprochement automatique Discogs/Subsonic, état « écouté » ou
nouveau stockage de liens de lecture. Les marque-pages de position (/api/bookmarks) restent indépendants.

## Code

- listen_later_entities.py : ListeningTarget et ListenLaterEntry.
- recommendation_entities.py : Recommendation, RecommendationComment, groupes, livraisons, pages et statut typés ;
  limites des commentaires et des pages définies une seule fois.
- listening_targets.py : validation et résolution via Folders, Library.song et Discogs.
- listen_later.py : règles des entrées personnelles ; recommendations.py : envoi, regroupement,
  archivage, droits des deux participants, commentaires et accusés de lecture.
- storage/listen_later.py, storage/recommendations.py et storage/recommendation_comments.py : SQL et retour d'entités ;
  storage/listening_targets.py mutualise la projection SQL de la référence.
- controllers/listen_later.py : adaptation HTTP. Assemblage dans app.py.
- web-pc/static/js/listen-later.js et css/listen-later.css : boutons, dialogue et page.
  Liste de morceaux et chargement de la file dans le même composant ; intégrations dans les fiches, tableaux
  de titres, DiscogsUI.card, la navigation et les réglages existants.
- web-pc/static/js/recommendation-comments.js : un seul composant de fil privé pour les conseils reçus,
  envoyés et archivés ; champ de commentaire également réutilisé à l'envoi initial.
- DiscogsRelease.image utilise le validateur d'images existant ; projection de cache passée en version 3.

## API et accès

| Route | Corps / résultat |
|---|---|
| GET /api/listen-later | bookmarks et recommendations regroupées |
| POST /api/listen-later/add | kind, source, sourceId |
| POST /api/listen-later/remove | id |
| POST /api/recommendation/send | recipient, kind, source, sourceId, comment facultatif ; recommendation et created |
| POST /api/recommendation/remove | kind, source, sourceId : archivage du groupe reçu |
| GET /api/recommendation/discussions | scope=sent ou archived, before facultatif ; pages de recommandations |
| GET /api/recommendation/comments | id, before ou after facultatif ; fil privé paginé, maxLength et pageSize |
| POST /api/recommendation/comment | recommendationId, body, requestId facultatif ; auteur issu de la session |
| POST /api/recommendation/comments/read | recommendationId, commentId effectivement affiché |
| GET /api/song?id= | Métadonnées actuelles d'un morceau, relues avec le compte connecté |

Session obligatoire et protection CSRF existante pour les écritures.
Le propriétaire, l'émetteur et le destinataire d'un retrait viennent de la session.
Une référence Subsonic conseillée est aussi vérifiée avec le compte du destinataire.
L'état client est réinitialisé à chaque connexion pour éviter de reprendre celui d'un autre compte.

## Morceaux recommandés (1.13)

Migration 20 : reconstruction transactionnelle de listen_later et recommendations pour accepter song,
avec contrainte song/subsonic. Identifiants, dates, références, clés étrangères, index, unicités et marqueurs
de lecture sont conservés. Les migrations déjà publiées restent inchangées.

La liste s'affiche et se supprime depuis les descriptions enregistrées, même si la source devient indisponible.
À la lecture, au plus quatre demandes getSong sont simultanées. Les morceaux supprimés ou devenus inaccessibles
(404) sont ignorés avec un message ; si le morceau choisi manque ou si aucune piste ne reste, la file est
conservée. Les autres erreurs conservent aussi la lecture actuelle. La navigation ou un changement de compte
annule le démarrage différé. Les boutons de lecture respectent le droit stream ; le retrait reste disponible.
La liste reçue a ses colonnes propres (titre, artiste, conseillers, commandes) : elle n'affiche pas de tags absents
des descriptions conservées. Elle défile horizontalement sur écran étroit.

Il s'agit d'une sélection chargée dans la file du lecteur ; elle ne crée pas de playlist Subsonic enregistrée.
L'envoi de morceaux Discogs, YouTube, SoundCloud ou Jamendo n'est pas proposé.

Validation locale de la 1.13 : 853 tests Python passent, ainsi que les parcours jsdom PC général, file et
À écouter. Chrome vérifie deux comptes avec le vrai flux SSE, l'écoute de toute la liste et le retrait
individuel ; rendu clair/sombre contrôlé à 1440, 390 et 320 px, commandes visibles et défilement limité au
tableau sur petit écran. Les serveurs musicaux sont simulés pour ces essais.

La 1.13 est publiée le 21/11/2026 sur https://music2.foos.fr depuis l'instantané du commit `da9edc6`.
Migration 20 répétée sur copie puis vérifiée en production : intégrité et clés étrangères valides,
marque-pages, recommandations et marqueurs de lecture conservés. Conteneur sain sans erreur de démarrage,
231 fichiers applicatifs et 52 ressources HTTPS conformes, session et CSRF vérifiés sur les routes.
Sauvegarde préalable : `../pimedia-backups/pre-1.13-20261121T174551Z/` ; image précédente conservée sous
`pimedia-web:pre-1.13-20261121t174551z`. Aucun conseil ni marque-page de production créé pour les contrôles.

## Pastille des recommandations (1.9.2)

- Point rouge sur le menu « À écouter » lorsqu'un conseil reçu est non lu ; libellé accessible explicite.
- État conservé pour le compte, partagé entre ses onglets et navigateurs. Un nouveau conseiller sur un même
  album/artiste signale une nouveauté ; renvoyer exactement le même conseil déjà lu ne change pas son état.
- La page marque les conseils comme lus après affichage réussi, par lots limités. Les requêtes de lecture
  de liste seules ne changent rien, et un onglet masqué n'acquitte pas les conseils.
- Les réponses de statut anciennes sont ignorées. Une arrivée après la liste chargée reste non lue jusqu'à
  son affichage. Si la page est ouverte et visible, un événement actualise les conseils puis les acquitte.
- Le flux SSE existant porte un événement recommendations ciblé sur le destinataire. Connexion/reconnexion et
  retour au premier plan relisent le statut ; aucun intervalle ou flux supplémentaire.
- Lors d'un changement de compte, l'état est réinitialisé et le flux reconnecté pour le nouveau destinataire.

Migration 18 : colonne nullable recommendations.unread_token et index partiel par destinataire.
Un marqueur aléatoire identifie une livraison non lue ; son effacement vaut lecture. Il distingue aussi un
conseil supprimé puis recréé, même si SQLite lui réattribue le même identifiant numérique. Les conseils
déjà présents reçoivent un marqueur à la migration. Les favoris et marque-pages ne sont pas modifiés.

| Route | Rôle |
|---|---|
| GET /api/recommendation/status | Statut non lu du compte connecté |
| POST /api/recommendation/read | Accusé portant les tokens des conseils affichés |

La réponse de GET /api/listen-later contient unreadTokens par groupe et readBatchSize.
La limite READ_BATCH_SIZE est définie une seule fois côté service et transmise à la page ; écriture protégée
par CSRF et limitée au destinataire et au serveur de bibliothèque courant.
Le regroupement, l'envoi et le retrait restent dans Recommendations ; SQL dans son dépôt,
adaptation HTTP dans ListenLaterController et notifications/affichage dans ListenLaterUI.

Vérifications ajoutées : conservation après réouverture, migration depuis 17, conseils identiques et nouveaux
conseillers, destinataires et bibliothèques distincts, suppression/recréation avec identifiant réutilisé,
arrivées pendant un accusé, événements réservés aux onglets du destinataire, validation des lots et CSRF.
Le parcours jsdom retarde une ancienne réponse, intercale un nouveau conseil et un accusé, masque l'onglet
et simule une erreur de chargement. Chrome valide deux onglets avec le vrai flux SSE.

La 1.9.2 est déployée le 10/11/2026 : conteneur et HTTPS sains, schéma 18 intègre, données conservées.
Les 212 fichiers de l’image, les ressources publiques et les protections des nouvelles routes sont vérifiés.

## Commentaires privés des recommandations (1.14, publiée le 22/11/2026)

Le commentaire initial et chaque réponse sont la même entité `RecommendationComment`, sans type question/réponse
ni avis structuré. Un fil appartient à une recommandation entre deux comptes, quel que soit son type musical.
Sur une carte regroupant plusieurs conseillers, chaque bouton ouvre uniquement le fil de ce conseiller avec le
destinataire. Aucun message n'est copié dans le salon ou dans les commentaires publics d'album.

La page À écouter conserve les marque-pages et les conseils reçus, puis montre les recommandations envoyées et
les recommandations archivées. Le filtre artistes/albums/morceaux s'applique à toutes ces sections. Un bouton
« Lire les nouveaux commentaires » ouvre directement un fil non lu, même ancien ou archivé au-delà de la première
page. Le fil affiche le contexte musical, les auteurs, les dates et les textes, avec un formulaire unique.

Migration 21, ajoutée sans changer les migrations publiées :

| Table | Champs nouveaux |
|---|---|
| recommendation_comments | id autoincrémenté, recommendation_id, author_id, body, created_at, client_token |
| recommendations | recipient_archived_at, sender_last_read_comment_id, recipient_last_read_comment_id |

La reconstruction transactionnelle de recommendations conserve les identifiants, dates, références, contraintes,
clés étrangères et marqueurs de livraison existants. L'unicité émetteur/destinataire/référence devient un index
partiel sur les conseils actifs. Les identifiants de recommandations et de commentaires ne sont pas réutilisés.
Les deux curseurs valent initialement zéro ; aucun commentaire n'est inventé pour les anciens conseils.

Un envoi initial et son commentaire sont insérés dans la même transaction. Une répétition d'un conseil actif
renvoie celui-ci avec created=false, sans nouveau commentaire ni écrasement. Pour ajouter du texte à un conseil
existant, on ouvre son fil ; un texte saisi lors d'un second envoi y reste en brouillon pour être envoyé
explicitement, sans créer de doublon automatique. Le client fournit un requestId conservé lors d'un nouvel essai réseau ; l'unicité
(recommendation_id, author_id, client_token) évite le double enregistrement. Le même identifiant avec un autre
texte est refusé en 409. Ce marqueur technique n'est pas exposé dans les commentaires retournés.

Le texte est facultatif à l'envoi initial et obligatoire pour ajouter un commentaire. Il est limité à 1 000
caractères côté service et dans les champs HTML, avec une limite transmise par l'API. Les historiques et listes
d'envois/archives sont chargés par pages de 50 ; before récupère les anciens éléments et after rattrape les nouveaux
commentaires sans doublons. Il n'y a pas de limite au nombre de réponses, ni de réponses imbriquées, édition,
suppression ou réaction dans cette version.

Le service contrôle les deux participants et le serveur de bibliothèque courant avant chaque accès au fil.
Un tiers reçoit 404, même s'il conseille le même album. La création vérifie toujours l'accès musical des deux
comptes ; consulter et commenter un conseil enregistré ne nécessite plus de rappeler une source devenue
indisponible. Les nouvelles écritures passent par la session et la protection CSRF existantes. Les contenus
sont affichés comme texte DOM, sans HTML interprété. Les suppressions de comptes conservent les cascades existantes.

Le flux SSE existant ne porte que des invalidations ciblées sur les participants. Le statut inclut les nouveaux
conseils et les commentaires écrits par l'autre participant après le curseur de lecture. L'onglet doit être visible
et le fil ouvert pour acquitter les commentaires jusqu'au dernier identifiant affiché. Une arrivée plus récente
reste non lue ; les curseurs avancent uniquement, et un identifiant futur ou appartenant à un autre fil ne les
modifie pas. Écrire soi-même ne masque pas les commentaires entrants non lus. Les lectures mettent à jour les
onglets du lecteur ; les envois et les réponses actualisent aussi immédiatement la page du compte courant.
Reconnexion, retour au premier plan et actualisation manuelle permettent le rattrapage. Le brouillon est conservé
pendant une mise à jour ou un échec d'envoi ; le changement de compte ferme le fil et ignore les réponses anciennes.

Validation : tests de migration 20→21, transaction initiale, livraisons et essais concurrents, persistance,
cascades, participants et conseillers distincts, validation, CSRF, archivage et nouvel envoi, pagination, lecture
concurrente et diffusion ciblée dans tests/test_recommendation_comments.py. Le parcours jsdom À écouter couvre
l'envoi initial, les échanges successifs, le texte non interprété, le double clic, le brouillon, un onglet masqué,
la coupure après enregistrement, les vues reçues/envoyées/archivées, les pages d'historique et le changement de compte.
Le navigateur réel vérifie deux comptes fictifs avec le vrai flux SSE, un nouvel envoi depuis un marque-page et le
fil contenu à 390 et 320 px. Le débordement des barres générales sur petit écran est antérieur à cette évolution.
La 1.14 est publiée le 22/11/2026 sur https://music2.foos.fr depuis le commit `68ba21a`. L'instantané
exact passe 869 tests Python et quatre parcours jsdom PC. La migration a été répétée sur une copie SQLite de
la sauvegarde : valeurs des 25 tables existantes et marqueurs de lecture conservés, intégrité et clés étrangères
valides. Après publication : schéma 21 intègre, 234 fichiers applicatifs et 53 ressources HTTPS conformes,
conteneur sain, configuration conservée et protections session/CSRF vérifiées. Aucun commentaire de production
créé pour les contrôles. Sauvegarde préalable : `../pimedia-backups/pre-1.14-20261122T210559Z/` ;
image précédente `pimedia-web:pre-1.14-20261122t210559z`. Le correctif de tags préparé séparément n'est pas inclus.

## Tests et limites

- tests/test_listen_later.py : migration/réouverture, concurrence, dossier/ID3, séparation des comptes,
  types/sources/serveurs, descriptions vérifiées, lecture hors ligne, propriété des retraits, favoris conservés,
  quatre conseillers, répétition idempotente, coexistence, accès du destinataire, validation et CSRF.
  Pour les morceaux : migration 19→20 avec marqueurs lus/non lus conservés, unicités et suppressions en cascade,
  descriptions et métadonnées relues dans Subsonic, séparation morceau/album, validation des types et accès
  des deux comptes, suppression possible après disparition de la source.
- tests/e2e_listen_later.js : vraie interface dans jsdom, fiches Subsonic/Discogs, envoi d'un conseil,
  regroupement, conservation facultative, filtres, retrait indépendant, recherche existante et changement de compte.
  Morceaux : envoi depuis la deuxième piste d'un album, liste reçue, plusieurs conseillers, lecture de tout le
  groupe et à partir d'une ligne, passage à la piste suivante, double-clic, panne préservant la file,
  piste indisponible ignorée, droit d'écoute, marque-page conservé et retraits jusqu'à la liste vide.
  Ajouté à tests/run_e2e.py.
- File TCP du serveur de parcours PC portée à 128 connexions pour charger les scripts jsdom sur macOS.
- Validation locale : 633 tests Python passent ; parcours PC existant et nouveau parcours jsdom passent.
  Syntaxe JavaScript contrôlée, contenu vérifié dans Chrome à 1440, 390 et 320 px, en clair et sombre.
  Les barres générales existantes restent trop larges sur mobile ; le contenu de la nouvelle page s'adapte.
- Déployé le 10/11/2026 sur https://music2.foos.fr en version 1.9 : conteneur et HTTPS sains,
  schéma 17 intègre, dix comptes conservés, 212 fichiers de l’image conformes aux instantanés testés.
  Nouveaux JavaScript/CSS versionnés et textes publics vérifiés. Sources externes et Subsonic simulés pour les tests ;
  parcours interactif avec un compte de production encore à essayer.
  La 1.9.2 déployée ajoute la pastille et les événements temps réel décrits ci-dessus.
