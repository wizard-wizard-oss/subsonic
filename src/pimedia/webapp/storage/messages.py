"""Salon global et commentaires d'albums : messages, réactions, mentions, lectures."""
import time

from ..entities import Attachment, ChatMessage, DiscussedAlbum, ReplyPreview

EXCERPT = 120

SELECT = ("SELECT m.*, u.username AS author, r.id AS r_id, r.body AS r_body, r.deleted_at AS r_deleted, "
          "ru.username AS r_author FROM chat_messages m JOIN users u ON u.id = m.user_id "
          "LEFT JOIN chat_messages r ON r.id = m.reply_to_id LEFT JOIN users ru ON ru.id = r.user_id ")


def excerpt(text):
    text = " ".join(text.split())
    return text if len(text) <= EXCERPT else text[:EXCERPT - 1] + "…"


class MessageRepository:
    def __init__(self, db):
        self.db = db

    # --- écriture ---
    def add(self, topic, user_id, body, reply_to_id=None, attachment=None, mention_ids=(), now=None):
        now = int(now or time.time())
        with self.db.transaction() as conn:
            cursor = conn.execute(
                "INSERT INTO chat_messages (topic, user_id, body, reply_to_id, attachment, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (topic, user_id, body, reply_to_id, attachment.to_json() if attachment else "", now))
            message_id = cursor.lastrowid
            for mentioned in set(mention_ids):
                conn.execute("INSERT OR IGNORE INTO message_mentions (message_id, user_id) VALUES (?, ?)",
                             (message_id, mentioned))
        return message_id

    def edit(self, message_id, body, mention_ids=(), now=None):
        with self.db.transaction() as conn:
            conn.execute("UPDATE chat_messages SET body = ?, edited_at = ? WHERE id = ?",
                         (body, int(now or time.time()), message_id))
            conn.execute("DELETE FROM message_mentions WHERE message_id = ?", (message_id,))
            for mentioned in set(mention_ids):
                conn.execute("INSERT OR IGNORE INTO message_mentions (message_id, user_id) VALUES (?, ?)",
                             (message_id, mentioned))

    def delete(self, message_id, by_user_id, now=None):
        """Suppression douce : la ligne reste (les réponses gardent leur fil), le contenu est effacé."""
        with self.db.transaction() as conn:
            conn.execute("UPDATE chat_messages SET deleted_at = ?, deleted_by = ?, body = '', attachment = '' "
                         "WHERE id = ?", (int(now or time.time()), by_user_id, message_id))
            conn.execute("DELETE FROM message_reactions WHERE message_id = ?", (message_id,))
            conn.execute("DELETE FROM message_mentions WHERE message_id = ?", (message_id,))

    def toggle_reaction(self, message_id, user_id, emoji, now=None):
        """True si la réaction est ajoutée, False si elle est retirée."""
        with self.db.transaction() as conn:
            removed = conn.execute("DELETE FROM message_reactions WHERE message_id = ? AND user_id = ? AND emoji = ?",
                                   (message_id, user_id, emoji)).rowcount
            if removed:
                return False
            conn.execute("INSERT INTO message_reactions (message_id, user_id, emoji, created_at) VALUES (?, ?, ?, ?)",
                         (message_id, user_id, emoji, int(now or time.time())))
            return True

    # --- lecture ---
    def get(self, message_id):
        rows = self.db.query(SELECT + "WHERE m.id = ?", (message_id,))
        return self._build(rows)[0] if rows else None

    def page(self, topic, before_id=None, after_id=None, limit=50):
        """Messages d'un sujet, du plus ancien au plus récent : les « limit » derniers (avant before_id),
        ou ceux arrivés après after_id (rattrapage après une coupure)."""
        limit = max(1, min(int(limit), 200))
        if after_id:
            rows = self.db.query(SELECT + "WHERE m.topic = ? AND m.id > ? ORDER BY m.id LIMIT ?",
                                 (topic, after_id, limit))
        else:
            rows = self.db.query(SELECT + "WHERE m.topic = ? AND m.id < ? ORDER BY m.id DESC LIMIT ?",
                                 (topic, before_id or 2 ** 62, limit))[::-1]
        return self._build(rows)

    def search(self, topic, words, limit=30):
        clauses = " AND ".join("m.body LIKE ? ESCAPE '\\'" for _ in words)
        params = [topic] + ["%" + w.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%" for w in words]
        rows = self.db.query(SELECT + "WHERE m.topic = ? AND m.deleted_at IS NULL AND %s ORDER BY m.id DESC LIMIT ?"
                             % clauses, params + [limit])
        return self._build(rows)

    def mentions_of(self, user_id, limit=30):
        rows = self.db.query(SELECT + "JOIN message_mentions mm ON mm.message_id = m.id WHERE mm.user_id = ? "
                             "AND m.deleted_at IS NULL ORDER BY m.id DESC LIMIT ?", (user_id, limit))
        return self._build(rows)

    def recent_count(self, user_id, since):
        """Messages de cet utilisateur depuis « since » (anti-spam)."""
        return self.db.one("SELECT COUNT(*) FROM chat_messages WHERE user_id = ? AND created_at >= ?",
                           (user_id, since))[0]

    def count(self, topic):
        return self.db.one("SELECT COUNT(*) FROM chat_messages WHERE topic = ? AND deleted_at IS NULL", (topic,))[0]

    def counts(self, topics):
        topics = list(dict.fromkeys(topics))[:500]
        if not topics:
            return {}
        rows = self.db.query("SELECT topic, COUNT(*) AS n FROM chat_messages WHERE deleted_at IS NULL AND topic IN (%s) "
                             "GROUP BY topic" % ",".join("?" * len(topics)), topics)
        return {r["topic"]: r["n"] for r in rows}

    def _build(self, rows):
        if not rows:
            return []
        ids = [r["id"] for r in rows]
        marks = ",".join("?" * len(ids))
        reactions, mentions = {}, {}
        for r in self.db.query("SELECT mr.message_id, mr.emoji, u.username FROM message_reactions mr "
                               "JOIN users u ON u.id = mr.user_id WHERE mr.message_id IN (%s) "
                               "ORDER BY mr.created_at" % marks, ids):
            reactions.setdefault(r["message_id"], {}).setdefault(r["emoji"], []).append(r["username"])
        for r in self.db.query("SELECT mm.message_id, u.username FROM message_mentions mm JOIN users u "
                               "ON u.id = mm.user_id WHERE mm.message_id IN (%s)" % marks, ids):
            mentions.setdefault(r["message_id"], []).append(r["username"])
        messages = []
        for r in rows:
            reply = None
            if r["r_id"] is not None:
                reply = ReplyPreview(r["r_id"], r["r_author"], "" if r["r_deleted"] else excerpt(r["r_body"]),
                                     r["r_deleted"] is not None)
            messages.append(ChatMessage(r["id"], r["topic"], r["user_id"], r["author"], r["body"], r["created_at"],
                                        r["edited_at"], r["deleted_at"], Attachment.from_json(r["attachment"]), reply,
                                        reactions.get(r["id"], {}), sorted(mentions.get(r["id"], []))))
        return messages

    # --- lectures (non-lus) ---
    def mark_read(self, user_id, topic, message_id):
        self.db.execute("INSERT INTO topic_reads (user_id, topic, last_read_id) VALUES (?, ?, ?) "
                        "ON CONFLICT (user_id, topic) DO UPDATE SET last_read_id = MAX(last_read_id, excluded.last_read_id)",
                        (user_id, topic, message_id))

    def unread(self, user_id, topic):
        row = self.db.one("SELECT last_read_id FROM topic_reads WHERE user_id = ? AND topic = ?", (user_id, topic))
        last = row["last_read_id"] if row else 0
        return self.db.one("SELECT COUNT(*) FROM chat_messages WHERE topic = ? AND id > ? AND user_id != ? "
                           "AND deleted_at IS NULL", (topic, last, user_id))[0]

    def last_read(self, user_id, topic):
        row = self.db.one("SELECT last_read_id FROM topic_reads WHERE user_id = ? AND topic = ?", (user_id, topic))
        return row["last_read_id"] if row else 0

    # --- albums commentés ---
    def touch_album(self, album_id, title, artist, cover_id, now=None):
        self.db.execute("INSERT INTO albums_discussed (album_id, title, artist, cover_id, last_message_at) "
                        "VALUES (?, ?, ?, ?, ?) ON CONFLICT (album_id) DO UPDATE SET title = excluded.title, "
                        "artist = excluded.artist, cover_id = excluded.cover_id, "
                        "last_message_at = excluded.last_message_at",
                        (album_id, title, artist, cover_id, int(now or time.time())))

    def discussed_albums(self, limit=12):
        rows = self.db.query(
            "SELECT a.*, (SELECT COUNT(*) FROM chat_messages m WHERE m.topic = 'album:' || a.album_id "
            "AND m.deleted_at IS NULL) AS comments FROM albums_discussed a ORDER BY a.last_message_at DESC LIMIT ?",
            (limit,))
        return [DiscussedAlbum(r["album_id"], r["title"], r["artist"], r["cover_id"], r["last_message_at"],
                               r["comments"]) for r in rows if r["comments"]]
