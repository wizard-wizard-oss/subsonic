"""Playlists communautaires : lesquelles le sont, et qui a ajouté chaque titre (Subsonic ne garde pas l'auteur)."""
import time


class CommunityRepository:
    def __init__(self, db):
        self.db = db

    def community_ids(self):
        return {r["playlist_id"] for r in self.db.query("SELECT playlist_id FROM community_playlists")}

    def owner_id(self, playlist_id):
        """Créateur de la playlist si elle est communautaire, sinon None."""
        row = self.db.one("SELECT owner_id FROM community_playlists WHERE playlist_id = ?", (playlist_id,))
        return row["owner_id"] if row else None

    def enable(self, playlist_id, owner_id, now=None):
        self.db.execute("INSERT OR IGNORE INTO community_playlists (playlist_id, owner_id, created_at) VALUES (?, ?, ?)",
                        (playlist_id, owner_id, int(now or time.time())))

    def disable(self, playlist_id):
        self.db.execute("DELETE FROM community_playlists WHERE playlist_id = ?", (playlist_id,))

    def record(self, playlist_id, song_ids, user_id, now=None):
        """Dernier ajout d'un titre : c'est lui qui est affiché."""
        now = int(now or time.time())
        with self.db.transaction() as conn:
            for song_id in song_ids:
                conn.execute("INSERT INTO playlist_additions (playlist_id, song_id, added_by, added_at) VALUES (?, ?, ?, ?) "
                             "ON CONFLICT (playlist_id, song_id) DO UPDATE SET added_by = excluded.added_by, "
                             "added_at = excluded.added_at", (playlist_id, song_id, user_id, now))

    def authors(self, playlist_id):
        """{titre: nom de la personne qui l'a ajouté}."""
        return {r["song_id"]: r["username"] for r in self.db.query(
            "SELECT a.song_id, u.username FROM playlist_additions a JOIN users u ON u.id = a.added_by "
            "WHERE a.playlist_id = ?", (playlist_id,))}

    def forget_songs(self, playlist_id, song_ids):
        with self.db.transaction() as conn:
            for song_id in song_ids:
                conn.execute("DELETE FROM playlist_additions WHERE playlist_id = ? AND song_id = ?", (playlist_id, song_id))

    def forget(self, playlist_id):
        """Playlist supprimée."""
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM community_playlists WHERE playlist_id = ?", (playlist_id,))
            conn.execute("DELETE FROM playlist_additions WHERE playlist_id = ?", (playlist_id,))
