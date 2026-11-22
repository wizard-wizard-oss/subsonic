"""Recommendations, durable private threads and delivery acknowledgements."""
import secrets

from ..recommendation_entities import Recommendation, RecommendationDelivery, RecommendationPage
from .listening_targets import COLUMNS, values
from .recommendation_comments import insert_comment


SELECT = ("SELECT r.*, sender.username AS sender_name, recipient.username AS recipient_name, "
          "(SELECT COUNT(*) FROM recommendation_comments c WHERE c.recommendation_id = r.id) AS comment_count, "
          "COALESCE((SELECT body FROM recommendation_comments c WHERE c.recommendation_id = r.id "
          "ORDER BY c.id LIMIT 1), '') AS comment_preview, "
          "COALESCE((SELECT MAX(c.id) FROM recommendation_comments c WHERE c.recommendation_id = r.id "
          "AND c.author_id = r.sender_id), 0) AS sender_last_comment_id, "
          "COALESCE((SELECT MAX(c.id) FROM recommendation_comments c WHERE c.recommendation_id = r.id "
          "AND c.author_id = r.recipient_id), 0) AS recipient_last_comment_id "
          "FROM recommendations r JOIN users sender ON sender.id = r.sender_id "
          "JOIN users recipient ON recipient.id = r.recipient_id ")
LIBRARY = "(r.source != 'subsonic' OR r.library_key = ?) "
UNREAD_COMMENTS = ("EXISTS (SELECT 1 FROM recommendation_comments c WHERE c.recommendation_id = r.id "
                   "AND c.author_id != ? AND c.id > CASE WHEN r.sender_id = ? THEN r.sender_last_read_comment_id "
                   "ELSE r.recipient_last_read_comment_id END)")


class RecommendationRepository:
    def __init__(self, db):
        self.db = db

    def received(self, recipient_id, library_key):
        rows = self.db.query(SELECT + "WHERE r.recipient_id = ? AND r.recipient_archived_at IS NULL AND " + LIBRARY +
                             "ORDER BY r.created_at DESC, r.id DESC", (recipient_id, library_key))
        return [Recommendation.from_row(row) for row in rows]

    def get(self, user_id, identity, library_key):
        row = self.db.one(SELECT + "WHERE r.id = ? AND (r.sender_id = ? OR r.recipient_id = ?) AND " + LIBRARY,
                          (identity, user_id, user_id, library_key))
        return Recommendation.from_row(row) if row else None

    def page(self, user_id, library_key, scope, before, limit):
        owner = "r.sender_id = ?" if scope == "sent" else "r.recipient_id = ? AND r.recipient_archived_at IS NOT NULL"
        rows = self.db.query(SELECT + "WHERE " + owner + " AND r.id < ? AND " + LIBRARY + "ORDER BY r.id DESC LIMIT ?",
                             (user_id, before or 2 ** 63 - 1, library_key, limit + 1))
        return RecommendationPage(tuple(Recommendation.from_row(row) for row in rows[:limit]), len(rows) > limit)

    def add(self, sender_id, recipient_id, target, now, comment=""):
        with self.db.transaction() as connection:
            created = connection.execute(
                "INSERT INTO recommendations (sender_id, recipient_id, " + COLUMNS + ", created_at, unread_token) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT (sender_id, recipient_id, kind, source, library_key, source_id) "
                "WHERE recipient_archived_at IS NULL DO NOTHING",
                (sender_id, recipient_id) + values(target) + (now, secrets.token_hex(16))).rowcount > 0
            row = connection.execute(SELECT + "WHERE r.sender_id = ? AND r.recipient_id = ? "
                                     "AND r.kind = ? AND r.source = ? AND r.library_key = ? AND r.source_id = ? "
                                     "AND r.recipient_archived_at IS NULL", (sender_id, recipient_id) + target.key).fetchone()
            if created and comment:
                insert_comment(connection, row["id"], sender_id, comment, now, secrets.token_hex(16))
                row = connection.execute(SELECT + "WHERE r.id = ?", (row["id"],)).fetchone()
        return RecommendationDelivery(Recommendation.from_row(row), created)

    def archive(self, recipient_id, reference, now):
        return self.db.execute("UPDATE recommendations SET recipient_archived_at = ?, unread_token = NULL "
                               "WHERE recipient_id = ? AND recipient_archived_at IS NULL "
                               "AND kind = ? AND source = ? AND library_key = ? AND source_id = ?",
                               (now, recipient_id) + reference).rowcount

    def has_unread(self, user_id, library_key):
        return self.db.one(
            "SELECT 1 FROM recommendations r WHERE (r.sender_id = ? OR r.recipient_id = ?) AND " + LIBRARY +
            "AND ((r.recipient_id = ? AND r.recipient_archived_at IS NULL AND r.unread_token IS NOT NULL) "
            "OR " + UNREAD_COMMENTS + ") LIMIT 1",
            (user_id, user_id, library_key, user_id, user_id, user_id)) is not None

    def unread_discussion(self, user_id, library_key):
        row = self.db.one(SELECT + "WHERE (r.sender_id = ? OR r.recipient_id = ?) AND " + LIBRARY +
                          "AND " + UNREAD_COMMENTS + " ORDER BY r.id DESC LIMIT 1",
                          (user_id, user_id, library_key, user_id, user_id))
        return Recommendation.from_row(row) if row else None

    def mark_read(self, recipient_id, library_key, tokens):
        placeholders = ",".join("?" for _ in tokens)
        return self.db.execute("UPDATE recommendations SET unread_token = NULL WHERE recipient_id = ? "
                               "AND (source != 'subsonic' OR library_key = ?) AND unread_token IN (" +
                               placeholders + ")", (recipient_id, library_key) + tuple(tokens)).rowcount
