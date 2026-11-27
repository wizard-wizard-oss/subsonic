"""Recommendations, durable private threads and delivery acknowledgements."""
import secrets

from ..recommendation_entities import Recommendation, RecommendationDelivery, RecommendationPage
from .listening_targets import BY_KEY, COLUMNS, IN_LIBRARY, save_target
from .recommendation_comments import insert_comment

# Un seul agrégat par conseil affiché, puis le premier commentaire par sa clé : pas de sous-requête par ligne.
INNER = ("SELECT r.id, r.sender_id, r.recipient_id, r.created_at, r.read_at, r.archived_at, " + COLUMNS + ", "
         "sender.username AS sender_name, recipient.username AS recipient_name, COUNT(c.id) AS comment_count, "
         "MIN(c.id) AS first_comment_id, "
         "COALESCE(SUM(c.recipient_id = ? AND c.read_at IS NULL), 0) AS unread_comments "
         "FROM recommendations r JOIN listening_targets t ON t.id = r.target_id "
         "JOIN users sender ON sender.id = r.sender_id JOIN users recipient ON recipient.id = r.recipient_id "
         "LEFT JOIN recommendation_comments c ON c.recommendation_id = r.id ")
UNREAD_COMMENT = ("EXISTS (SELECT 1 FROM recommendation_comments u WHERE u.recommendation_id = r.id "
                  "AND u.recipient_id = ? AND u.read_at IS NULL)")


def select(where, tail=""):
    """Conseils vus par une personne (premier paramètre) : nombre de commentaires, aperçu et non-lus pour elle."""
    return ("SELECT x.*, COALESCE(p.body, '') AS comment_preview FROM (" + INNER + "WHERE " + where +
            " GROUP BY r.id " + tail + ") x LEFT JOIN recommendation_comments p ON p.id = x.first_comment_id "
            "ORDER BY x.id DESC")


class RecommendationRepository:
    def __init__(self, db):
        self.db = db

    def _page(self, user_id, where, params, before, limit):
        rows = self.db.query(select(where + " AND r.id < ?", "ORDER BY r.id DESC LIMIT ?"),
                             (user_id,) + params + (before or 2 ** 63 - 1, limit + 1))
        return RecommendationPage(tuple(Recommendation.from_row(row) for row in rows[:limit]), len(rows) > limit)

    def received(self, recipient_id, library_key, limit=200, before=None):
        return self._page(recipient_id, "r.recipient_id = ? AND r.archived_at IS NULL AND " + IN_LIBRARY,
                          (recipient_id, library_key), before, limit)

    def page(self, user_id, library_key, scope, before, limit):
        owner = "r.sender_id = ?" if scope == "sent" else "r.recipient_id = ? AND r.archived_at IS NOT NULL"
        return self._page(user_id, owner + " AND " + IN_LIBRARY, (user_id, library_key), before, limit)

    def get(self, user_id, identity, library_key):
        row = self.db.one(select("r.id = ? AND (r.sender_id = ? OR r.recipient_id = ?) AND " + IN_LIBRARY),
                          (user_id, identity, user_id, user_id, library_key))
        return Recommendation.from_row(row) if row else None

    def add(self, sender_id, recipient_id, target, now, comment=""):
        with self.db.transaction() as connection:
            target_id = save_target(connection, target)
            created = connection.execute(
                "INSERT INTO recommendations (sender_id, recipient_id, target_id, created_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT (sender_id, recipient_id, target_id) WHERE archived_at IS NULL DO NOTHING",
                (sender_id, recipient_id, target_id, now)).rowcount > 0
            identity = connection.execute(
                "SELECT id FROM recommendations WHERE sender_id = ? AND recipient_id = ? AND target_id = ? "
                "AND archived_at IS NULL", (sender_id, recipient_id, target_id)).fetchone()[0]
            if created and comment:
                insert_comment(connection, identity, sender_id, comment, now, secrets.token_hex(16))
            row = connection.execute(select("r.id = ?"), (sender_id, identity)).fetchone()
        return RecommendationDelivery(Recommendation.from_row(row), created)

    def archive(self, recipient_id, reference, now):
        return self.db.execute("UPDATE recommendations SET archived_at = ?, read_at = COALESCE(read_at, ?) "
                               "WHERE recipient_id = ? AND archived_at IS NULL AND target_id = (" + BY_KEY + ")",
                               (now, now, recipient_id) + reference).rowcount

    def has_unread(self, user_id, library_key):
        delivery = ("SELECT 1 FROM recommendations r JOIN listening_targets t ON t.id = r.target_id "
                    "WHERE r.recipient_id = ? AND r.archived_at IS NULL AND r.read_at IS NULL AND " + IN_LIBRARY)
        comment = ("SELECT 1 FROM recommendation_comments c JOIN recommendations r ON r.id = c.recommendation_id "
                   "JOIN listening_targets t ON t.id = r.target_id "
                   "WHERE c.recipient_id = ? AND c.read_at IS NULL AND " + IN_LIBRARY)
        return self.db.one("SELECT EXISTS (" + delivery + ") OR EXISTS (" + comment + ")",
                           (user_id, library_key, user_id, library_key))[0] == 1

    def unread_discussion(self, user_id, library_key):
        row = self.db.one(select("(r.sender_id = ? OR r.recipient_id = ?) AND " + IN_LIBRARY + " AND " + UNREAD_COMMENT,
                                 "ORDER BY r.id DESC LIMIT 1"),
                          (user_id, user_id, user_id, library_key, user_id))
        return Recommendation.from_row(row) if row else None

    def mark_read(self, recipient_id, library_key, ids, now):
        placeholders = ",".join("?" for _ in ids)
        return self.db.execute(
            "UPDATE recommendations SET read_at = ? WHERE recipient_id = ? AND read_at IS NULL "
            "AND id IN (" + placeholders + ") AND target_id IN (SELECT t.id FROM listening_targets t WHERE " +
            IN_LIBRARY + ")", (now, recipient_id) + tuple(ids) + (library_key,)).rowcount
