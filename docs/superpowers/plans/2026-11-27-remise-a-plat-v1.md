# Remise à plat de l'architecture avant la v1 — plan d'exécution

> **Pour les agents :** sous-skill requise : superpowers:executing-plans (ou superpowers:subagent-driven-development). Les étapes utilisent des cases `- [ ]`.

**But :** reprendre tout le contenu de la PR 2 (1.10.2 → 1.19.1) pour que le code respecte les règles de base. Chaque service externe a une seule classe, les couches sont propres, il n'y a pas de duplication, les fonctions et les fichiers restent courts, les bugs relevés en revue sont corrigés et la suite de tests est verte. Le tout est livré dans **une seule PR** vers `main`, qui remplace la PR 2.

**Architecture :**
- Tous les fournisseurs externes passent dans `src/pimedia/shared/providers/`, avec un seul transport HTTP, un seul cache de métadonnées et un module par fournisseur.
- Les services n'importent plus rien de `controllers/`.
- Les fonctionnalités de la PR 2 sont rangées en paquets par fonctionnalité, comme `library/` l'est déjà. Le SQL reste dans `storage/`.
- `app.py` ne fait plus qu'assembler : chaque contrôleur déclare ses routes, et le câblage des services va dans son propre module.
- Côté front, les gros modules et les longues fonctions sont découpés, et les règles (listes de champs, style par défaut, identifiants de requête) sont fournies par le serveur ou par `core.js`.

**Pile technique :** Python 3.11 (conteneur `docker/tests`), SQLite, `unittest`, JS sans bundler (scripts chargés par `src/web-pc/index.html`), parcours jsdom (`tests/run_e2e.py`).

**Référence :** la revue de la PR 2 du 27/11/2026 (constats repris dans chaque tâche), `AGENTS.md`, `docs/CONVENTIONS.md`, `docs/architecture/README.md`.

## Contraintes globales

- **Base de départ :** la branche `refactor/v1-architecture`, créée depuis `origin/feature/1.7.5` (tête `c3d590f`) dans un *worktree* séparé de `sources/`. Le clone `sources/` actuel (sur un ancien `main`, avec des fichiers `.idea/` indexés) n'est pas touché.
- **Le comportement visible ne change pas**, sauf pour les bugs listés dans la tâche 12. Chaque tâche se termine sur une suite verte.
- **Tests :** `docker compose -p v1 --profile tests run --rm --build tests` lance les tests unitaires et les parcours jsdom. Pour une tâche ciblée, lancer seulement les modules concernés : `docker compose -p v1 --profile tests run --rm tests python3 -m unittest tests.test_x`.
- **SQL :** uniquement dans `src/pimedia/webapp/storage/*.py` et `schema.py`. Les dépôts renvoient des entités.
- **Contrôleurs :** ils lisent la requête, appellent un service et renvoient `ok(entity.to_api())`. Aucune règle, aucune boucle métier.
- **Services :** ils renvoient des entités avec `to_api()`, jamais de `dict` construit à la main.
- **Taille :** 40 lignes au plus par fonction (Python et JS), hors tables de données littérales. 300 lignes au plus par fichier Python ou JS. Les exceptions existantes sont listées une fois dans `tests/test_code_size.py` et ne peuvent que diminuer.
- **Services externes :** un module par fournisseur dans `shared/providers/`. Tout appel HTTP du site et du code commun passe par `shared/providers/http.py`. Seule exception : `webapp/subsonic.py`, le serveur de musique local en flux continu.
- **Limites et options :** définies une seule fois, puis réutilisées pour la validation, le SQL et le front (voir la tâche 8).
- **Comparaisons de noms musicaux :** `pimedia.shared.text.normalize`.
- **Versions :** une seule entrée dans `src/i18n/versions.yaml`, `1.19.2`, datée du jour de mise en ligne. Elle décrit seulement les corrections visibles de la tâche 12. Le refactoring invisible n'y apparaît pas.
- **Commits :** un par tâche, en français, au format `refactor: …`, `fix: …` ou `test: …`. Aucun push ni aucune PR sans l'accord de Thomas.

## Points de vigilance de la revue

1. **Le Pi (édition `server/`) fonctionne sans la base du site.** Les genres et les anecdotes MusicBrainz passent par `MemoryStore`, et `server/` n'importe jamais `webapp/`. Ce point est vérifié par `test_architecture`, plus un test dans la tâche 3.
2. **La base de production (version 23) migre jusqu'à la version 28 sans perte.**
   - Aucune reconstruction de table ne déclenche de cascade (tâche 1 b).
   - États lu/non lu, cibles et abonnements sont repris à l'identique (tâche 1 c).
   - Seules les anciennes clés de cache MusicBrainz sont purgées (tâche 3).
   - Test de bout en bout : une copie anonymisée du schéma de production en version 23, avec des lignes dans chaque table touchée.
3. **Un fournisseur en panne, ou qui répond 403 ou 404, sert la copie périmée de moins de 30 jours** au lieu d'une erreur 503. Tests dans la tâche 2 (socle) et dans la tâche 3.
4. **Deux requêtes simultanées sur des clés différentes ne s'attendent pas**, au-delà de la cadence propre au fournisseur. Test de concurrence dans la tâche 2.
5. **Les déplacements de modules ne laissent aucun import cassé.** Les parcours jsdom chargent bien tous les scripts dans l'ordre d'`index.html` après le découpage du front. Vérifié par la suite complète en fin de tâches 9, 10 et 11.

---

### Tâche 1 : mise en place et suite verte

**Fichiers :**
- Modifier : `src/web-pc/static/js/listen-later.js:45-57`
- Modifier : `src/web-pc/static/js/recommendation-comments.js:32,113`
- Test : `tests/e2e_listen_later.js:369` (existant, actuellement en échec)

