"""Photos de profil envoyées sur le site (petites images, gardées en base)."""
import time


class AvatarRepository:
    def __init__(self, db):
        self.db = db

    def save(self, user_id, mime, data, now=None):
        now = int(now or time.time())
        self.db.execute("INSERT INTO user_avatars (user_id, mime, data, updated_at) VALUES (?, ?, ?, ?) "
                        "ON CONFLICT (user_id) DO UPDATE SET mime = excluded.mime, data = excluded.data, "
                        "updated_at = excluded.updated_at", (user_id, mime, data, now))
        return now

    def get(self, user_id):
        row = self.db.one("SELECT mime, data, updated_at FROM user_avatars WHERE user_id = ?", (user_id,))
        return (row["mime"], bytes(row["data"]), row["updated_at"]) if row else None

    def delete(self, user_id):
        self.db.execute("DELETE FROM user_avatars WHERE user_id = ?", (user_id,))

    def versions(self):
        """{nom: version} : la version change à chaque nouvelle photo (le navigateur recharge l'image)."""
        return {r["username"]: r["updated_at"] for r in self.db.query(
            "SELECT u.username, a.updated_at FROM user_avatars a JOIN users u ON u.id = a.user_id")}
