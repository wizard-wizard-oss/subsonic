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
  **Évolution, finition visuelle ou correction de la même fonctionnalité : troisième niveau** (1.7.1, 1.7.2,
  1.7.3…). Décision utilisateur du 08/11/2026 : le lot de fiches artiste/album, choix Discogs mémorisé, biographie,
  images et raccourcis est la **1.8** ; la retouche des compteurs est la **1.7.13**, après la 1.7.12.
  Réserver la version **mineure** à une fonctionnalité distincte ou à un lot significatif, et la
  **majeure** à un grand changement. Rien ne part en production sans cette entrée.