- [ ] **Étape 1 : créer le worktree.**
  - `git -C sources fetch origin`
  - `git -C sources worktree add ../v1 -b refactor/v1-architecture origin/feature/1.7.5`
- [ ] **Étape 2 : lancer la suite complète.** Attendu : 895 tests unitaires OK et `Parcours en échec : e2e_listen_later.js` (0 carte au lieu de 3 à la ligne 369).
- [ ] **Étape 3 : corriger le re-rendu complet.** Quand le bus `recommendations` porte un `discussionId`, `ListenLaterUI` met à jour seulement le bouton de résumé de ce fil (classe `unread`, compteur) au lieu d'appeler `page.render()`. Un événement sans `discussionId` garde le comportement actuel.
- [ ] **Étape 4 : ajouter des assertions à `e2e_listen_later.js`.** Après l'ouverture d'un fil non lu, le `<details>` des archives reste ouvert et le nombre de cartes chargées par « plus » ne change pas.
- [ ] **Étape 5 : relancer la suite complète.** Attendu : `Tous les parcours sont OK`.
- [ ] **Étape 6 : commit** `fix: garder la page À écouter en place à l'ouverture d'une discussion`.

### Tâche 1 b : migrations sûres

**Constat :**
- `Database.migrate` (`src/pimedia/storage/database.py`) exécute chaque migration dans une transaction avec `foreign_keys=ON` et découpe le script sur `;`.
- Une reconstruction de table (CREATE puis INSERT … SELECT, DROP, RENAME, le modèle des migrations 20 et 21) déclenche donc les `ON DELETE CASCADE` des tables enfants. Essai fait : reconstruire `recommendations` efface tous les `recommendation_comments`.
- Le découpage sur `;` casse aussi toute instruction qui contient un `;` dans un texte, ainsi que les triggers.

**Fichiers :**
- Modifier : `src/pimedia/storage/database.py` (`migrate`)
- Test : `tests/test_database_migrations.py`

