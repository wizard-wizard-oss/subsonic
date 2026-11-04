"""Import, une seule fois, des anciens fichiers (config.json et données JSON) dans le .env et la base.
Les fichiers importés sont renommés en « .importe » : rien n'est supprimé."""
import json
import os
import time

from ..settings import ENV_TYPES
from ..tracks import clean_track

DONE_KEY = "legacy_import_done"
# anciennes clés françaises du menu tactile -> nouvelles clés anglaises (.env)
# réglages de l'ancienne édition serveur (comptes, envois) : sans objet sur le Pi, ignorés
OBSOLETE_KEYS = {"mode", "admins", "uploaders", "upload_dir", "upload_max_mb", "upload_max_unzipped_mb", "session_days"}
RENAMED_KEYS = {"nom": "device_name", "ville": "weather_city", "latitude": "weather_latitude",
                "longitude": "weather_longitude", "veille_secondes": "screensaver_seconds"}
OLD_FAVORITES_ID = "favoris"


def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def env_text(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return ",".join(str(v) for v in value)
    return str(value)


class LegacyImport:
    def __init__(self, paths, db, env_file, store):
        self.paths = paths
        self.db = db
        self.env_file = env_file
        self.store = store

    def run(self):
        if self.store.get(DONE_KEY):
            return
        self._config()
        self._podcasts()
        self._playlists()
        self._history()
        self._unplayable()
        self.store.set_many({DONE_KEY: True})

    def _archive(self, path):
        try:
            os.replace(path, path + ".importe")
        except OSError:
            pass

    # --- config.json -> .env (installation, secrets) et app_settings (le reste) ---
    def _config(self):
        data = read_json(self.paths.legacy_config)
        if not isinstance(data, dict):
            return
        data = {RENAMED_KEYS.get(k, k): v for k, v in data.items() if k not in OBSOLETE_KEYS}
        present = self.env_file.values()
        env = {k.upper(): env_text(v) for k, v in data.items() if k in ENV_TYPES and k.upper() not in present}
        if env:
            self.env_file.set(**env)
        others = {k: v for k, v in data.items() if k not in ENV_TYPES}
        if others:
            self.store.set_many(others)
        self._archive(self.paths.legacy_config)

    # --- podcasts.json ---
    def _podcasts(self):
        data = read_json(self.paths.legacy_podcasts)
        if not isinstance(data, dict):
            return
        now = int(time.time())
        with self.db.transaction() as conn:
            for feed, sub in (data.get("subs") or {}).items():
                conn.execute("INSERT OR IGNORE INTO podcast_subscriptions (feed_url, title, image_url, author, subscribed_at) "
                             "VALUES (?, ?, ?, ?, ?)", (feed, sub.get("title") or feed, sub.get("image") or "",
                                                       sub.get("author") or "", int(sub.get("added") or now)))
            for feed in data.get("hidden") or []:
                conn.execute("INSERT OR IGNORE INTO hidden_podcasts (feed_url) VALUES (?)", (feed,))
            for episode_id, p in (data.get("progress") or {}).items():
                conn.execute("INSERT OR IGNORE INTO episode_progress (episode_id, feed_url, title, podcast_title, image_url, "
                             "audio_url, position_s, duration_s, played, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                             (episode_id, p.get("feed", ""), p.get("title", ""), p.get("podcast", ""), p.get("image", ""),
                              p.get("audio", ""), float(p.get("pos") or 0), float(p.get("dur") or 0),
                              int(bool(p.get("played"))), int(p.get("t") or now)))
        self._archive(self.paths.legacy_podcasts)

    # --- playlists.json (dont l'ancienne liste réservée « favoris ») ---
    def _playlists(self):
        data = read_json(self.paths.legacy_playlists)
        if not isinstance(data, dict):
            return
        now = int(time.time())
        with self.db.transaction() as conn:
            for order, playlist in enumerate(data.get("lists") or []):
                tracks = [t for t in (self._track(raw) for raw in playlist.get("songs") or []) if t]
                if playlist.get("id") == OLD_FAVORITES_ID:
                    for track in tracks:
                        conn.execute("INSERT OR IGNORE INTO external_favorites (track_id, track, added_at) VALUES (?, ?, ?)",
                                     (track["id"], json.dumps(track, ensure_ascii=False), now))
                    continue
                conn.execute("INSERT OR IGNORE INTO local_playlists (id, name, created_at) VALUES (?, ?, ?)",
                             (playlist["id"], playlist.get("name") or "Playlist", now + order))
                conn.executemany("INSERT OR IGNORE INTO playlist_tracks (playlist_id, position, track_id, track) VALUES (?, ?, ?, ?)",
                                 [(playlist["id"], i, t["id"], json.dumps(t, ensure_ascii=False)) for i, t in enumerate(tracks)])
        self._archive(self.paths.legacy_playlists)

    @staticmethod
    def _track(raw):
        try:
            return clean_track(raw)
        except ValueError:
            return None

    # --- recherches.json : listes de la plus récente à la plus ancienne ---
    def _history(self):
        data = read_json(self.paths.legacy_history)
        if not isinstance(data, dict):
            return
        base = time.time_ns()
        with self.db.transaction() as conn:
            for kind in ("music", "podcasts"):
                for rank, text in enumerate(t for t in data.get(kind) or [] if isinstance(t, str)):
                    conn.execute("INSERT OR IGNORE INTO search_history (kind, query, query_key, searched_at) VALUES (?, ?, ?, ?)",
                                 (kind, text, text.lower(), base - rank))
        self._archive(self.paths.legacy_history)

    def _unplayable(self):
        data = read_json(self.paths.legacy_unplayable)
        if not isinstance(data, dict):
            return
        base = time.time_ns()
        with self.db.transaction() as conn:
            for rank, video_id in enumerate(i for i in data.get("ids") or [] if isinstance(i, str)):
                conn.execute("INSERT OR IGNORE INTO unplayable_videos (video_id, marked_at) VALUES (?, ?)", (video_id, base + rank))
        self._archive(self.paths.legacy_unplayable)
