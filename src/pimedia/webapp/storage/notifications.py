"""Stockage des notifications et de leur lecture, limité au destinataire."""
from ..notifications.entities import Notification, NotificationDelivery


class NotificationRepository:
    def __init__(self, db):
        self.db = db

    def add(self, sender_id, recipient_id, title, body, token, now):
        with self.db.transaction() as connection:
            inserted = connection.execute(
                "INSERT INTO notifications (sender_id, recipient_id, title, body, client_token, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (sender_id, recipient_id, client_token) DO NOTHING",
                (sender_id, recipient_id, title, body, token, now))
            row = connection.execute(
                "SELECT * FROM notifications WHERE sender_id = ? AND recipient_id = ? AND client_token = ?",
                (sender_id, recipient_id, token)).fetchone()
            return NotificationDelivery(Notification.from_row(row), inserted.rowcount == 1)

    def page(self, recipient_id, before, limit):
        where, params = ("", ()) if before is None else (" AND id < ?", (before,))
        rows = self.db.query("SELECT * FROM notifications WHERE recipient_id = ?" + where +
                             " ORDER BY id DESC LIMIT ?", (recipient_id,) + params + (limit,))
        return [Notification.from_row(row) for row in rows]

    def unread(self, recipient_id):
        return self.db.one("SELECT COUNT(*) FROM notifications WHERE recipient_id = ? AND read_at IS NULL",
                           (recipient_id,))[0]

    def mark_read(self, recipient_id, identity, now):
        self.db.execute("UPDATE notifications SET read_at = ? WHERE recipient_id = ? AND id = ? AND read_at IS NULL",
                        (now, recipient_id, identity))
