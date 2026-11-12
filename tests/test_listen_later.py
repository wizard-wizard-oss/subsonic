"""Listening intentions: identity, persistence, ownership and recommendation lifecycle."""
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from pimedia.storage.database import Database
from pimedia.webapp.folders import FolderNotFound
from pimedia.webapp.listen_later_entities import ListeningTarget
from pimedia.webapp.schema import MIGRATIONS
from pimedia.webapp.recommendations import READ_BATCH_SIZE
from pimedia.webapp.storage.listen_later import ListenLaterRepository
from pimedia.webapp.storage.recommendations import RecommendationRepository
from pimedia.webapp.storage.users import UserRepository
from tests.fake_discogs import FakeDiscogs
from tests.webapp_support import WebAppTestCase


class ListenLaterStorageTest(unittest.TestCase):
    def test_migration_preserves_existing_data_and_bookmarks_survive_reopening(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "webapp.db")
            old = Database(path, MIGRATIONS[:16])
            user = UserRepository(old).save_login("listener", "salt", "token", frozenset())
            old.execute("INSERT INTO albums_discussed (album_id, title, last_message_at) VALUES (?, ?, ?)",
                        ("existing", "Kept", 123))
            old.connection().close()
            db = Database(path, MIGRATIONS)
            target = ListeningTarget("album", "discogs", "", "101", "Arrival", "ABBA")
            entry = ListenLaterRepository(db).add(user.id, target, 100)
            db.connection().close()
            reopened = Database(path, MIGRATIONS)
            self.assertEqual(reopened.version, len(MIGRATIONS))
            self.assertEqual(reopened.one("SELECT title FROM albums_discussed")[0], "Kept")
            self.assertEqual(ListenLaterRepository(reopened).all(user.id, "server")[0], entry)
            reopened.execute("DELETE FROM users WHERE id = ?", (user.id,))
            self.assertEqual(reopened.one("SELECT COUNT(*) FROM listen_later")[0], 0)
            reopened.connection().close()

    def test_concurrent_additions_keep_one_entry_and_original_date(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(os.path.join(directory, "webapp.db"), MIGRATIONS)
            user = UserRepository(db).save_login("listener", "salt", "token", frozenset())
            repository = ListenLaterRepository(db)
            target = ListeningTarget("artist", "discogs", "", "7", "ABBA")
            first = repository.add(user.id, target, 100)
            with ThreadPoolExecutor(max_workers=4) as executor:
                entries = list(executor.map(lambda _: repository.add(user.id, target, 200), range(12)))
            self.assertTrue(all(entry == first for entry in entries))
            self.assertEqual(repository.all(user.id, "server"), [first])
            db.connection().close()


class ListenLaterHttpTest(WebAppTestCase):
    environ = {"PI_MEDIA_WEB_DISCOGS_API_KEY": "test-key"}

    def setUp(self):
        super().setUp()
        self.app.discogs.http = FakeDiscogs()
        self.app.discogs.sleep = lambda seconds: None
        self.alice = self.client("alice", "secret")
        self.bob = self.client("bob", "pw2")

    def add(self, client=None, kind="album", source="subsonic", source_id="al1", **extra):
        return (client or self.alice).post_json("/api/listen-later/add",
            dict(kind=kind, source=source, sourceId=source_id, **extra))

    def send(self, client=None, recipient="bob", kind="album", source="subsonic", source_id="al1"):
        return (client or self.alice).post_json("/api/recommendation/send",
            dict(recipient=recipient, kind=kind, source=source, sourceId=source_id))

    def page(self, client=None):
        return (client or self.alice).get("/api/listen-later").json()

    def test_folder_and_id3_references_are_the_same_bookmark(self):
        self.app.listen_later.clock = lambda: 100
        first = self.add().json()["bookmark"]
        self.app.listen_later.clock = lambda: 200
        second = self.add(source_id="fdir-al1").json()["bookmark"]
        self.assertEqual(first, second)
        self.assertEqual(first["target"]["sourceId"], "fdir-al1")
        self.assertEqual(first["createdAt"], 100)
        self.assertEqual(len(self.page()["bookmarks"]), 1)
        self.assertEqual(self.subsonic.starred_albums, set())

    def test_artist_id3_and_folder_references_are_the_same(self):
        first = self.add(kind="artist", source_id="ar1").json()["bookmark"]
        second = self.add(kind="artist", source_id="fdir-ar1").json()["bookmark"]
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(first["target"]["sourceId"], "fdir-ar1")

    def test_source_and_kind_are_part_of_identity(self):
        self.add(source="discogs", source_id="101")
        self.add(kind="artist", source="discogs", source_id="101")
        self.add()
        self.assertEqual(len(self.page()["bookmarks"]), 3)
        self.assertEqual(self.page(self.bob), dict(bookmarks=[], recommendations=[], readBatchSize=READ_BATCH_SIZE))

    def test_description_is_resolved_on_server_and_snapshot_needs_no_source(self):
        entry = self.add(title="forged", imageRef="https://untrusted.invalid/").json()["bookmark"]
        self.assertEqual(entry["target"]["title"], "Arrival")
        with patch.object(self.app.folders, "album", side_effect=OSError("offline")):
            self.assertEqual(self.page()["bookmarks"], [entry])
            response = self.alice.post_json("/api/listen-later/remove", {"id": entry["id"]})
        self.assertTrue(response.json()["removed"])

    def test_delete_is_scoped_to_owner_and_does_not_remove_favorites(self):
        entry = self.add().json()["bookmark"]
        self.assertFalse(self.bob.post_json("/api/listen-later/remove", {"id": entry["id"]}).json()["removed"])
        self.alice.post_json("/api/favorite", dict(kind="album", id="al1", on=True))
        self.alice.post_json("/api/listen-later/remove", {"id": entry["id"]})
        self.assertEqual(self.subsonic.starred_albums, {"al1"})
        self.assertEqual(self.page()["bookmarks"], [])

    def test_discogs_artist_and_release_can_be_saved_without_library_match(self):
        artist = self.add(kind="artist", source="discogs", source_id="7").json()["bookmark"]
        album = self.add(source="discogs", source_id="104").json()["bookmark"]
        self.assertEqual(artist["target"]["title"], "ABBA")
        self.assertEqual(album["target"]["title"], "Rare")
        self.assertEqual(album["target"]["artist"], "Artiste discret")

    def test_recommendations_are_independent_and_group_multiple_senders(self):
        first = self.send(source="discogs", source_id="104")
        self.assertEqual(first.status, 200)
        for name in ("charlie", "dana", "eric"):
            self.subsonic.users[name] = "pw3"
            sender = self.client(name, "pw3")
            self.assertEqual(self.send(client=sender, source="discogs", source_id="104").status, 200)
        data = self.page(self.bob)
        self.assertEqual(data["bookmarks"], [])
        self.assertEqual(len(data["recommendations"]), 1)
        group = data["recommendations"][0]
        self.assertEqual({s["username"] for s in group["senders"]}, {"alice", "charlie", "dana", "eric"})
        self.assertEqual(len(group["senders"]), 4)
        self.assertEqual(self.page()["recommendations"], [])

    def test_repeated_recommendation_is_idempotent(self):
        self.app.recommendations.clock = lambda: 100
        first = self.send().json()["recommendation"]
        self.app.recommendations.clock = lambda: 200
        second = self.send(source_id="fdir-al1").json()["recommendation"]
        self.assertEqual(first, second)

    def test_bookmark_and_recommendation_can_coexist_and_be_removed_independently(self):
        entry = self.add(client=self.bob).json()["bookmark"]
        self.send()
        group = self.page(self.bob)["recommendations"][0]
        reference = {k: group["target"][k] for k in ("kind", "source", "sourceId")}
        self.assertEqual(self.alice.post_json("/api/recommendation/remove", reference).json()["removed"], 0)
        self.bob.post_json("/api/listen-later/remove", {"id": entry["id"]})
        self.assertEqual(len(self.page(self.bob)["recommendations"]), 1)
        self.add(client=self.bob)
        self.assertEqual(self.bob.post_json("/api/recommendation/remove", reference).json()["removed"], 1)
        self.assertEqual(len(self.page(self.bob)["bookmarks"]), 1)
        self.assertEqual(self.page(self.bob)["recommendations"], [])

    def test_dismissal_works_after_source_disappears(self):
        self.send()
        group = self.page(self.bob)["recommendations"][0]
        with patch.object(self.app.folders, "album", side_effect=FolderNotFound("gone")):
            response = self.bob.post_json("/api/recommendation/remove", group["target"])
        self.assertEqual(response.json()["removed"], 1)

    def test_subsonic_recommendation_checks_recipient_access(self):
        resolve = self.app.folders.album
        def accessible(user, identity):
            if user.username == "bob":
                raise FolderNotFound(identity)
            return resolve(user, identity)
        with patch.object(self.app.folders, "album", side_effect=accessible):
            self.assertEqual(self.send().status, 404)
        self.assertEqual(self.page(self.bob)["recommendations"], [])

    def test_reference_from_another_library_is_not_opened_in_current_library(self):
        owner = self.app.users.by_name("alice")
        target = ListeningTarget("album", "subsonic", "another-server", "fdir-al1", "Old")
        self.app.listen_later.repository.add(owner.id, target, 1)
        self.assertEqual(self.page()["bookmarks"], [])
        self.assertEqual(self.app.db.one("SELECT COUNT(*) FROM listen_later")[0], 1)

    def test_inputs_and_recipient_are_validated(self):
        for extra in (dict(kind="song"), dict(source="youtube"), dict(source_id=""),
                      dict(source_id=True), dict(source="discogs", source_id="m123")):
            with self.subTest(extra=extra):
                self.assertEqual(self.add(**extra).status, 400)
        for identity in (None, True, 0, -1, "1", [], 2**80):
            self.assertEqual(self.alice.post_json("/api/listen-later/remove", {"id": identity}).status, 400)
        self.assertEqual(self.send(recipient="missing").json()["error"], "listen_later.recipient_unknown")
        self.assertEqual(self.send(recipient="alice").json()["error"], "listen_later.self_recommendation")

    def test_all_routes_require_session_and_writes_require_csrf(self):
        anonymous = self.client()
        self.assertEqual(anonymous.get("/api/listen-later").status, 401)
        operations = (
            ("/api/listen-later/add", dict(kind="album", source="subsonic", sourceId="al1")),
            ("/api/listen-later/remove", dict(id=1)),
            ("/api/recommendation/send", dict(recipient="bob", kind="artist", source="discogs", sourceId="7")),
            ("/api/recommendation/remove", dict(kind="album", source="discogs", sourceId="101")),
        )
        for path, body in operations:
            self.assertEqual(anonymous.post_json(path, body).status, 401)
            self.assertEqual(self.alice.post_json(path, body, csrf=False).status, 403)

    def unread(self, client=None):
        return (client or self.bob).get("/api/recommendation/status").json()["unread"]

    def tokens(self, client=None):
        return [token for group in self.page(client or self.bob)["recommendations"] for token in group["unreadTokens"]]

    def read(self, tokens, client=None):
        return (client or self.bob).post_json("/api/recommendation/read", {"tokens": tokens})

    def test_reading_list_does_not_acknowledge_and_read_state_survives_new_connections(self):
        self.assertFalse(self.unread())
        self.send()
        tokens = self.tokens()
        self.assertTrue(self.unread())
        self.assertEqual(len(tokens), 1)
        self.assertFalse(self.read(tokens).json()["unread"])
        db = Database(self.app.db.path, MIGRATIONS)
        owner = self.app.users.by_name("bob")
        self.assertFalse(RecommendationRepository(db).has_unread(owner.id, self.app.recommendations.targets.library_key))
        self.assertEqual(self.tokens(), [])
        db.close()

    def test_identical_advice_stays_read_but_another_sender_is_unread(self):
        self.send(source="discogs", source_id="104")
        self.read(self.tokens())
        self.send(source="discogs", source_id="104")
        self.assertFalse(self.unread())
        self.subsonic.users["charlie"] = "pw3"
        charlie = self.client("charlie", "pw3")
        self.send(client=charlie, source="discogs", source_id="104")
        group = self.page(self.bob)["recommendations"][0]
        self.assertEqual(len(group["senders"]), 2)
        self.assertEqual(len(group["unreadTokens"]), 1)
        self.assertTrue(self.unread())

    def test_only_displayed_deliveries_are_marked_read(self):
        self.send(source="discogs", source_id="104")
        displayed = self.tokens()
        self.send(source="discogs", source_id="101")
        self.assertTrue(self.read(displayed).json()["unread"])
        self.assertEqual(len(self.tokens()), 1)
        self.assertFalse(self.read(self.tokens()).json()["unread"])

    def test_stale_acknowledgment_cannot_read_recreated_advice_even_if_id_is_reused(self):
        original = self.send().json()["recommendation"]
        tokens = self.tokens()
        target = self.page(self.bob)["recommendations"][0]["target"]
        self.bob.post_json("/api/recommendation/remove", target)
        recreated = self.send().json()["recommendation"]
        self.assertEqual(original["id"], recreated["id"])
        self.assertNotEqual(tokens, self.tokens())
        self.assertTrue(self.read(tokens).json()["unread"])

    def test_acknowledgments_are_scoped_to_the_recipient_and_library(self):
        self.send()
        self.send(client=self.bob, recipient="alice", source="discogs", source_id="104")
        alice_tokens = self.tokens(self.alice)
        self.read(alice_tokens)
        self.assertTrue(self.unread(self.alice))
        self.assertTrue(self.unread(self.bob))
        owner = self.app.users.by_name("bob")
        reference = ListeningTarget("album", "subsonic", "old-server", "fdir-al1", "Old")
        old = self.app.recommendations.repository.add(self.app.users.by_name("alice").id, owner.id, reference, 100)
        self.read([old.unread_token])
        rows = self.app.db.query("SELECT unread_token FROM recommendations WHERE library_key = 'old-server'")
        self.assertEqual(rows[0]["unread_token"], old.unread_token)

    def test_unread_events_only_reach_recipient_tabs_and_reading_updates_them(self):
        alice = self.app.hub.subscribe(self.app.users.by_name("alice"))
        bob = self.app.hub.subscribe(self.app.users.by_name("bob"))
        bob_tab = self.app.hub.subscribe(self.app.users.by_name("bob"))
        for subscriber in (alice, bob, bob_tab):
            while not subscriber.events.empty():
                subscriber.events.get_nowait()
        self.send()
        self.assertTrue(alice.events.empty())
        for subscriber in (bob, bob_tab):
            self.assertIn("event: recommendations", subscriber.events.get_nowait())
        self.read(self.tokens())
        self.assertTrue(alice.events.empty())
        for subscriber in (bob, bob_tab):
            self.assertIn("event: recommendations", subscriber.events.get_nowait())
        self.read(["0" * 32])
        self.assertTrue(bob.events.empty())

    def test_unread_routes_require_authentication_csrf_and_valid_batches(self):
        self.assertEqual(self.client().get("/api/recommendation/status").status, 401)
        self.assertEqual(self.client().post_json("/api/recommendation/read", {"tokens": ["0" * 32]}).status, 401)
        self.assertEqual(self.bob.post_json("/api/recommendation/read", {"tokens": ["0" * 32]}, csrf=False).status, 403)
        for tokens in (None, [], True, "0" * 32, [None], ["A" * 32], ["0" * 31], ["0" * 32] * (READ_BATCH_SIZE + 1)):
            with self.subTest(tokens=tokens):
                self.assertEqual(self.read(tokens).status, 400)
        self.send()
        target = self.page(self.bob)["recommendations"][0]["target"]
        self.bob.post_json("/api/recommendation/remove", target)
        self.assertFalse(self.unread())


class RecommendationUnreadMigrationTest(unittest.TestCase):
    def test_existing_recommendations_become_unread_without_losing_bookmarks(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "migration.db")
            old = Database(path, MIGRATIONS[:17])
            users = UserRepository(old)
            sender = users.save_login("sender", "salt", "token", frozenset())
            recipient = users.save_login("recipient", "salt", "token", frozenset())
            old.execute("INSERT INTO recommendations (sender_id, recipient_id, kind, source, source_id, title, created_at) "
                        "VALUES (?, ?, 'album', 'discogs', '101', 'Arrival', 100)", (sender.id, recipient.id))
            bookmark = ListenLaterRepository(old).add(recipient.id, ListeningTarget("artist", "discogs", "", "7", "ABBA"), 100)
            old.close()
            migrated = Database(path, MIGRATIONS)
            repository = RecommendationRepository(migrated)
            self.assertTrue(repository.has_unread(recipient.id, "server"))
            advice = repository.received(recipient.id, "server")[0]
            self.assertRegex(advice.unread_token, r"^[0-9a-f]{32}$")
            self.assertEqual(ListenLaterRepository(migrated).all(recipient.id, "server"), [bookmark])
            migrated.close()
