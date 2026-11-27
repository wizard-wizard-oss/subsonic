"""Abonnements personnels aux styles MusicBrainz, identifiés par leur nom exact."""


class ReleaseSubscriptions:
    def __init__(self, db):
        self.db = db

    def for_user(self, user_id):
        rows = self.db.query("SELECT genre FROM release_subscriptions WHERE user_id = ? ORDER BY genre", (user_id,))
        return [row["genre"] for row in rows]

    def follow(self, user_id, genre):
        self.db.execute("INSERT OR IGNORE INTO release_subscriptions (user_id, genre) VALUES (?, ?)", (user_id, genre))

    def unfollow(self, user_id, genre):
        self.db.execute("DELETE FROM release_subscriptions WHERE user_id = ? AND genre = ?", (user_id, genre))
