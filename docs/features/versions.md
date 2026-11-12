# Versions : l'historique des mises à jour du site (site web)

## Ce que ça fait
Page **« Versions »** (`#/versions`) : ce qui a changé sur le site, **version par version, la plus récente en haut**,
chacune avec son numéro (« majeure.mineure » ou « majeure.mineure.correction »), sa **date de mise en ligne**, un titre et la liste des changements, écrits
pour les personnes qui utilisent le site. Le numéro de la dernière version (ex. `v1.2`) est affiché **à côté du titre du
site** (lien vers la page) ; une **pastille rouge** dessus et la mention « Nouveau » sur les versions pas encore vues
signalent une mise à jour. Ouvrir la page la marque comme vue. Lien aussi en haut de la page « Nouveautés ».

## Tenir l'historique (à CHAQUE modification du site)
- Le contenu est dans **`src/i18n/versions.yaml`** : ajouter une entrée **en tête** avant de déployer, **à chaque fois**.
  Évolution, finition visuelle ou correction de la même fonctionnalité : **troisième niveau** (1.7.1 → 1.7.2 → 1.7.3).
  Fonctionnalité distincte : **mineure** ; grand changement : **majeure** (décision utilisateur du 07/11/2026).
- Le numéro doit grandir et la date ne pas reculer ; un champ manquant ou mal écrit **empêche le site de démarrer**
  (`InvalidVersions`) et fait échouer `tests/test_versions.py`.
- `deploy/pc/push.sh` affiche la version déployée et rappelle d'en ajouter une si la plus récente n'est pas datée du jour
  (rappel seulement, il ne bloque pas).
- Exception explicite du 07/11/2026 : la livraison brièvement publiée comme 1.8 est renumérotée **1.7.3** à la
  demande de l'utilisateur. Le navigateur recale un numéro vu retiré de l'historique pour conserver les prochaines pastilles.

## Où
`pimedia/webapp/versions.py` (lecture et contrôle du fichier), route publique `GET /api/versions` dans `app.py`,
`web-pc/static/js/versions.js` (page, numéro et pastille), `index.html` (`#version-tag`), `i18n/fr.yaml`
(`webapp.versions`, `webapp.whatsnew.versions`), `web-pc/static/css/layout.css` (`.version-tag`) et `views.css` (`.version*`).

## Tests
`tests/test_versions.py` (vrai fichier bien tenu, ordre 1.10 > 1.9, fichiers mal tenus refusés),
`tests/test_webapp.py` (`/api/versions`), `tests/e2e_webapp.js` (numéro et pastille, page, pastille retirée, lien
depuis Nouveautés). Vu à l'écran sur la démo.

## N'existe pas / limites
- « Déjà vue » est retenu **par navigateur** (stockage local), pas par compte : sur un autre ordinateur, la pastille
  revient une fois. Navigation privée : elle revient à chaque visite.
- Pas de notification hors du site.
- L'historique avant la 1.1 a été reconstitué d'après `docs/ETAT.md` (versions 0.1, 0.2, 1.0).
