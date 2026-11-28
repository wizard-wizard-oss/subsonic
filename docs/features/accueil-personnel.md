# Accueil personnel du site · 1.25

Sur ordinateur, l’accueil présente la reprise de la file puis une grande rangée défilante par thème : recommandations
reçues, albums écoutés personnellement sur le site, suggestions du même genre, sorties de la semaine et derniers ajouts.
Les écrans tactiles sans survol jusqu’à 1100 px conservent la disposition mobile ; une fenêtre étroite sur ordinateur
garde le menu du bureau. IBM Plex Mono et le choix du thème s’appliquent à tout le site.

## Navigation et présentation

Le bouton ☰ replie le menu de gauche. Il réunit Accueil, Bibliothèque (la page Albums existante), Favoris,
À écouter (onglet des marque-pages), Créer un mix, Webzines, Sorties et Envoyer un album selon les droits.
Les playlists existantes restent en dessous, avec leurs filtres, création, import et glisser-déposer.
Compilations apparaît dans les filtres de la page Bibliothèque, juste après Nouveaux, à partir des dossiers épinglés
existants. Un échec de chargement propose de réessayer sur place. La liste permanente des artistes disparaît sur
ordinateur ; les recherches et fiches restent disponibles.

La barre du haut conserve la recherche et le salon, fermé à chaque activation du bureau. Le sous-marin jaune ouvre
la page Help existante sans libellé visible, avec un nom accessible « À bord ». Les réglages, raccourcis et versions
se trouvent dans le menu du compte. La recherche mesure au plus 480 px, avec une hauteur de 42 px et des bords arrondis.
Les adaptateurs déplacent puis rendent les mêmes nœuds lors des changements de disposition.

Chaque rangée se parcourt au doigt ou au pavé tactile, avec inertie native et défilement fluide ; ses flèches restent
disponibles. L’historique et le radar chargent la page suivante à leur extrémité. Les pochettes mesurent de 150 à 180 px,
sans cadre autour des titres et artistes. Les titres des rangées ouvrent leur page, sans bouton « Tout voir ».
Une erreur se réessaie dans la seule rangée concernée. La reprise suit le lecteur et sa file restaurée, sans lancer
la lecture à l’ouverture. Les recommandations viennent en première rangée après la reprise, uniquement si elles
existent, avec « Conseillé par… ». Leurs commentaires restent sur la page complète. Cet aperçu reprend le cache
À écouter et ne marque rien comme lu. Les sorties utilisent les mêmes appels et cartes `WeeklyRadar` que la page Sorties.

Dans les tableaux de morceaux, le bouton de lecture est toujours visible à gauche du numéro : `▶ 1 Titre`.
Sa colonne reste disponible si le compte masque les numéros de piste.

