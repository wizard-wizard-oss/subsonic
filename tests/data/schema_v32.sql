index | chat_messages_topic | CREATE INDEX chat_messages_topic ON chat_messages (topic, id)
index | ext_favorites_by_date | CREATE INDEX ext_favorites_by_date ON ext_favorites (user_id, added_at DESC)
index | listen_later_by_date | CREATE INDEX listen_later_by_date ON listen_later (user_id, created_at DESC, id DESC)
index | listening_history_user_target | CREATE INDEX listening_history_user_target ON listening_history (user_id, target_id, id DESC)
index | message_mentions_user | CREATE INDEX message_mentions_user ON message_mentions (user_id, message_id)
index | news_articles_by_date | CREATE INDEX news_articles_by_date ON news_articles (published_at DESC, id DESC)
index | notifications_by_recipient | CREATE INDEX notifications_by_recipient ON notifications (recipient_id, id DESC)
index | notifications_unread_by_recipient | CREATE INDEX notifications_unread_by_recipient ON notifications (recipient_id) WHERE read_at IS NULL
index | playlist_ext_tracks_by_place | CREATE INDEX playlist_ext_tracks_by_place ON playlist_ext_tracks (playlist_id, after_songs, place, id)
index | radar_release_artists_artist | CREATE INDEX radar_release_artists_artist ON radar_release_artists (artist_id)
index | radar_release_sources_source | CREATE INDEX radar_release_sources_source ON radar_release_sources (source_kind, source_identity)
index | radar_releases_date | CREATE INDEX radar_releases_date ON radar_releases (released_on)
index | recommendation_comments_by_thread | CREATE INDEX recommendation_comments_by_thread ON recommendation_comments (recommendation_id, id)
index | recommendation_comments_unread | CREATE INDEX recommendation_comments_unread ON recommendation_comments (recipient_id) WHERE read_at IS NULL
index | recommendations_active_target | CREATE UNIQUE INDEX recommendations_active_target
        ON recommendations (sender_id, recipient_id, target_id) WHERE archived_at IS NULL
index | recommendations_by_recipient | CREATE INDEX recommendations_by_recipient ON recommendations (recipient_id, created_at DESC, id DESC)
index | recommendations_by_sender | CREATE INDEX recommendations_by_sender ON recommendations (sender_id, id DESC)
index | recommendations_unread_by_recipient | CREATE INDEX recommendations_unread_by_recipient ON recommendations (recipient_id) WHERE read_at IS NULL
index | release_sources_identity | CREATE INDEX release_sources_identity ON release_sources (kind, identity)
index | sessions_user | CREATE INDEX sessions_user ON sessions (user_id)
index | upload_history_by_user | CREATE INDEX upload_history_by_user ON upload_history (user_id, id DESC)
table | album_labels | CREATE TABLE album_labels (
        album_id TEXT PRIMARY KEY,
        label_id TEXT,
        label_name TEXT,
        release_id TEXT,
        looked_up_at INTEGER NOT NULL
    )
table | albums_discussed | CREATE TABLE albums_discussed (
        album_id TEXT PRIMARY KEY,                       -- pour la liste « albums commentés récemment »
        title TEXT NOT NULL DEFAULT '',
        artist TEXT NOT NULL DEFAULT '',
        cover_id TEXT NOT NULL DEFAULT '',
        last_message_at INTEGER NOT NULL
    )
table | artist_discogs_links | CREATE TABLE artist_discogs_links (
        user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        library_key TEXT NOT NULL,
        artist_id TEXT NOT NULL,
        discogs_artist_id TEXT NOT NULL,
        selected_at INTEGER NOT NULL,
        PRIMARY KEY (user_id, library_key, artist_id)
    )
table | artist_indexes | CREATE TABLE artist_indexes (
        folders TEXT PRIMARY KEY,                        -- dossiers de musique visibles (« 1,2 »)
        artists TEXT NOT NULL,                           -- JSON
        since INTEGER NOT NULL,                          -- date Subsonic (ms) pour getIndexes ifModifiedSince
        built_at INTEGER NOT NULL
    )
table | artist_resolutions | CREATE TABLE artist_resolutions (
        name_key TEXT PRIMARY KEY,
        artist_id TEXT,
        resolved_at INTEGER NOT NULL
    )
