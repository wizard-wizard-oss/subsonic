# Page « Rangement » — plan de construction

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal :** une page réservée aux administrateurs qui montre ce que le rangement a fait, ce qui reste dans Incoming et
pourquoi, et propose de réunir les groupes éparpillés sous plusieurs noms (orthographe proche ou MusicBrainz).

**Architecture :** un journal des rangements en base, rempli par les trois endroits qui déplacent un album (envoi,
rattrapage d'Incoming, regroupement), tous derrière un même verrou de bibliothèque. Les raisons d'attente réutilisent
les règles de `MusicTree.place`. Les propositions de doublons combinent une comparaison d'écritures (hors ligne) et un
cache MusicBrainz rempli en tâche de fond (1 requête/s). Un contrôleur `/api/sorting/*` (droit `admin`) et une vue
`Views.sorting` (`#/sorting`).

**Tech stack :** Python 3.11 bibliothèque standard (urllib, sqlite3, threading), unittest ; JavaScript sans build,
parcours jsdom (`tests/e2e_webapp.js`).

**Spec :** `docs/superpowers/specs/2026-10-27-page-rangement-design.md` (à lire avant ce plan).

**Pas de dépôt git** dans ce projet : pas d'étape « commit ». À la fin de chaque tâche, les tests de la tâche passent.

**Lancer les tests** (racine `sources/`) : une tâche → `python3 -m unittest tests.<module> -v` ; tout →
`docker compose build tests && docker compose run --rm tests` (sans `build`, l'image teste l'ancien code).

## Global Constraints
- Règles de `docs/CONVENTIONS.md` : dépôts (SQL seulement, renvoient des entités) → services → contrôleurs (HTTP
  seulement), tout assemblé dans `app.py` ; entités en dataclasses avec `to_api()`.
- Migrations numérotées : ajouter à la fin de la liste de `src/pimedia/webapp/schema.py` (la dernière publiée est la 14),
  jamais modifier une migration existante ; tables et colonnes en anglais.
- Textes en français dans `src/i18n/fr.yaml`, clés en anglais, section `sorting` ; erreurs renvoyées comme clés de texte.
- Pas d'`innerHTML`, un fichier JS par composant, couleurs en variables de thème.
- Écritures protégées CSRF (`write(...)` dans `app.py`), entrées validées côté serveur.
- Réservé aux administrateurs : droit `admin` (`user.can("admin")`, rôle Subsonic `adminRole`).
- Jamais écraser ni effacer un titre ; jamais réunir sans validation.
- MusicBrainz : au plus **1 requête par seconde**, `User-Agent` = `shared.external.USER_AGENT` (aucune adresse e-mail),
  réponses gardées en base.
- Les collaborations ne sont jamais proposées au regroupement.
- Fiche `docs/features/rangement.md`, `docs/features/README.md`, `docs/ETAT.md` à jour à la fin.

## Review Focus
1. **Noms qui ne sont pas de l'UTF-8 valide** (`Chopin/Int\udce9grale…` existe sur le serveur) : la page s'affiche
   (caractère de remplacement) et le regroupement déplace le bon dossier → clés de dossier opaques (Tâche 5), test en
   Tâches 5 et 7.
2. **Proposition périmée** : un dossier renommé ou déjà réuni entre l'affichage et la validation → refus propre
   `sorting.stale`, rien déplacé (Tâche 7).
3. **Nom gardé qui ne diffère que par la casse d'un dossier existant** (`osees` alors que `Osees` existe, disque Linux
   sensible à la casse) → c'est le même dossier, pas un second (Tâche 7).
4. **MusicBrainz absent, lent ou qui refuse (503)** : les propositions d'orthographe s'affichent quand même, la tâche de
   fond ralentit et réessaie plus tard (Tâche 4).
5. **Rattrapage d'Incoming pendant un regroupement** : jamais en même temps (verrou, Tâche 1) ; un album bloqué
   n'empêche pas les autres d'être rangés (Tâche 1).

---

### Tâche 0 : constater ce que Subsonic perd quand un dossier change de chemin

Pas de code livré : le résultat décide de ce que compte la Tâche 6 et si la Tâche 7 reporte les commentaires.

