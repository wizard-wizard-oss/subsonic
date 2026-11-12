"""Recommendations addressed to a user, independent of their bookmarks."""
import secrets

from ..listen_later_entities import Recommendation
from .listening_targets import COLUMNS, values

SELECT = ("SELECT r.*, u.username AS sender_name FROM recommendations r "
          "JOIN users u ON u.id = r.sender_id ")


class RecommendationRepository:
    def __init__(self, db):
        self.db = db

    def received(self, recipient_id, library_key):
        rows = self.db.query(SELECT + "WHERE r.recipient_id = ? "
                             "AND (r.source != 'subsonic' OR r.library_key = ?) "
                             "ORDER BY r.created_at DESC, r.id DESC", (recipient_id, library_key))
        return [Recommendation.from_row(row) for row in rows]

    def add(self, sender_id, recipient_id, target, now):
        with self.db.transaction() as connection:
            connection.execute("INSERT INTO recommendations (sender_id, recipient_id, " + COLUMNS + ", created_at, unread_token) "
                               "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                               "ON CONFLICT (sender_id, recipient_id, kind, source, library_key, source_id) DO NOTHING",
                               (sender_id, recipient_id) + values(target) + (now, secrets.token_hex(16)))
            row = connection.execute(SELECT + "WHERE r.sender_id = ? AND r.recipient_id = ? "
                                     "AND r.kind = ? AND r.source = ? AND r.library_key = ? AND r.source_id = ?",
                                     (sender_id, recipient_id) + target.key).fetchone()
        return Recommendation.from_row(row)

    def remove(self, recipient_id, reference):
        return self.db.execute("DELETE FROM recommendations WHERE recipient_id = ? "
                               "AND kind = ? AND source = ? AND library_key = ? AND source_id = ?",
                               (recipient_id,) + reference).rowcount

    def has_unread(self, recipient_id, library_key):
        return self.db.one("SELECT 1 FROM recommendations WHERE recipient_id = ? AND unread_token IS NOT NULL "
                           "AND (source != 'subsonic' OR library_key = ?) LIMIT 1",
                           (recipient_id, library_key)) is not None

    def mark_read(self, recipient_id, library_key, tokens):
        placeholders = ",".join("?" for _ in tokens)
        return self.db.execute("UPDATE recommendations SET unread_token = NULL WHERE recipient_id = ? "
                               "AND (source != 'subsonic' OR library_key = ?) AND unread_token IN (" +
                               placeholders + ")", (recipient_id, library_key) + tuple(tokens)).rowcount
