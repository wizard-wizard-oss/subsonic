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

## Où
`web-pc/static/js/player.js`, `engine.js`, `queue.js`, `css/player.css` ; serveur : `controllers/library.py` (`/api/stream`).

## Tests
`tests/e2e_webapp.js` (lecteur, écoute comptée à la moitié), parcours jsdom seulement : **pas de vrai son testé**.

## N'existe pas / pas vérifié
- Mode haute fidélité (mpv) : **seulement sur le Pi**.
- File partagée avec les applis (`getPlayQueue`/`savePlayQueue`) et marque-pages : routes serveur prêtes, **pas branchées dans la page**.
- La file n'est pas gardée entre deux visites (rien n'est restauré au rechargement).
- Pas de répétition (boucle) ni de mode aléatoire sur la file en cours (le mélange se fait au lancement d'un album).
- Pas vérifié : lecture avec un vrai Subsonic derrière le proxy, YouTube avec de vraies clés.
