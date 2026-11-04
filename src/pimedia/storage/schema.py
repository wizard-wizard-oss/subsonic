"""Schéma de la base. Une migration = un script SQL, appliqué une seule fois, dans l'ordre.
Ne jamais modifier une migration déjà publiée : en ajouter une nouvelle à la fin."""

MIGRATIONS = [
    # 1 : première version (remplace config.json et les fichiers JSON de données)
    """
    CREATE TABLE app_settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL                     -- valeur JSON
    );
    CREATE TABLE podcast_subscriptions (
        feed_url TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        image_url TEXT NOT NULL DEFAULT '',
        author TEXT NOT NULL DEFAULT '',
        subscribed_at INTEGER NOT NULL
    );
    CREATE TABLE hidden_podcasts (
        feed_url TEXT PRIMARY KEY
    );
    CREATE TABLE episode_progress (
        episode_id TEXT PRIMARY KEY,
        feed_url TEXT NOT NULL DEFAULT '',
        title TEXT NOT NULL DEFAULT '',
        podcast_title TEXT NOT NULL DEFAULT '',
        image_url TEXT NOT NULL DEFAULT '',
        audio_url TEXT NOT NULL DEFAULT '',
        position_s REAL NOT NULL DEFAULT 0,
        duration_s REAL NOT NULL DEFAULT 0,
        played INTEGER NOT NULL DEFAULT 0,
        updated_at INTEGER NOT NULL
    );
    CREATE INDEX episode_progress_feed ON episode_progress (feed_url);
    CREATE TABLE local_playlists (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        created_at INTEGER NOT NULL
    );
    CREATE TABLE playlist_tracks (
        playlist_id TEXT NOT NULL REFERENCES local_playlists (id) ON DELETE CASCADE,
        position INTEGER NOT NULL,
        track_id TEXT NOT NULL,
        track TEXT NOT NULL,                    -- titre au format de l'interface (JSON)
        PRIMARY KEY (playlist_id, position)
    );
    CREATE TABLE external_favorites (
        track_id TEXT PRIMARY KEY,
        track TEXT NOT NULL,
        added_at INTEGER NOT NULL
    );
    CREATE TABLE search_history (
        kind TEXT NOT NULL,                     -- « music » ou « podcasts »
        query TEXT NOT NULL,
        query_key TEXT NOT NULL,                -- en minuscules : une recherche refaite remonte au lieu d'être répétée
        searched_at INTEGER NOT NULL,
        PRIMARY KEY (kind, query_key)
    );
    CREATE TABLE unplayable_videos (
        video_id TEXT PRIMARY KEY,
        marked_at INTEGER NOT NULL
    );
    CREATE TABLE play_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        track_id TEXT NOT NULL,
        title TEXT NOT NULL DEFAULT '',
        artist TEXT NOT NULL DEFAULT '',
        album TEXT NOT NULL DEFAULT '',
        album_id TEXT NOT NULL DEFAULT '',
        source TEXT NOT NULL DEFAULT 'subsonic',
        played_at INTEGER NOT NULL
    );
    CREATE INDEX play_history_album ON play_history (album_id, played_at);
    CREATE TABLE queue_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        position INTEGER NOT NULL,
        track TEXT NOT NULL,                    -- JSON
        added_by TEXT NOT NULL DEFAULT 'screen',
        added_at INTEGER NOT NULL
    );
    CREATE INDEX queue_items_position ON queue_items (position);
    CREATE TABLE queue_state (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        current_item_id INTEGER,
        version INTEGER NOT NULL DEFAULT 0
    );
    INSERT INTO queue_state (id, current_item_id, version) VALUES (1, NULL, 0)
    """,
    # 2 : demandes d'ajout à la file (téléphones) en attente d'être prises par l'écran du Pi
    """
    CREATE TABLE queue_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        track TEXT NOT NULL,                    -- JSON
        mode TEXT NOT NULL CHECK (mode IN ('next', 'end')),
        added_by TEXT NOT NULL,
        requested_at INTEGER NOT NULL
    )
    """,
]
