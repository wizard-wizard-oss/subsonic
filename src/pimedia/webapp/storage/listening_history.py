"""Événements d’écoute personnels, sans purge ni copie des tags des fichiers."""
from ..personal_home.entities import HistoryEntry
from .listening_targets import save_target


class ListeningHistoryRepository:
    def __init__(self, db):
        self.db = db

    def add(self, user_id, target, request_id, played_at):
        with self.db.transaction() as connection:
            existing = connection.execute(
                "SELECT h.id, t.source_id, h.played_at, t.kind, t.source, t.library_key FROM listening_history h "
                "JOIN listening_targets t ON t.id = h.target_id WHERE h.user_id = ? AND h.request_id = ?",
                (user_id, request_id)).fetchone()
            if existing:
                key = (existing["kind"], existing["source"], existing["library_key"], existing["source_id"])
                if key != target.key:
                    raise ValueError("request conflict")
                return HistoryEntry(existing["id"], existing["source_id"], existing["played_at"])
            target_id = save_target(connection, target)
            cursor = connection.execute(
                "INSERT INTO listening_history (user_id, target_id, request_id, played_at) VALUES (?, ?, ?, ?)",
                (user_id, target_id, request_id, played_at))
            return HistoryEntry(cursor.lastrowid, target.source_id, played_at)

    def recent(self, user_id, library_key, limit, before=None):
        rows = self.db.query(
            "SELECT MAX(h.id) AS latest_id, t.source_id, MAX(h.played_at) AS played_at "
            "FROM listening_history h JOIN listening_targets t ON t.id = h.target_id "
            "WHERE h.user_id = ? AND t.library_key = ? GROUP BY h.target_id "
            "HAVING (? IS NULL OR MAX(h.id) < ?) ORDER BY latest_id DESC LIMIT ?",
            (user_id, library_key, before, before, limit))
        return tuple(HistoryEntry(*row) for row in rows)
