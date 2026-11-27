# Radar des sorties — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** remplacer « un style à la fois » par un radar personnel des sorties (styles, labels, artistes suivis,
tendances d'après les favoris, découvertes Last.fm), synchronisé en tâche de fond et lu en base.

**Architecture :** un fil `daemon` (comme `News.run`) synchronise la nuit et au démarrage l'union des sources de
tous les comptes vers des tables partagées ; la page lit la base (aucun appel externe à l'affichage ni au
changement de semaine). Les requêtes externes s'ajoutent aux classes existantes `MusicBrainz` et `LastFm`.

**Tech Stack :** Python 3 (stdlib, `unittest`), SQLite via `pimedia.storage.database.Database`, JS sans framework
(`App.el`), tests de page jsdom.

**Spec :** `docs/superpowers/specs/2026-11-27-radar-sorties-design.md`

## Global Constraints

- Règles de `AGENTS.md` (toutes) ; en particulier : une seule classe par service externe, SQL seulement dans
  `webapp/storage/` et `schema.py`, contrôleur mince, entités avec `to_api()`, **40 lignes par fonction, 300 par
  fichier dans `src/`**, une limite définie une seule fois côté serveur et envoyée au front.
- `src/pimedia/webapp/app.py` fait 294 lignes : le câblage du radar va dans `weekly_releases/assembly.py`,
  `app.py` n'y gagne que l'appel et le lancement du fil.
- Migrations publiées intouchables ; nouvelles migrations à la suite (29, …), testées sur une base remplie.
- Comparaisons de noms : `pimedia.shared.text.normalize`.
- Constantes (fichier `weekly_releases/limits.py`, seule définition) :
  `WINDOW_BEFORE_DAYS = 14`, `WINDOW_AFTER_DAYS = 60`, `PURGE_AFTER_DAYS = 30`, `FULL_SYNC_EVERY = 86400`,
  `NIGHT_HOUR = 4`, `REFRESH_COOLDOWN = 600`, `STYLE_PAGES_PER_WEEK = 2`, `MB_PAGE = 100`,
  `TREND_ARTISTS = 30`, `TREND_LABEL_ALBUMS = 30`, `TREND_STYLES = 5`, `SIMILAR_PER_ARTIST = 5`,
  `DISCOVERIES_PER_USER = 60`, `ARTISTS_PER_QUERY = 20`.
- Types de source : `style`, `label`, `artist`, `similar` ; origines : `manual`, `trends`, `discovery`.
- Signaux des tendances (spec + utilisateur) : favoris Subsonic (`getStarred2` : artistes, albums, morceaux) et
  marque-pages « À écouter ». **Pas** de `getAlbumList2 type=frequent` (commun au serveur). *Écart à la spec :*
  la table `album_ratings` n'est lue par aucun code (les notes passent par Subsonic dans `ratings.py`) ; elle
  n'est pas utilisée.
- Version : entrée **1.24** en tête de `src/i18n/versions.yaml`.
- Tests : `python3 -m unittest tests.<module> -v` pendant le travail ; à la fin
  `docker compose --profile tests run --rm tests`, entièrement vert.

## Review Focus

1. **Compte sans favori ni source** : la page propose de choisir des styles (style par défaut actuel), pas
   d'erreur ni de grille vide muette. → Task 6.
2. **MusicBrainz ou Last.fm en panne pendant la synchronisation** : les sorties déjà en base restent affichées,
   la source garde son dernier succès, l'échec est noté et la nuit suivante reprend. → Task 5.
3. **Source retirée puis tendance recalculée** : elle ne revient pas (masquée, pas supprimée). → Task 4.
4. **Nom d'artiste court ou homonyme** sans MBID (« Air ») : la recherche par nom n'accepte que l'égalité
   normalisée du nom crédité. → Task 2.
5. **Clics répétés sur ↻** : un seul lancement par compte toutes les 10 min ; la réponse donne l'heure de la
   prochaine possibilité. → Task 5.

