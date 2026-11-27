"""Schéma de la base de l'édition PC (webapp.db). Une migration = un script SQL, appliqué une seule fois.
Ne jamais modifier une migration publiée : en ajouter une à la fin."""

MIGRATIONS = [
    # 1 : comptes, sessions, réglages, notes d'albums, salon et commentaires
    """
    CREATE TABLE users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE COLLATE NOCASE,   -- identifiant Subsonic
        subsonic_salt TEXT NOT NULL,                     -- jeton Subsonic = md5(mot de passe + sel), jamais le mot de passe
        subsonic_token TEXT NOT NULL,
        is_admin INTEGER NOT NULL DEFAULT 0,             -- rôle administrateur côté Subsonic
        created_at INTEGER NOT NULL,
        last_seen_at INTEGER NOT NULL
    );
    CREATE TABLE sessions (
        token_hash TEXT PRIMARY KEY,                     -- sha256 du cookie : une fuite de la base n’ouvre aucune session
        user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        created_at INTEGER NOT NULL,
        expires_at INTEGER NOT NULL
    );
    CREATE INDEX sessions_user ON sessions (user_id);
    CREATE TABLE user_preferences (
        user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        key TEXT NOT NULL,
        value TEXT NOT NULL,                             -- JSON
        PRIMARY KEY (user_id, key)
    );
    CREATE TABLE album_ratings (
        user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        album_id TEXT NOT NULL,
        rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
        rated_at INTEGER NOT NULL,
        PRIMARY KEY (user_id, album_id)
    );
    CREATE INDEX album_ratings_album ON album_ratings (album_id);
    CREATE TABLE albums_discussed (
        album_id TEXT PRIMARY KEY,                       -- pour la liste « albums commentés récemment »
        title TEXT NOT NULL DEFAULT '',
        artist TEXT NOT NULL DEFAULT '',
        cover_id TEXT NOT NULL DEFAULT '',
        last_message_at INTEGER NOT NULL
    );
    CREATE TABLE chat_messages (
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
    );
    CREATE INDEX chat_messages_topic ON chat_messages (topic, id);
    CREATE TABLE message_reactions (
        message_id INTEGER NOT NULL REFERENCES chat_messages (id) ON DELETE CASCADE,
        user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        emoji TEXT NOT NULL,
        created_at INTEGER NOT NULL,
        PRIMARY KEY (message_id, user_id, emoji)
    );
    CREATE TABLE message_mentions (
        message_id INTEGER NOT NULL REFERENCES chat_messages (id) ON DELETE CASCADE,
        user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        PRIMARY KEY (message_id, user_id)
    );
    CREATE INDEX message_mentions_user ON message_mentions (user_id, message_id);
    CREATE TABLE topic_reads (
        user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        topic TEXT NOT NULL,
        last_read_id INTEGER NOT NULL,
        PRIMARY KEY (user_id, topic)
    )
    """,
    # 2 : photo de profil envoyée sur le site (sinon : avatar Subsonic, sinon initiale)
    """
    CREATE TABLE user_avatars (
        user_id INTEGER PRIMARY KEY REFERENCES users (id) ON DELETE CASCADE,
        mime TEXT NOT NULL,
        data BLOB NOT NULL,
        updated_at INTEGER NOT NULL
    )
    """,
    # 3 : les notes d'albums sont lues et écrites dans Subsonic (moyenne de tous les comptes) : plus de copie ici
    """
    DROP TABLE album_ratings
    """,
    # 4 : musique d'ailleurs gardée entre deux redémarrages (le quota YouTube est rare) :
    # recherches déjà faites, et ce qu'on sait de chaque vidéo (lue ici, ou refusée par le lecteur intégré)
    """
    CREATE TABLE ext_searches (
        search_key TEXT PRIMARY KEY,                     -- « youtube:daft punk »
        results TEXT NOT NULL,                           -- JSON
        searched_at INTEGER NOT NULL
    );
    CREATE TABLE youtube_videos (
        video_id TEXT PRIMARY KEY,
        plays INTEGER NOT NULL DEFAULT 0,                -- lectures réussies sur le site
        last_played_at INTEGER,
        refused_at INTEGER,                              -- refusée par le lecteur intégré (vide si lue depuis)
        error_code TEXT NOT NULL DEFAULT ''              -- code renvoyé par YouTube (101, 150…)
    )
    """,
    # 5 : liste des artistes de la barre, une pour tout le site (Subsonic peut mettre plus de 30 s à la calculer),
    # gardée entre deux redémarrages et recalculée seulement après un scan de Subsonic
    """
    CREATE TABLE artist_indexes (
        folders TEXT PRIMARY KEY,                        -- dossiers de musique visibles (« 1,2 »)
        artists TEXT NOT NULL,                           -- JSON
        since INTEGER NOT NULL,                          -- date Subsonic (ms) pour getIndexes ifModifiedSince
        built_at INTEGER NOT NULL
    )
    """,
    # 6 : droits du compte Subsonic (getUser), relus à chaque page. Comptes déjà là : tout permis comme avant,
    # corrigé dès leur prochaine page.
    """
    ALTER TABLE users ADD COLUMN roles TEXT NOT NULL DEFAULT '';
    UPDATE users SET roles = 'comment,coverArt,download,playlist,scrobble,settings,share,stream,upload'
        || CASE WHEN is_admin THEN ',admin' ELSE '' END
    """,
    # 7 : playlists communautaires. La playlist reste une playlist Subsonic de son créateur (rendue publique) :
    # quand quelqu'un d'autre y ajoute un titre, le site écrit avec le jeton du créateur et garde ici qui l'a ajouté
    """
    CREATE TABLE community_playlists (
        playlist_id TEXT PRIMARY KEY,                    -- identifiant Subsonic
        owner_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        created_at INTEGER NOT NULL
    );
    CREATE TABLE playlist_additions (
        playlist_id TEXT NOT NULL,
        song_id TEXT NOT NULL,
        added_by INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        added_at INTEGER NOT NULL,
        PRIMARY KEY (playlist_id, song_id)
    )
    """,
    # 8 : la barre des artistes suit les dossiers (getIndexes) et non plus les tags (getArtists) : les listes gardées,
    # calculées depuis les tags, sont recalculées
    """
    DELETE FROM artist_indexes
    """,
    # 9 : recherches YouTube gardées sans limite, mais seulement la liste des vidéos : titre, chaîne, durée sont ici,
    # relus tous les 30 jours (règles de YouTube) ; sert aussi à retrouver une vidéo déjà trouvée sans quota.
    # words : titre et chaîne sans accents ; checked_at vide : rien de connu sur elle. (Pas de commentaire dans les
    # ALTER TABLE : SQLite le recopierait dans la définition de la table.)
    """
    ALTER TABLE youtube_videos ADD COLUMN title TEXT NOT NULL DEFAULT '';
    ALTER TABLE youtube_videos ADD COLUMN artist TEXT NOT NULL DEFAULT '';
    ALTER TABLE youtube_videos ADD COLUMN image_url TEXT NOT NULL DEFAULT '';
    ALTER TABLE youtube_videos ADD COLUMN duration INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE youtube_videos ADD COLUMN words TEXT NOT NULL DEFAULT '';
    ALTER TABLE youtube_videos ADD COLUMN checked_at INTEGER
    """,
    # 10 : Actualité. Flux de webzines ajoutés par n'importe qui, lus toutes les heures ; chaque article est gardé
    # (titre, lien, date, début du résumé) pour retrouver plus tard ceux qui parlent d'un artiste.
    # news_hidden_feeds : flux que quelqu'un ne veut pas voir (par défaut chacun voit tous les flux).
    # words : titre sans accents ni ponctuation, entouré d'espaces (recherche du nom d'un artiste en mots entiers)
    """
    CREATE TABLE news_feeds (
        id INTEGER PRIMARY KEY,
        url TEXT NOT NULL UNIQUE,
        title TEXT NOT NULL DEFAULT '',
        site_url TEXT NOT NULL DEFAULT '',
        added_by INTEGER REFERENCES users (id) ON DELETE SET NULL,
        added_at INTEGER NOT NULL,
        checked_at INTEGER,
        error TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE news_articles (
        id INTEGER PRIMARY KEY,
        feed_id INTEGER NOT NULL REFERENCES news_feeds (id) ON DELETE CASCADE,
        link TEXT NOT NULL,
        title TEXT NOT NULL,
        summary TEXT NOT NULL DEFAULT '',
        published_at INTEGER NOT NULL,
        words TEXT NOT NULL,
        UNIQUE (feed_id, link)
    );
    CREATE INDEX news_articles_by_date ON news_articles (published_at DESC, id DESC);
    CREATE TABLE news_hidden_feeds (
        user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        feed_id INTEGER NOT NULL REFERENCES news_feeds (id) ON DELETE CASCADE,
        PRIMARY KEY (user_id, feed_id)
    );
    INSERT INTO news_feeds (url, title, site_url, added_at) VALUES
        ('https://www.lesinrocks.com/feed/', 'Les Inrocks', 'https://www.lesinrocks.com', 0),
        ('https://mowno.com/feed/', 'Mowno', 'https://mowno.com', 0),
        ('https://noisemag.net/feed/', 'New Noise', 'https://noisemag.net', 0)
    """,
    # 11 : Les Inrocks de départ = la rubrique Musique seulement (le flux du site entier parle aussi de séries, de livres…) ;
    # ses articles déjà gardés sont oubliés, le flux Musique est relu à la lecture suivante
    """
    DELETE FROM news_articles WHERE feed_id IN (SELECT id FROM news_feeds WHERE url = 'https://www.lesinrocks.com/feed/');
    UPDATE news_feeds SET url = 'https://www.lesinrocks.com/musique/feed/', title = 'Les Inrocks – Musique',
        site_url = 'https://www.lesinrocks.com/musique/', checked_at = NULL, error = ''
        WHERE url = 'https://www.lesinrocks.com/feed/'
        AND NOT EXISTS (SELECT 1 FROM news_feeds WHERE url = 'https://www.lesinrocks.com/musique/feed/')
    """,
    # 12 : favoris d'ailleurs, propres à chaque personne (Subsonic ne peut pas les garder) : vidéos YouTube, titres
    # SoundCloud (ajoutés par un lien) et Jamendo. YouTube : seulement l'identifiant, titre et chaîne sont lus dans
    # youtube_videos (relus tous les 30 jours, règle de YouTube) ; une vidéo oubliée là disparaît des favoris.
    # SoundCloud et Jamendo : ce qu'il faut pour les montrer et les lire.
    """
    CREATE TABLE ext_favorites (
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
    );
    CREATE INDEX ext_favorites_by_date ON ext_favorites (user_id, added_at DESC)
    """,
    # 13 : titres d'ailleurs dans les playlists Subsonic. Subsonic ne garde que ses propres titres (c'est tout ce que
    # voient les applications Subsonic) ; le site garde les autres ici et les montre à leur place. after_songs : nombre
    # de titres Subsonic avant celui-ci au moment de l'ajout. Mêmes colonnes et même règle YouTube que ext_favorites.
    """
    CREATE TABLE playlist_ext_tracks (
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
        added_at INTEGER NOT NULL,
        UNIQUE (playlist_id, source, item_id)
    );
    CREATE INDEX playlist_ext_tracks_by_place ON playlist_ext_tracks (playlist_id, after_songs, id)
    """,
    # 14 : titres d'ailleurs remis dans un autre ordre par le créateur de la playlist. place : leur rang parmi les titres
    # d'ailleurs d'une même playlist (à after_songs égal, le plus petit d'abord) ; 0 pour ceux d'avant, rangés par id.
    """
    ALTER TABLE playlist_ext_tracks ADD COLUMN place INTEGER NOT NULL DEFAULT 0;
    DROP INDEX playlist_ext_tracks_by_place;
    CREATE INDEX playlist_ext_tracks_by_place ON playlist_ext_tracks (playlist_id, after_songs, place, id)
    """,
    # 15 : métadonnées publiques MusicBrainz (éditions, labels, crédits), jamais de résultats Subsonic partagés.
    """
    CREATE TABLE music_metadata (
        cache_key TEXT PRIMARY KEY,
        payload TEXT NOT NULL,
        fetched_at INTEGER NOT NULL
    )
    """,
    # 16 : choix Discogs durables, indépendants du cache public et des homonymes.
    """
    CREATE TABLE artist_discogs_links (
        user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        library_key TEXT NOT NULL,
        artist_id TEXT NOT NULL,
        discogs_artist_id TEXT NOT NULL,
        selected_at INTEGER NOT NULL,
        PRIMARY KEY (user_id, library_key, artist_id)
    )
    """,

    # 17: personal artist/album bookmarks and independently addressed recommendations.
    """
    CREATE TABLE listen_later (
        id INTEGER PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        kind TEXT NOT NULL CHECK (kind IN ('artist', 'album')),
        source TEXT NOT NULL CHECK (source IN ('subsonic', 'discogs')),
        library_key TEXT NOT NULL DEFAULT '',
        source_id TEXT NOT NULL,
        title TEXT NOT NULL,
        artist TEXT NOT NULL DEFAULT '',
        image_ref TEXT NOT NULL DEFAULT '',
        created_at INTEGER NOT NULL,
        CHECK ((source = 'subsonic' AND library_key != '') OR (source = 'discogs' AND library_key = '')),
        UNIQUE (user_id, kind, source, library_key, source_id)
    );
    CREATE INDEX listen_later_by_date ON listen_later (user_id, created_at DESC, id DESC);
    CREATE TABLE recommendations (
        id INTEGER PRIMARY KEY,
        sender_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        recipient_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        kind TEXT NOT NULL CHECK (kind IN ('artist', 'album')),
        source TEXT NOT NULL CHECK (source IN ('subsonic', 'discogs')),
        library_key TEXT NOT NULL DEFAULT '',
        source_id TEXT NOT NULL,
        title TEXT NOT NULL,
        artist TEXT NOT NULL DEFAULT '',
        image_ref TEXT NOT NULL DEFAULT '',
        created_at INTEGER NOT NULL,
        CHECK (sender_id != recipient_id),
        CHECK ((source = 'subsonic' AND library_key != '') OR (source = 'discogs' AND library_key = '')),
        UNIQUE (sender_id, recipient_id, kind, source, library_key, source_id)
    );
    CREATE INDEX recommendations_by_recipient ON recommendations (recipient_id, created_at DESC, id DESC)
    """,

    # 18: unread recommendations, acknowledged by their unique delivery token.
    """
    ALTER TABLE recommendations ADD COLUMN unread_token TEXT;
    UPDATE recommendations SET unread_token = lower(hex(randomblob(16)));
    CREATE INDEX recommendations_unread_by_recipient
        ON recommendations (recipient_id, library_key) WHERE unread_token IS NOT NULL
    """,
    # 19 : historique des envois réussis, attribués au compte authentifié.
    """
    CREATE TABLE upload_history (
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
    );
    CREATE INDEX upload_history_by_user ON upload_history (user_id, id DESC);
    CREATE TABLE upload_albums (
        library_key TEXT NOT NULL,
        album_path TEXT NOT NULL,
        upload_id INTEGER NOT NULL REFERENCES upload_history (id),
        PRIMARY KEY (library_key, album_path)
    )
    """,
    # 20: individual library songs in bookmarks and recommendations, preserving unread deliveries.
    """
    CREATE TABLE listen_later_songs (
        id INTEGER PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        kind TEXT NOT NULL CHECK (kind IN ('artist', 'album', 'song')),
        source TEXT NOT NULL CHECK (source IN ('subsonic', 'discogs')),
        library_key TEXT NOT NULL DEFAULT '',
        source_id TEXT NOT NULL,
        title TEXT NOT NULL,
        artist TEXT NOT NULL DEFAULT '',
        image_ref TEXT NOT NULL DEFAULT '',
        created_at INTEGER NOT NULL,
        CHECK (kind != 'song' OR source = 'subsonic'),
        CHECK ((source = 'subsonic' AND library_key != '') OR (source = 'discogs' AND library_key = '')),
        UNIQUE (user_id, kind, source, library_key, source_id)
    );
    INSERT INTO listen_later_songs SELECT * FROM listen_later;
    DROP TABLE listen_later;
    ALTER TABLE listen_later_songs RENAME TO listen_later;
    CREATE INDEX listen_later_by_date ON listen_later (user_id, created_at DESC, id DESC);
    CREATE TABLE recommendations_songs (
        id INTEGER PRIMARY KEY,
        sender_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        recipient_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        kind TEXT NOT NULL CHECK (kind IN ('artist', 'album', 'song')),
        source TEXT NOT NULL CHECK (source IN ('subsonic', 'discogs')),
        library_key TEXT NOT NULL DEFAULT '',
        source_id TEXT NOT NULL,
        title TEXT NOT NULL,
        artist TEXT NOT NULL DEFAULT '',
        image_ref TEXT NOT NULL DEFAULT '',
        created_at INTEGER NOT NULL,
        unread_token TEXT,
        CHECK (sender_id != recipient_id),
        CHECK (kind != 'song' OR source = 'subsonic'),
        CHECK ((source = 'subsonic' AND library_key != '') OR (source = 'discogs' AND library_key = '')),
        UNIQUE (sender_id, recipient_id, kind, source, library_key, source_id)
    );
    INSERT INTO recommendations_songs SELECT * FROM recommendations;
    DROP TABLE recommendations;
    ALTER TABLE recommendations_songs RENAME TO recommendations;
    CREATE INDEX recommendations_by_recipient ON recommendations (recipient_id, created_at DESC, id DESC);
    CREATE INDEX recommendations_unread_by_recipient
        ON recommendations (recipient_id, library_key) WHERE unread_token IS NOT NULL
    """,
    # 21: private recommendation comments, durable threads and participant read cursors.
    """
    CREATE TABLE recommendations_discussions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        recipient_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        kind TEXT NOT NULL CHECK (kind IN ('artist', 'album', 'song')),
        source TEXT NOT NULL CHECK (source IN ('subsonic', 'discogs')),
        library_key TEXT NOT NULL DEFAULT '',
        source_id TEXT NOT NULL,
        title TEXT NOT NULL,
        artist TEXT NOT NULL DEFAULT '',
        image_ref TEXT NOT NULL DEFAULT '',
        created_at INTEGER NOT NULL,
        unread_token TEXT,
        recipient_archived_at INTEGER,
        sender_last_read_comment_id INTEGER NOT NULL DEFAULT 0 CHECK (sender_last_read_comment_id >= 0),
        recipient_last_read_comment_id INTEGER NOT NULL DEFAULT 0 CHECK (recipient_last_read_comment_id >= 0),
        CHECK (sender_id != recipient_id),
        CHECK (kind != 'song' OR source = 'subsonic'),
        CHECK ((source = 'subsonic' AND library_key != '') OR (source = 'discogs' AND library_key = ''))
    );
    INSERT INTO recommendations_discussions
        (id, sender_id, recipient_id, kind, source, library_key, source_id, title, artist, image_ref, created_at, unread_token)
        SELECT id, sender_id, recipient_id, kind, source, library_key, source_id, title, artist, image_ref, created_at, unread_token
        FROM recommendations;
    DROP TABLE recommendations;
    ALTER TABLE recommendations_discussions RENAME TO recommendations;
    CREATE UNIQUE INDEX recommendations_active_target
        ON recommendations (sender_id, recipient_id, kind, source, library_key, source_id)
        WHERE recipient_archived_at IS NULL;
    CREATE INDEX recommendations_by_recipient ON recommendations (recipient_id, created_at DESC, id DESC);
    CREATE INDEX recommendations_by_sender ON recommendations (sender_id, id DESC);
    CREATE INDEX recommendations_unread_by_recipient
        ON recommendations (recipient_id, library_key) WHERE unread_token IS NOT NULL;
    CREATE TABLE recommendation_comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        recommendation_id INTEGER NOT NULL REFERENCES recommendations (id) ON DELETE CASCADE,
        author_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        body TEXT NOT NULL CHECK (length(trim(body)) > 0),
        created_at INTEGER NOT NULL,
        client_token TEXT NOT NULL,
        UNIQUE (recommendation_id, author_id, client_token)
    );
    CREATE INDEX recommendation_comments_by_thread ON recommendation_comments (recommendation_id, id)
    """,
    # 22: private administrative notifications and per-recipient read state.
    """
    CREATE TABLE notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_id INTEGER REFERENCES users (id) ON DELETE SET NULL,
        recipient_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        title TEXT NOT NULL CHECK (length(trim(title)) BETWEEN 1 AND 120),
        body TEXT NOT NULL CHECK (length(trim(body)) BETWEEN 1 AND 2000),
        client_token TEXT NOT NULL,
        created_at INTEGER NOT NULL,
        read_at INTEGER,
        UNIQUE (sender_id, recipient_id, client_token)
    );
    CREATE INDEX notifications_by_recipient ON notifications (recipient_id, id DESC);
    CREATE INDEX notifications_unread_by_recipient ON notifications (recipient_id) WHERE read_at IS NULL
    """,
    # 23: personally followed MusicBrainz genres.
    """
    CREATE TABLE release_subscriptions (
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        genre_id TEXT NOT NULL,
        name TEXT NOT NULL,
        PRIMARY KEY (user_id, genre_id)
    )
    """,
    # 24 : une cible écoutée décrite une seule fois ; une date de lecture par destinataire pour chaque message.
    """
    CREATE TABLE listening_targets (
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
    );
    INSERT INTO listening_targets (kind, source, library_key, source_id, title, artist, image_ref)
        SELECT kind, source, library_key, source_id, title, artist, image_ref FROM (
            SELECT kind, source, library_key, source_id, title, artist, image_ref, created_at, 0 AS origin, id
            FROM listen_later
            UNION ALL
            SELECT kind, source, library_key, source_id, title, artist, image_ref, created_at, 1 AS origin, id
            FROM recommendations
        ) WHERE true ORDER BY created_at, origin, id
        ON CONFLICT (kind, source, library_key, source_id) DO UPDATE
        SET title = excluded.title, artist = excluded.artist, image_ref = excluded.image_ref;
    CREATE TABLE listen_later_targets (
        id INTEGER PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        target_id INTEGER NOT NULL REFERENCES listening_targets (id),
        created_at INTEGER NOT NULL,
        UNIQUE (user_id, target_id)
    );
    INSERT INTO listen_later_targets (id, user_id, target_id, created_at)
        SELECT l.id, l.user_id, t.id, l.created_at FROM listen_later l
        JOIN listening_targets t USING (kind, source, library_key, source_id);
    DROP TABLE listen_later;
    ALTER TABLE listen_later_targets RENAME TO listen_later;
    CREATE INDEX listen_later_by_date ON listen_later (user_id, created_at DESC, id DESC);
    CREATE TABLE recommendations_targets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        recipient_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        target_id INTEGER NOT NULL REFERENCES listening_targets (id),
        created_at INTEGER NOT NULL,
        read_at INTEGER,
        archived_at INTEGER,
        CHECK (sender_id != recipient_id)
    );
    INSERT INTO recommendations_targets (id, sender_id, recipient_id, target_id, created_at, read_at, archived_at)
        SELECT r.id, r.sender_id, r.recipient_id, t.id, r.created_at,
               CASE WHEN r.unread_token IS NULL THEN r.created_at END, r.recipient_archived_at
        FROM recommendations r JOIN listening_targets t USING (kind, source, library_key, source_id);
    CREATE TABLE recommendation_comments_read (
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
    );
    INSERT INTO recommendation_comments_read
        (id, recommendation_id, author_id, recipient_id, body, client_token, created_at, read_at)
        SELECT c.id, c.recommendation_id, c.author_id,
               CASE WHEN c.author_id = r.sender_id THEN r.recipient_id ELSE r.sender_id END,
               c.body, c.client_token, c.created_at,
               CASE WHEN c.id <= CASE WHEN c.author_id = r.sender_id THEN r.recipient_last_read_comment_id
                                      ELSE r.sender_last_read_comment_id END THEN c.created_at END
        FROM recommendation_comments c JOIN recommendations r ON r.id = c.recommendation_id;
    DROP TABLE recommendation_comments;
    DROP TABLE recommendations;
    ALTER TABLE recommendations_targets RENAME TO recommendations;
    ALTER TABLE recommendation_comments_read RENAME TO recommendation_comments;
    CREATE UNIQUE INDEX recommendations_active_target
        ON recommendations (sender_id, recipient_id, target_id) WHERE archived_at IS NULL;
    CREATE INDEX recommendations_by_recipient ON recommendations (recipient_id, created_at DESC, id DESC);
    CREATE INDEX recommendations_by_sender ON recommendations (sender_id, id DESC);
    CREATE INDEX recommendations_unread_by_recipient ON recommendations (recipient_id) WHERE read_at IS NULL;
    CREATE INDEX recommendation_comments_by_thread ON recommendation_comments (recommendation_id, id);
    CREATE INDEX recommendation_comments_unread ON recommendation_comments (recipient_id) WHERE read_at IS NULL
    """,
    # 25 : les longueurs maximales des notifications vivent dans le code (notification_entities), pas dans le schéma.
    """
    CREATE TABLE notifications_text (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_id INTEGER REFERENCES users (id) ON DELETE SET NULL,
        recipient_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        title TEXT NOT NULL CHECK (length(trim(title)) > 0),
        body TEXT NOT NULL CHECK (length(trim(body)) > 0),
        client_token TEXT NOT NULL,
        created_at INTEGER NOT NULL,
        read_at INTEGER,
        UNIQUE (sender_id, recipient_id, client_token)
    );
    INSERT INTO notifications_text SELECT id, sender_id, recipient_id, title, body, client_token, created_at, read_at
        FROM notifications;
    DROP TABLE notifications;
    ALTER TABLE notifications_text RENAME TO notifications;
    CREATE INDEX notifications_by_recipient ON notifications (recipient_id, id DESC);
    CREATE INDEX notifications_unread_by_recipient ON notifications (recipient_id) WHERE read_at IS NULL
    """,
    # 26 : un style suivi est identifié par son nom exact dans le catalogue MusicBrainz, celui envoyé dans les recherches.
    """
    CREATE TABLE release_subscriptions_by_name (
        user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        genre TEXT NOT NULL CHECK (length(genre) > 0),
        PRIMARY KEY (user_id, genre)
    );
    INSERT OR IGNORE INTO release_subscriptions_by_name (user_id, genre) SELECT user_id, name FROM release_subscriptions;
    DROP TABLE release_subscriptions;
    ALTER TABLE release_subscriptions_by_name RENAME TO release_subscriptions
    """,
    # 27 : le cache MusicBrainz passe sous le préfixe « musicbrainz: » ; les anciennes clés (adresses complètes) partent.
    """
    DELETE FROM music_metadata WHERE cache_key LIKE 'https://musicbrainz.org/%'
    """,
    # 28 : une seule classe Last.fm ; son cache passe sous le préfixe « lastfm: ».
    """
    UPDATE music_metadata SET cache_key = 'lastfm:' || substr(cache_key, 14) WHERE cache_key LIKE 'label-lastfm:%'
    """,
    # 29 : radar des sorties. Les styles suivis deviennent des sources parmi d'autres (labels, artistes, proches) ;
    # les sorties trouvées par la synchronisation de fond sont partagées entre les comptes.
    """
    CREATE TABLE release_sources (
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
    );
    INSERT INTO release_sources (user_id, kind, identity, name, origin, created_at)
        SELECT user_id, 'style', genre, genre, 'manual', 0 FROM release_subscriptions;
    DROP TABLE release_subscriptions;
    CREATE INDEX release_sources_identity ON release_sources (kind, identity);
    CREATE TABLE radar_releases (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        artist TEXT NOT NULL,
        released_on TEXT NOT NULL,
        kind TEXT NOT NULL,
        tags TEXT NOT NULL DEFAULT '[]'
    );
    CREATE INDEX radar_releases_date ON radar_releases (released_on);
    CREATE TABLE radar_release_sources (
        release_id TEXT NOT NULL REFERENCES radar_releases (id) ON DELETE CASCADE,
        source_kind TEXT NOT NULL,
        source_identity TEXT NOT NULL,
        PRIMARY KEY (release_id, source_kind, source_identity)
    );
    CREATE INDEX radar_release_sources_source ON radar_release_sources (source_kind, source_identity);
    CREATE TABLE radar_sync (
        source_kind TEXT NOT NULL,
        source_identity TEXT NOT NULL,
        synced_at INTEGER,
        failed_at INTEGER,
        PRIMARY KEY (source_kind, source_identity)
    );
    CREATE TABLE radar_runs (
        name TEXT PRIMARY KEY,
        finished_at INTEGER NOT NULL
    );
    CREATE TABLE album_labels (
        album_id TEXT PRIMARY KEY,
        label_id TEXT,
        label_name TEXT,
        release_id TEXT,
        looked_up_at INTEGER NOT NULL
    );
    CREATE TABLE radar_profiles (
        user_id INTEGER PRIMARY KEY REFERENCES users (id) ON DELETE CASCADE,
        tags TEXT NOT NULL DEFAULT '{}',
        computed_at INTEGER,
        refresh_requested_at INTEGER,
        discoveries_off INTEGER NOT NULL DEFAULT 0
    )
    """,
    # 30 : radar, version 2. Les découvertes deviennent « Autour de… » (calculé à la demande) : plus de sources
    # « proches ». Chaque sortie garde ses artistes crédités ; un nom d'artiste résolu dans MusicBrainz est mémorisé ;
    # le profil dit d'où viennent les styles proposés (favoris du compte ou, sans favori, le sub).
    """
    DELETE FROM radar_release_sources WHERE source_kind = 'similar';
    DELETE FROM radar_sync WHERE source_kind = 'similar';
    DELETE FROM release_sources WHERE kind = 'similar';
    CREATE TABLE radar_release_artists (
        release_id TEXT NOT NULL REFERENCES radar_releases (id) ON DELETE CASCADE,
        artist_id TEXT NOT NULL,
        PRIMARY KEY (release_id, artist_id)
    );
    CREATE INDEX radar_release_artists_artist ON radar_release_artists (artist_id);
    CREATE TABLE artist_resolutions (
        name_key TEXT PRIMARY KEY,
        artist_id TEXT,
        resolved_at INTEGER NOT NULL
    );
    ALTER TABLE radar_profiles ADD COLUMN basis TEXT
    """,
    # 31 : pochette d'une sortie du radar, connue de ListenBrainz ou trouvée sur Last.fm (une recherche par sortie).
    """
    ALTER TABLE radar_releases ADD COLUMN cover TEXT NOT NULL DEFAULT '';
    ALTER TABLE radar_releases ADD COLUMN cover_checked_at INTEGER
    """,
]
