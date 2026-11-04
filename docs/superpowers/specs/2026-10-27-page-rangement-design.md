# Page « Rangement » : voir où vont les albums, réunir les groupes en double

Date : 27/10/2026. Édition PC (`src/pimedia/webapp/`, `src/web-pc/`).

## Pourquoi
Le site range seul les albums envoyés ou corrigés dans `Incoming` (`docs/features/envoi-fichiers.md`). Le 27/10/2026,
environ 85 albums sont partis d'un coup après un problème de droits ; on n'en voit la liste que dans le journal du
conteneur. L'administrateur veut **voir où chaque album est allé**, savoir **pourquoi un album reste dans Incoming**, et
**repérer les groupes éparpillés sous plusieurs noms** pour les réunir.

Cas réel : la bibliothèque a trois dossiers pour le même groupe, `Osees`, `Thee Oh Sees` et `Thee Oh Sees _ Osees`
(le groupe de John Dwyer a changé de nom de nombreuses fois : OCS, The Ohsees, Thee Oh Sees, Oh Sees, Osees depuis 2020).
Le rangement automatique ne rapproche que les noms identiques aux majuscules et accents près ; il ne peut pas deviner
un changement de nom.

## Pour qui
Les **administrateurs Subsonic** (`user.is_admin`), seulement. Les autres comptes ne voient ni le lien ni la page, et
l'API répond « droit manquant ».

## Ce que la page montre

### 1. Ce qui a été rangé
- Liste des albums rangés, du plus récent au plus ancien : date, `Artiste/Album` d'arrivée, nom d'origine dans Incoming
  (ou dans le zip) quand il diffère, et la façon : **envoi** (rangé aussitôt, avec le compte qui a envoyé) ou
  **rattrapage d'Incoming**.
- Le rangement doit donc être **noté en base** à chaque album rangé (aujourd'hui il n'est écrit que dans le journal).
  Rien n'existe avant cette nouveauté : la liste commence au déploiement.
- Un album rapproché d'un artiste existant sous une autre écriture (« Lamb of God » → `Lamb Of God`) est signalé : c'est
  là qu'on vérifie que le rapprochement est bon.

### 2. Ce qui reste dans Incoming, et pourquoi
Pour chaque album d'Incoming (`Incoming/Artiste/Album`, et les titres seuls à la racine), la raison, avec les règles
du rangement automatique : pas de majuscule, sous-dossiers hors nomenclature, album déjà présent chez l'artiste (avec
le dossier en question), nom caché (commence par un point), en attente (modifié il y a moins de `INCOMING_WAIT_HOURS`),
ou « prêt, rangé au prochain passage ». La page ne fait que constater : on corrige toujours dans Incoming, à la main.

