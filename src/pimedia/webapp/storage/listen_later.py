"""SQLite persistence for each user's listening bookmarks."""
from ..listen_later_entities import ListenLaterEntry
from .listening_targets import COLUMNS, IN_LIBRARY, save_target

SELECT = ("SELECT l.id, l.user_id, l.created_at, " + COLUMNS + " FROM listen_later l "
          "JOIN listening_targets t ON t.id = l.target_id ")


class ListenLaterRepository:
    def __init__(self, db):
        self.db = db

    def all(self, user_id, library_key):
        rows = self.db.query(SELECT + "WHERE l.user_id = ? AND " + IN_LIBRARY + " ORDER BY l.created_at DESC, l.id DESC",
                             (user_id, library_key))
        return [ListenLaterEntry.from_row(row) for row in rows]

    def add(self, user_id, target, now):
        with self.db.transaction() as connection:
            target_id = save_target(connection, target)
            connection.execute("INSERT INTO listen_later (user_id, target_id, created_at) VALUES (?, ?, ?) "
                               "ON CONFLICT (user_id, target_id) DO NOTHING", (user_id, target_id, now))
            row = connection.execute(SELECT + "WHERE l.user_id = ? AND l.target_id = ?", (user_id, target_id)).fetchone()
        return ListenLaterEntry.from_row(row)

    def remove(self, user_id, identity):
        return bool(self.db.execute("DELETE FROM listen_later WHERE user_id = ? AND id = ?",
                                    (user_id, identity)).rowcount)
