# Affichage mobile du site

## Fonctionnement

Les fichiers dédiés `web-pc/static/css/mobile/` et `web-pc/static/js/mobile/` adaptent l’affichage
à 820 px de largeur ou moins, ainsi que sur écran tactile sans survol jusqu’à 1100 px (téléphone en paysage).
Le bouton ☰ ouvre un volet avec les liens de navigation,
les artistes et playlists existants, leurs filtres, le compte et les réglages. Un second clic, Fermer,
Échap, le fond ou le choix d’une destination referme le volet. Le salon dispose de son propre volet.
La saisie du salon, l’accueil, le lecteur et la fenêtre vidéo tiennent dans la largeur disponible.
Les tableaux de morceaux conservent leurs colonnes et leur défilement dans le contenu.

Les volets sont temporaires : ouvrir/fermer le menu ou le salon ne sauvegarde aucune préférence PC.
Le code mobile intercepte leurs boutons seulement sur petit écran ; les gestionnaires du bureau restent
en place. Les nœuds de navigation existants sont déplacés, pas copiés. Au retour à une largeur supérieure
au seuil mobile, ils retrouvent leur place et leurs attributs, et les événements mobiles sont retirés.
La détection utilise `matchMedia`, sans reconnaissance du navigateur ni de son nom.

La visibilité du fil du salon dépend du volet effectivement ouvert, sans modifier la préférence PC.
Un message reçu lorsque le volet mobile est masqué reste non lu.

## Organisation et périmètre

Édition web uniquement. Aucun changement des styles ou scripts de navigation PC, des routes,
de l’édition Pi, des préférences serveur ou du moteur de lecture YouTube.
`js/mobile/bootstrap.js` assemble et détruit l’adaptateur `navigation.js` selon l’écran et la session.
Les règles métier et données restent dans les composants et services existants ; aucune nouvelle route,
base ou copie des playlists n’est créée. `css/mobile/layout.css` porte la disposition et `video.css` borne
simplement la fenêtre vidéo à la largeur disponible. Les CSS ont la même condition que le point d’entrée JS.

Périmètre confirmé le 26/11/2026 : responsive en premier. Chargement et comportement YouTube conservés,
sans préchargement, changement de moteur, contrôles de déplacement ou agrandissement. Les retours réels
sur les vidéos seront traités séparément.

## Vérification

`tests/e2e_mobile.js` vérifie les vrais gestionnaires du bouton PC, les trois préférences de barre latérale,
l’ouverture/fermeture, le focus, l’accès aux playlists, les liens conservés, le salon, les raccourcis,
la perte de session, la visibilité réelle du salon et les allers-retours entre tailles sans duplication
ni écriture des préférences. Les feuilles mobiles sont vérifiées conditionnelles et sans règle globale.
Les parcours PC existants vérifient que l’ajout des fichiers laisse leurs comportements en place.
`tests/e2e_mobile_page.js` vérifie la page complète connectée : artistes, création et sélection de playlist,
liens existants, salon, priorité d’Échap dans une réponse, dialogues et retour au bureau.

Revue indépendante puis recontrôle : anciennes règles mobiles retirées des CSS communs, priorité des
contrôles du salon conservée, barres compactées en paysage court pour laisser la vidéo hors des commandes.
Les responsabilités et couches de données existantes restent en place ; aucune logique métier dupliquée.

Les quatre parcours jsdom PC passent. L’affichage initial à 390 px avait été vérifié dans un navigateur.
La validation visuelle finale (dont 320 px et paysage) reste à faire : le navigateur de vérification ne
démarre plus. La lecture YouTube réelle sur téléphone n’a pas été vérifiée.
