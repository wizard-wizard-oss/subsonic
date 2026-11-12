# Labels et collaborations (site web)

Ajouté le 07/11/2026, version 1.7. Source : **MusicBrainz**, sans compte ni clé API. Lecture seulement : aucun
changement des tags, des fichiers ou des données de Subsonic. Discogs reste une évolution séparée.

## Parcours
1. Sur la page album, sous les titres, **Découvrir les crédits**. Les titres et la lecture sont disponibles avant
   toute requête externe.
2. Le serveur lit l'album avec le compte Subsonic de la personne et cherche les éditions MusicBrainz par titre et
   artiste. Seuls les noms identiques après normalisation sont retenus, sans rapprochement approximatif. Depuis
   le correctif 1.7.1, les ligatures `æ` / `ae` et `œ` / `oe` sont également équivalentes (titres et artistes), sans
   modifier les noms affichés ou stockés. Depuis la 1.7.9, cette comparaison utilise `shared.text.normalize`,
   également employée pour retrouver les dossiers, les genres, les pochettes et les raccourcis. Jusqu'à
   100 résultats de recherche sont examinés. Le filtre accepte les noms canoniques individuels et le crédit
   complet affiché par MusicBrainz : « Fennesz + Sakamoto » et le nom crédité « Prodigy » (identité canonique
   « The Prodigy ») retrouvent leurs éditions. Le titre doit toujours correspondre exactement après normalisation.
3. La personne **choisit explicitement l'édition**, même s'il n'y en a qu'une. Date, pays, format, labels connus et
   début d'identifiant permettent de les distinguer. Les crédits et le label peuvent varier selon l'édition.
4. Les **labels**, les **artistes principaux** et les **crédits** de l'album et des enregistrements sont cliquables :
   production, interprètes / instruments, chant, composition, paroles, direction, mixage, prise de son et mastering.
   Une personne peut avoir plusieurs rôles ; le même crédit retrouvé sur plusieurs pistes n'est affiché qu'une fois.
5. Un **label** ouvre son catalogue MusicBrainz, paginé par 25 éditions (les rééditions restent distinctes).
6. Une **personne ou un groupe** ouvre ses sorties principales (groupes de sorties MusicBrainz, paginés par 25),
   ses participations directement renseignées dans les relations MusicBrainz, ses membres ou ses groupes liés avec
   les dates connues. Ces relations sont également cliquables : groupe → membre → autre groupe.
7. **Chercher chez moi**, sur un disque ou une participation, cherche dans Subsonic avec le compte courant et
   affiche les correspondances exactes de titre et d'artiste. Un clic ouvre l'album local ; « Élargir la recherche »
   permet une recherche normale. Aucun résultat local ni disponibilité n'est partagé entre comptes.
8. Une **source MusicBrainz** accompagne l'édition et chaque fiche / disque. Les textes signalent que la couverture
   communautaire peut être incomplète. Une réponse n'actualise pas une page quittée entre-temps.

### Membres et autres projets (version 1.7.3, 07/11/2026)
- **Page artiste de la bibliothèque** : bloc « Membres et autres projets » → « Explorer les membres et les projets ».
  Recherche d'identités MusicBrainz au nom exact normalisé, 25 résultats au plus. S'il existe plusieurs homonymes,
  un choix explicite présente le type (groupe, personne…), le pays et la précision de MusicBrainz. Aucun homonyme
  n'est choisi automatiquement. Une identité unique est ouverte directement.
- **Page album, après choix de l'édition** : depuis la version **1.7.4**, un bloc par artiste principal charge et
  affiche directement ses membres / projets, sans bouton d'ouverture supplémentaire. L'identité vient du crédit
  MusicBrainz de l'édition choisie. Le chargement et les éventuelles erreurs restent propres à ce bloc.