table | chat_messages | CREATE TABLE chat_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        topic TEXT NOT NULL,                             -- « general » ou « album:<id> »
        user_id INTEGER NOT NULL REFERENCES users (id),
        body TEXT NOT NULL,
        reply_to_id INTEGER REFERENCES chat_messages (id),
        attachment TEXT NOT NULL DEFAULT '',             -- JSON : album ou titre partagé
        created_at INTEGER NOT NULL,
        edited_at INTEGER,
        deleted_at INTEGER,
        deleted_by INTEGER REFERENCES users (id)
    )
table | community_playlists | CREATE TABLE community_playlists (
        playlist_id TEXT PRIMARY KEY,                    -- identifiant Subsonic
        owner_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        created_at INTEGER NOT NULL
    )
table | ext_favorites | CREATE TABLE ext_favorites (
        user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        source TEXT NOT NULL,                            -- youtube, soundcloud, jamendo
        item_id TEXT NOT NULL,                           -- identifiant chez la source (vidéo, titre)
        title TEXT NOT NULL DEFAULT '',
        artist TEXT NOT NULL DEFAULT '',
        image_url TEXT NOT NULL DEFAULT '',
        duration INTEGER NOT NULL DEFAULT 0,
        play_url TEXT NOT NULL DEFAULT '',               -- son Jamendo, ou titre SoundCloud pour son lecteur officiel
        page_url TEXT NOT NULL DEFAULT '',               -- page du titre chez la source (« Ouvrir sur SoundCloud »)
        added_at INTEGER NOT NULL,
        PRIMARY KEY (user_id, source, item_id)
    )
table | ext_searches | CREATE TABLE ext_searches (
        search_key TEXT PRIMARY KEY,                     -- « youtube:daft punk »
        results TEXT NOT NULL,                           -- JSON
        searched_at INTEGER NOT NULL
    )
table | listen_later | CREATE TABLE "listen_later" (
        id INTEGER PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        target_id INTEGER NOT NULL REFERENCES listening_targets (id),
        created_at INTEGER NOT NULL,
        UNIQUE (user_id, target_id)
    )
table | listening_history | CREATE TABLE listening_history (
        id INTEGER PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        target_id INTEGER NOT NULL REFERENCES listening_targets (id),
        request_id TEXT NOT NULL,
        played_at INTEGER NOT NULL,
        UNIQUE (user_id, request_id)
    )
table | listening_targets | CREATE TABLE listening_targets (
        id INTEGER PRIMARY KEY,
        kind TEXT NOT NULL CHECK (kind IN ('artist', 'album', 'song')),
        source TEXT NOT NULL CHECK (source IN ('subsonic', 'discogs')),
        library_key TEXT NOT NULL DEFAULT '',
        source_id TEXT NOT NULL,
        title TEXT NOT NULL,
        artist TEXT NOT NULL DEFAULT '',
        image_ref TEXT NOT NULL DEFAULT '',
        CHECK (kind != 'song' OR source = 'subsonic'),
        CHECK ((source = 'subsonic' AND library_key != '') OR (source = 'discogs' AND library_key = '')),
        UNIQUE (kind, source, library_key, source_id)
    )
table | message_mentions | CREATE TABLE message_mentions (
        message_id INTEGER NOT NULL REFERENCES chat_messages (id) ON DELETE CASCADE,
        user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        PRIMARY KEY (message_id, user_id)
    )
table | message_reactions | CREATE TABLE message_reactions (
        message_id INTEGER NOT NULL REFERENCES chat_messages (id) ON DELETE CASCADE,
        user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        emoji TEXT NOT NULL,
        created_at INTEGER NOT NULL,
        PRIMARY KEY (message_id, user_id, emoji)
    )
table | music_metadata | CREATE TABLE music_metadata (
        cache_key TEXT PRIMARY KEY,
        payload TEXT NOT NULL,
        fetched_at INTEGER NOT NULL
    )
table | news_articles | CREATE TABLE news_articles (
        id INTEGER PRIMARY KEY,
        feed_id INTEGER NOT NULL REFERENCES news_feeds (id) ON DELETE CASCADE,
        link TEXT NOT NULL,
        title TEXT NOT NULL,
        summary TEXT NOT NULL DEFAULT '',
        published_at INTEGER NOT NULL,
        words TEXT NOT NULL,
        UNIQUE (feed_id, link)
    )
