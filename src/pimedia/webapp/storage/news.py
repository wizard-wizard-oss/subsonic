"""Actualité gardée en base : flux suivis par le site et articles lus dans ces flux."""
import time

from ...server.podcasts.relevance import normalize
from ..entities import NewsArticle, NewsFeed

FEED_COLUMNS = ("f.*, (SELECT COUNT(*) FROM news_articles a WHERE a.feed_id = f.id) AS articles "
                "FROM news_feeds f")
ARTICLE_COLUMNS = ("a.id, a.feed_id, f.title AS feed_title, a.link, a.title, a.summary, a.published_at "
                   "FROM news_articles a JOIN news_feeds f ON f.id = a.feed_id")

HIDDEN_EXCLUDED = "a.feed_id NOT IN (SELECT feed_id FROM news_hidden_feeds WHERE user_id = ?)"


class NewsRepository:
    def __init__(self, db, clock=time.time):
        self.db, self.clock = db, clock

    # ---------- flux ----------
    def feeds(self):
        """Tous les flux, par nom, avec leur nombre d'articles gardés."""
        return [NewsFeed.from_row(r) for r in self.db.query(
            "SELECT " + FEED_COLUMNS + " ORDER BY f.title COLLATE NOCASE")]

    def feed(self, feed_id):
        row = self.db.one("SELECT " + FEED_COLUMNS + " WHERE f.id = ?", (feed_id,))
        return NewsFeed.from_row(row) if row else None

    def has_url(self, url):
        return self.db.one("SELECT 1 FROM news_feeds WHERE url = ?", (url,)) is not None

    def count(self):
        return self.db.one("SELECT COUNT(*) FROM news_feeds")[0]

    def add_feed(self, url, title, site_url, added_by):
        cursor = self.db.execute("INSERT INTO news_feeds (url, title, site_url, added_by, added_at) VALUES (?, ?, ?, ?, ?)",
                                 (url, title, site_url, added_by, int(self.clock())))
        return self.feed(cursor.lastrowid)

    def remove_feed(self, feed_id):
        """Le flux et ses articles."""
        self.db.execute("DELETE FROM news_feeds WHERE id = ?", (feed_id,))

    def checked(self, feed_id, error=""):
        """Lecture faite (error vide) ou ratée (clé de texte du problème)."""
        self.db.execute("UPDATE news_feeds SET checked_at = ?, error = ? WHERE id = ?",
                        (int(self.clock()), error[:200], feed_id))

    # ---------- flux masqués par une personne ----------
    def hidden(self, user_id):
        return {r["feed_id"] for r in self.db.query("SELECT feed_id FROM news_hidden_feeds WHERE user_id = ?", (user_id,))}

    def set_hidden(self, user_id, feed_id, hidden):
        if hidden:
            self.db.execute("INSERT OR IGNORE INTO news_hidden_feeds (user_id, feed_id) VALUES (?, ?)", (user_id, feed_id))
        else:
            self.db.execute("DELETE FROM news_hidden_feeds WHERE user_id = ? AND feed_id = ?", (user_id, feed_id))

    # ---------- articles ----------
    def add_articles(self, feed_id, articles):
        """Garde les articles pas encore connus (même lien dans le même flux : déjà là). Renvoie le nombre d'ajouts."""
        added = 0
        with self.db.transaction() as conn:
            for a in articles:
                cursor = conn.execute(
                    "INSERT OR IGNORE INTO news_articles (feed_id, link, title, summary, published_at, words) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (feed_id, a["link"], a["title"], a["summary"], int(a["date"] or self.clock()), normalize(a["title"])))
                added += cursor.rowcount
        return added

    def latest(self, user_id, feed_id=None, before=None, limit=40):
        """Les plus récents d'abord ; before : (date, id) du dernier article déjà affiché (pour « Afficher plus »).
        Tous les flux : sauf ceux que la personne a masqués ; un flux choisi : même masqué."""
        where, params = [], []
        if feed_id:
            where.append("a.feed_id = ?")
            params.append(feed_id)
        else:
            where.append(HIDDEN_EXCLUDED)
            params.append(user_id)
        if before:
            where.append("(a.published_at < ? OR (a.published_at = ? AND a.id < ?))")
            params += [before[0], before[0], before[1]]
        sql = "SELECT " + ARTICLE_COLUMNS + (" WHERE " + " AND ".join(where) if where else "")
        return [NewsArticle.from_row(r) for r in self.db.query(
            sql + " ORDER BY a.published_at DESC, a.id DESC LIMIT ?", params + [limit])]

    def mentioning(self, user_id, name, limit=10):
        """Articles dont le titre contient le nom (mots entiers, sans accents ni ponctuation), récents d'abord,
        sauf ceux des flux que la personne a masqués."""
        words = normalize(name)
        if not words.strip():
            return []
        return [NewsArticle.from_row(r) for r in self.db.query(
            "SELECT " + ARTICLE_COLUMNS + " WHERE instr(a.words, ?) > 0 AND " + HIDDEN_EXCLUDED +
            " ORDER BY a.published_at DESC LIMIT ?", (words, user_id, limit))]