- **Fiche musicale d'une personne ou d'un groupe** : même présentation des liens musicaux, au-dessus du catalogue.
- **Cartes des membres** : nom cliquable, rôle et périodes connues, bouton « Autres groupes et projets ». Ce bouton
  charge les seules relations musicales du musicien (un appel léger, pas son catalogue), puis affiche les liens vers
  ses autres groupes / projets. Le groupe de départ est exclu à cet endroit. Chaque lien ouvre la fiche du groupe
  avec ses disques et ses membres : groupe → membre → autre groupe.
- Plusieurs périodes de la même personne / du même groupe sont regroupées sous un seul lien par rôle ; les dates
  sont conservées. Une réponse déjà chargée se replie / se rouvre sans nouveau chargement.
- Présentation : cartes de musiciens avec initiales en médaillon, noms mis en avant, bouton d'ouverture et autres
  projets en pastilles ; couleurs des thèmes existants, adaptation aux petites fenêtres et mouvements réduits.
- Relations montrées : membres, collaborations explicitement renseignées, sous-groupes et groupes d'origine,
  accompagnement instrumental ou vocal. Les relations personnelles (famille, mariage…) ne sont pas exposées.
- Composition du groupe **toutes périodes confondues**, signalée dans l'interface : ce n'est pas une affirmation que
  tous ses membres ont joué sur l'album choisi. Seuls les crédits de l'édition / des pistes l'établissent.
- Les relations de chaque artiste principal sont chargées à l'ouverture de ses crédits ; les autres projets de
  chaque membre restent chargés au clic. Aucun parcours automatique récursif ni appel pour chaque membre au
  chargement de la page. Ces demandes réutilisent le cache, les reprises et le secours en cas d'interruption.

## Cache, réseau et accès
- Routes de lecture authentifiées : `GET /api/explore/album?id=[&release=]`,
  `GET /api/explore/profile?kind=artist|label&id=[&offset=]`, `GET /api/explore/local?title=[&artist=]`.
- Relations ciblées : `GET /api/explore/artists?name=`, `GET /api/explore/connections?id=<UUID>` ; mêmes exigences de
  session, validation du nom / de l'identifiant, cache public et indicateur `stale`.
- UUID externes validés ; aucune URL fournie par le navigateur n'est téléchargée. Une édition choisie doit appartenir
  aux correspondances de l'album accessible au compte.
- Cache public SQLite `music_metadata`, migration **15**, fraîcheur de 7 jours, conservé au redémarrage. Depuis la
  1.7.2, si l'actualisation échoue, les données datant de moins de 30 jours peuvent être affichées avec un avertissement.
  Leur date d'origine est préservée : une erreur ne rajeunit jamais le cache. Pas de secrets.
- Les appels MusicBrainz de `shared/external.py` partagent un régulateur par processus (au moins 1,05 seconde entre
  les départs de requêtes), avec User-Agent de l'application. Plusieurs instances sur la même IP devront coordonner
  leur quota séparément.
- Requêtes d'exploration dédupliquées par verrou. Depuis la 1.7.2 : un second essai après 2 secondes pour une erreur
  réseau / JSON ou HTTP 500 / 502 / 503 / 504. `Retry-After` (durée ou date) respecté ; attente supérieure à 2 secondes
  laissée au prochain clic, sans immobiliser la requête HTTP. Un 429 sans consigne demande 60 secondes. Les autres
  erreurs HTTP ne sont pas réessayées et ne servent pas de cache ancien.
- Après échec des tentatives : délai d'au moins 60 secondes **pour cette seule URL**, jamais un blocage global.
  Cache valide ou cache ancien de secours consultables pendant l'attente ; sans données utilisables, HTTP 503
  `explore.unavailable` et bouton Réessayer. L'interface signale les données anciennes (`stale` sur les réponses
  album et profil, y compris les pages suivantes du catalogue). Les erreurs sont journalisées par type d'entité et
  statut, sans titre recherché, compte, jeton ni URL complète.

## Code et tests
- Entités : `src/pimedia/webapp/exploration_entities.py`.
- Accès MusicBrainz nommé `MusicBrainzMetadata` ; normalisation des noms dans `shared/text.py`, sans dépendance
  aux règles de rangement. Les requêtes SQLite restent dans le dépôt, qui renvoie `CachedMetadata`.
  Cette entité est définie avec les autres entités d’exploration ; le service ne dépend plus du module de stockage.
