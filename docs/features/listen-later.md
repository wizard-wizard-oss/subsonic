# À écouter : artistes, albums et recommandations (site web)

## Fonctionnement

- Page #/listen-later dans la navigation et les réglages rapides : deux sections indépendantes,
  « Mes marque-pages » et « Les recommandations reçues », filtre artistes/albums.
- Bouton marque-page sur les fiches artiste/album Subsonic, la fiche artiste Discogs et les cartes des catalogues
  Discogs existants. Le bouton indique son état ; un second clic retire l'entrée personnelle.
- « Conseiller à quelqu’un » aux mêmes endroits et dans la liste personnelle : choix d'un autre compte déjà
  connecté au site. Le conseil arrive dans les recommandations, sans créer de marque-page.
- Plusieurs personnes peuvent conseiller la même référence : une carte regroupe tous leurs noms.
  Une même personne ne crée pas deux conseils identiques pour le même destinataire.
- Une recommandation peut être gardée comme marque-page. Les deux cartes peuvent coexister et se retirent
  indépendamment. Retirer une recommandation retire tous les conseils reçus pour cette référence.
- Les entrées Subsonic ouvrent les fiches existantes. L'artiste Discogs ouvre sa fiche dans le site ;
  l'album Discogs ouvre l'édition retenue sur Discogs.
- « Rechercher pour écouter » ouvre la recherche actuelle préremplie : bibliothèque, vidéos YouTube déjà connues
  et recherche YouTube sur demande. Lecteur, favoris et playlists existants prennent ensuite le relais.
- Ajouter ou retirer un marque-page ne modifie aucun favori Subsonic ou YouTube.
- Images manquantes : icône de remplacement. Textes français dans i18n/fr.yaml et nomenclature anglaise.

## Données

Migration 17 dans webapp/schema.py, ajoutée à la suite des migrations existantes :

| Table | Colonnes |
|---|---|
| listen_later | id, user_id, kind, source, library_key, source_id, title, artist, image_ref, created_at |
| recommendations | id, sender_id, recipient_id, kind, source, library_key, source_id, title, artist, image_ref, created_at |

kind : artist ou album ; source : subsonic ou discogs.
Folders ramène les références Subsonic aux dossiers : un ajout depuis l'ID3 ou depuis un dossier donne la même
entrée. library_key réutilise l'identité de serveur calculée par ArtistDiscogsLinks. Les entrées d'un ancien
serveur restent conservées ; seules celles du serveur configuré et celles de Discogs sont affichées.

Pour Discogs : identifiant d'artiste, ou identifiant de l'édition déjà utilisée par la carte (editions[0]).
Deux éditions restent deux références distinctes. Les descriptions sont résolues par les services côté serveur.

Unicité des marque-pages par propriétaire et référence complète ; des conseils par émetteur, destinataire et
référence complète. Un nouvel ajout identique conserve la date initiale. Les clés étrangères nettoient les
entrées à la suppression du compte correspondant.

Les descriptions conservées permettent d'afficher et retirer une entrée sans rappeler les sources.
Aucun catalogue complet importé, cron, rapprochement automatique Discogs/Subsonic, état « écouté » ou
nouveau stockage de liens de lecture. Les marque-pages de position (/api/bookmarks) restent indépendants.

## Code

- listen_later_entities.py : ListeningTarget, ListenLaterEntry, Recommendation, RecommendationGroup.
- listening_targets.py : validation et résolution via Folders et Discogs.
- listen_later.py : règles des entrées personnelles ; recommendations.py : envoi, regroupement et retrait.
- storage/listen_later.py et storage/recommendations.py : SQL et retour d'entités ;
  storage/listening_targets.py mutualise la projection SQL de la référence.
- controllers/listen_later.py : adaptation HTTP. Assemblage dans app.py.
- web-pc/static/js/listen-later.js et css/listen-later.css : boutons, dialogue et page.
  Intégrations dans les fiches, DiscogsUI.card, la navigation et les réglages existants.
- DiscogsRelease.image utilise le validateur d'images existant ; projection de cache passée en version 3.

## API et accès

| Route | Corps / résultat |
|---|---|
| GET /api/listen-later | bookmarks et recommendations regroupées |
| POST /api/listen-later/add | kind, source, sourceId |
| POST /api/listen-later/remove | id |
| POST /api/recommendation/send | recipient, kind, source, sourceId |
| POST /api/recommendation/remove | kind, source, sourceId : retrait du groupe reçu |

Session obligatoire et protection CSRF existante pour les écritures.
Le propriétaire, l'émetteur et le destinataire d'un retrait viennent de la session.
Une référence Subsonic conseillée est aussi vérifiée avec le compte du destinataire.
L'état client est réinitialisé à chaque connexion pour éviter de reprendre celui d'un autre compte.

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

## Tests et limites

- tests/test_listen_later.py : migration/réouverture, concurrence, dossier/ID3, séparation des comptes,
  types/sources/serveurs, descriptions vérifiées, lecture hors ligne, propriété des retraits, favoris conservés,
  quatre conseillers, répétition idempotente, coexistence, accès du destinataire, validation et CSRF.
- tests/e2e_listen_later.js : vraie interface dans jsdom, fiches Subsonic/Discogs, envoi d'un conseil,
  regroupement, conservation facultative, filtres, retrait indépendant, recherche existante et changement de compte.
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
