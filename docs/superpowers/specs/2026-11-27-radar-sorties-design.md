# Radar des sorties : sorties de la semaine personnalisées — conception

Date : 27/11/2026. Édition web seulement (le Pi n'est pas concerné).

## Intention

Aujourd'hui l'onglet « Sorties de la semaine » (`#/news/releases`) montre, pour **un style MusicBrainz à la fois**,
les albums et EP dont la première sortie tombe dans la semaine. Chaque changement de semaine ou de style refait
un appel MusicBrainz, puis un appel `/api/explore/local` par carte (24 par page) et 24 pochettes Cover Art Archive.

On veut un **radar personnel** : chacun voit d'un coup les sorties de **ce qu'il suit** (styles, labels, artistes),
**pré-rempli d'après ses écoutes**, et **étendu à ce qui pourrait lui plaire** (artistes proches de ses goûts),
avec un filtre rapide quand il y a trop de choses (« juste la techno »). L'intérêt est la découverte.
Le tout doit coûter **moins** d'appels qu'aujourd'hui et s'afficher sans attente.

## Objectifs

1. Sources par compte, de trois types : **style**, **label**, **artiste**. Ajout et retrait manuels.
2. **Tendances** : pré-remplissage automatique d'artistes, de labels et de styles d'après les favoris et les albums
   les plus écoutés. Visible, étiqueté « d'après tes écoutes », retirable ; une source retirée n'est jamais
   réajoutée par le calcul suivant.
3. **Découvertes (1)** : sorties des **artistes proches** des artistes de la personne, absents de sa bibliothèque.
   Carte étiquetée « proche de X ».
4. **Tri selon les goûts (2)** : dans chaque vue, les sorties dont les tags ressemblent le plus au profil de tags de
   la personne passent devant. Aucun appel supplémentaire.
5. **Filtres** : pastilles en haut de page (disposition A validée) : Tout · un par style suivi · Labels ·
   Mes artistes · ✨ Découvertes, chacune avec son nombre de sorties dans la semaine.
6. **Tâche de fond** dans le serveur : les appels MusicBrainz se font la nuit et au démarrage, pas à l'affichage.
   La page lit la base seulement ; changer de semaine ne déclenche aucun appel externe.
7. Bouton **↻ Actualiser** et mention « mis à jour il y a N min », avec limite de fréquence.
8. Rapprochement avec la bibliothèque (« Dans ta bibliothèque ») fait **côté serveur**, plus de 24 appels par page.

## Non-objectifs (version suivante)

- Partie communauté (« ce que suivent les autres »).
- Projets parallèles et collaborations via les relations MusicBrainz (piste 3).
- Notification du lundi.
- Autre source que MusicBrainz (Discogs écarté : pas de filtre par plage de dates ; Deezer : pas de styles fins).

## Anti-objectifs

- Une page qui attend MusicBrainz à l'ouverture ou au changement de semaine.
- Dépasser la cadence MusicBrainz (1 requête/s, partagée avec anecdotes, tags et exploration) : aucun second
  client ni second limiteur ; tout passe par la classe `MusicBrainz` existante.
- Des suggestions imposées : tout ce qui est automatique se voit et se retire.
- Perdre les styles déjà suivis (table `release_subscriptions`).

## Approches considérées

| | Principe | Verdict |
|---|---|---|
| A. À la demande | Appels à l'affichage, cache 1 h (fonctionnement actuel) | Écartée : une minute d'attente avec des dizaines d'artistes |
| B. Crontab | Processus séparé lancé par cron | Écartée : second processus dans le conteneur, second limiteur MusicBrainz |
| **C. Tâche de fond dans le serveur + base** | Fil `daemon` comme la lecture des flux de l'Actualité (`news.run`) | **Retenue** |

Pour la découverte, trois pistes : (1) artistes proches, (2) tri selon les tags, (3) relations MusicBrainz.
**1 et 2 retenues** pour cette version ; 3 reportée (fiable mais peu de résultats).

Disposition de page : trois maquettes montrées (pastilles en haut / colonne à gauche / onglets).
**A retenue** : pastilles de filtre en haut, réglage des sources dans un panneau « ⚙ Mes sources ».

## Ce qui a été décidé

### Synchronisation (tâche de fond)

- Un fil lancé dans `app.py` à côté de `news.run` : synchronise **au démarrage si la dernière synchronisation
  complète date de plus de 24 h**, puis **chaque nuit**. La mise en production lance donc la première
  synchronisation sans action manuelle.
- Elle traite l'**union dédoublonnée** des sources de tous les comptes : un label suivi par trois personnes coûte
  un appel.
- **Fenêtre de dates** : de J−14 à J+60 en une requête par source (ou par groupe d'artistes), avec pagination
  MusicBrainz (100 par page) et un plafond par source. Les semaines dans la fenêtre se lisent en base.
- **Styles : une requête par semaine** (*décision de conception*). Un style large (« rock ») dépasserait tout
  plafond sur 74 jours, et MusicBrainz trie par pertinence, pas par date : tronquer retirerait des sorties au
  hasard. Donc, pour chaque style suivi, une requête par semaine de la fenêtre (11 semaines), 2 pages de 100 au
  plus par semaine. Avec une dizaine de styles distincts sur le site : 110 à 220 appels, 2 à 4 min la nuit.
- **Labels : nouveautés seulement** (*décision de conception*), comme pour les styles : première sortie du groupe
  dans la fenêtre. La recherche `release` (seule à filtrer par label) donne des éditions ; on garde celles dont le
  groupe a sa première sortie dans la fenêtre, en lisant le groupe si besoin (appel mis en cache 7 jours ; un
  label sort peu de disques par semaine, le surcoût est faible). Le lien sortie ↔ source pointe vers le groupe.
- **Artistes groupés** dans une même requête (`arid:(a OR b …)` ou `artist:"…" OR …`), taille de groupe à
  déterminer en vérifiant la limite de longueur de requête.
- **Ajout d'une source** : synchronisation immédiate de cette seule source (en arrière-plan ; la page affiche
  « en cours » puis les résultats).
- **↻ Actualiser** : resynchronise les sources de la personne ; au plus une fois toutes les 10 min par compte
  (limite définie une seule fois côté serveur et envoyée au front).
- **Semaines hors fenêtre** (plus de 14 jours en arrière ou plus de 60 jours en avant) : seule la vue par style
  reste consultable à la demande, comme aujourd'hui (cache 1 h ; 7 jours pour une semaine passée). Les autres
  types de sources affichent « hors de la période suivie ».
- Interruption (redémarrage) : chaque source garde sa date de dernière synchronisation ; la reprise commence par
  les plus anciennes.

### Tendances et découvertes (calcul par compte, pendant la synchronisation)

- La tâche appelle Subsonic **au nom de chaque compte** (`Credentials.of(user)`, comme `ArtistIndexes`).
- **Artistes des tendances : signaux propres à chaque compte seulement.** La liste « plus écoutés » de Subsonic
  (`getAlbumList2 type=frequent`) est commune au serveur (confirmé par l'utilisateur) : elle n'est **pas**
  utilisée. Signaux retenus, du plus fort au plus faible : artistes, albums et morceaux favoris (`getStarred2`) ;
  albums bien notés sur le site (table `album_ratings`) ; marque-pages « À écouter » (artistes et albums).
  Plafond (ex. 30) défini une seule fois.
- Le site ne garde pas d'historique d'écoute par compte (le scrobble part vers Subsonic, puis Last.fm si la
  personne l'a relié) : un historique propre au site est une piste pour plus tard, hors de cette version.
- **Labels des tendances, via MusicBrainz** (choix de l'utilisateur) : pour chaque album favori ou bien noté,
  on retrouve son édition MusicBrainz (`find_releases`, puis `release_credits` qui donne ses labels) et on
  **enregistre en base le lien album ↔ label** (album Subsonic, MBID et nom du label, édition retenue, date de
  recherche ; un « rien trouvé » est aussi enregistré pour ne pas refaire la recherche à chaque nuit). Le lien
  sert ensuite sans appel. Ces labels entrent dans les sources suivies (origine « tendances ») et se décochent
  comme les autres. Discogs n'intervient pas. On ne lit pas le label dans Subsonic : il est stocké dans notre
  base, lié à l'identifiant de l'album (choix de l'utilisateur).
- **Styles des tendances** : styles du catalogue MusicBrainz les plus fréquents parmi les tags des artistes des
  tendances (déjà lus par la synchronisation). Même règle que les artistes et les labels des tendances
  (*décision de conception*) : suivis d'office, étiquetés « d'après tes écoutes », retirables, jamais réajoutés
  après retrait. Pas d'état « proposé » à part.
- **Découvertes, via Last.fm directement** (choix de l'utilisateur) : pour les artistes des tendances, appel
  `artist.getSimilar` de Last.fm, ajouté à la classe existante `webapp/providers/lastfm.py` (règle 1), et non
  `getArtistInfo2` de Subsonic, qui se limite en pratique aux artistes de la bibliothèque. On écarte les proches
  déjà présents dans la bibliothèque. Last.fm donne souvent le MBID de l'artiste, ce qui permet les requêtes
  groupées `arid:` ; sans MBID, on cherche par nom. Chaque proche est mémorisé avec l'artiste d'origine
  (« proche de X »). Résultats mis en cache 7 jours. Plafond de proches par compte. Si Last.fm n'est pas
  configuré (pas de clé), la pastille Découvertes n'apparaît pas et le panneau dit pourquoi.
- **Profil de tags** : tags pondérés de la bibliothèque de la personne (artistes des tendances), stocké par
  compte ; sert au tri (2).

### Modèle de données (nouvelles migrations, rien de modifié dans les publiées)

- **Sources d'un compte** : (compte, type ∈ {style, label, artiste, proche}, identité, nom affiché, origine ∈
  {manuel, tendances, découverte}, masqué, « proche de » pour les découvertes). Les styles de
  `release_subscriptions` y sont recopiés (origine manuel) par une migration testée sur une base remplie.
  Identité : le nom exact du catalogue pour un style (règle 4), le MBID pour un label ou un artiste quand il est
  connu, sinon le nom normalisé (`shared.text.normalize`) pour un proche sans MBID.
- **Sorties synchronisées** (partagées) : groupe de sorties MusicBrainz (MBID, titre, artiste, date, type, tags).
- **Lien sortie ↔ source** : quelle source a trouvé quelle sortie (une sortie peut venir de plusieurs sources).
- **État de synchronisation par source** : dernière réussite, dernier échec.
- **Lien album ↔ label** (partagé, la bibliothèque est commune) : album Subsonic, MBID et nom du label, édition
  MusicBrainz retenue, date de recherche, résultat vide possible. Réutilisable plus tard ailleurs (fiche album).
- Les tables des sorties sont purgées hors fenêtre (plus de 30 jours après la date).

### Page (disposition A)

- En-tête : semaine, flèches, « mis à jour il y a N min », ↻.
- Pastilles : Tout · chaque style · Labels · Mes artistes · ✨ Découvertes, avec leurs nombres. Changer de
  pastille ou de semaine remplace la grille seulement (règle 18).
- Carte : pochette, titre, artiste, type et date, **raison** (« label Warp », « tu l'écoutes »,
  « proche de Moderat »), « Dans ta bibliothèque » ou « Écouter » (recherche) comme aujourd'hui.
- Tri : ordre « pour toi » (score de ressemblance des tags) par défaut ; à score égal, par date.
- Panneau « ⚙ Mes sources » : trois groupes (Styles, Labels, Artistes), chaque source avec son origine et une
  croix ; recherche pour ajouter un label ou un artiste ; catalogue des styles comme aujourd'hui ; section
  Découvertes (activer ou couper, retirer un proche).
- Pochettes en chargement différé (`loading="lazy"`).
- **« Dans ta bibliothèque »** (*décision de conception*) : le but est de supprimer les 24 requêtes du
  navigateur. Le serveur fait les recherches Subsonic de la page en parallèle, au nom de la personne (ses droits
  de dossiers), et les met en cache quelques minutes ; la réponse de la semaine contient déjà le résultat. Pas
  d'index de bibliothèque en base dans cette version.
- Compte sans source ni écoutes : la page propose de choisir des styles (le style par défaut actuel reste la
  suggestion de départ).

### Règles du dépôt à respecter

Nouvelles requêtes dans la classe `MusicBrainz` uniquement ; paquet `webapp/weekly_releases/` (entités, service,
synchronisation dans des fichiers distincts) ; SQL dans `webapp/storage/` ; contrôleur mince ; limites définies une
fois ; 40 lignes par fonction, 300 par fichier ; tests écrits avant le code (unitaires + parcours jsdom) ; entrée
**1.22** dans `src/i18n/versions.yaml` ; documentation `docs/features/actualite.md` et guide Help mis à jour.

## Laissé au constructeur

- Taille des groupes d'artistes par requête et forme exacte (`arid` vs nom), après vérification.
- Formule exacte du score de ressemblance (ex. cosinus sur tags pondérés), tant que le tri reste stable et testé.
- Valeurs des plafonds (artistes de tendances, proches par compte, sorties par source), définies une seule fois.
- Heure de la synchronisation de nuit.

## À vérifier au début de l'implémentation

- Les résultats de recherche `release-group` de MusicBrainz contiennent-ils les tags ? Sinon, le tri (2) se fait
  sur les tags de l'artiste.
- `artist.getSimilar` renvoie-t-il des MBID pour la majorité des proches ? (La clé Last.fm est configurée en
  production.)
- Nombre d'écoutes par compte : non utilisé dans cette version (décision de l'utilisateur).

Document validé par l'utilisateur le 27/11/2026.