---

### Task 1 : modèle de données et dépôts

**Files:**
- Modify: `src/pimedia/webapp/schema.py` (migration 29 ajoutée à `MIGRATIONS`)
- Create: `src/pimedia/webapp/storage/release_radar.py` (dépôts `ReleaseSources`, `RadarReleases`, `AlbumLabels`)
- Modify: `src/pimedia/webapp/storage/weekly_releases.py` (supprimé : remplacé par `ReleaseSources`)
- Create: `src/pimedia/webapp/weekly_releases/entities.py`, `src/pimedia/webapp/weekly_releases/limits.py`
- Test: `tests/test_release_radar_storage.py`

**Interfaces — Produces:**
- Migration 29 : `release_sources(id, user_id, kind, identity, name, origin, hidden, via, created_at)`,
  `UNIQUE(user_id, kind, identity)` ; `radar_releases(id TEXT PRIMARY KEY /* MBID groupe */, title, artist,
  released_on, kind, tags /* JSON trié */)` ; `radar_release_sources(release_id, source_kind, source_identity)` ;
  `radar_sync(source_kind, source_identity, synced_at, failed_at)` ; `album_labels(album_id PRIMARY KEY,
  label_id, label_name, release_id, looked_up_at)` (label_id NULL = rien trouvé) ; `radar_profiles(user_id
  PRIMARY KEY, tags /* JSON {tag: poids} */, computed_at, refresh_requested_at, discoveries_off INTEGER NOT NULL
  DEFAULT 0)`. Copie de
  `release_subscriptions` en `kind='style', origin='manual'`, puis `DROP TABLE release_subscriptions`.
- Entités : `RadarSource(id, kind, identity, name, origin, hidden, via)`, `RadarRelease(id, title, artist,
  released_on: date, kind, tags: tuple)`, `RadarCard(release, reasons: tuple[RadarSource], score: float,
  local: dict|None)`, `RadarWeek(monday, cards, filters: tuple[RadarFilter], updated_at, refresh_after)`,
  `RadarFilter(key, label, count)` ; chacune avec `to_api()`.
- `ReleaseSources` : `for_user(user_id, include_hidden=False) -> list[RadarSource]`,
  `add(user_id, kind, identity, name, origin, via=None) -> RadarSource` (ne réactive jamais une ligne masquée si
  `origin != 'manual'`), `hide(user_id, source_id)`, `active_union() -> list[(kind, identity, name)]`.
- `RadarReleases` : `save(source_kind, source_identity, releases)` (remplace les liens de cette source dans la
  fenêtre), `for_sources(sources, start, end) -> list[(RadarRelease, kind, identity)]`, `purge(before: date)`,
  `mark_synced(kind, identity, at)`, `mark_failed(kind, identity, at)`, `oldest_first(union) -> list`,
  `last_full_sync() -> int|None`.
- `AlbumLabels` : `get(album_id)`, `save(album_id, label_id, label_name, release_id, at)`.

- [ ] **Step 1 : tests en échec** — `test_migration_keeps_followed_styles` (base créée avec les migrations
  1–28, deux comptes, styles « noise rock » et « techno » ; après 29 : deux sources `style/manual` par compte,
  `PRAGMA foreign_key_check` vide) ; `test_hidden_trend_is_not_readded` (`add(... origin='trends')` après
  `hide` → toujours masquée ; `add(... origin='manual')` → réactivée) ; `test_union_is_deduplicated` (même label
  chez deux comptes → une entrée) ; `test_for_sources_filters_window_and_keeps_reason` ;
  `test_album_label_not_found_is_remembered` (`label_id is None` relu).
- [ ] **Step 2 :** `python3 -m unittest tests.test_release_radar_storage -v` → échec (module absent).
- [ ] **Step 3 :** migration, entités, `limits.py`, dépôts. Remplacer les usages de `ReleaseSubscriptions`
  (service, `app.py`, `tests/test_weekly_releases.py`) par `ReleaseSources` filtré sur `kind='style'`.
