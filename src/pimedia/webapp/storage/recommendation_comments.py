"""SQL for private recommendation comments; also used by atomic initial delivery."""
from ..recommendation_entities import RecommendationComment, RecommendationCommentPage


SELECT = ("SELECT c.*, u.username AS author_name FROM recommendation_comments c "
          "JOIN users u ON u.id = c.author_id ")


def insert_comment(connection, recommendation_id, author_id, body, now, client_token):
    """Le destinataire du commentaire est l'autre participant du fil ; un tiers n'écrit rien."""
    connection.execute("INSERT INTO recommendation_comments "
                       "(recommendation_id, author_id, recipient_id, body, created_at, client_token) "
                       "SELECT id, ?, CASE WHEN sender_id = ? THEN recipient_id ELSE sender_id END, ?, ?, ? "
                       "FROM recommendations WHERE id = ? AND (sender_id = ? OR recipient_id = ?) "
                       "ON CONFLICT (recommendation_id, author_id, client_token) DO NOTHING",
                       (author_id, author_id, body, now, client_token, recommendation_id, author_id, author_id))
    row = connection.execute(SELECT + "WHERE c.recommendation_id = ? AND c.author_id = ? AND c.client_token = ?",
                             (recommendation_id, author_id, client_token)).fetchone()
    return RecommendationComment.from_row(row) if row else None


class RecommendationCommentRepository:
    def __init__(self, db):
        self.db = db

    def add(self, recommendation_id, author_id, body, now, client_token):
        with self.db.transaction() as connection:
            return insert_comment(connection, recommendation_id, author_id, body, now, client_token)

    def page(self, recommendation_id, before, after, limit):
        if after is not None:
            rows = self.db.query(SELECT + "WHERE c.recommendation_id = ? AND c.id > ? ORDER BY c.id LIMIT ?",
                                 (recommendation_id, after, limit + 1))
            return RecommendationCommentPage(tuple(RecommendationComment.from_row(row) for row in rows[:limit]), len(rows) > limit)
        rows = self.db.query(SELECT + "WHERE c.recommendation_id = ? AND c.id < ? ORDER BY c.id DESC LIMIT ?",
                             (recommendation_id, before or 2 ** 63 - 1, limit + 1))
        return RecommendationCommentPage(tuple(RecommendationComment.from_row(row) for row in rows[:limit][::-1]), len(rows) > limit)

    def mark_read(self, recommendation_id, user_id, through_id, now):
        """Lus jusqu'au commentaire affiché, qui doit appartenir à ce fil : un identifiant étranger ne lit rien."""
        return self.db.execute(
            "UPDATE recommendation_comments SET read_at = ? WHERE recommendation_id = ? AND recipient_id = ? "
            "AND read_at IS NULL AND id <= ? "
            "AND EXISTS (SELECT 1 FROM recommendation_comments WHERE id = ? AND recommendation_id = ?)",
            (now, recommendation_id, user_id, through_id, through_id, recommendation_id)).rowcount
