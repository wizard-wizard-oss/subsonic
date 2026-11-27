"""Notifications privées : droits HTTP, destinataires, lecture durable et diffusion SSE ciblée."""
import json
import queue
import tempfile
import unittest
from pathlib import Path

from pimedia.storage.database import Database
from pimedia.webapp.notification_entities import BODY_MAX_LENGTH, PAGE_SIZE, TITLE_MAX_LENGTH
from pimedia.webapp.schema import MIGRATIONS
from pimedia.webapp.storage.notifications import NotificationRepository
from tests.webapp_support import WebAppTestCase


class NotificationsHttpTest(WebAppTestCase):
    def setUp(self):
        super().setUp()
        self.alice = self.client("alice", "secret")
        self.bob = self.client("bob", "pw2")

    def payload(self, **changes):
        return dict(dict(recipient="bob", title="Envoi retiré", body="Les MP3 seuls ne sont pas autorisés.",
                         requestId="notification-test-0001"), **changes)

    def send(self, **changes):
        response = self.alice.post_json("/api/notifications/send", self.payload(**changes))
        self.assertEqual(response.status, 200, response.body)
        return response.json()

    def test_service_answers_with_entities(self):
        self.send()
        bob = self.app.users.by_name("bob")
        page, status = self.app.notifications.page(bob), self.app.notifications.status(bob)
        self.assertEqual(type(page).__name__, "NotificationPage")
        self.assertEqual(status.to_api(), {"unread": 1})
        self.assertEqual(set(page.to_api()), {"entries", "before", "unread", "limits"})

    def test_admin_can_send_and_only_recipient_can_read(self):
        entry = self.send()
        page = self.bob.get("/api/notifications").json()
        self.assertEqual(page["entries"], [entry])
        self.assertEqual(page["unread"], 1)
        self.assertIsNone(entry["readAt"])
        self.assertEqual(self.alice.get("/api/notifications").json()["entries"], [])
        self.assertNotIn("sender_id", json.dumps(page))
        self.assertEqual(self.bob.get("/api/notifications/status").json(), dict(unread=1))

    def test_authentication_admin_right_and_csrf_are_required(self):
        self.assertEqual(self.client().get("/api/notifications").status, 401)
        self.assertEqual(self.bob.post_json("/api/notifications/send", self.payload()).status, 403)
        self.assertEqual(self.bob.get("/api/notifications/recipients").status, 403)
        self.assertEqual(self.alice.request("POST", "/api/notifications/send", body=json.dumps(self.payload()).encode(), csrf=False).status, 403)
        self.send()
        self.assertEqual(self.bob.request("POST", "/api/notifications/read", body=b'{"id":1}', csrf=False).status, 403)
        self.subsonic.roles["alice"] = {"adminRole": False}
        self.alice.get("/api/me")
        self.assertEqual(self.alice.post_json("/api/notifications/send", self.payload()).status, 403)

    def test_recipient_list_uses_existing_members(self):
        self.assertEqual(set(self.alice.get("/api/notifications/recipients").json()["usernames"]), {"alice", "bob"})

    def test_read_is_owned_idempotent_and_survives_a_new_connection(self):
        entry = self.send()
        self.alice.post_json("/api/notifications/read", dict(id=entry["id"]))
        self.assertEqual(self.bob.get("/api/notifications/status").json()["unread"], 1)
        self.assertEqual(self.bob.post_json("/api/notifications/read", dict(id=entry["id"])).json(), dict(unread=0))
        first = self.bob.get("/api/notifications").json()["entries"][0]
        self.assertIsInstance(first["readAt"], int)
        self.bob.post_json("/api/notifications/read", dict(id=entry["id"]))
        self.assertEqual(self.bob.get("/api/notifications").json()["entries"][0], first)
        db = Database(self.app.db.path, MIGRATIONS)
        try:
            repo = NotificationRepository(db)
            self.assertEqual(repo.page(self.app.users.by_name("bob").id, None, 1)[0].to_api(), first)
            self.assertEqual(repo.unread(self.app.users.by_name("bob").id), 0)
        finally:
            db.close()

    def test_retries_do_not_duplicate_messages_and_changed_payload_is_rejected(self):
        entry = self.send()
        self.assertEqual(self.send(), entry)
        response = self.alice.post_json("/api/notifications/send", self.payload(body="Autre message"))
        self.assertEqual((response.status, response.json()["error"]), (400, "notifications.request_conflict"))
        self.assertEqual(self.bob.get("/api/notifications").json()["unread"], 1)

    def test_unread_events_are_private_and_are_emitted_after_storage(self):
        alice = self.app.hub.subscribe(self.app.users.by_name("alice"))
        bob = self.app.hub.subscribe(self.app.users.by_name("bob"))
        self.addCleanup(self.app.hub.unsubscribe, alice)
        self.addCleanup(self.app.hub.unsubscribe, bob)
        for sub in (alice, bob):
            while not sub.events.empty():
                sub.events.get_nowait()
        entry = self.send()
        self.assertIn("event: notifications", bob.events.get_nowait())
        with self.assertRaises(queue.Empty):
            alice.events.get_nowait()
        self.assertEqual(self.bob.get("/api/notifications").json()["entries"], [entry])
        self.send()
        with self.assertRaises(queue.Empty):
            bob.events.get_nowait()
        self.bob.post_json("/api/notifications/read", dict(id=entry["id"]))
        self.assertIn("event: notifications", bob.events.get_nowait())

    def test_validation_does_not_write_messages(self):
        for changes in (dict(title=" "), dict(title="x" * (TITLE_MAX_LENGTH + 1)), dict(body=""),
                        dict(body="x" * (BODY_MAX_LENGTH + 1)), dict(body=None), dict(recipient="absent"),
                        dict(recipient=4), dict(requestId="bad")):
            with self.subTest(changes=changes):
                self.assertEqual(self.alice.post_json("/api/notifications/send", self.payload(**changes)).status, 400)
        for identity in (True, 0, -1, "1", 2**63):
            self.assertEqual(self.bob.post_json("/api/notifications/read", dict(id=identity)).status, 400)
        for cursor in ("bad", "0", "-1", str(2**63)):
            self.assertEqual(self.bob.get("/api/notifications?before=" + cursor).status, 400)
        self.assertEqual(self.bob.get("/api/notifications").json()["entries"], [])

    def test_pagination_does_not_lose_messages_when_new_ones_arrive(self):
        for i in range(PAGE_SIZE + 1):
            self.send(requestId=f"notification-test-{i:04d}")
        first = self.bob.get("/api/notifications").json()
        self.assertEqual(len(first["entries"]), PAGE_SIZE)
        self.send(requestId="notification-test-latest")
        second = self.bob.get("/api/notifications?before=" + str(first["before"])).json()
        self.assertEqual(len(second["entries"]), 1)
        self.assertIsNone(second["before"])
        self.assertFalse({e["id"] for e in first["entries"]} & {e["id"] for e in second["entries"]})


class NotificationMigrationTest(unittest.TestCase):
    def test_upgrade_from_21_keeps_existing_data(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "old.db")
            old = Database(path, MIGRATIONS[:21])
            old.execute("INSERT INTO users (username, subsonic_salt, subsonic_token, created_at, last_seen_at) VALUES ('kept', 's', 't', 1, 1)")
            old.execute("INSERT INTO upload_history (user_id,username,filename,byte_count,file_count,skipped_count,placed,waiting,uploaded_at) VALUES (1,'kept','old.mp3',12,1,0,'[]','[\"old.mp3\"]',1)")
            tables = [row["name"] for row in old.query("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
            before = {table: [tuple(row) for row in old.query('SELECT * FROM "' + table + '"')] for table in tables}
            old.close()
            new = Database(path, MIGRATIONS[:22])
            try:
                self.assertEqual(new.version, 22)
                self.assertEqual({table: [tuple(row) for row in new.query('SELECT * FROM "' + table + '"')] for table in tables}, before)
                self.assertEqual(new.query("SELECT * FROM notifications"), [])
                self.assertEqual(new.query("PRAGMA foreign_key_check"), [])
            finally:
                new.close()
