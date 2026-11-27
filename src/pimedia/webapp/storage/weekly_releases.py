"""Abonnements personnels aux genres MusicBrainz."""
from ..weekly_release_entities import ReleaseGenre


class ReleaseSubscriptions:
    def __init__(self, db):
        self.db = db

    def for_user(self, user_id):
        rows = self.db.query("SELECT genre_id, name FROM release_subscriptions WHERE user_id = ? ORDER BY name",
                             (user_id,))
        return [ReleaseGenre(row["genre_id"], row["name"]) for row in rows]

    def follow(self, user_id, genre):
        self.db.execute(
            "INSERT OR IGNORE INTO release_subscriptions (user_id, genre_id, name) SELECT ?, ?, ? "
            "WHERE NOT EXISTS (SELECT 1 FROM release_subscriptions WHERE user_id = ? AND name = ?)",
            (user_id, genre.id, genre.name, user_id, genre.name),
        )

    def unfollow(self, user_id, name):
        self.db.execute("DELETE FROM release_subscriptions WHERE user_id = ? AND name = ?", (user_id, name))
