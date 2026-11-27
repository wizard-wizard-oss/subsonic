# Consignes du dépôt

Ce fichier s'impose à **tout agent de code** (Claude, ChatGPT/Codex ou autre), pour toute modification et toute revue.
Lire aussi `docs/CONVENTIONS.md` (règles du projet) et `docs/architecture/README.md` (dépendances entre éditions).
Une règle de ce fichier ne se contourne pas : si elle bloque, le dire dans la réponse au lieu de l'ignorer.

## Développement et review

- Examiner la maintenabilité avec la correction fonctionnelle : signaler les responsabilités mélangées, les noms trompeurs et les règles métier dupliquées, avec un exemple concret et une correction proposée.
- Avant d’ajouter une comparaison de noms musicaux, chercher l’utilitaire existant. Utiliser `pimedia.shared.text.normalize` pour les clés de comparaison ; conserver les textes originaux pour l’affichage et les fichiers. Les identifiants, chemins et noms de comptes ont leurs propres règles.
- Garder le SQL dans les dépôts, qui renvoient des entités. Les entités décrivent les données ; les services portent les règles. Définir une seule fois les limites et options, puis les réutiliser dans la validation et les parcours. En review, lire les appels et les utilitaires voisins pour repérer les duplications au-delà du diff.

## Règles issues de la revue de la PR 2 (27/11/2026)

Chacune a été enfreinte au moins une fois. Avant de rendre un travail, relire cette liste et vérifier chaque point.

### Services externes
1. **Une seule classe par service externe** (MusicBrainz, Last.fm, Discogs, Wikipédia, paroles, Gravatar…), dans `src/pimedia/shared/providers/`. Elle porte la connexion, la cadence, le cache, les reprises et **toutes** les requêtes vers ce service. Avant d'appeler un service, chercher sa classe et y ajouter la méthode manquante ; ne jamais créer un second client.
2. **Aucune URL d'API externe hors de sa classe.** Un autre module n'écrit jamais `musicbrainz.org/ws/…`, `ws.audioscrobbler.com…`, etc., et ne lit pas le JSON brut d'un service : la classe renvoie des entités.
3. **Un seul transport HTTP** (`shared/providers/http.py`) : pas de `urllib.request`, `requests` ou `urlopen` ailleurs dans le code du site et le code commun (exception : le client Subsonic).
4. **Une même chose a une seule identité** envoyée au service et stockée en base (ex. un style = son nom exact dans le catalogue MusicBrainz). Pas de colonne qui accepte deux formats.

### Couches
5. **Contrôleur = requête HTTP → appel d'un service → `ok(entité.to_api())`.** Aucune règle métier, aucune boucle métier, aucun SQL dans un contrôleur.
6. **Un service n'importe jamais `controllers/`.** Les exceptions de droits vivent dans `webapp/errors.py`.
7. **Un service renvoie des entités** (avec `to_api()`), jamais un `dict` construit à la main.
8. **SQL uniquement dans `webapp/storage/` et `schema.py`.**

### Taille et rangement
9. **Dans `src/` : 40 lignes au plus par fonction** (Python et JS), hors tables de données littérales, **et 300 lignes au plus par fichier.** Découper avant de dépasser, pas après.
10. **Une fonctionnalité = un paquet** (`webapp/tags/`, `webapp/notifications/`…) avec ses entités et son service ; pas de nouveaux modules à plat dans `webapp/`. Un fichier = une responsabilité (ex. lecture des formats audio ≠ sécurité des fichiers ≠ journal de transaction).
11. **`app.py` assemble seulement** : chaque contrôleur déclare ses routes ; le câblage des services est à part.

### Règles et limites
12. **Chaque règle, limite, liste de champs ou valeur par défaut est définie une seule fois**, côté serveur, et envoyée au front si besoin. Pas de copie en dur dans un CHECK SQL, dans un second service ou dans le JS (ex. liste des champs de tags, style par défaut, longueur d'un nom, format d'un jeton de requête).
13. **Un utilitaire commun plutôt que deux variantes** (ex. `App.requestId()` dans `core.js` pour tous les identifiants de requête ; pas de `crypto.randomUUID()`, indisponible en HTTP sur le réseau local).

### Base de données
14. **Une migration publiée ne se modifie jamais** ; on en ajoute une. Toute migration qui change des données a un test qui part d'une base remplie dans la version précédente et vérifie que **rien n'est perdu** (lignes enfants comprises, `PRAGMA foreign_key_check` vide).
15. **Un seul modèle de lecture** : chaque message (notification, recommandation, commentaire) a un destinataire et une date `read_at`. Pas de nouveau mécanisme (jeton, curseur) sans accord.
16. **Une donnée décrite une seule fois** : pas de mêmes colonnes et CHECK recopiés dans plusieurs tables (ex. la cible écoutée vit dans `listening_targets`).
17. **Toute liste qui peut grandir est paginée** et lue sans sous-requête corrélée par ligne.

### Front
18. **Mettre à jour la partie concernée, pas toute la page** : un événement sur un élément ne redessine pas la page (filtres, sections ouvertes, pagination et défilement restent en place).
19. **Le texte venant des utilisateurs ou des services passe par `textContent` / `App.el(..., {text})`**, jamais par `innerHTML`.
20. **Un sondage a une fin** : intervalle croissant et arrêt avec une action « Reprendre ».

### Tests et livraison
21. **Chaque fonctionnalité ou correction arrive avec ses tests** (unitaires + parcours jsdom pour la page), **écrits et vus en échec avant le code**. Pendant le travail, relancer seulement les tests concernés ; la suite complète (`docker compose --profile tests run --rm tests`) tourne après les gros déplacements et avant la PR, et doit être verte : un parcours en échec ne part jamais dans une PR.
22. **Chaque modification visible du site ajoute une entrée dans `src/i18n/versions.yaml`** : nouvelle fonctionnalité = mineure, correction de bug = troisième numéro (1.19.2), jamais un changement de libellé numéroté comme correction de bug.
23. **Une PR = un sujet**, avec un titre et une description qui disent ce qu'elle contient. Le nom de la branche correspond à son contenu.