- [ ] **Étape 1 :** lancer un Subsonic de test (`gzurowski/subsonic`, image du serveur) sur une **copie** de 2 artistes
  (jamais la bibliothèque réelle), scanner, puis avec un compte : cœur sur un titre, un album, l'artiste ; une étoile sur
  le dossier d'album (`setRating`) ; le titre dans une playlist. Noter les identifiants (titre, dossier, album ID3,
  artiste ID3).
- [ ] **Étape 2 :** déplacer le dossier d'album chez l'autre artiste, scanner (`startScan`, attendre `getScanStatus`).
- [ ] **Étape 3 :** relever pour chaque élément s'il survit (`getStarred`, `getStarred2`, `getPlaylist`,
  `getMusicDirectory` → `userRating`) et si l'identifiant d'album ID3 a changé (`getSong` du titre → `albumId`).
- [ ] **Étape 4 :** écrire le tableau du résultat dans `docs/features/rangement.md` (section « Ce que Subsonic perd »).
  Expected : la liste `LOST` de la Tâche 6 et la décision « reporter les commentaires » (oui si `albumId` change) en
  découlent.

---

### Tâche 1 : journal des rangements et verrou de la bibliothèque

**Files :**
- Modify : `src/pimedia/webapp/schema.py` (migration 15), `src/pimedia/webapp/entities.py`,
  `src/pimedia/webapp/layout.py`, `src/pimedia/webapp/uploads.py`, `src/pimedia/webapp/incoming.py`,
  `src/pimedia/webapp/app.py`
- Create : `src/pimedia/webapp/storage/placements.py`
- Test : `tests/test_sorting.py` (nouveau), `tests/test_incoming.py`, `tests/test_webapp_upload.py`

**Interfaces :**
- Produces :
  - table `placements (id INTEGER PRIMARY KEY, placed_at INTEGER NOT NULL, origin TEXT NOT NULL, destination TEXT NOT
    NULL, how TEXT NOT NULL, user_id INTEGER REFERENCES users (id) ON DELETE SET NULL)` + index `(placed_at DESC)` ;
    `how` ∈ `upload`, `incoming`, `regroup` ; `origin` et `destination` = « Artiste/Album » (texte affichable).
  - `entities.Placement(id, placed_at, origin, destination, how, username)` avec `to_api()` →
    `{"id", "placedAt", "origin", "destination", "how", "by", "matched"}` ; `matched` = vrai quand le nom d'artiste
    d'origine diffère de celui d'arrivée (« Lamb of God » → « Lamb Of God »).
  - `PlacementRepository(db)` : `add(placed_at, origin, destination, how, user_id=None)`, `recent(limit=200) -> list[Placement]`.
  - `layout.display(name) -> str` : `name.encode("utf-8", "surrogateescape").decode("utf-8", "replace")`.
  - `MusicTree.lock` : un `threading.RLock()` partagé par tout ce qui déplace des albums.
  - `MusicTree(music_dir, incoming, journal=None)` ; `journal(origin, destination, how, user_id)` est appelé par
    `place()` après chaque déplacement réussi (noms passés par `display`).
  - `MusicTree.place(folder, artist, album, how="incoming", user_id=None)` (signature étendue, retour inchangé).

