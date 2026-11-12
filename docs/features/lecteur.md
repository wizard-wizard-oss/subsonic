# Lecteur et file d'attente (site web)

## Ce que ça fait
- Barre du bas : précédent/lecture/suivant, position, volume (gardé dans le navigateur), pochette et titre, boutons file
  et paroles. Raccourcis : Espace, N, P, ← →, / (recherche), A (barre), C (salon), L (paroles), ? (aide), Échap.
- Moteur (`engine.js`) : audio du navigateur (flux Subsonic relayé par le site `/api/stream`, droit `stream`), son Jamendo,
  ou lecteur officiel YouTube, vidéo en haut du panneau de droite. Media Session (touches multimédia).
- **File d'attente** (`queue.js`) : s'ouvre au survol du lecteur (0,7 s) ou au bouton ☰ ; colonnes pochette (27/10/2026), titre, album, artiste,
  durée, genre, année, format ; « N titres • durée » ; « Vider la suite » ; « Annuler » (20 niveaux) ; glisser-déposer des
  lignes (poignée ⋮⋮) ou Alt+↑/↓ ; Entrée lit, Suppr retire ; fermeture au clic ailleurs, Échap.
- **Écoute signalée à Subsonic** : « en cours » au démarrage de chaque titre Subsonic, « écoutée » après la moitié du titre
  ou 4 minutes réellement écoutées (un saut en avant ne compte pas). Voir `ecoute-en-cours.md`.

## File sauvegardée (1.10.1)
- Au démarrage et après reconnexion, le lecteur utilise `getPlayQueue` via `GET /api/play-queue`.
  Il affiche les titres dans leur ordre, marque le titre courant et sa position, sans charger de flux,
  ouvrir YouTube/SoundCloud ni compter une écoute. Le bouton Lecture reprend à la position gardée.
- Chaque modification de file est copiée immédiatement dans `localStorage`, sous une clé propre au compte.
  `savePlayQueue` reçoit les identifiants Subsonic répétés, le titre courant et la position en millisecondes,
  via `POST /api/play-queue/save`. Envoi différé de 600 ms, écritures sérialisées, points de sauvegarde
  toutes les 15 secondes, à la pause, au masquage et au départ de la page, et avant déconnexion explicite.
  Au départ, les requêtes de moins de 60 ko utilisent `keepalive` ; la copie locale prend le relais sinon.
  L'envoi à Subsonic utilise un POST pour les longues files ; maximum 5 000 titres, sans troncature silencieuse.
- Après déconnexion puis reconnexion, la file reste attachée au compte Subsonic ; un autre navigateur la retrouve
  également. La copie locale conserve les métadonnées, les doublons avec leur rang exact et les sources externes.
  Si Subsonic renvoie la dernière file envoyée, cette copie complète est conservée. Une file différente enregistrée
  par une autre application remplace la copie déjà synchronisée. Une modification locale encore en attente prime.
- Si Subsonic est injoignable, la copie locale reste affichée ; les changements sont réessayés au retour du réseau
  ou au point de sauvegarde suivant. Sans copie locale, le retour du réseau réessaie la restauration.
  Une réponse lente ne remplace pas une nouvelle sélection ni la file d'un autre compte.
- API officielle vérifiée le 12/11/2026 : [Subsonic, getPlayQueue et savePlayQueue](https://www.subsonic.org/pages/api.jsp#getPlayQueue),
  disponibles depuis l'API 1.12.0 ; déjà exposées par le serveur du projet, désormais branchées au lecteur web.

## Où
`web-pc/static/js/player.js`, `engine.js`, `queue.js`, `queue-memory.js`, `app.js`, `css/player.css` ;
serveur : `controllers/library.py` (`/api/stream`), `webapp/listening.py`, `controllers/listening.py` (file).

## Tests
`tests/e2e_webapp.js` (lecteur, écoute comptée à la moitié), `tests/e2e_webapp_queue.js` (composants,
restauration serveur et locale, rafraîchissement, réseau coupé puis retrouvé, sources mixtes, doublons,
position, réponses lentes, écritures sérialisées, changements de comptes et stockage refusé).
`tests/test_webapp_music.py::ListeningHttpTest` : HTTP authentifié, reconnexion, isolation, unités,
validation/CSRF et file de 3 000 titres envoyée en POST. Validation du 12/11/2026 : 694 tests Python et
sept parcours jsdom réussis dans Docker sans réseau externe, puis les deux parcours PC rejoués sur le code final
(32 contrôles dédiés à la file). Parcours jsdom : **pas de vrai son testé**.
Publication du 12/11/2026 sur https://music2.foos.fr : version 1.10.1 et conteneur sain,
216 fichiers applicatifs identiques, scripts modifiés servis avec leur empreinte de cache, protections
session/CSRF vérifiées. La page publique a été chargée dans jsdom : connexion en français et composant
de file présent, sans erreur JavaScript. Les parcours connectés restent exécutés sur le faux Subsonic ;
aucune file ni identité de production utilisée pour ces contrôles.

## N'existe pas / pas vérifié
- Mode haute fidélité (mpv) : **seulement sur le Pi**.
- Les titres externes restent dans ce navigateur : l'API Subsonic ne stocke que ses propres morceaux.
  Une file entièrement externe ne remplace pas la file Subsonic ; sur un autre navigateur, seule cette dernière existe.
- L'API standard identifie le titre courant par son ID : si ce titre figure plusieurs fois, seul le navigateur
  ayant la copie locale peut retrouver son rang exact. Les autres clients prennent sa première occurrence.
- Le site ne possède pas de service worker : si le serveur web lui-même est inaccessible, un chargement complet
  de la page hors réseau n'est pas garanti. La copie locale reste stockée, mais il faut pouvoir charger le site
  et authentifier le compte pour l'afficher. Aucun flux audio n'est mis en cache pour écouter hors ligne.
- Stockage bloqué/plein ou effacé : seule la sauvegarde Subsonic reste disponible ; si cette API est indisponible
  également, aucune persistance durable n'est possible. L'interface et la lecture continuent à fonctionner.
- Pas de synchronisation en direct entre plusieurs appareils ouverts : la restauration lit le serveur au démarrage
  et à la reconnexion ; le dernier envoi gagne. Les changements de position non sauvegardés peuvent représenter
  jusqu'à 15 secondes si le navigateur se ferme brutalement sans événement de départ.
- Marque-pages : routes prêtes, pas branchées dans la page.
- Pas de répétition (boucle) ni de mode aléatoire sur la file en cours (le mélange se fait au lancement d'un album).
- Pas vérifié : lecture avec un vrai Subsonic derrière le proxy, YouTube avec de vraies clés.
