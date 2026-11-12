"""SQLite persistence for each user's listening bookmarks."""
from ..listen_later_entities import ListenLaterEntry
from .listening_targets import COLUMNS, values

REFERENCE = "user_id = ? AND kind = ? AND source = ? AND library_key = ? AND source_id = ?"


class ListenLaterRepository:
    def __init__(self, db):
        self.db = db

    def all(self, user_id, library_key):
        rows = self.db.query("SELECT * FROM listen_later WHERE user_id = ? "
                             "AND (source != 'subsonic' OR library_key = ?) ORDER BY created_at DESC, id DESC",
                             (user_id, library_key))
        return [ListenLaterEntry.from_row(row) for row in rows]

    def add(self, user_id, target, now):
        with self.db.transaction() as connection:
            connection.execute("INSERT INTO listen_later (user_id, " + COLUMNS + ", created_at) "
                               "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                               "ON CONFLICT (user_id, kind, source, library_key, source_id) DO NOTHING",
                               (user_id,) + values(target) + (now,))
            row = connection.execute("SELECT * FROM listen_later WHERE " + REFERENCE,
                                     (user_id,) + target.key).fetchone()
        return ListenLaterEntry.from_row(row)

    def remove(self, user_id, identity):
        return bool(self.db.execute("DELETE FROM listen_later WHERE user_id = ? AND id = ?",
                                    (user_id, identity)).rowcount)
