"""Vidéos YouTube que le lecteur intégré a refusées : on ne les propose plus."""
import re
import time

MAX_IDS = 5000
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{6,20}$")


class UnplayableVideos:
    def __init__(self, db):
        self.db = db

    def __contains__(self, video_id):
        return self.db.one("SELECT 1 FROM unplayable_videos WHERE video_id = ?", (str(video_id),)) is not None

    def add(self, video_id):
        video_id = str(video_id or "")
        if not VIDEO_ID.match(video_id):
            raise ValueError("identifiant de vidéo invalide")
        with self.db.transaction() as conn:
            conn.execute("INSERT OR IGNORE INTO unplayable_videos (video_id, marked_at) VALUES (?, ?)", (video_id, time.time_ns()))
            conn.execute("DELETE FROM unplayable_videos WHERE rowid NOT IN "
                         "(SELECT rowid FROM unplayable_videos ORDER BY marked_at DESC LIMIT ?)", (MAX_IDS,))