- [ ] **Step 4 :** relancer ce test et `tests.test_weekly_releases` → verts.
- [ ] **Step 5 :** commit `feat(radar): tables des sources et des sorties synchronisées`.

### Task 2 : requêtes MusicBrainz du radar

**Files:**
- Modify: `src/pimedia/shared/providers/musicbrainz/client.py`, `parsing.py`, `entities.py`
- Modify: `tests/fake_musicbrainz.py`
- Test: `tests/test_musicbrainz_radar.py`

**Interfaces — Consumes:** `RadarRelease` n'est pas utilisé ici (couche commune) : on étend `WeeklyRelease`
d'un champ `tags: tuple = ()`. **Produces :**
- `weekly_groups(genre, monday, sunday, limit, offset)` inchangé en signature, avec tags remplis.
- `groups_by_artists(artist_ids: tuple[str], start: date, end: date, offset=0) -> WeeklyReleasePage` :
  `arid:(id1 OR id2 …) AND (primarytype:album OR primarytype:ep) AND firstreleasedate:[start TO end]`.
- `groups_by_artist_name(name: str, start, end) -> WeeklyReleasePage` : `artist:"name"`, ne garde que les
  groupes dont `normalize(artist_name(row)) == normalize(name)`.
- `label_groups(label_id: str, start, end, offset=0) -> WeeklyReleasePage` : recherche `release` sur
  `laid:… AND date:[start TO end]`, regroupée par groupe de sortie ; garde un groupe si sa première sortie est
  dans la fenêtre (lecture `release-group/<id>` si la réponse ne la donne pas, TTL 7 jours).
- `search_labels(name) -> Result[tuple[MusicLabel(id, name, country, disambiguation)]]`.
- `artist_tags(artist_id) -> tuple[str]` (via `artist/<id>?inc=tags`, TTL 7 jours).
- Fenêtre : TTL `WEEKLY_TTL` réutilisé.

