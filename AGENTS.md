# Consignes du dépôt

Lire `docs/CONVENTIONS.md` pour les règles du projet et `docs/architecture/README.md` pour les dépendances entre éditions.

## Développement et review

- Examiner la maintenabilité avec la correction fonctionnelle : signaler les responsabilités mélangées, les noms trompeurs et les règles métier dupliquées, avec un exemple concret et une correction proposée.
- Avant d’ajouter une comparaison de noms musicaux, chercher l’utilitaire existant. Utiliser `pimedia.shared.text.normalize` pour les clés de comparaison ; conserver les textes originaux pour l’affichage et les fichiers. Les identifiants, chemins et noms de comptes ont leurs propres règles.
- Garder le SQL dans les dépôts, qui renvoient des entités. Les entités décrivent les données ; les services portent les règles. Définir une seule fois les limites et options, puis les réutiliser dans la validation et les parcours. En review, lire les appels et les utilitaires voisins pour repérer les duplications au-delà du diff.
