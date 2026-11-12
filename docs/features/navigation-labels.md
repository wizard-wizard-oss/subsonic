# Navigation par labels (web) — brouillon

Noté le 08/11/2026 à la demande utilisateur. **Conception pour plus tard, non implémentée et non déployée.**
Les échanges et la maquette sur les fiches artiste/album ne déclenchent pas sa réalisation.

## Intention

Naviguer dans les labels présents dans la bibliothèque comme on navigue dans les artistes, puis approfondir
leur catalogue et compléter l’écoute avec YouTube. La navigation courante doit fonctionner depuis un index
persistant, sans refaire une recherche Discogs ou YouTube à chaque visite.

## Parcours envisagé

- Une entrée « Labels » donne une liste recherchable des labels identifiés dans les albums accessibles au compte.
- Chaque label ouvre une vraie page : logo lorsqu’il est disponible, nom et repères connus (pays, création…),
  histoire courte et sourcée avec « Lire la suite », artistes et pochettes. Informations absentes laissées absentes ;
  origine des textes/images et date d’actualisation conservées.
- Trois vues : « Dans ma bibliothèque », « Tout le catalogue », « À découvrir ». Le catalogue non encore analysé
  est distingué d’un catalogue vide ; un rapprochement incertain ne devient pas une absence certaine.
- Chaque disque indique sa présence locale et les versions YouTube déjà vérifiées. Distinguer une disponibilité
  complète, des pistes partielles, une recherche non effectuée et une recherche sans résultat.
- Le choix d’une version YouTube est mémorisé et réutilisé ; les liens devenus indisponibles peuvent être revérifiés.
  Écoute officielle et playlists mixtes existantes, sans téléchargement de média.
- « Découvrir le label » et « Top du label » réutilisent les services existants et leurs critères affichés.
  Depuis un album, les labels identifiés renvoient vers ces pages.

## Données envisagées

- `labels` : identité interne, identifiants des sources, nom original, éléments de présentation et provenance.
- `albums` ou une projection dédiée : inventaire des disques et références de catalogue, en séparant l’identité
  d’un disque de son éventuelle édition locale. Le projet n’a pas encore de table complète d’albums persistés.
- `album_labels` : relation plusieurs-à-plusieurs, édition/source ayant établi le lien et état de confirmation.
- Associations vers les sources d’écoute : réutiliser le stockage YouTube existant, en y reliant les choix validés
  au disque ou à la piste. Un disque peut être disponible à la fois dans la bibliothèque et sur YouTube.

Ce sont des propositions de modèle, pas des migrations préparées. Le cache public `music_metadata` (24 h) reste
distinct de cet index et des décisions durables. La présence locale suit les dossiers autorisés du compte,
comme l’index des artistes ; elle ne se déduit pas du catalogue public partagé.

## Construction envisagée

1. Inventorier les albums de la bibliothèque et lire les informations de label disponibles. Vérifier ce que le
   serveur Subsonic expose réellement ; prévoir la lecture des tags si nécessaire, sans supposer un champ universel.
2. Enrichir progressivement avec Discogs : travail en arrière-plan, borné, reprenable, avec progression et états
   « à confirmer » pour les identités ou éditions ambiguës. Distinguer label musical et société de droits/fabrication.
3. Actualiser les albums ajoutés ou modifiés après les scans, en conservant les rapprochements déjà confirmés.
4. Étendre ensuite les catalogues des labels identifiés et les correspondances YouTube, à la demande et par lots.

Rééditions regroupées pour la présentation, sans perdre les relations propres à chaque édition ni les albums
publiés chez plusieurs labels. Pas de scan de tous les labels mondiaux nécessaire pour démarrer.

## Périmètre et questions restant à concevoir

- Commencer par la navigation dans les labels de la bibliothèque ; enrichir ensuite le catalogue et l’écoute externe.
- Choisir les règles de partage/correction des rapprochements, la fréquence d’actualisation et les possibilités
  de conservation des textes et images de chaque source.
- Reprendre les cartes, icônes, thèmes et dialogues de l’application, avec une hiérarchie visuelle soignée.
- Aucun code, test d’indexation, migration ou déploiement réalisé pour ce brouillon.

Fonctionnalité actuelle : [découverte des labels et discographies Discogs](decouverte-labels.md).
