"""Liste des artistes gardée en base : Subsonic peut mettre plus de 30 s à la calculer."""
import json

from ..entities import ArtistIndex


class ArtistIndexRepository:
    def __init__(self, db):
        self.db = db

    def get(self, folders):
        row = self.db.one("SELECT * FROM artist_indexes WHERE folders = ?", (folders,))
        return self._entity(row) if row else None

    def all(self):
        return [self._entity(r) for r in self.db.query("SELECT * FROM artist_indexes ORDER BY built_at DESC")]

    def save(self, index):
        self.db.execute("INSERT INTO artist_indexes (folders, artists, since, built_at) VALUES (?, ?, ?, ?) "
                        "ON CONFLICT (folders) DO UPDATE SET artists = excluded.artists, since = excluded.since, "
                        "built_at = excluded.built_at",
                        (index.folders, json.dumps(index.artists, ensure_ascii=False), index.since, index.built_at))

    @staticmethod
    def _entity(row):
        return ArtistIndex(row["folders"], json.loads(row["artists"]), row["since"], row["built_at"])
