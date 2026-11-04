"""Historique des recherches de l'écran du Pi (une liste pour la musique, une pour les podcasts)."""
import time

KINDS = ("music", "podcasts")
MAX_ENTRIES = 15
MAX_LENGTH = 100


class SearchHistory:
    def __init__(self, db):
        self.db = db

    @staticmethod
    def _kind(kind):
        if kind not in KINDS:
            raise ValueError("historique inconnu")
        return kind

    def entries(self, kind):
        rows = self.db.query("SELECT query FROM search_history WHERE kind = ? ORDER BY searched_at DESC, rowid DESC LIMIT ?",
                             (self._kind(kind), MAX_ENTRIES))
        return [r["query"] for r in rows]

    def add(self, kind, text):
        """Recherche la plus récente en tête ; une recherche déjà présente remonte au lieu d'être répétée."""
        text = " ".join(str(text or "").split())[:MAX_LENGTH]
        if len(text) < 2:
            return
        kind = self._kind(kind)
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM search_history WHERE kind = ? AND query_key = ?", (kind, text.lower()))
            conn.execute("INSERT INTO search_history (kind, query, query_key, searched_at) VALUES (?, ?, ?, ?)",
                         (kind, text, text.lower(), time.time_ns()))
            conn.execute("DELETE FROM search_history WHERE kind = ? AND rowid NOT IN (SELECT rowid FROM search_history "
                         "WHERE kind = ? ORDER BY searched_at DESC LIMIT ?)", (kind, kind, MAX_ENTRIES))

    def remove(self, kind, text):
        self.db.execute("DELETE FROM search_history WHERE kind = ? AND query = ?", (self._kind(kind), text))

    def clear(self, kind):
        self.db.execute("DELETE FROM search_history WHERE kind = ?", (self._kind(kind),))
