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
]