**Règles :**
- `migrate` découpe le script avec `sqlite3.complete_statement`, en accumulant les lignes jusqu'à obtenir une instruction complète.
- Avant chaque migration : `PRAGMA foreign_keys=OFF`, **hors transaction**. Puis `BEGIN IMMEDIATE`, la migration, `PRAGMA foreign_key_check` (s'il retourne une ligne : `ROLLBACK` et `RuntimeError` avec le numéro de migration), `COMMIT`, et enfin `PRAGMA foreign_keys=ON`.

- [ ] **Étape 1 : écrire les tests.**
  - `test_rebuilding_a_parent_table_keeps_child_rows` : une migration de test qui reconstruit `recommendations` ; les commentaires sont conservés.
  - `test_migration_with_semicolon_in_literal` : `INSERT … VALUES ('a;b')`.
  - `test_broken_foreign_key_rolls_back_migration` : la version ne change pas.
- [ ] **Étape 2 : les lancer.** Attendu : échec, 0 commentaire au lieu de 1.
- [ ] **Étape 3 : implémenter.**
- [ ] **Étape 4 : lancer la suite complète.** Toutes les migrations 1 à 23 rejouées sur une base neuve donnent le même schéma qu'avant : comparer `sqlite_master` avec un instantané pris à l'étape 1.
- [ ] **Étape 5 : commit** `fix: migrations sans cascade lors des reconstructions de tables`.

### Tâche 1 c : modèle de données (un seul « lu », recommandations découpées, une seule identité de style)

Elle dépend de la tâche 1 b : migrations sans cascade.

**Décisions de Thomas (27/11) :**
- un seul modèle de lecture ;
- la table `recommendations` ne mélange plus l'objet recommandé, la livraison et le fil ;
- un style a une seule identité, celle envoyée à MusicBrainz ;
- pas de purge des notifications ni des commentaires pour l'instant.

**Schéma cible :** migrations 24 à 26, chacune avec reprise des données existantes.

| Table | Colonnes | Remarques |
|---|---|---|
| `listening_targets` (nouvelle) | `id`, `kind`, `source`, `library_key`, `source_id`, `title`, `artist`, `image_ref` | `UNIQUE (kind, source, library_key, source_id)`. Les CHECK actuels (`kind`, `source`, `song` réservé à `subsonic`, `library_key`) sont écrits **une seule fois**, ici. Le titre, l'artiste et l'image sont mis à jour à chaque nouvel ajout ou envoi. |
| `listen_later` | `id`, `user_id`, `target_id`, `created_at` | `UNIQUE (user_id, target_id)`, index `(user_id, created_at DESC, id DESC)` |
| `recommendations` | `id`, `sender_id`, `recipient_id`, `target_id`, `created_at`, `read_at`, `archived_at` | `CHECK (sender_id != recipient_id)`, unicité partielle `(sender_id, recipient_id, target_id) WHERE archived_at IS NULL`. Plus de `unread_token`, plus de curseurs. |
| `recommendation_comments` | `id`, `recommendation_id`, `author_id`, `recipient_id`, `body`, `client_token`, `created_at`, `read_at` | `recipient_id` est l'autre participant du fil, fixé à l'écriture. Index partiel `(recipient_id) WHERE read_at IS NULL`. |
| `notifications` | colonnes inchangées | Reconstruite **sans** les bornes de longueur dans le CHECK : seul `length(trim(x)) > 0` reste, les bornes vivent dans `notification_entities.py`. |
| `release_subscriptions` | `user_id`, `genre`, PK `(user_id, genre)` | `genre` est le nom exact du catalogue MusicBrainz, c'est-à-dire la valeur envoyée dans `tag:"…"`. La colonne `genre_id` disparaît. |

**Règle unique de lecture :** chaque message (notification, recommandation, commentaire) a **un destinataire** et une date `read_at`.
- Marquer comme lu : `UPDATE … SET read_at = ? WHERE id IN (…) AND recipient_id = ? AND read_at IS NULL`.
- « Non lu » : `read_at IS NULL AND recipient_id = ?`.
- Le front envoie des identifiants, plus de jetons : `unreadIds` remplace `unreadTokens` dans `listen-later.js:66-72` et dans `RecommendationGroup.to_api()`.
- La protection qu'apportait le jeton est conservée : un identifiant ne désigne qu'une seule livraison.

**Lecture des recommandations reçues :**
- `received()` est paginé comme `page()` (`before`, `limit`), avec `RECEIVED_PAGE_SIZE = 50` dans `recommendation_entities.py`.
- Le nombre de commentaires, l'aperçu et le nombre de non-lus sont calculés par **une seule** jointure agrégée sur `recommendation_comments`, au lieu de 4 sous-requêtes corrélées par ligne.

**Reprise des données :**
- **`listening_targets` :** une ligne par cible distincte trouvée dans `listen_later` et `recommendations`, avec le titre, l'artiste et l'image de la ligne la plus récente.
- **`recommendations.read_at` :**
  - `NULL` si `unread_token IS NOT NULL` ;
  - sinon `created_at` ;
  - `archived_at` reprend `recipient_archived_at`.
- **`recommendation_comments` :**
  - `recipient_id` est l'autre participant ;
  - `read_at` vaut `created_at` si `id <=` le curseur de ce destinataire, sinon `NULL`.
- **`release_subscriptions` :**
  - `genre` vaut `name`, dédupliqué par `(user_id, name)` ;
  - un nom absent du catalogue est conservé tel quel ;
  - **côté code :** `ReleaseGenre` n'a plus que `name`, son `to_api()` renvoie `{"name": …}`, l'API `follow` reçoit `genre` (le nom), et `weekly-releases.js` utilise le nom partout.
- **`notifications` :** copie à l'identique.

**Fichiers :**
- `src/pimedia/webapp/schema.py` (migrations 24 à 26)
- `src/pimedia/webapp/storage/listening_targets.py`, qui devient un vrai dépôt : `upsert(target) -> int` pour l'identifiant de la cible
- `storage/listen_later.py`, `storage/recommendations.py`, `storage/recommendation_comments.py`, `storage/notifications.py`, `storage/weekly_releases.py`
- `recommendation_entities.py`, `notification_entities.py`, `weekly_release_entities.py`, `recommendations.py`, `weekly_releases.py`
- `src/web-pc/static/js/listen-later.js`, `recommendation-comments.js`, `weekly-releases.js`
- **Tests :**
  - `tests/test_data_model_migration.py` (nouveau)
  - adapter `test_recommendations.py`, `test_recommendation_comments.py`, `test_listen_later.py`, `test_notifications.py`, `test_weekly_releases.py`
  - adapter les parcours `e2e_listen_later.js`, `e2e_notifications.js`, `e2e_weekly_releases.js`

- [ ] **Étape 1 : écrire `test_data_model_migration.py`.** On part d'une base en version 23 remplie avec :
  - 2 comptes ;
  - la même cible présente dans « À écouter » et dans une recommandation ;
  - une recommandation non lue et une lue ;
  - une archivée puis renvoyée ;
  - 3 commentaires, dont 1 lu par le destinataire ;
  - un abonnement au format MBID et un au format `genre:` pour le même style.

  On vérifie ensuite :
  - une seule ligne dans `listening_targets` ;
  - les deux `read_at` attendus ;
  - les comptes de commentaires non lus identiques à ceux d'avant la migration, pour chaque compte ;
  - un seul abonnement, avec le nom ;
  - `PRAGMA foreign_key_check` vide.
- [ ] **Étape 2 : écrire les tests de comportement.**
  - `test_mark_read_ignores_other_recipients_ids`
  - `test_comment_unread_for_other_participant_only`
  - `test_follow_and_unfollow_by_name`
  - `test_week_uses_the_followed_name_in_the_query` : le faux MusicBrainz reçoit `tag:"noise rock"`.
  - `test_target_title_refreshed_on_new_bookmark`
  - `test_received_is_paginated`
- [ ] **Étape 3 : lancer les tests.** Attendu : échec.
- [ ] **Étape 4 : écrire les migrations, les dépôts, les entités, les services et le front.**
- [ ] **Étape 5 : lancer la suite complète.** Attendu : tout passe.
- [ ] **Étape 6 : commit** `refactor: un seul modèle de lecture, cibles partagées et styles identifiés par leur nom`.

### Tâche 2 : socle commun des fournisseurs (transport, cache, métadonnées)

**Fichiers :**
- Créer : `src/pimedia/shared/providers/__init__.py`
- Créer : `src/pimedia/shared/providers/http.py`, qui remplace `JsonFetcher` (`shared/external.py`), `MetadataHttp` (`webapp/music_metadata.py`) et `ImageDownloader` (`webapp/covers.py`)
- Créer : `src/pimedia/shared/providers/cache.py`
- Créer : `src/pimedia/shared/providers/metadata.py`, qui remplace `webapp/music_metadata.py` (`PublicMetadata`)
- Modifier : `src/pimedia/webapp/exploration_entities.py` (retirer `CachedMetadata`), `src/pimedia/webapp/storage/exploration.py` (import)
- Test : `tests/test_providers_http.py`, `tests/test_providers_metadata.py` (reprendre les cas de cache et de 429 des tests actuels de `music_metadata`)

**Interfaces produites :**
- **`http.py` :**
  - `class HttpClient(opener=urllib.request.urlopen, timeout=10, max_bytes=8*1024*1024)`
  - `.get_json(url, headers=None) -> dict | list`
  - `.get_text(url, headers=None) -> str` (lève `ValueError` si le type n'est pas `text/plain`)
  - `.get_bytes(url, headers=None, accept="*/*", public_only=False) -> bytes`. Avec `public_only=True`, il reprend la vérification d'hôte public et les redirections contrôlées de `covers.py`.
  - Le User-Agent est toujours `USER_AGENT`.
- **`cache.py` :**
  - `@dataclass(frozen=True) class CachedMetadata(key: str, data: dict, fetched_at: int)`
  - `class MetadataStore(Protocol)` : `get(key) -> CachedMetadata | None`, `save(entry) -> None`, `expire(prefix, before) -> None`, `discard(prefix, keep) -> None`
  - `class MemoryStore(MetadataStore)`, une implémentation en mémoire pour le Pi et les tests. `ExplorationRepository` satisfait déjà ce protocole.
- **`metadata.py` :**
  - `class ProviderUnavailable(ValueError)`, qui porte une clé i18n (`discovery.unavailable` ou `discovery.rate_limited`). Elle remplace `MusicSourceError` et `ExplorationUnavailable`.
  - `@dataclass(frozen=True) class Fetched(data: dict, stale: bool = False)`
  - `class PublicMetadata`, avec les attributs de classe `prefix: str`, `interval: float` (secondes entre deux départs), `ttl: int` et `stale_ttl: int = 30*86400`.
    - Constructeur : `__init__(store, http=None, clock=time.time, sleep=time.sleep)`.
    - `.fetch(key, url, *, read=None, ttl=None, headers=None) -> Fetched`. Par défaut, `read` vaut `http.get_json`.
- **Règles de `fetch` :**
  - Une copie en cache plus jeune que `ttl` est renvoyée telle quelle.
  - Sinon, un verrou est pris **par clé** (pas de verrou global). La cadence `interval` est commune à tout le fournisseur.
  - Une erreur transitoire (429, 5xx, réseau) est reprise une seule fois si `Retry-After` vaut 2 s ou moins.
  - En cas d'échec, quelle que soit l'erreur (y compris 4xx), la copie de moins de `stale_ttl` est servie avec `stale=True`. Sans copie, `ProviderUnavailable` est levée.
  - Chaque enregistrement appelle `store.expire(prefix, now - stale_ttl)`.

- [ ] **Étape 1 : écrire les tests d'`HttpClient`.** Avec un `opener` factice :
  - `test_json_sends_user_agent_and_timeout`
  - `test_text_rejects_html`
  - `test_bytes_public_only_refuses_private_redirect`
  - `test_body_over_max_bytes_is_refused`
- [ ] **Étape 2 : écrire les tests de `PublicMetadata`.** Ils utilisent une sous-classe `Fake` (`prefix="fake:"`, `interval=1`, `ttl=60`), `MemoryStore` et des horloges factices :
  - `test_fresh_copy_skips_network`
  - `test_403_serves_stale_copy` (attendu : `Fetched(data, stale=True)`)
  - `test_no_copy_raises_provider_unavailable`
  - `test_retry_once_on_503_then_succeeds`
  - `test_save_expires_old_entries_of_prefix_only`
  - `test_two_keys_do_not_wait_on_each_other`. Deux threads, une clé lente, une rapide : la rapide se termine sans attendre la lente, au-delà de `interval`.
- [ ] **Étape 3 : lancer les tests.** Attendu : échec à l'import.
- [ ] **Étape 4 : implémenter les trois modules.** Déplacer `CachedMetadata` et mettre à jour les imports.
- [ ] **Étape 5 : lancer les nouveaux tests, puis la suite unitaire.** Attendu : tout passe.
- [ ] **Étape 6 : commit** `refactor: socle commun des fournisseurs externes (transport, cache, métadonnées)`.

### Tâche 3 : MusicBrainz, une seule classe

**Fichiers :**
- Créer : `src/pimedia/shared/providers/musicbrainz/__init__.py` (exporte `MusicBrainz`, `mbid`)
- Créer : `src/pimedia/shared/providers/musicbrainz/client.py`, qui contient la classe `MusicBrainz`
- Créer : `src/pimedia/shared/providers/musicbrainz/parsing.py`, des fonctions pures du JSON vers les entités : `mbid`, `artist_name`, `artist_names`, `search_phrase`, `search_terms`, `genres`, `formats`, `number`, `edition`, `release`, `weekly_group`, `connections`, `credits`, `ROLES`
- Créer : `src/pimedia/shared/providers/musicbrainz/entities.py`. Il regroupe `webapp/musicbrainz_entities.py`, `webapp/weekly_release_entities.py`, ainsi que `MusicLink`, `MusicArtist` et `MusicWork` d'`exploration_entities.py`.
- Supprimer :
  - `webapp/musicbrainz.py`
  - `webapp/musicbrainz_entities.py`
  - `webapp/weekly_release_entities.py`
  - la classe `MusicBrainz` et `MusicBrainzPacer`/`MUSICBRAINZ_PACER` de `shared/external.py`
  - le test sur l'hôte `musicbrainz.org` dans `JsonFetcher`
- Modifier :
  - `webapp/exploration.py`, qui garde seulement les règles : filtrer les homonymes avec `normalize`, vérifier que l'édition appartient à la liste, composer `AlbumCredits` et `MusicProfile`
  - `webapp/weekly_releases.py`, `webapp/tag_sources.py`, `webapp/facts.py`
  - `webapp/app.py` (une seule instance)
  - `server/app.py`, `server/external.py` (le Pi utilise `MusicBrainz(MemoryStore())`)
  - `shared/external.py` (`FactsBuilder` reçoit le nouveau client)
  - `webapp/schema.py`, migration 27 : `DELETE FROM music_metadata WHERE cache_key LIKE 'https://musicbrainz.org/%'`
- Tests :
  - Créer `tests/test_musicbrainz.py` à partir de `tests/test_musicbrainz_genres.py` et des cas MusicBrainz de `test_exploration.py`, `test_tag_sources.py`, `test_weekly_releases.py` et `test_label_discovery.py`
  - Adapter `tests/webapp_support.py`, `tests/e2e_webapp_harness.py` et `tests/fake_musicbrainz.py`. Il ne reste qu'un seul point d'injection : `app.musicbrainz.http`.

**Entités :**
- `MusicEdition` (exploration, avec labels) et `MusicBrainzEdition` (tags, avec `track_count`) fusionnent en `Edition(id, title, artist, date, country, format, track_count=0, labels=())`.
- Leurs `to_api()` gardent les clés actuelles des deux réponses JSON (vérifié par les tests existants des contrôleurs).

**Interfaces produites :** `class MusicBrainz(PublicMetadata)`, avec `prefix="musicbrainz:"`, `interval=1.05` et `ttl=7*86400`.
- **Anecdotes et genres (Pi et site) :**
  - `genres(artist) -> dict`, au format actuel `{"genres": [...]}`
  - `release_fact(artist, album) -> str | None`, qui renvoie `None` en cas d'erreur, comme aujourd'hui
- **Exploration :**
  - `search_artists(name) -> Fetched` (les données contiennent des `MusicArtist`)
  - `artist_relations(identity) -> Fetched`
  - `find_releases(title, artist, limit=100) -> Fetched`
  - `release_credits(identity) -> Fetched`
  - `profile(kind, identity) -> Fetched`
  - `catalog(kind, identity, offset, limit) -> Fetched`
- **Tags :**
  - `search_releases(artist, album) -> tuple[Edition, ...]`
  - `release(identity) -> Release`
- **Sorties de la semaine :**
  - `release_genres() -> tuple[ReleaseGenre, ...]`, avec un TTL de 86 400 s
  - `weekly_groups(genre, monday, sunday, limit, offset) -> WeeklyReleasePage`, avec un TTL de 3 600 s
- **Optimisation du nombre de connexions :** hors périmètre. Elle sera traitée plus tard, quand la classe unique sera en place.

- [ ] **Étape 1 : écrire `tests/test_musicbrainz.py`.** Reprendre les cas existants et ajouter :
  - `test_pi_uses_memory_store_without_webapp`
  - `test_403_on_genre_catalog_serves_yesterdays_copy`
  - `test_cache_keys_are_prefixed_and_expire`
  - `test_migration_27_purges_only_old_musicbrainz_keys`. Une base en version 26 avec une clé `https://musicbrainz.org/...`, une clé `discogs:...` et une clé `label-lastfm:...` : après la migration, seules les deux dernières restent.
- [ ] **Étape 2 : ajouter la règle d'architecture `test_only_the_musicbrainz_provider_calls_its_api`** dans `tests/test_architecture.py`. Aucun fichier de `src/` hors de `shared/providers/musicbrainz/` ne contient `musicbrainz.org/ws/`.
- [ ] **Étape 3 : lancer les tests.** Attendu : échec.
- [ ] **Étape 4 : implémenter le client et le parsing, migrer les consommateurs, supprimer les anciens modules.**
- [ ] **Étape 5 : ajouter les bornes dans `WeeklyReleases.week`.**
  - `monday` doit tomber à un an au plus de la date du jour, dans un sens ou dans l'autre.
  - `offset` doit être un multiple de `PAGE_SIZE` et ne pas dépasser `MAX_OFFSET = 10 * PAGE_SIZE`.
  - Sinon : `ValueError("week")`, soit une erreur 400.
  - Tests : `test_week_far_in_past_is_refused` et `test_offset_not_multiple_of_page_is_refused`.
- [ ] **Étape 6 : lancer la suite complète.** Attendu : tout passe.
- [ ] **Étape 7 : commit** `refactor: une seule classe MusicBrainz pour les anecdotes, l'exploration, les tags et les sorties`.

### Tâche 4 : Last.fm, Discogs et les autres fournisseurs

**Fichiers :**
- Créer : `shared/providers/lastfm.py`, qui contient `class LastFm(PublicMetadata)` avec `prefix="lastfm:"`, `interval=0.25` et `ttl=86400`
  - `album(artist, title, cached=False) -> AlbumPopularity`, repris de `webapp/lastfm.py`
  - `album_images(artist, album) -> list[CoverCandidate]`, repris de `covers.LastFmAlbums.search`
- Déplacer : `webapp/discogs.py` et `webapp/discogs_entities.py` vers `shared/providers/discogs.py` et `shared/providers/discogs_entities.py`, sans changer le comportement
- Créer :
  - `shared/providers/wikipedia.py` (`Wikipedia`, extrait de `shared/external.py`)
  - `shared/providers/lyrics.py` (`LyricsFinder`, LRCLIB et lyrics.ovh)
  - `shared/providers/gravatar.py` (repris de `webapp/avatars.py`)
- Supprimer : `webapp/lastfm.py`, `covers.LastFmAlbums`, la constante `covers.LASTFM` et `webapp/music_metadata.py`
- Modifier :
  - `webapp/covers.py`, qui reçoit `LastFm` et `HttpClient` (`get_bytes(..., public_only=True)`)
  - `webapp/avatars.py`, `webapp/radios.py`, `webapp/import_readers.py` et `webapp/label_discovery.py`, qui passent par `HttpClient`
  - `webapp/app.py` (une seule instance de chaque fournisseur)
  - migration 28 : renommer le préfixe de cache `label-lastfm:` en `lastfm:` (`UPDATE ... SET cache_key = 'lastfm:' || substr(cache_key, 14)`)
- Tests :
  - Déplacer et adapter les tests existants de Last.fm, Discogs, pochettes et avatars
  - Ajouter la règle d'architecture `test_http_goes_through_the_provider_transport` : dans `webapp/` et `shared/`, seul `shared/providers/http.py` importe `urllib.request`, avec une exception pour `webapp/subsonic.py`

- [ ] **Étape 1 : écrire la règle d'architecture et les tests de `LastFm.album_images`**, repris de ceux de `LastFmAlbums`. Les lancer : échec attendu.
- [ ] **Étape 2 : déplacer et fusionner, puis mettre à jour les imports et le câblage.**
- [ ] **Étape 3 : lancer la suite complète.** Attendu : tout passe.
- [ ] **Étape 4 : commit** `refactor: un module par fournisseur externe et un seul transport HTTP`.

### Tâche 4 b : Jamendo, Deezer, iTunes, Spotify, SoundCloud et PodcastIndex (ajoutée le 27/11 sur remarque de Thomas)

**YouTube est hors de cette tâche (décision de Thomas, 27/11) :** il garde ses propres transports pour l'instant (pas de passage forcé par l'API). Plus tard : une seule classe YouTube qui fait toutes ses recherches (API Data, YouTube Music, oEmbed), avec ses transports à elle.

**Constat :** ces services vivent dans `server/` (édition Pi) et passent par un second transport, `JsonHttp` (`server/podcasts/directories.py`), que le site importe aussi (`webapp/app.py`, `ext_favorites.py`, `import_readers.py`).
- **YouTube :** appelé à trois endroits, `server/extmusic/sources.py` (API Data), `server/extmusic/ytmusic.py` (YouTube Music, via `requests`) et `server/links.py` (oEmbed).
- **Deezer :** appelé depuis `server/links.py` et `webapp/import_readers.py`.
- **iTunes :** appelé depuis `server/links.py` et `server/podcasts/directories.py`.

**Cible :** une classe par service, utilisée par les deux éditions, dans `shared/providers/` :
- `jamendo.py`, `deezer.py`, `itunes.py`, `spotify.py`, `soundcloud.py` et `podcastindex.py`.

**Transport :** `HttpClient` remplace `JsonHttp`. Le site n'importe plus `server/` pour un service externe. La règle `test_http_goes_through_the_provider_transport` s'étend à `server/`, avec ces exceptions déclarées :
- `server/upstream.py` (Subsonic) ;
- les flux audio ;
- YouTube (`server/extmusic/ytmusic.py`, `sources.py` pour YouTube, `links.py` pour l'oEmbed YouTube) ;
- la lecture des flux RSS de podcasts, si elle demande un traitement en flux.

**Tests :** déplacer les tests existants des sources et des liens, ajouter une règle d'architecture qui interdit les adresses d'API de ces services hors de leur classe, puis lancer les parcours e2e Pi (`e2e_podcasts.js`, `e2e_music.js`) et site (`e2e_webapp.js`).

**Commit :** `refactor: un service musical par classe (hors YouTube), un seul transport`.

### Tâche 5 : couches (erreurs du domaine, services qui renvoient des entités)

**Fichiers :**
- Créer : `src/pimedia/webapp/errors.py` (`MissingRight`, `Forbidden` et les autres exceptions de droits aujourd'hui dans `controllers/base.py`). `controllers/base.py` les réimporte pour `error_reply`.
- Modifier : `webapp/notifications.py` et `webapp/album_tags.py` (imports)
- Créer : `NotificationPage(items, next_before)` et `NotificationStatus(unread)` dans `notification_entities.py`, ainsi que `TagEditorStatus(enabled, reason)` dans `tag_entities.py`, tous avec `to_api()` aux clés actuelles
- Modifier : `notifications.page`, `notifications.status` et `AlbumTags.status`, qui renvoient ces entités. Les contrôleurs appellent `.to_api()`.
- Test : `tests/test_architecture.py::test_services_never_import_controllers`. Hors de `controllers/` et d'`app.py`, aucun module de `webapp/` n'importe `pimedia.webapp.controllers`.

- [ ] **Étape 1 : écrire la règle d'architecture et la lancer.** Attendu : échec, qui cite `album_tags.py` et `notifications.py`.
- [ ] **Étape 2 : déplacer les exceptions et créer les entités.**
- [ ] **Étape 3 : lancer la suite complète.** Attendu : tout passe.
- [ ] **Étape 4 : commit** `refactor: les services ne dépendent plus de la couche HTTP`.

### Tâche 6 : rangement en paquets par fonctionnalité

**Fichiers (déplacements, sans changer la logique) :**
- **`webapp/tags/` :**
  - `service.py` (ex-`album_tags.py`), `entities.py` (ex-`tag_entities.py`), `matching.py` (ex-`tag_matching.py`), `sources.py` (ex-`tag_sources.py`)
  - `audio_tags.py` découpé en trois :
    - `formats.py` : `_load`, `_read`, `_write`, `validate_changes`, les tables `_ID3_FIELDS`, `_COMMENT_FIELDS`, `_MP4_FIELDS`, et `_text`, `_number`, `_date`, `_with_total`, `_with_date`, `_discard`
    - `files.py` : `_path`, `_copy`, `_sync`, `_sync_directory`, `_identity`, `_revision`, `_digest`, `_temporary`, `_space`
    - `journal.py` : `_manifest`, `_backup_path`, `_matches_publication`, `_rollback`, `_recover`, `recover`, `_cleanup_temporaries`, `_prune`, `_exclusive`
  - `AudioTags` (`apply`, `inspect`) reste une façade de moins de 100 lignes dans `tags/audio.py`. Ses fonctions de plus de 40 lignes sont découpées : `_apply` (63), `_write` (49), `_rollback` (42).
- **`webapp/notifications/` :** `service.py` et `entities.py`
- **`webapp/recommendations/` :** `service.py` et `entities.py` (ex-`recommendations.py` et `recommendation_entities.py`)
- **`webapp/listen_later/` :** `service.py`, `entities.py` et `targets.py` (ex-`listening_targets.py`)
- **`webapp/weekly_releases/` :** `service.py`
- Les dépôts restent dans `storage/`, conformément à la convention.
- Tests : mettre à jour les imports. Ajouter `tests/test_code_size.py`, qui vérifie la limite de 40 lignes par fonction et de 300 lignes par fichier Python sous `src/pimedia/webapp` et `src/pimedia/shared`, avec une liste `KNOWN_EXCEPTIONS` des cas existants (par exemple `webapp/mixes.py:build`). Le test échoue si un nouveau cas apparaît, ou si une exception listée n'existe plus (la liste ne peut que diminuer).

- [ ] **Étape 1 : écrire `test_code_size.py` et le lancer.** Attendu : échec sur `audio_tags.py`.
- [ ] **Étape 2 : faire les déplacements et le découpage.** Supprimer les alias morts `TEXT_LIMIT` et `MAX_NUMBER`.
- [ ] **Étape 3 : lancer la suite complète.** Attendu : tout passe.
- [ ] **Étape 4 : commit** `refactor: ranger tags, notifications, recommandations et sorties en paquets`.

### Tâche 7 : `app.py` qui assemble seulement

**Fichiers :**
- Créer : `src/pimedia/webapp/wiring.py`, avec `build_services(config, db) -> Services`. `Services` est un `@dataclass` qui regroupe toutes les instances créées aujourd'hui dans `App.__init__`.
- Modifier : chaque fichier de `controllers/*.py`, qui gagne `routes(self) -> list[Route]`. `Route(method, path, handler, right=None, csrf=...)` reprend exactement les options d'aujourd'hui.
- Modifier : `webapp/app.py`, qui concatène `controller.routes()`. `_routes` (154 lignes) et `__init__` (77 lignes) disparaissent.
- Test : `tests/test_webapp_routes.py::test_route_table_is_unchanged`. Avant le changement, on capture la liste triée `(méthode, chemin, droit, csrf)` dans un fichier de référence `tests/data/routes.txt`, puis on vérifie l'égalité après.

- [ ] **Étape 1 : capturer la table de routes actuelle et écrire le test.** Il passe sur l'ancien code.
- [ ] **Étape 2 : déplacer les routes et le câblage.**
- [ ] **Étape 3 : lancer le test de routes et la suite complète.** Attendu : tout passe, et `test_code_size` ne liste plus `app.py`.
- [ ] **Étape 4 : commit** `refactor: chaque contrôleur déclare ses routes, le câblage sort d'app.py`.

### Tâche 8 : règles et limites définies une seule fois

Pour chaque ligne, une seule source et un test qui lie les usages :

| Règle | Source unique | Usages à brancher |
|---|---|---|
| Longueurs titre et corps d'une notification | `notifications/entities.py` (`TITLE_MAX_LENGTH`, `BODY_MAX_LENGTH`) | Le CHECK SQL est déjà retiré en tâche 1 c. Ici, `error_reply` traduit en plus toute `sqlite3.IntegrityError` en 400, jamais en 500. |
| Longueur du nom du destinataire (200) | `shared/limits.py` : `USERNAME_MAX_LENGTH` | `notifications`, `recommendations` |
| Identifiant d'entrée | `listen_later/targets.py:entry_id` | `notifications.py:47,59` |
| Jeton de requête idempotent | `shared/limits.py` : `REQUEST_ID = re.compile(r"[0-9a-f]{32}")` | notifications et recommandations côté serveur. Côté front, `App.requestId()` dans `core.js` (avec `getRandomValues`) remplace `crypto.randomUUID()` dans `notifications.js` et la version locale de `recommendation-comments.js`. |
| Correspondance champs Subsonic → tags | `tags/entities.py` : `SUBSONIC_FIELDS` | `tags/service.py` (`_read_song`, `_verify_index`) |
| Liste des champs de tags | `tags/entities.py` : `TAG_FIELDS`, envoyé par `/api/tags/status` | `album-tags.js` (`FIELDS` et `IMPORT_FIELDS`, qui étaient identiques) |
| Dossier d'album d'après les chemins Subsonic | `library/folders.py` | `upload_attribution.py:16-26` |
| Style par défaut des sorties de la semaine | `weekly_releases/service.py` : `DEFAULT_GENRE = "noise rock"`, envoyé dans `/api/news/releases/genres` | `weekly-releases.js:128` |

- [ ] **Étape 1 : écrire un test par ligne du tableau.** Par exemple, `test_notification_title_limit_matches_storage` insère un titre à la limite, puis à la limite + 1 : erreur 400, pas 500. Les lancer : échec attendu.
- [ ] **Étape 2 : brancher chaque règle sur sa source unique.** Aucune migration dans cette tâche.
- [ ] **Étape 3 : lancer la suite complète.** Attendu : tout passe.
- [ ] **Étape 4 : commit** `refactor: chaque règle et chaque limite définie une seule fois`.

### Tâche 9 : front découpé

**Fichiers :**
- Découper `src/web-pc/static/js/album-tags.js` (593 lignes) en :
  - `album-tags/draft.js` (brouillon, copie et comparaison)
  - `album-tags/sources.js` (recherche Discogs et MusicBrainz, import)
  - `album-tags/save.js` (aperçu, enregistrement, suivi de l'opération)
  - `album-tags/editor.js` (dialogue et assemblage)
  - Les ajouter dans `index.html`, dans cet ordre.
- Découper en fonctions de 40 lignes au plus :
  - `weekly-releases.js:18 render` (117 lignes)
  - `whatsnew.js:97 render` (88)
  - `views.js:85 songTable` (69)
  - `notifications.js:84 render` (51)
  - `listen-later.js:274 songRecommendations` (44)
- Étendre `tests/test_code_size.py` aux fichiers JS : il mesure les fonctions par appariement d'accolades et ignore l'IIFE de premier niveau qui enveloppe chaque module.

- [ ] **Étape 1 : étendre `test_code_size.py` au JS et le lancer.** Attendu : échec sur les cinq fonctions et sur `album-tags.js`.
- [ ] **Étape 2 : découper.**
- [ ] **Étape 3 : lancer la suite complète.** Les parcours `e2e_album_tags.js`, `e2e_weekly_releases.js`, `e2e_help.js`, `e2e_notifications.js` et `e2e_listen_later.js` doivent passer.
- [ ] **Étape 4 : commit** `refactor: découper l'éditeur de tags et les longues fonctions du front`.

### Tâche 10 : corrections des bugs relevés en revue

Chaque bug a d'abord son test qui échoue, puis sa correction.

1. **Sorties de la semaine, bouton « À écouter » :** `/api/explore/local` renvoie `folderId` pour chaque album, et `weekly-releases.js:163` utilise `local.folderId`. Le parcours `e2e_weekly_releases.js` vérifie qu'un album déjà gardé s'affiche « gardé », puis qu'un clic le retire.
2. **Tags, conflit pendant la publication :** `tags/journal.py:_rollback` considère comme intact un fichier jamais publié (fichier temporaire présent, ou pas de `published_revision`). Test : `test_conflict_on_unpublished_file_does_not_block_editor` (l'éditeur reste actif, pas de `needs_recovery`).
3. **Tags, fichier d'un autre propriétaire :** `inspect` ne marque modifiable que si `st_uid == os.geteuid()`, et `_copy` ne fait plus de `chown` sur la sauvegarde. Test : `test_foreign_owner_file_is_not_editable`.
4. **Scan après un scan long :** `library_scan.synchronize` lance quand même `startScan` après le délai de 90 s, et l'opération indique `scan_queued`. Test : `test_save_during_long_scan_still_requests_scan`.
5. **Préférence refusée :** `App.savePreference` rétablit l'ancienne valeur et réémet `preferences` en cas d'échec. Parcours : `e2e_webapp.js`, colonne décochée puis erreur 500, la colonne réapparaît.
6. **Sondage des tags :** l'intervalle passe à 1 s, 2 s, 5 s puis 10 s. Après 60 essais, l'éditeur propose « Reprendre le suivi » (`retryOperation` existant).
7. **Envoi ZIP :** le refus `album_required` est vérifié sur `zipfile.infolist()` avant l'extraction. Test : `test_zip_without_album_is_refused_before_extraction`.
8. **Rangement concurrent :** le verrou `_placement_lock` passe dans `LibraryFiles.place`. Test : deux `place` simultanés dans le même dossier d'artiste, sans `FileExistsError`.
9. **Erreurs masquées :** `tags/sources.py` n'attrape plus `TypeError`, `KeyError` ni `AttributeError`, et `tags/service.py:_save` utilise `LOG.exception`.
10. **Note de guide manquante :** `whatsnew.js` teste `App.texts[key + ".note"]`.

- [ ] **Étapes 1 à 10 : pour chaque bug, test rouge → correction → test vert.**
- [ ] **Étape 11 : lancer la suite complète.**
- [ ] **Étape 12 : commit** `fix: corrections relevées en revue (sorties de la semaine, tags, envois, préférences)`.

**À trancher avec Thomas avant cette tâche :**
- Une playlist doit-elle afficher son rang (comme avant la 1.12) ou le numéro de piste de l'album d'origine (comme maintenant) ?

### Tâche 11 : finalisation et PR

**Fichiers :**
- Modifier : `src/i18n/versions.yaml`, avec l'entrée `1.19.2`, datée du jour de mise en ligne. Elle décrit pour les utilisateurs les corrections 1, 3, 5 et 6 de la tâche 10, ainsi que le service des sorties de la semaine quand MusicBrainz est en panne.
- Modifier : `docs/architecture/README.md` (fournisseurs, paquets, règles vérifiées par les tests), `docs/CONVENTIONS.md` (limites de taille, un module par fournisseur), `docs/ETAT.md`

- [ ] **Étape 1 : lancer la suite complète une dernière fois.** Attendu : environ 900 tests OK et `Tous les parcours sont OK`.
- [ ] **Étape 2 : demander la revue finale** de toute la branche à un relecteur neuf (`superpowers:requesting-code-review`).
- [ ] **Étape 3 : avec l'accord de Thomas**, pousser `refactor/v1-architecture` et ouvrir une PR vers `main`, qui remplace la PR 2. Puis fermer la PR 2 avec un lien vers la nouvelle.

---

## Plus tard (hors de ce plan)

- **YouTube :** une seule classe (API Data, YouTube Music, oEmbed) qui garde ses transports propres ; décision de Thomas le 27/11.

- **Optimisation MusicBrainz :** une connexion HTTP persistante réutilisée pour plusieurs requêtes, et le regroupement des appels avec `inc=` pour en faire moins.
- Découper les autres modules à plat de `webapp/` (environ 50 modules d'avant la PR 2) au fil des prochaines fonctionnalités. `test_code_size.py` empêche déjà le problème de s'aggraver.
