"""Private recommendation comments: migration, ownership, retries and read boundaries."""
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from pimedia.storage.database import Database
from pimedia.webapp.listen_later.entities import ListeningTarget
from pimedia.webapp.recommendations.entities import COMMENT_MAX_LENGTH, DISCUSSION_PAGE_SIZE, RecommendationComment
from pimedia.webapp.schema import MIGRATIONS
from pimedia.webapp.storage.recommendation_comments import RecommendationCommentRepository
from pimedia.webapp.storage.recommendations import RecommendationRepository
from pimedia.webapp.storage.users import UserRepository
from tests.webapp_support import WebAppTestCase


class RecommendationCommentStorageTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = os.path.join(directory.name, "webapp.db")
        self.db = Database(self.path, MIGRATIONS)
        self.addCleanup(self.db.close)
        users = UserRepository(self.db)
        self.alice = users.save_login("alice", "salt", "token", ())
        self.bob = users.save_login("bob", "salt", "token", ())
        self.repository = RecommendationRepository(self.db)
        self.comments = RecommendationCommentRepository(self.db)
        self.target = ListeningTarget("album", "discogs", "", "101", "Album")

    def test_initial_comment_rolls_back_with_failed_delivery(self):
        with patch("pimedia.webapp.storage.recommendations.insert_comment", side_effect=RuntimeError("write failed")):
            with self.assertRaises(RuntimeError):
                self.repository.add(self.alice.id, self.bob.id, self.target, 100, "Pourquoi")
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM recommendations")[0], 0)
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM recommendation_comments")[0], 0)

    def test_concurrent_initial_delivery_and_comment_retries_do_not_duplicate(self):
        def deliver(_):
            try:
                return self.repository.add(self.alice.id, self.bob.id, self.target, 100, "Pourquoi")
            finally:
                self.db.close()
        with ThreadPoolExecutor(max_workers=4) as executor:
            deliveries = list(executor.map(deliver, range(12)))
        self.assertEqual(sum(delivery.created for delivery in deliveries), 1)
        identity = deliveries[0].recommendation.id
        self.assertTrue(all(delivery.recommendation.id == identity for delivery in deliveries))
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM recommendation_comments")[0], 1)

        def reply(_):
            try:
                return self.comments.add(identity, self.bob.id, "Super", 200, "a" * 32)
            finally:
                self.db.close()
        with ThreadPoolExecutor(max_workers=4) as executor:
            replies = list(executor.map(reply, range(12)))
        self.assertIsInstance(replies[0], RecommendationComment)
        self.assertTrue(all(comment == replies[0] for comment in replies))
        self.db.close()
        reopened = Database(self.path, MIGRATIONS)
        self.addCleanup(reopened.close)
        self.assertEqual(reopened.one("SELECT COUNT(*) FROM recommendation_comments")[0], 2)
        reopened.execute("DELETE FROM users WHERE id = ?", (self.bob.id,))
        self.assertEqual(reopened.one("SELECT COUNT(*) FROM recommendation_comments")[0], 0)
        self.assertEqual(reopened.query("PRAGMA foreign_key_check"), [])

    def test_sent_and_archived_pages_keep_all_threads_without_overlap(self):
        for index in range(DISCUSSION_PAGE_SIZE + 2):
            target = ListeningTarget("album", "discogs", "", str(index + 1), "Album")
            self.repository.add(self.alice.id, self.bob.id, target, 100)
            self.repository.archive(self.bob.id, target.key, 200)
        for scope, user in (("sent", self.alice), ("archived", self.bob)):
            first = self.repository.page(user.id, "library", scope, None, DISCUSSION_PAGE_SIZE)
            self.assertTrue(first.has_more)
            second = self.repository.page(user.id, "library", scope, first.recommendations[-1].id, DISCUSSION_PAGE_SIZE)
            self.assertFalse(second.has_more)
            self.assertEqual(len(first.recommendations), DISCUSSION_PAGE_SIZE)
            self.assertEqual(len(second.recommendations), 2)
            identities = [item.id for item in first.recommendations + second.recommendations]
            self.assertEqual(len(set(identities)), DISCUSSION_PAGE_SIZE + 2)
            self.assertEqual(identities, sorted(identities, reverse=True))

    def test_migration_20_preserves_existing_values_and_initializes_cursors(self):
        self.db.close()
        os.remove(self.path)
        old = Database(self.path, MIGRATIONS[:20])
        users = UserRepository(old)
        alice = users.save_login("alice", "salt", "token", ())
        bob = users.save_login("bob", "salt", "token", ())
        for kind, source_id, token in (("album", "al1", "a" * 32), ("song", "s1", None)):
            old.execute("INSERT INTO recommendations (sender_id, recipient_id, kind, source, library_key, source_id, "
                        "title, created_at, unread_token) VALUES (?, ?, ?, 'subsonic', 'library', ?, 'Titre', 100, ?)",
                        (alice.id, bob.id, kind, source_id, token))
        before = [dict(row) for row in old.query("SELECT * FROM recommendations ORDER BY id")]
        old.close()
        migrated = Database(self.path, MIGRATIONS[:23])   # la migration 21 dans le schéma de sa version
        self.addCleanup(migrated.close)
        for previous, row in zip(before, migrated.query("SELECT * FROM recommendations ORDER BY id")):
            self.assertEqual({key: row[key] for key in previous}, previous)
            self.assertEqual(row["sender_last_read_comment_id"], 0)
            self.assertEqual(row["recipient_last_read_comment_id"], 0)
            self.assertIsNone(row["recipient_archived_at"])
        self.assertEqual(migrated.one("PRAGMA integrity_check")[0], "ok")
        self.assertEqual(migrated.query("PRAGMA foreign_key_check"), [])
        self.assertEqual(migrated.one("SELECT COUNT(*) FROM recommendation_comments")[0], 0)