- API externe et service : `src/pimedia/webapp/exploration.py`, dépôt : `storage/exploration.py`, contrôleur :
  `controllers/exploration.py`, assemblage et routes dans `app.py`.
- Interface : `src/web-pc/static/js/explore.js`, intégration dans `views.js` / `app.js`, styles dans `views.css` ;
  textes `webapp.explore` de `src/i18n/fr.yaml`.
- `tests/test_exploration.py` : éditions ambiguës, crédits de pistes, déduplication, cache et expiration, panne,
  pagination, membres, séparation des comptes, validation HTTP et authentification. Source simulée :
  `tests/fake_musicbrainz.py`. Parcours navigateur : `tests/e2e_webapp.js`.
- Vérification finale Docker : 494 tests Python OK (dont 19 tests d'exploration) et parcours PC OK. Les parcours Pi
  passent aussi ; le test de préchargement haute fidélité a nécessité un rejeu isolé après un échec intermittent.

## Limites et vérification réelle
- Correctif des crédits complets, 1.7.9 (07/11/2026, local non déployé) : les collaborations et les noms crédités
  sont pris en compte en plus des noms canoniques, sans sélectionner une édition automatiquement. Trois tests
  ajoutés couvrent les collaborations, noms crédités / canoniques et crédits absents ; titres différents et
  collaborations avec un autre partenaire restent exclus. Les 39 tests d’exploration et 5 tests d’architecture
  passent sur les sources intégrant la normalisation commune. Source MusicBrainz simulée.
- Version 1.7.4 (07/11/2026) : bouton intermédiaire des membres supprimé dans les crédits d'album. Les cartes
  apparaissent directement après le choix de l'édition. Parcours jsdom existant adapté à cet affichage automatique ;
  contrôle de syntaxe et de l'historique uniquement, sans relancer les suites de tests, selon la demande utilisateur.
  Déployée le 07/11/2026 : version et JavaScript servis en HTTPS vérifiés, site et conteneur sains. Parcours connecté
  à regarder en production. Code et image précédents sauvegardés dans
  `/home/subsonic/pimedia-backups/pre-1.7.4-20261107T141821Z/` ; pas de changement de base.
- Version 1.7.3 : exemple public Kyuss vérifié dans l'API : sept membres ; Josh Homme est relié notamment à Queens
  of the Stone Age, Desert Sessions, Eagles of Death Metal et Them Crooked Vultures. Plusieurs périodes pour QOTSA
  existent dans les données et sont préservées. La recherche « Kyuss » renvoie aussi deux homonymes personnes : le
  choix de l'identité est nécessaire depuis une page artiste ; une édition d'album donne directement l'identité.
  36 tests ciblés de relations / homonymes et 511 tests Python passent. Parcours navigateur complété et validé :
  album → membres → autres projets, artiste → choix d'identité → membres, musicien → autre groupe. Les parcours Pi
  passent aussi ; celui de haute fidélité a nécessité un rejeu isolé après un échec intermittent du préchargement.
  Livraison initialement déployée comme 1.8 puis renumérotée 1.7.3 à la demande de l'utilisateur : contrôle depuis
  le conteneur et cache persistant chargé pour Kyuss, ses sept
  membres et leurs liens musicaux (huit autres groupes / projets pour Josh Homme), sans compte ni jeton de production.
  La finition visuelle et la renumérotation ont ensuite été contrôlées par syntaxe / lecture YAML, sans relancer les
  suites de tests, à la demande explicite de l'utilisateur (changement de présentation).
  Présentation et numéro 1.7.3 déployés le 07/11/2026 : fichiers CSS / JS et version publique vérifiés en HTTPS.
- Correctif 1.7.2 (07/11/2026) : reprise automatique des erreurs temporaires, délai isolé par URL, cache de secours
  signalé dans l'interface. Une vraie indisponibilité prolongée reste possible pour une fiche jamais récupérée,
  ou dont le cache a plus de 30 jours. Aucun résultat ni crédit n'est inventé pour masquer une panne.
  Vérification : 30 tests ciblés d'exploration, 505 tests Python au total et cinq parcours jsdom passent ; le
  parcours PC simule un premier 503 puis vérifie les crédits, le catalogue et l'avertissement de cache ancien.
  Déployé et vérifié le 07/11/2026. Le cache persistant de production a été rempli avec le seul exemple public
  fourni : Vitalic / Dissidaence Episode 2, ses crédits, la première page du catalogue Clivage Music (25 éditions),
  la fiche Vitalic (45 sorties et participations chargées). Aucun compte ni jeton de production utilisé.
- Correctif 1.7.1 (07/11/2026) : la recherche MusicBrainz trouvait bien « Dissidænce Episode 2 » de Vitalic, mais le
  filtre local rejetait ce titre pour un dossier nommé « Dissidaence Episode 2 ». NFKD seul ne développe pas `æ`.
  La comparaison propre à l'exploration développe désormais `æ` et `œ` ; l'épisode 1 et le coffret « 1 & 2 » restent
  exclus. Les recherches locales de disques utilisent la même comparaison. Les réponses MusicBrainz déjà en cache
  restent réutilisables : aucun vidage de base nécessaire. Tests unitaires et HTTP de non-régression ajoutés :
  497 tests Python et les cinq parcours jsdom passent. Cas réel vérifié (métadonnées fournies par l'utilisateur) :
  édition `6cadade2-5f25-4328-9a60-f478bce87e4f`, label Clivage Music. Correctif déployé le 07/11/2026 et même
  parcours vérifié depuis le conteneur de production avec ces seules métadonnées, sans compte ni jeton.
- Déployé en production le 07/11/2026 (version 1.7), migration 15 et intégrité de la base vérifiées, site HTTPS sain.
  Depuis le conteneur déployé, exemple public fixe ABBA / Arrival : 33 éditions, 49 crédits, catalogue Atlantic de
  25 éditions. Ce contrôle n'utilise aucun compte ni jeton de production. L'authentification des routes est vérifiée
  par leur réponse 401 sans session ; le parcours avec un vrai compte dans un navigateur reste à essayer.
- Essais réseau le 07/11/2026 : 503 depuis Docker ; depuis le poste, recherche d'« Arrival » / ABBA validée (33 éditions
  exactes), édition américaine de 1976 / Atlantic, 49 entrées de crédits, fiche ABBA et membres, sorties et
  participations chargées. Catalogue réel du label Polar ensuite validé : 25 éditions et pagination proposée.
  Le service a aussi répondu 503 pendant ces essais : sa disponibilité reste variable. Les tests automatisés
  utilisent une source simulée, jamais le vrai serveur de musique. Pas encore essayé dans un vrai navigateur
  connecté au Subsonic de production.
- Pas de recherche floue ni de validation persistante d'identité ; les homonymes restent à contrôler avec la source.
  L'édition choisie n'est pas mémorisée. Les noms de dossiers différents des titres MusicBrainz ne sont pas devinés.
- Les participations proviennent des relations disponibles sur la fiche artiste ; pas de parcours exhaustif de chaque
  enregistrement du catalogue. Les relations absentes dans MusicBrainz ne peuvent pas être proposées.
- La recherche locale utilise les résultats bornés de `search3` (12 albums / 30 titres) : absence de correspondance
  ne prouve pas l'absence d'un fichier. Une correspondance textuelle ne certifie pas l'édition exacte.
- Pas encore de complément Discogs, de lecture des identifiants MusicBrainz dans les tags, de regroupement des
  rééditions d'un label, de filtre global « tous les albums de ce label présents chez moi », ni de mix par label.
- Sources : [API MusicBrainz](https://musicbrainz.org/doc/MusicBrainz_API),
  [exemples](https://musicbrainz.org/doc/MusicBrainz_API/Examples).