IBM Plex Mono est servie localement en WOFF2, avec sa licence SIL dans `static/fonts/ibm-plex-mono/`.
Le texte courant utilise la graisse 400 et les titres la graisse 500.
Source : [Google Fonts, IBM Plex Mono](https://github.com/google/fonts/tree/main/ofl/ibmplexmono).
Le thème initial est sombre pour tous les comptes, indépendamment du système. Chacun peut choisir Clair ou Sombre
dans Réglages ou Mon compte ; le choix est conservé par le service de préférences existant. L’essai ne nécessite
aucune migration des préférences. Les boutons pleins utilisent `--button-bg: #220022` avec un texte clair ;
les couleurs de danger et les commandes transparentes gardent leur rôle.

## Sources de personnalisation

1. Les écoutes confirmées sur le site, propres au compte et à la bibliothèque Subsonic configurée.
2. En l’absence de référence encore accessible, le morceau courant de `getPlayQueue`.
3. Si la file est vide ou indisponible, les favoris du compte lus par `getStarred2` (titres, albums, artistes).
4. Sans ces sources, les derniers ajouts déjà présentés par l’accueil.

La consultation de la file ne crée aucune écoute. Les titres à venir dans cette file ne sont pas considérés comme
écoutés. Les listes globales `recent` et `frequent` de Subsonic ne sont pas utilisées pour établir les goûts personnels.
Les suggestions emploient le genre exact du morceau ou de l’album de départ et les listes Subsonic par genre.
Elles excluent l’album de départ. Un genre absent donne une sélection vide. Aucun appel Last.fm n’est ajouté.
Les sorties de la semaine et les articles restent accessibles séparément par Sorties et Webzines ; leurs onglets
communs sont masqués sur ordinateur et conservés dans la disposition mobile. L’accueil ne crée aucun second fournisseur de sorties.

## Enregistrement

Le lecteur enregistre une écoute d’un titre de la bibliothèque après la moitié de sa durée (à partir de 30 secondes)
ou quatre minutes effectivement écoutées. Une avance rapide ne remplit pas ce seuil. Les limites sont définies côté
serveur dans `ListeningPolicy` et envoyées au navigateur par `/api/me`.

Le nouveau dépôt `storage/listening_history.py` conserve des événements, pas de copies des tags. Chaque événement
référence une cible `listening_targets`, son compte, la date et un identifiant de requête. Répéter une requête conserve
le même événement ; réécouter le morceau avec un autre identifiant crée un événement distinct.
La migration 32 ajoute la table et son index sans transformer les anciennes données. Aucune purge n’est activée.
La lecture regroupe les morceaux par leur dernière écoute, avec pagination par identifiant d’événement.

Le signalement à Subsonic conserve son fonctionnement et son droit `scrobble`. L’historique propre au site demande le
droit `stream`, la session et l’en-tête CSRF habituel. Les requêtes ne permettent pas de choisir un autre destinataire.

## Code et vérifications

- Entités, limites, service, adaptation du catalogue et assemblage dans `webapp/personal_home/`.
- SQL dans `webapp/storage/listening_history.py`, migration dans `webapp/schema.py`.
- HTTP dans `controllers/personal_home.py` : `GET /api/home/personal?before=` et `POST /api/listening/history`.
- Affichage dans `desktop-home.js`, `album-rail.js`, `home-resume.js` ; cadre dans `desktop-navigation.js`
  et `css/desktop-layout.css`, suivi de l’écoute dans `player.js`. `mobile/bootstrap.js` choisit l’adaptateur.
- `library-shortcuts.js` réutilise les raccourcis chargés par `sidebar.js` et ses événements, sans second catalogue.
- Typographie dans `fonts.css` et `base.css` ; thèmes dans `preferences.py`, exposés par `/api/me`, appliqués
  dans `app.js` et proposés par `Dialogs.display`.
- Tests `test_personal_home.py`, `test_home_catalog.py`, `test_personal_home_http.py`, `e2e_personal_home.js`.
  Ils couvrent les replis, les favoris de différents types, les données supprimées, la pagination, les doublons,
  les comptes séparés, CSRF, le seuil de lecture, les réponses tardives et une migration depuis une base 30 remplie.
- `e2e_desktop_home.js`, `e2e_desktop_navigation.js`, `e2e_desktop_page.js` : composants et vraie page connectée,
  réutilisation du radar, reprise, pagination, changements de compte, menu, marque-pages, Webzines/Sorties,
  playlists, Help, thèmes, ressources de police et allers-retours mobile. `PreferencesTest` couvre le thème initial
  et le choix clair conservé pour un seul compte.
- `e2e_desktop_breakpoint.js`, `e2e_library_shortcuts.js` et `e2e_song_actions.js` couvrent le choix tactile/bureau,
  Compilations dans les filtres et le bouton de lecture visible avant le numéro.

Validation locale du 28/11/2026 : 1046 tests Python et 19 parcours jsdom complets réussis avant les derniers ajustements
de présentation. Ces ajustements ont ensuite été vérifiés par les parcours ciblés et dans le navigateur local.
Les suites complètes ne sont pas relancées à la demande de l’utilisateur. Docker n’est pas démarré ; la commande
Compose n’a pas pu démarrer les tests. Aucun déploiement effectué.

## Limites actuelles

L’historique commence à l’installation. Il n’importe pas les anciennes écoutes de Subsonic ni celles des applications
mobiles. Ces dernières peuvent contribuer au point de reprise lorsqu’elles utilisent `savePlayQueue`.
Les sources YouTube, Jamendo et SoundCloud ne sont pas encore enregistrées dans cet historique personnel.
Une panne réseau au moment de la confirmation peut faire perdre ce signalement ; aucune file hors ligne n’est ajoutée.
La sélection initiale utilise un genre et n’applique pas encore de pondération selon le nombre d’écoutes.