table | news_feeds | CREATE TABLE news_feeds (
        id INTEGER PRIMARY KEY,
        url TEXT NOT NULL UNIQUE,
        title TEXT NOT NULL DEFAULT '',
        site_url TEXT NOT NULL DEFAULT '',
        added_by INTEGER REFERENCES users (id) ON DELETE SET NULL,
        added_at INTEGER NOT NULL,
        checked_at INTEGER,
        error TEXT NOT NULL DEFAULT ''
    )
table | news_hidden_feeds | CREATE TABLE news_hidden_feeds (
        user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        feed_id INTEGER NOT NULL REFERENCES news_feeds (id) ON DELETE CASCADE,
        PRIMARY KEY (user_id, feed_id)
    )
table | notifications | CREATE TABLE "notifications" (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_id INTEGER REFERENCES users (id) ON DELETE SET NULL,
        recipient_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        title TEXT NOT NULL CHECK (length(trim(title)) > 0),
        body TEXT NOT NULL CHECK (length(trim(body)) > 0),
        client_token TEXT NOT NULL,
        created_at INTEGER NOT NULL,
        read_at INTEGER,
        UNIQUE (sender_id, recipient_id, client_token)
    )
table | playlist_additions | CREATE TABLE playlist_additions (
        playlist_id TEXT NOT NULL,
        song_id TEXT NOT NULL,
        added_by INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        added_at INTEGER NOT NULL,
        PRIMARY KEY (playlist_id, song_id)
    )
table | playlist_ext_tracks | CREATE TABLE playlist_ext_tracks (
        id INTEGER PRIMARY KEY,
        playlist_id TEXT NOT NULL,                       -- playlist Subsonic
        after_songs INTEGER NOT NULL,
        source TEXT NOT NULL,
        item_id TEXT NOT NULL,
        title TEXT NOT NULL DEFAULT '',
        artist TEXT NOT NULL DEFAULT '',
        image_url TEXT NOT NULL DEFAULT '',
        duration INTEGER NOT NULL DEFAULT 0,
        play_url TEXT NOT NULL DEFAULT '',
        page_url TEXT NOT NULL DEFAULT '',
        added_by INTEGER REFERENCES users (id) ON DELETE SET NULL,
        added_at INTEGER NOT NULL, place INTEGER NOT NULL DEFAULT 0,
        UNIQUE (playlist_id, source, item_id)
    )
table | radar_profiles | CREATE TABLE radar_profiles (
        user_id INTEGER PRIMARY KEY REFERENCES users (id) ON DELETE CASCADE,
        tags TEXT NOT NULL DEFAULT '{}',
        computed_at INTEGER,
        refresh_requested_at INTEGER,
        discoveries_off INTEGER NOT NULL DEFAULT 0
    , basis TEXT)
table | radar_release_artists | CREATE TABLE radar_release_artists (
        release_id TEXT NOT NULL REFERENCES radar_releases (id) ON DELETE CASCADE,
        artist_id TEXT NOT NULL,
        PRIMARY KEY (release_id, artist_id)
    )
table | radar_release_sources | CREATE TABLE radar_release_sources (
        release_id TEXT NOT NULL REFERENCES radar_releases (id) ON DELETE CASCADE,
        source_kind TEXT NOT NULL,
        source_identity TEXT NOT NULL,
        PRIMARY KEY (release_id, source_kind, source_identity)
    )
table | radar_releases | CREATE TABLE radar_releases (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        artist TEXT NOT NULL,
        released_on TEXT NOT NULL,
        kind TEXT NOT NULL,
        tags TEXT NOT NULL DEFAULT '[]'
    , cover TEXT NOT NULL DEFAULT '', cover_checked_at INTEGER)
table | radar_runs | CREATE TABLE radar_runs (
        name TEXT PRIMARY KEY,
        finished_at INTEGER NOT NULL
    )
table | radar_sync | CREATE TABLE radar_sync (
        source_kind TEXT NOT NULL,
        source_identity TEXT NOT NULL,
        synced_at INTEGER,
        failed_at INTEGER, past_synced_at INTEGER,
        PRIMARY KEY (source_kind, source_identity)
    )
