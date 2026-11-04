"""Podcasts de l'écran du Pi : abonnements, podcasts masqués, progression d'écoute."""
import time

from ..entities import EpisodeProgress, PodcastSubscription

MAX_RESUME = 12
FINISHED_MARGIN_S = 30          # à moins de 30 s de la fin, un épisode compte comme écouté


def _subscription(row):
    return PodcastSubscription(row["feed_url"], row["title"], row["image_url"], row["author"], row["subscribed_at"])


def _progress(row):
    return EpisodeProgress(row["episode_id"], row["feed_url"], row["title"], row["podcast_title"], row["image_url"],
                           row["audio_url"], row["position_s"], row["duration_s"], bool(row["played"]), row["updated_at"])


class PodcastLibrary:
    def __init__(self, db):
        self.db = db

    # --- abonnements ---
    def subscribe(self, feed, title, image="", author=""):
        self.db.execute(
            "INSERT INTO podcast_subscriptions (feed_url, title, image_url, author, subscribed_at) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT (feed_url) DO UPDATE SET title = excluded.title, image_url = excluded.image_url, author = excluded.author",
            (feed, title, image or "", author or "", int(time.time())))

    def unsubscribe(self, feed):
        self.db.execute("DELETE FROM podcast_subscriptions WHERE feed_url = ?", (feed,))

    def is_subscribed(self, feed):
        return self.db.one("SELECT 1 FROM podcast_subscriptions WHERE feed_url = ?", (feed,)) is not None

    def subscriptions(self):
        rows = self.db.query("SELECT * FROM podcast_subscriptions ORDER BY title COLLATE NOCASE")
        return [_subscription(r) for r in rows]

    # --- masqués ---
    def hide(self, feed):
        self.db.execute("INSERT OR IGNORE INTO hidden_podcasts (feed_url) VALUES (?)", (feed,))

    def is_hidden(self, feed):
        return self.db.one("SELECT 1 FROM hidden_podcasts WHERE feed_url = ?", (feed,)) is not None

    # --- progression ---
    def save_progress(self, episode):
        """episode : {id, feed, title, podcast, image, audio, pos, dur}. Un épisode fini est marqué « écouté »."""
        position, duration = float(episode.get("pos", 0)), float(episode.get("dur", 0))
        finished = duration > 0 and position >= duration - FINISHED_MARGIN_S
        self.db.execute(
            "INSERT INTO episode_progress (episode_id, feed_url, title, podcast_title, image_url, audio_url, position_s, "
            "duration_s, played, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (episode_id) DO UPDATE SET "
            "feed_url = excluded.feed_url, title = excluded.title, podcast_title = excluded.podcast_title, "
            "image_url = excluded.image_url, audio_url = excluded.audio_url, position_s = excluded.position_s, "
            "duration_s = excluded.duration_s, played = excluded.played, updated_at = excluded.updated_at",
            (episode["id"], episode.get("feed", ""), episode.get("title", ""), episode.get("podcast", ""),
             episode.get("image", ""), episode.get("audio", ""), 0 if finished else position, duration,
             int(finished), int(time.time())))

    def mark_played(self, episode_id, played=True):
        if played:
            self.db.execute("UPDATE episode_progress SET played = 1, position_s = 0 WHERE episode_id = ?", (episode_id,))
        else:
            self.db.execute("UPDATE episode_progress SET played = 0 WHERE episode_id = ?", (episode_id,))

    def forget(self, episode_id):
        """Retire un épisode de « Reprendre l'écoute » (sa position est oubliée)."""
        self.db.execute("DELETE FROM episode_progress WHERE episode_id = ?", (episode_id,))

    def progress_of(self, episode_id):
        row = self.db.one("SELECT * FROM episode_progress WHERE episode_id = ?", (episode_id,))
        return _progress(row) if row else None

    def progress_for_feed(self, feed):
        return {r["episode_id"]: _progress(r) for r in self.db.query("SELECT * FROM episode_progress WHERE feed_url = ?", (feed,))}

    def resume_list(self):
        """Épisodes commencés et non terminés, le plus récent d'abord."""
        rows = self.db.query("SELECT * FROM episode_progress WHERE played = 0 AND position_s > 10 "
                             "ORDER BY updated_at DESC, rowid DESC LIMIT ?", (MAX_RESUME,))
        return [_progress(r) for r in rows]
