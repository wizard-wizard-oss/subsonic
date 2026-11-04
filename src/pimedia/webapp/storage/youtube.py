"""Musique d'ailleurs gardée en base : recherches déjà faites, vidéos lues ou refusées."""
import json
import time

from ...server.podcasts.relevance import normalize, words_of


class ExtSearchRepository:
    """Résultats de recherche (Jamendo, YouTube), réutilisés tant qu'ils ne sont pas trop vieux
    (max_age None : sans limite)."""

    def __init__(self, db, max_age, clock=time.time):
        self.db, self.max_age, self.clock = db, max_age, clock

    def get(self, key):
        oldest = 0 if self.max_age is None else int(self.clock() - self.max_age)
        row = self.db.one("SELECT results FROM ext_searches WHERE search_key = ? AND searched_at > ?", (key, oldest))
        return json.loads(row["results"]) if row else None

    def put(self, key, results):
        self.db.execute("INSERT INTO ext_searches (search_key, results, searched_at) VALUES (?, ?, ?) "
                        "ON CONFLICT (search_key) DO UPDATE SET results = excluded.results, "
                        "searched_at = excluded.searched_at", (key, json.dumps(results), int(self.clock())))


class YouTubeVideoRepository:
    """Ce que le site sait de chaque vidéo. Une vidéo refusée est réessayée après `forget_after` secondes
    (son propriétaire peut autoriser l'intégration plus tard) ; une lecture réussie efface le refus.
    Titre, chaîne, image et durée des vidéos trouvées : relus régulièrement (`stale`), oubliés si elles disparaissent."""

    def __init__(self, db, forget_after, clock=time.time):
        self.db, self.forget_after, self.clock = db, forget_after, clock

    def __contains__(self, video_id):
        """Vidéo refusée récemment (sert de liste des vidéos à ne plus proposer)."""
        return self.db.one("SELECT 1 FROM youtube_videos WHERE video_id = ? AND refused_at > ?",
                           (str(video_id), int(self.clock() - self.forget_after))) is not None

    def add(self, video_id, code=""):
        self.db.execute("INSERT INTO youtube_videos (video_id, refused_at, error_code) VALUES (?, ?, ?) "
                        "ON CONFLICT (video_id) DO UPDATE SET refused_at = excluded.refused_at, "
                        "error_code = excluded.error_code", (str(video_id), int(self.clock()), str(code)[:20]))

    def played(self, video_id):
        self.db.execute("INSERT INTO youtube_videos (video_id, plays, last_played_at) VALUES (?, 1, ?) "
                        "ON CONFLICT (video_id) DO UPDATE SET plays = plays + 1, last_played_at = excluded.last_played_at, "
                        "refused_at = NULL, error_code = ''", (str(video_id), int(self.clock())))

    def plays(self, video_ids):
        """{vidéo: nombre de lectures réussies} pour celles qui ont déjà été lues."""
        ids = list(dict.fromkeys(str(v) for v in video_ids))[:200]
        if not ids:
            return {}
        return {r["video_id"]: r["plays"] for r in self.db.query(
            "SELECT video_id, plays FROM youtube_videos WHERE plays > 0 AND video_id IN (%s)" % ",".join("?" * len(ids)), ids)}

    def error_code(self, video_id):
        row = self.db.one("SELECT error_code FROM youtube_videos WHERE video_id = ? AND refused_at IS NOT NULL",
                          (str(video_id),))
        return row["error_code"] if row else None

    # ---------- vidéos trouvées par une recherche ----------
    def remember(self, tracks, checked_at=None):
        """Garde titre, chaîne, image et durée (relus à `checked_at`, maintenant par défaut)."""
        checked = int(self.clock() if checked_at is None else checked_at)
        for t in tracks:
            self.db.execute(
                "INSERT INTO youtube_videos (video_id, title, artist, image_url, duration, words, checked_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (video_id) DO UPDATE SET title = excluded.title, "
                "artist = excluded.artist, image_url = excluded.image_url, duration = excluded.duration, "
                "words = excluded.words, checked_at = excluded.checked_at",
                (str(t["youtubeId"]), t.get("title") or "", t.get("artist") or "", t.get("imageUrl") or "",
                 int(t.get("duration") or 0), normalize((t.get("title") or "") + " " + (t.get("artist") or "")), checked))

    def tracks(self, video_ids):
        """Les vidéos connues, dans l'ordre demandé (celles oubliées entre-temps sont sautées)."""
        ids = list(dict.fromkeys(str(v) for v in video_ids))[:200]
        if not ids:
            return []
        rows = {r["video_id"]: r for r in self.db.query(
            "SELECT * FROM youtube_videos WHERE checked_at IS NOT NULL AND video_id IN (%s)" % ",".join("?" * len(ids)), ids)}
        return [_track(rows[v]) for v in ids if v in rows]

    def find(self, term, limit=20):
        """Vidéos déjà trouvées dont le titre ou la chaîne contient tous les mots (début de mot), les plus lues d'abord."""
        words = words_of(term)[:8]
        if not words:
            return []
        rows = self.db.query(
            "SELECT * FROM youtube_videos WHERE checked_at IS NOT NULL" + " AND words LIKE ?" * len(words) +
            " ORDER BY plays DESC, last_played_at DESC, checked_at DESC LIMIT ?",
            ["% " + w + "%" for w in words] + [int(limit)])          # normalize : seulement a-z, 0-9 et espaces
        return [_track(r) for r in rows]

    def stale(self, older_than, limit=50):
        """Vidéos à relire : rien vérifié depuis `older_than` secondes."""
        return [r["video_id"] for r in self.db.query(
            "SELECT video_id FROM youtube_videos WHERE checked_at IS NOT NULL AND checked_at <= ? "
            "ORDER BY checked_at LIMIT ?", (int(self.clock() - older_than), int(limit)))]

    def forget(self, video_ids):
        """Vidéo disparue ou devenue illisible : tout ce qu'on en savait est effacé."""
        for video_id in video_ids:
            self.db.execute("DELETE FROM youtube_videos WHERE video_id = ?", (str(video_id),))


def _track(row):
    return {"id": "yt-" + row["video_id"], "youtubeId": row["video_id"], "title": row["title"], "artist": row["artist"],
            "album": "", "duration": row["duration"], "imageUrl": row["image_url"], "ext": "youtube"}