- [ ] **Étape 1 : tests qui échouent**, dans `tests/test_sorting.py` (base `MusicTestCase` de `test_incoming.py`,
  journal = liste en mémoire) :
  - `test_place_notes_the_move` : `place(…"Lamb of God", "Into Oblivion", how="upload", user_id=7)` avec
    `Lamb Of God/` existant → journal `[("Lamb of God/Into Oblivion", "Lamb Of God/Into Oblivion", "upload", 7)]`.
  - `test_refused_place_notes_nothing` : album déjà présent → journal vide.
  - `test_repository_recent_first` : trois `add` → `recent()` du plus récent au plus ancien, `username` rempli par
    jointure sur `users`, `None` si le compte a disparu.
  - `test_matched_flag` : `Placement(…, origin="Lamb of God/X", destination="Lamb Of God/X").to_api()["matched"]` vrai,
    faux quand les artistes sont identiques.
  - dans `tests/test_incoming.py`, `test_one_blocked_album_does_not_stop_the_others` : deux albums prêts, le premier
    dans un dossier en lecture seule (`chmod 0o555` sur son dossier d'artiste cible) → le second est rangé, l'erreur
    est écrite dans le journal du conteneur (`log`).
  - `test_sorter_waits_for_the_lock` : verrou tenu par un autre fil → `sort()` renvoie `[]` sans rien déplacer.
  - dans `tests/test_webapp_upload.py`, `test_zip_placement_is_noted_with_the_sender` : zip `Converge/Jane Doe/01.flac`
    envoyé par bob → `app.placements.recent()[0]` a `how == "upload"` et `username == "bob"`.
- [ ] **Étape 2 :** `python3 -m unittest tests.test_sorting tests.test_incoming tests.test_webapp_upload -v` → FAIL.
- [ ] **Étape 3 : implémenter.** Migration 15 avec commentaire en tête comme les autres. `IncomingSorter.sort` :
  `if not library.lock.acquire(blocking=False): return []`, `try/finally` ; l'`OSError` se rattrape **par album**
  (journalisé, on continue) au lieu d'interrompre le passage. `Uploads.save` / `_save_zip` / `_place_albums` reçoivent
  `user` et appellent `place(…, how="upload", user_id=user.id)` sous `with self.library.lock`. `app.py` :
  `self.placements = PlacementRepository(self.db)` et `MusicTree(…, journal=lambda o, d, h, u:
  self.placements.add(int(time.time()), o, d, h, u))`.
- [ ] **Étape 4 :** mêmes tests → PASS ; tout `tests.test_incoming` et `tests.test_webapp_upload` passe encore.

---

### Tâche 2 : pourquoi un album reste dans Incoming

**Files :**
- Modify : `src/pimedia/webapp/layout.py`, `src/pimedia/webapp/incoming.py`
- Test : `tests/test_sorting.py`

**Interfaces :**
- Produces :
  - `MusicTree.refusal(folder, artist, album) -> str` : `""` si `place` le rangerait, sinon une clé parmi
    `lowercase`, `subfolders`, `incoming_name`, `exists`. `place()` l'utilise (pas de règle en double).
  - `MusicTree.existing_album(artist, album) -> str` : « Artiste/Album » du dossier déjà présent (pour `exists`).
  - `IncomingSorter.waiting() -> list[dict]` : un élément par album d'`Incoming/Artiste/Album` et par fichier ou dossier
    à la racine d'Incoming : `{"path": display(chemin relatif à Incoming), "reason": clé, "detail": texte ou ""}`.
    Clés en plus de celles de `refusal` : `hidden` (nom commençant par un point, sauf fichiers techniques `.xxx.part`
    et `.unzip` en cours, ignorés), `loose` (titre ou dossier sans artiste à la racine), `recent` (modifié depuis moins
    de `wait_hours`, `detail` = heure prévue « 14h37 »), `ready` (rangé au prochain passage), `disabled`
    (`wait_hours == 0`). `__MACOSX` n'est pas listé.

- [ ] **Étape 1 : tests qui échouent** (`IncomingSorter` avec horloge factice, comme dans `test_incoming.py`) :
  `test_waiting_reasons` construit `Le$/lost In Japan`, `..htop/Lykke`, `Converge/Axe to fall` (présent en
  bibliothèque), `Converge/Live/Face A/01.flac`, `titre.mp3` à la racine, `Premo Rice/Reset` modifié il y a 10 min,
  `Chat Pile/Cool World` vieux de 2 h, et vérifie la liste exacte des `(path, reason)` :
  `lowercase`, `hidden`, `exists` (detail `Converge/Axe To Fall`), `subfolders`, `loose`, `recent`, `ready`.
  `test_place_and_refusal_agree` : pour chacun de ces albums, `refusal() == ""` ⇔ `place()` renvoie une place.
- [ ] **Étape 2 :** `python3 -m unittest tests.test_sorting -v` → FAIL.
- [ ] **Étape 3 :** implémenter `refusal`, `existing_album`, `waiting` ; `place()` appelle `refusal()`.
- [ ] **Étape 4 :** `tests.test_sorting`, `tests.test_incoming` → PASS.

---

### Tâche 3 : doublons par l'écriture

**Files :**
- Create : `src/pimedia/webapp/duplicates.py`
- Test : `tests/test_sorting.py`

**Interfaces :**
- Produces :
  - `is_collaboration(name) -> bool` : vrai si le nom contient ` & `, `, `, ` feat`, ` feat.`, ` ft. `, ` x `, ` with `
    (insensible à la casse) ; **sauf** si ce nom exact est aussi un artiste MusicBrainz connu (paramètre
    `known_bands: set[str]` de normalisés, vide par défaut) — ainsi « Simon & Garfunkel » reste un groupe une fois
    MusicBrainz passé.
  - `spelling_key(name) -> str` : `normalised(name)` sans ponctuation ni espaces, et sans article de tête
    `the `/`thee ` (« Thee Oh Sees » → `ohsees`, « The Oh Sees » → `ohsees`).
  - `spelling_groups(names: list[str], known_bands=frozenset()) -> list[list[str]]` : groupes d'au moins 2 dossiers ;
    même `spelling_key`, ou nom `A _ B` dont `spelling_key(A)` ou `spelling_key(B)` est celle d'un autre dossier
    (le dossier `A _ B` rejoint ce groupe). Collaborations exclues. Chaque groupe trié, liste triée.

- [ ] **Étape 1 : tests qui échouent** : `test_spelling_groups` avec `["Osees", "Thee Oh Sees", "Thee Oh Sees _ Osees",
  "Jay Worthy", "Jay Worthy & Harry Fraud", "Jay Worthy, George Clinton & LNDN DRGS", "DJ Naze", "Converge"]` →
  `[["Osees", "Thee Oh Sees", "Thee Oh Sees _ Osees"]]` (« Osees » rejoint par le `_`, Jay Worthy jamais) ;
  `test_split_release_is_proposed` : `["Melvins", "Melvins _ Napalm Death"]` → un groupe (l'administrateur l'écartera) ;
  `test_collaboration_known_band` : `is_collaboration("Simon & Garfunkel", {"simon & garfunkel"})` faux.
- [ ] **Étape 2 :** FAIL. **Étape 3 :** implémenter. **Étape 4 :** PASS.

---

### Tâche 4 : MusicBrainz en tâche de fond

**Files :**
- Modify : `src/pimedia/webapp/schema.py` (migration 16), `src/pimedia/webapp/entities.py`, `src/pimedia/webapp/app.py`
- Create : `src/pimedia/webapp/musicbrainz.py`, `src/pimedia/webapp/storage/musicbrainz.py`
- Test : `tests/test_sorting.py` (fetcher factice, horloge et `sleep` factices)

**Interfaces :**
- Consumes : `layout.normalised`, `shared.external.JsonFetcher`, `query_url`.
- Produces :
  - table `musicbrainz_artists (folder TEXT PRIMARY KEY, mbid TEXT NOT NULL DEFAULT '', name TEXT NOT NULL DEFAULT '',
    aliases TEXT NOT NULL DEFAULT '[]', checked_at INTEGER NOT NULL)` ; `folder` = `normalised(nom du dossier)` ;
    `mbid` vide = « pas de rattachement sûr ».
  - `entities.BandIdentity(folder, mbid, name, aliases: list[str], checked_at)`.
  - `MusicBrainzRepository(db)` : `get(folder) -> BandIdentity|None`, `save(identity)`, `all() -> list[BandIdentity]`,
    `missing(folders: list[str]) -> list[str]`.
  - `MusicBrainz(fetcher, clock=time.time, sleep=time.sleep)` : `identify(folder_name) -> BandIdentity` ; requête
    `https://musicbrainz.org/ws/2/artist/` avec `query='artist:"<nom>" OR alias:"<nom>"'`, `fmt=json`, `limit=10` ;
    rattachement seulement si **un seul** candidat a `normalised(name)` ou un `normalised(alias)` égal à
    `normalised(folder_name)` ; au moins 1 s entre deux requêtes.
  - `MusicBrainzWatch(musicbrainz, repository, artist_folders: callable -> list[str], log=print)` : `run()` boucle
    infinie (comme `IncomingSorter.run`) ; `check(limit=None)` demande les dossiers absents du cache, garde la réponse
    (ou une identité vide) ; sur erreur réseau ou 503 : arrêt du passage, nouvel essai dans 1 h ; les identités vides
    sont redemandées après 30 jours. Lancée par `app.py` si la musique est réglée (thread démon).

- [ ] **Étape 1 : tests qui échouent** : `test_single_exact_match` (réponse avec « Osees », alias « Thee Oh Sees »,
  « Oh Sees », « OCS » → identité remplie pour « Thee Oh Sees ») ; `test_homonyms_give_nothing` (deux « Converge » →
  `mbid` vide) ; `test_one_request_per_second` (deux `identify` → `sleep` appelé avec ≥ 1 s cumulé) ;
  `test_watch_stops_on_error_and_keeps_what_it_has` (2e requête lève `URLError` → 1 identité gardée, passage arrêté) ;
  `test_watch_skips_cached` (dossier déjà en cache → aucune requête).
- [ ] **Étape 2 :** FAIL. **Étape 3 :** implémenter (migration 16 commentée). **Étape 4 :** PASS.

---

### Tâche 5 : propositions de regroupement et propositions écartées

**Files :**
- Modify : `src/pimedia/webapp/schema.py` (migration 17), `src/pimedia/webapp/duplicates.py`, `src/pimedia/webapp/entities.py`
- Create : `src/pimedia/webapp/storage/dismissed.py`
- Test : `tests/test_sorting.py`

**Interfaces :**
- Consumes : Tâches 3 et 4.
- Produces :
  - `folder_key(name) -> str` = `name.encode("utf-8", "surrogateescape").hex()` et `folder_name(key) -> str` (inverse ;
    `ValueError` si la clé n'est pas valide). Seul moyen de désigner un dossier dans l'API.
  - table `dismissed_duplicates (folders TEXT PRIMARY KEY, dismissed_at INTEGER NOT NULL, user_id INTEGER REFERENCES
    users (id) ON DELETE SET NULL)` ; `folders` = JSON trié des `normalised` des dossiers du groupe. Un groupe écarté
    revient s'il gagne un nouveau dossier (clé différente).
  - `DismissedRepository(db)` : `add(folders: list[str], user_id)`, `keys() -> set[str]`.
  - `entities.Proposal(kind, folders: list[dict], suggestion: str)` avec `to_api()` ; `kind` ∈ `spelling`,
    `musicbrainz` ; chaque dossier `{"key", "name": display(nom), "albums": [display(album)…]}` ; `suggestion` = nom
    MusicBrainz actuel s'il respecte `capitalised`, sinon `""`.
  - `Duplicates(music_dir, identities: MusicBrainzRepository, dismissed: DismissedRepository)` :
    `proposals() -> list[Proposal]` : groupes MusicBrainz (même `mbid`, ≥ 2 dossiers, hors collaborations) puis
    groupes d'écriture qui ne recouvrent pas un groupe MusicBrainz ; écartés retirés ; Incoming jamais inclus.
    `dismiss(keys: list[str], user)`.

- [ ] **Étape 1 : tests qui échouent** : `test_musicbrainz_group_with_suggestion` (dossiers `Osees`, `Thee Oh Sees`,
  identités même `mbid`, nom « Osees » → une proposition `musicbrainz`, suggestion « Osees », albums listés) ;
  `test_dismissed_group_disappears_until_it_grows` ; `test_undecodable_names_round_trip` (dossier créé avec
  `os.fsdecode(b"Int\xe9grale")` → `name` affiché avec « � », `folder_name(folder_key(n)) == n`).
- [ ] **Étape 2 :** FAIL. **Étape 3 :** implémenter. **Étape 4 :** PASS.

---

### Tâche 6 : ce qui serait perdu

**Files :**
- Create : `src/pimedia/webapp/losses.py`
- Modify : `tests/fake_subsonic.py` (dossiers d'artistes et favoris par compte si absents)
- Test : `tests/test_sorting.py`

**Interfaces :**
- Consumes : résultat de la Tâche 0 ; `UserRepository.by_priority()`, `SubsonicServer.call`, `Credentials.of`,
  `ArtistIndexes` (pour retrouver l'identifiant Subsonic d'un dossier d'artiste par son nom), `MessageRepository`.
- Produces : `Losses(subsonic, users, artist_indexes, messages)` :
  `count(folder_names: list[str]) -> dict` → `{"accounts": n, "starred": n, "playlists": n, "rated": n,
  "comments": n}`, en ne gardant que les clés de `LOST` (constante du module, fixée d'après la Tâche 0). Un compte dont
  le jeton est refusé est sauté (non compté dans `accounts`). Comptes : tous ceux de `by_priority()`.

- [ ] **Étape 1 : test qui échoue** `test_counts_across_known_accounts` : alice a un cœur sur un titre de
  « Thee Oh Sees », bob le met dans une playlist, carol a un jeton refusé → `accounts == 2`, `starred == 1`,
  `playlists == 1` (autres clés selon `LOST`).
- [ ] **Étape 2 :** FAIL. **Étape 3 :** implémenter. **Étape 4 :** PASS.

---

### Tâche 7 : réunir un groupe

**Files :**
- Create : `src/pimedia/webapp/regroup.py`
- Test : `tests/test_sorting.py`

**Interfaces :**
- Consumes : `MusicTree` (verrou, `_same`, journal), `folder_name`, `Uploads.scan_as_admin`, `MessageRepository`.
- Produces : `class RegroupError(ValueError)` (clé de texte) ; `Regroup(library, scanner, messages=None)` :
  `merge(user, keep: str, keys: list[str]) -> dict` → `{"kept": "Osees", "moved": ["Osees/Cara Maluco", …],
  "left": ["Thee Oh Sees/Off Course"]}`.
  - `keep` : nom gardé ; s'il désigne (normalisé) un dossier existant, c'est lui ; sinon nouveau dossier (ou dossier
    renommé si un seul des dossiers du groupe, sans conflit) ; doit respecter `capitalised` et ne pas être Incoming ou
    une collaboration → sinon `sorting.bad_name`.
  - chaque clé doit désigner un dossier d'artiste existant → sinon `sorting.stale`, rien déplacé.
  - verrou pris sans attendre → sinon `sorting.busy`.
  - chaque album déplacé d'un coup (`os.replace`) ; album déjà présent (normalisé) → reste et va dans `left` ;
    dossier vidé supprimé (fichiers cachés compris) ; chaque déplacement noté `how="regroup"` ; puis `scanner()`.
  - si la Tâche 0 a montré que l'`albumId` change : après le scan, reporter les sujets `album:<ancien>` sur
    `album:<nouveau>` (couple retrouvé par artiste gardé + nom d'album) ; sinon ne rien faire et le noter dans la fiche.

- [ ] **Étape 1 : tests qui échouent** : `test_merge_into_existing` (Osees ← Thee Oh Sees + Thee Oh Sees _ Osees, un
  album en double laissé dans `left`, dossiers vidés supprimés, journal `regroup`, scan appelé une fois) ;
  `test_keep_differs_only_by_case` (`keep="osees"`… refusé `bad_name` ; `keep="OSEES"` → dossier `Osees` réutilisé,
  pas de second dossier) ; `test_stale_key_moves_nothing` ; `test_busy_while_sorting` (verrou tenu → `sorting.busy`) ;
  `test_undecodable_folder_is_moved` (dossier `os.fsdecode(b"Chopin \xe9")` désigné par sa clé).
- [ ] **Étape 2 :** FAIL. **Étape 3 :** implémenter. **Étape 4 :** PASS.

---

### Tâche 8 : API `/api/sorting/*`

**Files :**
- Create : `src/pimedia/webapp/controllers/sorting.py`
- Modify : `src/pimedia/webapp/app.py` (assemblage et routes)
- Test : `tests/test_sorting_http.py` (base `WebAppTestCase`, comme `test_webapp_upload.py`)

**Interfaces :**
- Consumes : Tâches 1 à 7.
- Produces (toutes avec `right="admin"`) :
  - `GET /api/sorting/placed` → `{"placed": [Placement.to_api()…]}`
  - `GET /api/sorting/waiting` → `{"waiting": IncomingSorter.waiting()}`
  - `GET /api/sorting/duplicates` → `{"proposals": [Proposal.to_api()…], "musicbrainz": {"checked": n, "total": n}}`
  - `GET /api/sorting/losses?folders=<clé>,<clé>` → `Losses.count`
  - `POST /api/sorting/merge` `{"keep": str, "folders": [clé…]}` → `Regroup.merge` ; `RegroupError` → 400 avec la clé
  - `POST /api/sorting/dismiss` `{"folders": [clé…]}` → `{"ok": true}`

- [ ] **Étape 1 : tests qui échouent** : `test_admin_only` (bob → 403 « droit manquant » sur chaque route, alice → 200) ;
  `test_merge_round_trip` (alice réunit, `GET placed` montre les déplacements `regroup`) ; `test_merge_needs_csrf` ;
  `test_bad_keys_are_refused` (clé non hexadécimale → 400 `sorting.stale`).
- [ ] **Étape 2 :** FAIL. **Étape 3 :** implémenter. **Étape 4 :** `python3 -m unittest tests.test_sorting_http -v` → PASS.

---

### Tâche 9 : la page `#/sorting` et la documentation

**Files :**
- Create : `src/web-pc/static/js/sorting.js`, `docs/features/rangement.md`
- Modify : `src/web-pc/index.html` (lien `nav-sorting` à côté de `nav-upload`, script), `src/web-pc/static/js/app.js`
  (`parse` accepte `sorting` ; lien montré si `App.can("admin")`), `src/web-pc/static/css/views.css` (`.sorting-*`),
  `src/i18n/fr.yaml` (`nav.sorting`, section `sorting`), `tests/e2e_webapp.js`, `docs/features/README.md`,
  `docs/features/envoi-fichiers.md` (renvoi vers la page), `docs/ETAT.md`
- Test : `tests/e2e_webapp.js`

**Interfaces :**
- Consumes : API de la Tâche 8.
- Produces : `Views.sorting` (`render(main, route)`) en trois parties : « Rangé récemment » (date, destination, origin
  si différente, badge « rapproché » si `matched`, façon et compte) ; « En attente dans Incoming » (chemin + raison
  traduite `sorting.reason.<clé>`) ; « Groupes en double » (dossiers et albums, suggestion, champ du nom gardé
  prérempli avec la suggestion ou le dossier qui a le plus d'albums, bouton « Voir ce qui serait perdu » → chiffres,
  boutons « Réunir » — avec confirmation `dialogs.js` — et « Ce ne sont pas les mêmes »). État MusicBrainz « 1 200 /
  4 850 artistes vérifiés ».

- [ ] **Étape 1 : parcours jsdom qui échoue** dans `tests/e2e_webapp.js` : alice voit le lien « Rangement », bob non ;
  la page liste un rangement et une raison d'attente ; « Réunir » sur une proposition d'écriture appelle
  `/api/sorting/merge` et la proposition disparaît ; « Ce ne sont pas les mêmes » la retire.
- [ ] **Étape 2 :** `python3 -m tests.run_e2e` → FAIL.
- [ ] **Étape 3 :** implémenter la vue (nœuds DOM via `App.el`, textes via `App.t`).
- [ ] **Étape 4 :** `python3 -m tests.run_e2e` → PASS.
- [ ] **Étape 5 : documentation** : `docs/features/rangement.md` (ce que ça fait de A à Z, résultat de la Tâche 0, où
  est le code, tests, ce qui n'existe pas : mémoire des regroupements, collaborations, déplacement d'un album seul,
  historique d'avant) ; ligne dans `docs/features/README.md` ; `docs/ETAT.md` passe la fonctionnalité de « à venir » à
  « faite, à vérifier sur le serveur ».
- [ ] **Étape 6 :** `docker compose build tests && docker compose run --rm tests` → tout passe.
