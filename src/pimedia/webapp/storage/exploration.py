"""Cache persistant des réponses musicales publiques, indépendant des comptes Subsonic."""
import json
from dataclasses import dataclass


@dataclass(frozen=True)
class CachedMetadata:
    key: str
    data: dict
    fetched_at: int


class ExplorationRepository:
    def __init__(self, db):
        self.db = db

    def get(self, key):
        row = self.db.one("SELECT * FROM music_metadata WHERE cache_key = ?", (key,))
        return CachedMetadata(key, json.loads(row["payload"]), row["fetched_at"]) if row else None

    def save(self, entry):
        self.db.execute("INSERT OR REPLACE INTO music_metadata (cache_key, payload, fetched_at) VALUES (?, ?, ?)",
                        (entry.key, json.dumps(entry.data, ensure_ascii=True), entry.fetched_at))