### 3. Groupes en double
Des **propositions** de dossiers d'artistes qui sont sans doute le même groupe, de deux sortes :
- **Écriture proche** : noms identiques une fois la ponctuation et les espaces mis de côté, ou un nom fait de deux noms
  séparés par ` _ ` (trace d'un « / » dans une étiquette) dont l'un est un autre dossier (`Thee Oh Sees _ Osees` et
  `Osees`, `Thee Oh Sees`).
- **Changement de nom connu** : une base musicale en ligne, **MusicBrainz**, dit que deux dossiers sont le même artiste
  (son nom et ses alias). Elle donne aussi le **nom actuel** du groupe, affiché comme suggestion.

Les **collaborations gardent leur propre dossier** et ne sont jamais proposées au regroupement avec l'artiste principal
(`Jay Worthy & Harry Fraud`, `Jay Worthy, George Clinton & LNDN DRGS` restent à part de `Jay Worthy`). Décision de
l'administrateur, « pour le moment ».

Les noms en `A _ B` peuvent aussi être un disque partagé (`Melvins _ Napalm Death`) : ils sont proposés quand même,
l'administrateur écarte ceux qui n'en sont pas (choix de Claude).

**Rapprochement MusicBrainz** (choix de Claude) : un dossier n'est rattaché à un artiste MusicBrainz que si son nom
correspond exactement (majuscules et accents mis à part) au nom ou à un alias d'**un seul** artiste ; plusieurs
candidats (groupes homonymes, ex. Converge) = pas de rattachement. Mieux vaut peu de propositions que des fausses. Les
étiquettes des fichiers (identifiants MusicBrainz) ne sont pas lues. Un « nom actuel » qui ne respecte pas la
nomenclature (majuscule) n'est pas proposé tel quel.

Chaque proposition affiche, pour chaque dossier : ses albums, et **ce qui serait perdu** si on le déplace (voir plus bas).

## Réunir un groupe
1. L'administrateur choisit le **nom à garder** : un des dossiers existants, ou le nom actuel donné par MusicBrainz
   (le dossier est alors créé ou renommé), et quels dossiers y verser.
2. Avant de valider, il voit **ce qui serait perdu** : Subsonic reconnaît un titre par son chemin, un album déplacé
   devient en partie un nouvel album pour lui. Candidats, pour les albums des dossiers déplacés :
   - les cœurs (titres, albums, artiste) ;
   - les entrées dans des playlists ;
   - les étoiles posées sur les dossiers d'albums ;
   - les commentaires d'album du site (`chat_messages`, sujet `album:<id>`).
   **Première étape du travail** (choix de Claude) : constater sur une copie (Subsonic `gzurowski/subsonic` de test,
   jamais la bibliothèque réelle) ce qui est vraiment perdu après déplacement et scan. Les identifiants de titres et de
   dossiers suivent le chemin ; ceux d'album et d'artiste (par étiquettes) suivent peut-être le nom et survivraient.
   La page n'affiche **que les pertes constatées**. Si les commentaires du site changent d'identifiant d'album, le site
   les **reporte** sur le nouvel album après le scan (ce sont ses propres données).
   Le site ne peut lire les cœurs et playlists que des comptes qui se sont déjà connectés à lui (il garde leur jeton
   Subsonic) : la page le dit (« d'après les N comptes connus du site »). Il y a peu de comptes : si c'est peu ou rien,
   on réunit sans hésiter, c'est le but de l'affichage.
3. Le site **déplace chaque album** dans le dossier gardé, d'un coup par album (comme `MusicTree.place`). Il **n'écrase
   jamais** : un album du même nom (majuscules et accents mis à part) déjà présent reste où il est et est signalé. Un
   dossier vidé est supprimé (avec ses fichiers cachés, comme pour Incoming). Puis Subsonic scanne (`scan_as_admin`).
4. Le regroupement est noté dans la liste « Ce qui a été rangé » (chaque album déplacé, façon **regroupement**).

Une proposition peut être **écartée** (« ce ne sont pas les mêmes ») : elle n'est plus proposée.

## Objectifs, non-objectifs, à ne surtout pas faire
- **Objectifs** : voir le résultat du rangement ; comprendre ce qui reste ; réunir un groupe éparpillé en sachant ce
  qu'on perd.
- **Non-objectifs (pour l'instant)** : déplacer un album seul vers un autre artiste depuis la page ; regrouper les
  collaborations ; corriger les noms des albums ; reprendre l'historique d'avant le déploiement ; garder les cœurs,
  étoiles et playlists de Subsonic lors d'un déplacement ; **se souvenir d'un regroupement** : un album envoyé plus
  tard sous l'ancien nom recrée l'ancien dossier, et la page le propose de nouveau (rare, décision de
  l'administrateur) ; appels à une IA (Sonnet) pour deviner les cas que MusicBrainz ne connaît pas.
- **À ne surtout pas faire** : réunir ou renommer quoi que ce soit sans validation de l'administrateur ; écraser ou
  effacer un titre ; toucher aux dossiers pendant que le rattrapage d'Incoming les déplace (les deux ne doivent pas
  travailler en même temps sur la bibliothèque).

## Contraintes
- Règles du projet (`docs/CONVENTIONS.md`) : couches dépôt → service → contrôleur, migration numérotée dans `schema.py`,
  textes dans `i18n/fr.yaml`, pas d'`innerHTML`, un fichier JS par composant, écritures protégées (CSRF), tests unitaires
  + intégration + parcours jsdom, fiche `docs/features/` et `docs/ETAT.md` à jour.
- MusicBrainz : **une requête par seconde au plus**, `User-Agent` qui nomme l'application (sans l'adresse e-mail de
  l'utilisateur), réponses gardées en base pour ne pas redemander. La bibliothèque compte ~4 850 dossiers d'artistes :
  le premier passage prend plus d'une heure, il se fait en tâche de fond, puis seuls les nouveaux artistes sont
  demandés. Sans réseau ou si MusicBrainz ne répond pas, la page montre quand même les écritures proches.
- Sur le serveur, le disque distingue les majuscules (`converge` ≠ `Converge`) ; sur macOS non (tests).
- Le site écrit dans la musique sous l'uid 1001 / gid 100 ; les dossiers d'artistes lui ont été rendus le 27/10/2026.

## À vérifier
- Ce que Subsonic perd quand un dossier change de chemin (première étape, voir « Réunir un groupe »).
- Que MusicBrainz connaît bien les groupes de la bibliothèque (un premier essai rapide n'a rien donné : recherche exacte
  vide, puis refus probablement dû à des requêtes trop rapprochées).

## Laissé au constructeur
L'emplacement du lien (menu du haut, à côté d'« Envoyer », ou réglages), la présentation des trois parties (onglets ou
une seule page), la règle exacte de comparaison des écritures proches, la façon de reconnaître une collaboration
(` & `, `, `, `feat.`… en gardant les groupes dont le nom contient « & »), le rythme de la tâche MusicBrainz, le
format des tables, le verrou qui empêche rattrapage d'Incoming, rangement d'un envoi et regroupement de travailler en
même temps, ce sur quoi repose une proposition écartée.