table | recommendation_comments | CREATE TABLE "recommendation_comments" (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        recommendation_id INTEGER NOT NULL REFERENCES recommendations (id) ON DELETE CASCADE,
        author_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        recipient_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        body TEXT NOT NULL CHECK (length(trim(body)) > 0),
        client_token TEXT NOT NULL,
        created_at INTEGER NOT NULL,
        read_at INTEGER,
        CHECK (author_id != recipient_id),
        UNIQUE (recommendation_id, author_id, client_token)
    )
table | recommendations | CREATE TABLE "recommendations" (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        recipient_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        target_id INTEGER NOT NULL REFERENCES listening_targets (id),
        created_at INTEGER NOT NULL,
        read_at INTEGER,
        archived_at INTEGER,
        CHECK (sender_id != recipient_id)
    )
table | release_sources | CREATE TABLE release_sources (
        id INTEGER PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        kind TEXT NOT NULL,
        identity TEXT NOT NULL CHECK (length(identity) > 0),
        name TEXT NOT NULL,
        origin TEXT NOT NULL,
        hidden INTEGER NOT NULL DEFAULT 0,
        via TEXT,
        created_at INTEGER NOT NULL,
        UNIQUE (user_id, kind, identity)
    )
table | sessions | CREATE TABLE sessions (
        token_hash TEXT PRIMARY KEY,                     -- sha256 du cookie : une fuite de la base n’ouvre aucune session
        user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        created_at INTEGER NOT NULL,
        expires_at INTEGER NOT NULL
    )
table | topic_reads | CREATE TABLE topic_reads (
        user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        topic TEXT NOT NULL,
        last_read_id INTEGER NOT NULL,
        PRIMARY KEY (user_id, topic)
    )
table | upload_albums | CREATE TABLE upload_albums (
        library_key TEXT NOT NULL,
        album_path TEXT NOT NULL,
        upload_id INTEGER NOT NULL REFERENCES upload_history (id),
        PRIMARY KEY (library_key, album_path)
    )
table | upload_history | CREATE TABLE upload_history (
        id INTEGER PRIMARY KEY,
        user_id INTEGER REFERENCES users (id) ON DELETE SET NULL,
        username TEXT NOT NULL,
        filename TEXT NOT NULL,
        byte_count INTEGER NOT NULL,
        file_count INTEGER NOT NULL,
        skipped_count INTEGER NOT NULL,
        placed TEXT NOT NULL,
        waiting TEXT NOT NULL,
        uploaded_at INTEGER NOT NULL
    )
table | user_avatars | CREATE TABLE user_avatars (
        user_id INTEGER PRIMARY KEY REFERENCES users (id) ON DELETE CASCADE,
        mime TEXT NOT NULL,
        data BLOB NOT NULL,
        updated_at INTEGER NOT NULL
    )
table | user_preferences | CREATE TABLE user_preferences (
        user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        key TEXT NOT NULL,
        value TEXT NOT NULL,                             -- JSON
        PRIMARY KEY (user_id, key)
    )
table | users | CREATE TABLE users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE COLLATE NOCASE,   -- identifiant Subsonic
        subsonic_salt TEXT NOT NULL,                     -- jeton Subsonic = md5(mot de passe + sel), jamais le mot de passe
        subsonic_token TEXT NOT NULL,
        is_admin INTEGER NOT NULL DEFAULT 0,             -- rôle administrateur côté Subsonic
        created_at INTEGER NOT NULL,
        last_seen_at INTEGER NOT NULL
    , roles TEXT NOT NULL DEFAULT '')
table | youtube_videos | CREATE TABLE youtube_videos (
        video_id TEXT PRIMARY KEY,
        plays INTEGER NOT NULL DEFAULT 0,                -- lectures réussies sur le site
        last_played_at INTEGER,
        refused_at INTEGER,                              -- refusée par le lecteur intégré (vide si lue depuis)
        error_code TEXT NOT NULL DEFAULT ''              -- code renvoyé par YouTube (101, 150…)
    , title TEXT NOT NULL DEFAULT '', artist TEXT NOT NULL DEFAULT '', image_url TEXT NOT NULL DEFAULT '', duration INTEGER NOT NULL DEFAULT 0, words TEXT NOT NULL DEFAULT '', checked_at INTEGER)