class RecommendationCommentHttpTest(WebAppTestCase):
    def setUp(self):
        super().setUp()
        self.subsonic.users["charlie"] = "pw3"
        self.alice = self.client("alice", "secret")
        self.bob = self.client("bob", "pw2")
        self.charlie = self.client("charlie", "pw3")

    def send(self, comment="Pour la basse", client=None, source_id="al1"):
        return (client or self.alice).post_json("/api/recommendation/send", dict(
            recipient="bob", kind="album", source="subsonic", sourceId=source_id, comment=comment))

    def discussion(self, identity, client=None, extra=""):
        return (client or self.bob).get("/api/recommendation/comments?id=%s%s" % (identity, extra))

    def post(self, identity, body, client=None, **extra):
        return (client or self.bob).post_json("/api/recommendation/comment",
                                            dict(recommendationId=identity, body=body, **extra))

    def read(self, identity, comment_id, client=None):
        return (client or self.bob).post_json("/api/recommendation/comments/read",
                                            dict(recommendationId=identity, commentId=comment_id))

    def status(self, client=None):
        return (client or self.bob).get("/api/recommendation/status").json()

    def page(self, client=None):
        return (client or self.bob).get("/api/listen-later").json()

    def mark_delivery(self):
        ids = [identity for group in self.page()["recommendations"] for identity in group["unreadIds"]]
        if ids:
            self.bob.post_json("/api/recommendation/read", {"ids": ids})

    def test_initial_comment_and_both_participants_share_one_chronological_entity(self):
        sent = self.send("  Pour la basse\nEt les cuivres.  ").json()
        identity = sent["recommendation"]["id"]
        self.assertTrue(sent["created"])
        self.assertFalse(self.send("Un doublon").json()["created"])
        second = self.post(identity, "Trop bien !").json()["comment"]
        third = self.post(identity, "Essaie aussi le précédent.", self.alice).json()["comment"]
        discussion = self.discussion(identity).json()
        self.assertEqual([comment["body"] for comment in discussion["comments"]],
                         ["Pour la basse\nEt les cuivres.", "Trop bien !", "Essaie aussi le précédent."])
        self.assertEqual([comment["author"] for comment in discussion["comments"]], ["alice", "bob", "alice"])
        self.assertLess(second["id"], third["id"])
        self.assertTrue(all(comment["recommendationId"] == identity for comment in discussion["comments"]))
        sent_page = self.alice.get("/api/recommendation/discussions?scope=sent").json()
        self.assertEqual(sent_page["recommendations"][0]["id"], identity)
        self.assertEqual(sent_page["recommendations"][0]["recipient"], "bob")
        self.assertEqual(self.charlie.get("/api/recommendation/discussions?scope=sent").json()["recommendations"], [])

    def test_comment_is_optional_but_written_comments_must_be_nonempty_and_bounded(self):
        for invalid in (None, 3, [], {}, "x" * (COMMENT_MAX_LENGTH + 1)):
            with self.subTest(invalid=type(invalid)):
                self.assertEqual(self.send(invalid).status, 400)
        self.assertEqual(self.page()["recommendations"], [])
        identity = self.send(" \n ").json()["recommendation"]["id"]
        self.assertEqual(self.discussion(identity).json()["comments"], [])
        for invalid in (None, 3, [], {}, " \n ", "x" * (COMMENT_MAX_LENGTH + 1)):
            self.assertEqual(self.post(identity, invalid).status, 400)
        self.assertEqual(self.post(identity, "é" * COMMENT_MAX_LENGTH).status, 200)
        self.assertEqual(self.discussion(identity).json()["maxLength"], COMMENT_MAX_LENGTH)

    def test_private_threads_do_not_leak_to_a_third_user_or_another_adviser(self):
        identity = self.send().json()["recommendation"]["id"]
        other = self.send("Pour les paroles", self.charlie).json()["recommendation"]["id"]
        self.assertEqual(len(self.page()["recommendations"]), 1)
        entries = self.page()["recommendations"][0]["recommendations"]
        self.assertEqual({entry["id"] for entry in entries}, {identity, other})
        self.assertEqual(self.discussion(identity, self.charlie).status, 404)
        self.assertEqual(self.post(identity, "Intrusion", self.charlie).status, 404)
        self.assertEqual(self.read(identity, 1, self.charlie).status, 404)
        self.assertEqual(self.discussion(other, self.alice).status, 404)
        self.assertEqual(self.discussion(identity, self.alice).status, 200)

    def test_all_new_routes_require_session_and_writes_require_csrf(self):
        identity = self.send().json()["recommendation"]["id"]
        anonymous = self.client()
        for url in ("/api/recommendation/comments?id=%s" % identity, "/api/recommendation/discussions"):
            self.assertEqual(anonymous.get(url).status, 401)
        for url, body in (("/api/recommendation/comment", dict(recommendationId=identity, body="Réponse")),
                          ("/api/recommendation/comments/read", dict(recommendationId=identity, commentId=1))):
            self.assertEqual(anonymous.post_json(url, body).status, 401)
            self.assertEqual(self.bob.post_json(url, body, csrf=False).status, 403)

    def test_ownership_comes_from_session_and_invalid_ids_are_rejected(self):
        identity = self.send().json()["recommendation"]["id"]
        comment = self.post(identity, "Moi", authorId=9999).json()["comment"]
        self.assertEqual(comment["author"], "bob")
        for invalid in (None, True, "1", 0, -1, [], 2 ** 80):
            self.assertEqual(self.post(invalid, "Réponse").status, 400)
            self.assertEqual(self.read(identity, invalid).status, 400)
        self.assertEqual(self.discussion(identity, extra="&before=1&after=2").status, 400)
        self.assertEqual(self.discussion(identity, extra="&before=bad").status, 400)
        self.assertEqual(self.discussion(identity, extra="&after=bad").status, 400)
        self.assertEqual(self.bob.get("/api/recommendation/discussions?before=bad").status, 400)
        self.assertEqual(self.bob.get("/api/recommendation/discussions?scope=all").status, 400)

    def test_comment_retry_is_idempotent_and_reused_token_cannot_overwrite_text(self):
        identity = self.send().json()["recommendation"]["id"]
        first = self.post(identity, "Trop bien", requestId="a" * 32).json()["comment"]
        self.assertEqual(self.post(identity, "Trop bien", requestId="a" * 32).json()["comment"], first)
        self.assertEqual(self.post(identity, "Autre texte", requestId="a" * 32).status, 409)
        self.assertEqual(len(self.discussion(identity).json()["comments"]), 2)
        self.assertEqual(self.post(identity, "Réponse", requestId="bad").status, 400)

    def test_reading_history_does_not_acknowledge_and_old_ack_cannot_read_a_new_comment(self):
        identity = self.send().json()["recommendation"]["id"]
        self.mark_delivery()
        first = self.discussion(identity).json()["comments"][0]
        self.assertTrue(self.status()["unread"])
        self.assertEqual(self.status()["unreadDiscussion"]["id"], identity)
        second = self.post(identity, "Un autre détail", self.alice).json()["comment"]
        self.assertTrue(self.read(identity, first["id"]).json()["unread"])
        self.assertFalse(self.read(identity, second["id"]).json()["unread"])
        self.assertFalse(self.status()["unread"])
        self.assertFalse(self.status(self.alice)["unread"])

    def test_own_comment_does_not_hide_unread_incoming_and_foreign_ack_is_ignored(self):
        identity = self.send().json()["recommendation"]["id"]
        other = self.send(source_id="al2").json()["recommendation"]["id"]
        foreign = self.discussion(other).json()["comments"][0]
        self.mark_delivery()
        self.post(identity, "Merci")
        self.read(identity, foreign["id"])
        self.read(identity, 2 ** 62)
        self.assertTrue(self.status()["unread"])
        bob = self.app.users.by_name("bob").id
        self.assertEqual(self.app.db.one("SELECT COUNT(*) FROM recommendation_comments "
                                         "WHERE recipient_id = ? AND read_at IS NOT NULL", (bob,))[0], 0)

    def test_comment_is_unread_for_the_other_participant_only(self):
        identity = self.send().json()["recommendation"]["id"]
        self.mark_delivery()
        self.assertFalse(self.status(self.alice)["unread"])
        thread = self.discussion(identity).json()
        self.assertTrue(thread["recommendation"]["commentsUnread"])
        self.read(identity, thread["comments"][0]["id"])
        reply = self.post(identity, "Merci !").json()["comment"]
        self.assertFalse(self.status()["unread"])
        self.assertEqual(self.status(self.alice)["unreadDiscussion"]["id"], identity)
        self.assertFalse(self.read(identity, reply["id"], self.alice).json()["unread"])
        self.assertFalse(self.status(self.alice)["unread"])

    def test_archiving_keeps_the_thread_and_new_delivery_gets_a_separate_identity(self):
        identity = self.send().json()["recommendation"]["id"]
        target = self.page()["recommendations"][0]["target"]
        self.assertEqual(self.bob.post_json("/api/recommendation/remove", target).json()["removed"], 1)
        self.assertEqual(self.page()["recommendations"], [])
        archived = self.bob.get("/api/recommendation/discussions?scope=archived").json()["recommendations"]
        self.assertEqual(archived[0]["id"], identity)
        self.assertIsNotNone(archived[0]["archivedAt"])
        self.assertEqual(self.post(identity, "Je l’ai finalement écouté").status, 200)
        self.assertTrue(self.status(self.alice)["unread"])
        newer = self.send("Autre occasion").json()["recommendation"]["id"]
        self.assertNotEqual(identity, newer)
        self.assertEqual(len(self.discussion(identity).json()["comments"]), 2)
        self.assertEqual(len(self.discussion(newer).json()["comments"]), 1)
        self.assertEqual(len(self.page()["recommendations"]), 1)
        self.assertEqual(self.app.db.query("PRAGMA foreign_key_check"), [])

    def test_comment_pages_are_bounded_and_before_after_cursors_do_not_skip(self):
        identity = self.send("").json()["recommendation"]["id"]
        bob_id = self.app.users.by_name("bob").id
        for index in range(DISCUSSION_PAGE_SIZE * 2 + 3):
            self.app.recommendations.comments.add(identity, bob_id, str(index), 100, str(index))
        latest = self.discussion(identity).json()
        self.assertEqual(len(latest["comments"]), DISCUSSION_PAGE_SIZE)
        self.assertTrue(latest["hasMore"])
        previous = self.discussion(identity, extra="&before=" + str(latest["comments"][0]["id"])).json()
        first = self.discussion(identity, extra="&before=" + str(previous["comments"][0]["id"])).json()
        self.assertFalse(first["hasMore"])
        all_comments = first["comments"] + previous["comments"] + latest["comments"]
        self.assertEqual([comment["body"] for comment in all_comments], [str(i) for i in range(DISCUSSION_PAGE_SIZE * 2 + 3)])
        after = self.discussion(identity, extra="&after=" + str(all_comments[0]["id"])).json()
        self.assertEqual([comment["body"] for comment in after["comments"]], [str(i) for i in range(1, DISCUSSION_PAGE_SIZE + 1)])
        self.assertTrue(after["hasMore"])

    def test_comments_survive_unavailable_source_and_other_libraries_stay_private(self):
        identity = self.send().json()["recommendation"]["id"]
        with patch.object(self.app.recommendations.targets, "resolve", side_effect=AssertionError("no catalog lookup")):
            self.assertEqual(self.post(identity, "Même sans la source").status, 200)
            self.assertEqual(self.discussion(identity).status, 200)
        self.app.db.execute("UPDATE listening_targets SET library_key = 'old-server' WHERE id = "
                            "(SELECT target_id FROM recommendations WHERE id = ?)", (identity,))
        self.assertEqual(self.discussion(identity).status, 404)
        self.assertEqual(self.post(identity, "Ancienne bibliothèque").status, 404)
        self.assertFalse(self.status()["unread"])
        self.assertEqual(self.alice.get("/api/recommendation/discussions?scope=sent").json()["recommendations"], [])

    def test_comment_events_are_targeted_to_the_two_participants_and_reads_to_reader(self):
        identity = self.send("").json()["recommendation"]["id"]
        subscribers = {name: self.app.hub.subscribe(self.app.users.by_name(name)) for name in ("alice", "bob", "charlie")}
        for subscriber in subscribers.values():
            while not subscriber.events.empty():
                subscriber.events.get_nowait()
        comment = self.post(identity, "Privé").json()["comment"]
        for name in ("alice", "bob"):
            event = subscribers[name].events.get_nowait()
            self.assertIn("event: recommendations", event)
            self.assertNotIn("Privé", event)
        self.assertTrue(subscribers["charlie"].events.empty())
        self.read(identity, comment["id"], self.alice)
        self.assertFalse(subscribers["alice"].events.empty())
        self.assertTrue(subscribers["bob"].events.empty())
        self.assertTrue(subscribers["charlie"].events.empty())