- [ ] **Step 0 (vérification réelle, une fois) :** une requête `release-group` de recherche sur
  musicbrainz.org (avec l'User-Agent du projet) ; noter dans le commit si `tags` est présent dans les résultats.
  S'il est absent : `weekly_groups` laisse `tags=()` et le tri utilisera `artist_tags` (Task 4).
  Mesurer aussi la longueur maximale acceptée de `arid:(…)` avec 20 identifiants ; si refusée, réduire
  `ARTISTS_PER_QUERY`.
- [ ] **Step 1 : tests en échec** (faux MusicBrainz) : `test_artists_are_grouped_in_one_query`
  (20 MBID → 1 URL, la requête contient chaque `arid`) ; `test_name_search_rejects_homonyms` (« Air » ne garde
  pas « Air Supply ») ; `test_label_keeps_only_new_groups` (réédition d'un groupe sorti en 1999 écartée) ;
  `test_tags_are_parsed` ; `test_search_labels`.
- [ ] **Step 2 :** `python3 -m unittest tests.test_musicbrainz_radar -v` → échec.
- [ ] **Step 3 :** méthodes ci-dessus dans `MusicBrainz` (aucune URL ailleurs), analyse dans `parsing.py`.
- [ ] **Step 4 :** ce test, `tests.test_musicbrainz`, `tests.test_weekly_releases` → verts.
- [ ] **Step 5 :** commit `feat(musicbrainz): requêtes groupées par artiste, label et recherche de labels`.

### Task 3 : artistes proches Last.fm

**Files:**
- Modify: `src/pimedia/webapp/providers/lastfm.py`
- Test: `tests/test_lastfm_similar.py`

**Produces :** `LastFm.similar_artists(name: str, limit: int) -> tuple[SimilarArtist(name, mbid, match: float)]`
(`method=artist.getSimilar`, `autocorrect=1`, TTL 7 jours ; erreur Last.fm 6 « artiste inconnu » → `()` ;
désactivé si `not self.enabled` → `()`).

- [ ] **Step 1 :** `test_similar_artists_parses_mbid_and_match`, `test_unknown_artist_returns_empty`,
  `test_disabled_without_key_makes_no_call`.
- [ ] **Step 2 :** lancer → échec. **Step 3 :** implémenter via `_call`. **Step 4 :** vert.
- [ ] **Step 5 :** commit `feat(lastfm): artistes proches`.

### Task 4 : tendances, découvertes et tri selon les goûts

**Files:**
- Create: `src/pimedia/webapp/weekly_releases/trends.py` (`Trends`), `src/pimedia/webapp/weekly_releases/taste.py`
  (fonctions pures)
- Test: `tests/test_release_trends.py`

**Interfaces — Consumes :** Tasks 1–3 ; `Subsonic.call(Credentials.of(user), "getStarred2")` ;
`ListenLaterRepository` (`storage/listen_later.py`) pour les marque-pages ; `Exploration.library` non utilisé.
**Produces :**
- `Trends(subsonic, musicbrainz, lastfm, sources, album_labels, profiles, listen_later, clock)`
  `.refresh(user) -> None` : calcule et enregistre, pour un compte :
  artistes (favoris puis marque-pages, `TREND_ARTISTS` au plus, MBID via `search_artists` avec score ≥ 90 et nom
  égal normalisé) → sources `artist/trends` ; labels des albums favoris (`AlbumLabels` d'abord ; sinon
  `find_releases` + `release_credits`, première édition dont le titre et l'artiste correspondent ;
  `TREND_LABEL_ALBUMS` au plus par nuit) → sources `label/trends` ; profil de tags (somme des `artist_tags`
  des artistes des tendances) → `radar_profiles` ; `TREND_STYLES` styles du profil présents dans le catalogue
  → sources `style/trends` ; proches Last.fm (`SIMILAR_PER_ARTIST` par artiste, absents de la bibliothèque —
  nom normalisé absent des favoris et de l'index d'artistes —, `DISCOVERIES_PER_USER` au plus) → sources
  `similar/discovery` avec `via` = nom de l'artiste d'origine ; identité = MBID, sinon `name:` + nom normalisé.
- `taste.score(release_tags: tuple, profile: dict) -> float` : cosinus entre les tags de la sortie (poids 1)
  et le profil ; 0 si l'un est vide.
- `taste.rank(cards) -> list` : score décroissant, puis date, puis titre.

- [ ] **Step 1 :** `test_trends_use_only_personal_signals` (aucun appel `getAlbumList2`) ;
  `test_hidden_trend_stays_hidden_after_refresh` ; `test_album_label_is_looked_up_once` (deuxième refresh : aucun
  appel MusicBrainz pour cet album) ; `test_discoveries_skip_library_artists_and_keep_via` ;
  `test_score_prefers_matching_tags` (`score(("techno",), {"techno": 3}) > score(("folk",), {"techno": 3})`) ;
  `test_rank_is_stable_on_equal_scores`.
- [ ] **Step 2 :** lancer → échec. **Step 3 :** implémenter (fonctions ≤ 40 lignes ; `trends.py` ≤ 300 lignes,
  sinon séparer labels et découvertes dans `trend_labels.py`). **Step 4 :** vert.
- [ ] **Step 5 :** commit `feat(radar): tendances d'après les favoris et découvertes Last.fm`.

### Task 5 : synchronisation en tâche de fond

**Files:**
- Create: `src/pimedia/webapp/weekly_releases/sync.py` (`ReleaseSync`)
- Test: `tests/test_release_sync.py`

**Interfaces — Consumes :** Tasks 1–4. **Produces :**
- `ReleaseSync(musicbrainz, trends, sources, releases, profiles, users, today, clock, sleep)` :
  `.run()` (boucle : `sync_all()` au démarrage si `last_full_sync()` absent ou plus vieux que
  `FULL_SYNC_EVERY`, puis chaque nuit à `NIGHT_HOUR`) ; `.sync_all()` (trends de chaque compte, puis union des
  sources du plus ancien au plus récent, puis `purge`) ; `.sync_source(kind, identity, name)` (style : une
  requête par semaine de la fenêtre, `STYLE_PAGES_PER_WEEK` pages de `MB_PAGE` ; label : `label_groups` ;
  artistes : regroupés par `ARTISTS_PER_QUERY` avec `groups_by_artists`, sans MBID `groups_by_artist_name`) ;
  `.refresh_user(user) -> int` (heure de la prochaine possibilité ; lève `TooSoon(retry_at)` défini dans
  `webapp/errors.py` si moins de `REFRESH_COOLDOWN`) ; `.sync_new_source(source)` lancé dans un fil.
- Les échecs (`ProviderUnavailable`, `OSError`, `ValueError`) d'une source sont notés (`mark_failed`) et
  n'arrêtent pas les autres.

- [ ] **Step 1 :** `test_startup_syncs_when_never_synced` ; `test_startup_skips_recent_sync` ;
  `test_shared_label_costs_one_call` ; `test_style_queries_each_week_of_window` (11 semaines → 11 requêtes
  minimum) ; `test_failure_keeps_previous_releases` ; `test_refresh_cooldown` (deuxième appel avant 600 s →
  `TooSoon` avec `retry_at`) ; `test_purge_removes_old_releases`.
- [ ] **Step 2 :** lancer → échec. **Step 3 :** implémenter (horloge et `sleep` injectés). **Step 4 :** vert.
- [ ] **Step 5 :** commit `feat(radar): synchronisation de nuit et au démarrage`.

### Task 6 : service, contrôleur et routes

**Files:**
- Modify: `src/pimedia/webapp/weekly_releases/service.py` (le radar s'ajoute ; `week()` par style reste pour
  les semaines hors fenêtre)
- Create: `src/pimedia/webapp/weekly_releases/assembly.py` (`build(app) -> (controller, sync)`)
- Modify: `src/pimedia/webapp/controllers/weekly_releases.py`, `src/pimedia/webapp/app.py` (appel de
  `assembly.build` et `threading.Thread(target=sync.run, daemon=True).start()` à côté de `news.run`)
- Test: `tests/test_weekly_releases.py` (étendu)

**Produces (routes, réponses = `to_api()`) :**
- `GET /api/news/releases/radar?monday=YYYY-MM-DD&filter=all|style:<nom>|labels|artists|discoveries` →
  `RadarWeek` : cartes triées par `taste.rank`, chaque carte avec ses raisons et `local` (rapprochement
  bibliothèque fait par le service : `Exploration.local` en parallèle sur les cartes, cache 5 min par compte) ;
  `filters` avec nombres ; `updatedAt` ; `refreshAfter` ; `outOfWindow: true` si la semaine sort de la fenêtre
  (le front bascule alors sur la vue par style existante) ; `empty: "no-sources"` si le compte n'a aucune source.
- `GET /api/news/releases/sources` → sources du compte groupées par type + `discoveriesEnabled`
  (`lastfm.enabled`) + `limits` (`REFRESH_COOLDOWN`).
- `POST /api/news/releases/sources/add {kind, identity, name}` (style : nom du catalogue ; label/artiste :
  MBID issu de la recherche) → source créée + `sync_new_source`.
- `POST /api/news/releases/sources/hide {id}`.
- `POST /api/news/releases/discoveries {enabled}` (colonne `discoveries_off` ; coupées → pas de pastille
  Découvertes ni de calcul Last.fm pour ce compte).
- `GET /api/news/releases/search?kind=label|artist&q=` → résultats MusicBrainz.
- `POST /api/news/releases/refresh` → `{refreshAfter}` ou 429 avec `retryAt`.
- Les routes existantes (`/api/news/releases`, `/genres`, `/follow`) restent ; `/follow` écrit dans
  `release_sources`.

- [ ] **Step 1 :** tests de contrôleur avec session et CSRF (modèle des tests existants) :
  `test_radar_reads_database_without_external_call` ; `test_radar_filters_and_counts` ;
  `test_radar_card_reasons_and_local_match` ; `test_out_of_window_week` ; `test_account_without_sources` ;
  `test_sources_are_isolated_between_accounts` ; `test_refresh_too_soon_returns_429`.
- [ ] **Step 2 :** lancer → échec. **Step 3 :** implémenter ; `app.py` ≤ 300 lignes. **Step 4 :** vert.
- [ ] **Step 5 :** commit `feat(radar): routes du radar et câblage`.

### Task 7 : page (disposition A) et panneau « Mes sources »

**Files:**
- Modify: `src/web-pc/static/js/weekly-releases.js` (en-tête de semaine, pastilles, grille, raisons)
- Create: `src/web-pc/static/js/weekly-sources.js` (panneau ⚙ Mes sources : groupes Styles/Labels/Artistes/
  Découvertes, origine, croix, recherche d'ajout) ; l'inclure là où `weekly-releases.js` est chargé
- Modify: `src/web-pc/static/css/views.css`, `src/i18n/fr.yaml` (section `webapp.weekly`)
- Test: `tests/e2e_weekly_releases.js` (étendu), enregistré dans `tests/run_e2e`

**Comportement :** pastilles « Tout · <style>… · Labels · Mes artistes · ✨ Découvertes (n) » (Découvertes
absente si `discoveriesEnabled` est faux) ; changer de pastille ou de semaine remplace la grille seulement ;
carte = pochette (`loading="lazy"`), titre, artiste, type · date, raison (« label X », « tu suis cet artiste »,
« d'après tes écoutes », « proche de X »), « Dans ta bibliothèque » / « Écouter » ; « mis à jour il y a N min »
et ↻ désactivé jusqu'à `refreshAfter` ; semaine hors fenêtre → vue par style existante ; compte sans source →
choix d'un style (défaut serveur) ; source tout juste ajoutée → « recherche en cours » dans le panneau puis
rechargement de la grille ; interrupteur Découvertes dans le panneau ; textes via `App.el(..., {text})` seulement.

- [ ] **Step 1 :** parcours jsdom en échec : ouverture → une requête `/radar`, aucune requête `/explore/local` ;
  clic « Techno » → grille remplacée, pastilles intactes ; flèche → nouvelle requête `/radar` seulement ;
  ↻ puis 429 → bouton désactivé avec l'heure ; panneau : masquer une source → elle disparaît du panneau et des
  pastilles ; ajout d'un label par recherche ; pas de pastille Découvertes sans Last.fm ni quand
  l'interrupteur est coupé ; compte sans source.
- [ ] **Step 2 :** `node tests/e2e_weekly_releases.js` → échec. **Step 3 :** implémenter (fichiers ≤ 300 lignes,
  fonctions ≤ 40). **Step 4 :** vert.
- [ ] **Step 5 :** commit `feat(radar): page des sorties personnalisée`.

### Task 8 : version, documentation et suite complète

**Files:**
- Modify: `src/i18n/versions.yaml` (entrée `1.24`, date du jour de mise en ligne, titre « Sorties de la semaine
  pour toi », changements écrits pour les utilisateurs), `docs/features/actualite.md` (section « Sorties de la
  semaine » réécrite : radar, sources, tâche de fond, routes, tests), guide Help « Suivre les sorties de la
  semaine » dans `src/i18n/fr.yaml`.

- [ ] **Step 1 :** `docker compose --profile tests run --rm tests` → tout vert (sinon corriger avant d'aller
  plus loin).
- [ ] **Step 2 :** commit `docs(radar): version 1.24 et documentation`.
- [ ] **Step 3 (avec accord de l'utilisateur) :** mise en production par `deploy/pc/push.sh` ; vérifier dans
  les journaux du conteneur que la première synchronisation démarre, puis ouvrir `#/news/releases`.
