# Règles du projet

Projet durable : code propre et testé dès la première ligne, pas de « on verra plus tard ».

## Organisation
- Deux éditions séparées, aucune branche `if serveur` / `if Pi` dans le code :
  - **Pi** (un utilisateur, écran tactile 800×480) : `src/pimedia/server/`, `src/pimedia/menu/`, `src/web/` ;
  - **PC** (plusieurs utilisateurs, souris et clavier) : `src/pimedia/webapp/`, `src/web-pc/`.
- Socle commun : `pimedia/storage/database.py`, `envfile.py`, `i18n.py`, `pimedia/server/transport.py`.
- Racine du projet : un dossier par rôle (`src/` code, `tests/`, `docker/`, `deploy/pi|pc`, `docs/`), rien d'autre
  que `README.md`, `compose.yaml`, `requirements.txt`. Tout chemin de code est relatif à `src/`.
- Couches : dépôts (SQL seulement, renvoient des entités) → services (règles) → contrôleurs (HTTP seulement).
  Un seul endroit assemble tout (`app.py`).

## Données
- **API Subsonic en priorité** : pour la bibliothèque musicale et les fonctions gérées par Subsonic, utiliser son API
  au maximum (navigation, recherche, métadonnées, lecture, mix, favoris, notes, playlists…). Réutiliser les clients
  existants ; éviter un accès direct à ses fichiers ou à sa base interne lorsqu'une opération est couverte par l'API.
- **Les tags restent dans les fichiers audio**, puis sont indexés et exposés par Subsonic. Ne pas créer dans la base
  du site une copie des tags, un historique de leurs valeurs ou un second catalogue musical sans décision explicite.
  Les données propres au site et les caches techniques existants gardent leurs responsabilités distinctes.
- Si l'API ne couvre pas une opération nécessaire, limiter l'accès aux fichiers à ce besoin : par exemple l'écriture
  des tags, avec lecture ciblée des champs que l'API n'expose pas et préservation des autres métadonnées. Après une
  correction, demander une réindexation à Subsonic, puis relire et vérifier les données par son API.
- Tables et colonnes en anglais, migrations numérotées (`schema.py`), jamais modifier une migration publiée.
- Entités en dataclasses avec `to_api()` ; pas de dictionnaires qui traînent entre les couches.
- Secrets dans `.env` (hors code, hors archive) ; jamais de mot de passe en base (jeton Subsonic seulement).
- Chemins d'installation, adresses du serveur et identifiants personnels : configuration, environnement ou arguments
  de commande. Aucun chemin personnel codé en dur, y compris dans un script de diagnostic temporaire. Les chemins
  internes au projet se calculent depuis son emplacement ; un dossier personnel se résout avec le système.
  Les exemples de commande utilisent des noms génériques.

## Interface
- Textes en français dans `i18n/fr.yaml`, clés en anglais ; aucun texte en dur dans le code.
- Couleurs en variables (thèmes) ; aucun HTML construit par concaténation (nœuds DOM, pas d'`innerHTML`).
- JavaScript sans outil de build, un fichier par composant.

## Qualité
- Chaque fonctionnalité arrive avec ses tests (unitaires + intégration + parcours jsdom pour la page).
- Écritures protégées (en-tête CSRF), entrées validées côté serveur, erreurs renvoyées comme clés de texte.
- Commentaires et noms clairs, petites fonctions, pas de duplication.

## Documentation
- Toute fonctionnalité ajoutée, changée ou retirée met à jour sa fiche dans `docs/features/` (ce qu'elle fait de A à Z, où est le code,
  quels tests, ce qui n'existe pas ou n'est pas vérifié), et `docs/ETAT.md` pour l'état et les décisions.
- Tout déplacement de code entre la zone Pi, la zone web et `shared/` met à jour `docs/architecture/`.
- Un changement de déploiement met à jour `docs/DEPLOIEMENT.md`.
- **Toute modification du site met à jour la version**, à chaque fois, avant le déploiement : une entrée datée en tête de
  `src/i18n/versions.yaml` (page « Versions », écrite pour les utilisateurs ; voir `docs/features/versions.md`).
  **Nomenclature confirmée par l'utilisateur le 22/11/2026** :
  - **Mineure** (`1.13` → `1.14`) : ajout d'une fonctionnalité ou d'un comportement, y compris l'enrichissement
    d'une fonctionnalité existante. Les commentaires privés des recommandations sont la **1.14**.
  - **Correctif, troisième numéro** (`1.14.1`) : correction d'un bug uniquement. Ne pas numéroter une nouvelle
    possibilité comme un correctif au motif qu'elle complète une fonctionnalité existante.
  - **Majeure** : grand changement ou rupture de compatibilité.
  Les versions déjà publiées conservent leur numéro ; cette règle s'applique aux prochaines livraisons.
  Rien ne part en production sans son entrée datée.
