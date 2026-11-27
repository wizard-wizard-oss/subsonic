# Help : guides de l’application (site web)

## Fonctionnement

Page **Help** (`#/whatsnew`, menu du haut et menu mobile). Le nom court demandé par l’utilisateur
reste celui du menu et du titre. La refonte **1.16**, publiée le 26/11/2026, remplace les six parties
et 34 cartes par trois mises en avant puis sept thèmes et 40 guides.

Les mises en avant **salon**, **paroles synchronisées** et **presse musicale** ouvrent directement le guide
correspondant. Le lien **Les dernières nouveautés** mène à `#/versions` ; il conserve l’historique et
les indicateurs de versions existants. Une mise en avant n’est pas une annonce datée de publication.

Chaque thème propose ses guides. Un seul thème et un seul guide sont sélectionnés à la fois. Le guide
contient un titre, trois étapes, une précision sur son fonctionnement et, lorsque cela aide le geste,
une capture de l’application avec des données d’exemple. Les captures montrent les composants réels,
pas la maquette de conception. Six exemples : album, paroles, salon, crédits/label, import et flux RSS.

### Les sept thèmes

- **Écouter sa musique** (5 guides) : album entier, aléatoire et morceau ; file et ordre ; reprise ; paroles
  synchronisées ; anecdotes et raccourcis. Distingue file de lecture et playlist, synchronisation réelle,
  défilement estimé et absence de paroles.
- **Discuter et partager** (6) : salon, réponses/réactions/mentions et notifications, écoutes du moment,
  commentaires d’album, recommandations d’artistes/albums/morceaux, échanges privés, conseils envoyés
  et archives. Distingue le salon public et les conversations privées associées à chaque recommandation.
- **Explorer de nouvelles musiques** (7) : nouveautés/genres/décennies, recherche, artistes similaires et
  titres populaires, radios/créateur de mix, biographies/discographies, crédits/musiciens/autres groupes,
  découverte et Top des labels. Explique pourquoi le parcours label part d’un album et de son édition :
  un artiste peut publier chez plusieurs labels. Les versions YouTube sont proposées au choix.
- **Garder et préparer ses écoutes** (6) : cœurs/étoiles/marque-pages, À écouter, création et ordre des
  playlists, partagées/communautaires, import Spotify/Deezer/Apple Music, playlists mixtes. Lien vers le
  guide d’export existant ; Spotify passe par un CSV, les correspondances sont vérifiées avant création.
- **Écouter la musique d’ailleurs** (5) : recherche YouTube/Jamendo, liens YouTube/SoundCloud, playlist
  YouTube, favoris et playlists, vidéos refusées et limites. Maintient les explications des playlists
  privées, des lecteurs officiels, des 120 recherches/heure et des données absentes des clients Subsonic.
- **Suivre l’actualité musicale** (4) : lire, ajouter un journal ou flux RSS, masquer ses sources,
  retrouver **Dans la presse** sous les artistes. Le flux ajouté sert à tous ; le masquage est personnel.
  Les articles collectés sont rapprochés par le nom dans leur titre, sans recherche dans les archives.
- **Personnaliser et gérer** (6) : affichage/panneaux/colonnes, profil, téléchargement/envoi, pochettes/tags,
  droits du compte et répartition des données entre site, applications Subsonic et Last.fm.

### Navigation et accessibilité

Les thèmes et les guides sont des boutons natifs avec sélection `aria-pressed` et cibles `aria-controls`.
Le groupe de guides est nommé. Le choix d’un thème ou d’un guide ne lance aucune lecture et n’écrit
aucune préférence. Les actions explicites ouvrent les composants existants (paroles, file, salon,
recherche, réglages, raccourcis) ou les pages existantes. Ouvrir le salon revient à son onglet de discussion
et passe par le bouton commun pour respecter le volet mobile.

Le sommaire passe en grille puis en colonne selon la largeur disponible dans la zone centrale,
y compris lorsque les panneaux PC sont ouverts. Sur un sommaire empilé, un choix révèle le panneau
correspondant. Les raccourcis sont présentés comme des possibilités sur ordinateur, à côté des boutons.
Les captures sont chargées à la demande ; aucun appel externe ni service de découverte supplémentaire.

## Organisation du code

- `src/web-pc/static/js/whatsnew.js` : catalogue des thèmes, métadonnées de destinations/captures,
  sélection locale, rendu DOM et délégation aux commandes existantes. Aucune concaténation HTML.
- `src/i18n/fr.yaml`, section `webapp.whatsnew` : tous les textes, titres, trois étapes et précision
  de chaque guide. Le catalogue des guides vient des clés traduites ; pas de second décompte dans le rendu.
- `src/web-pc/static/css/help.css` : styles dédiés, variables et icônes existantes ; feuille chargée dans
  `index.html`. Les anciennes règles de cartes Help sont retirées de `views.css`.
- `src/web-pc/static/help/*.png` : six captures des composants sur le faux Subsonic de test.

Aucune modification de route, de base, de services musicaux, de lecture YouTube ni de l’édition Pi.

## Vérification

- `tests/e2e_help.js` : vrais textes servis, parcours des 40 guides, sélection exclusive, focus, ARIA,
  liens/import/labels/RSS, absence d’effets sur lecture/préférences, actions réutilisées et captures HTTP.
- `tests/e2e_webapp.js` : Help dans la page complète, menu actif, navigation et lien Versions.
- `tests/e2e_mobile_page.js` : navigation et composants mobiles existants.
- `tests/test_versions.py` : historique et numéro 1.16.

Validation locale du 26/11/2026 : 12 groupes de contrôles Help réussis (39 guides, six captures
servies par HTTP), parcours PC général (367 contrôles) et parcours mobile complet réussis, cinq tests
de versions réussis. Navigateur Chromium : thèmes et mises en avant utilisables à 1440, 900, 390 et
320 px, clair et sombre, aucun débordement du composant ni erreur JavaScript. Revue indépendante du
rendu, de la séparation textes/styles/navigation et de l’ouverture du salon depuis Mentions.

La validation utilise une bibliothèque et des comptes fictifs. Les captures sont explicitement légendées
comme des exemples ; elles ne contiennent aucune donnée du serveur de musique de production.
La lecture musicale réelle n’a pas été modifiée ni testée dans cette refonte.

## Publication 1.16

Publication le 26/11/2026 depuis une livraison isolée de la production 1.15.2, par
`deploy/pc/push.sh` (empreinte `e01ea663204e`). Seuls les 12 fichiers applicatifs Help
diffèrent de la production précédente. Les 245 fichiers exécutés et 64 ressources HTTPS, dont les
six captures, correspondent à cette livraison. Menu et titre Help, sept thèmes, 39 guides et
117 étapes confirmés par HTTPS. Conteneur sain, configuration et volume de données conservés ;
SQLite intègre au schéma 21, clés étrangères valides. Les recherches et autres écritures reçues
pendant la publication sont conservées. Sauvegarde code/configuration/SQLite :
`../pimedia-backups/pre-1.16-20261126T221729Z/` ; image précédente `pimedia-web:pre-1.16-20261126t221729z`.
Aucune migration. Le retour de code peut conserver la base courante.
Validation de la livraison exacte : 12 groupes Help, parcours PC général, parcours mobile complet
et cinq tests de versions réussis.
