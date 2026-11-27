"""Migrations 24 à 26 : cibles partagées, un seul modèle de lecture et styles identifiés par leur nom, sans perte."""
import os
import tempfile
import unittest

from pimedia.storage.database import Database
from pimedia.webapp.schema import MIGRATIONS

ALICE, BOB = 1, 2
ALBUM = ("album", "subsonic", "library", "f1")


def fill_version_23(db):
    db.execute("INSERT INTO users (id, username, subsonic_salt, subsonic_token, created_at, last_seen_at) "
               "VALUES (1, 'alice', 's', 't', 0, 0), (2, 'bob', 's', 't', 0, 0)")
    # La même cible dans « À écouter » (ancien titre) et dans une recommandation plus récente (titre corrigé).
    db.execute("INSERT INTO listen_later (user_id, kind, source, library_key, source_id, title, artist, image_ref, "
               "created_at) VALUES (1, 'album', 'subsonic', 'library', 'f1', 'Ancien titre', 'Artiste', 'c1', 100)")
    recommendation = ("INSERT INTO recommendations (id, sender_id, recipient_id, kind, source, library_key, source_id, "
                      "title, artist, image_ref, created_at, unread_token, recipient_archived_at, "
                      "sender_last_read_comment_id, recipient_last_read_comment_id) VALUES "
                      "(?, ?, ?, ?, ?, ?, ?, ?, 'Artiste', 'c2', ?, ?, ?, ?, ?)")
    db.execute(recommendation, (1, ALICE, BOB) + ALBUM + ("Titre corrigé", 200, "a" * 32, None, 0, 2))  # non lue
    db.execute(recommendation, (2, BOB, ALICE, "artist", "discogs", "", "7", "Groupe", 300, None, None, 0, 0))  # lue
    db.execute(recommendation, (3, ALICE, BOB, "artist", "discogs", "", "8", "Autre", 400, None, 450, 0, 0))  # archivée
    db.execute(recommendation, (4, ALICE, BOB, "artist", "discogs", "", "8", "Autre", 500, "b" * 32, None, 0, 0))  # renvoyée
    comment = ("INSERT INTO recommendation_comments (id, recommendation_id, author_id, body, created_at, client_token) "
               "VALUES (?, 1, ?, ?, ?, ?)")
    db.execute(comment, (1, ALICE, "Écoute la face B", 210, "t1"))     # lu par Bob (curseur 2)
    db.execute(comment, (2, ALICE, "Et le dernier titre", 220, "t2"))  # lu par Bob
    db.execute(comment, (3, BOB, "Merci !", 230, "t3"))                # non lu par Alice (curseur 0)
    db.execute("INSERT INTO notifications (sender_id, recipient_id, title, body, client_token, created_at) "
               "VALUES (1, 2, 'Maintenance', 'Ce soir', 'n1', 600)")
    db.execute("INSERT INTO release_subscriptions (user_id, genre_id, name) VALUES "
               "(1, '0a9a6a1e-4e3b-4b8c-9f1a-1a2b3c4d5e6f', 'noise rock'), (1, 'genre:noise rock', 'noise rock'), "
               "(2, 'genre:shoegaze', 'shoegaze')")


class DataModelMigrationTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = os.path.join(directory.name, "webapp.db")
        old = Database(path, MIGRATIONS[:23])
        fill_version_23(old)
        old.close()
        self.db = Database(path, MIGRATIONS)
        self.addCleanup(self.db.close)

    def test_one_shared_target_with_the_latest_description(self):
        rows = self.db.query("SELECT title, image_ref FROM listening_targets WHERE kind = 'album' AND source_id = 'f1'")
        self.assertEqual([tuple(row) for row in rows], [("Titre corrigé", "c2")])
        bookmark = self.db.one("SELECT l.user_id, l.created_at, t.source_id FROM listen_later l "
                               "JOIN listening_targets t ON t.id = l.target_id")
        self.assertEqual(tuple(bookmark), (ALICE, 100, "f1"))

    def test_recommendation_read_and_archive_states_are_kept(self):
        rows = self.db.query("SELECT id, read_at, archived_at FROM recommendations ORDER BY id")
        self.assertEqual([tuple(row) for row in rows], [(1, None, None), (2, 300, None), (3, 400, 450), (4, None, None)])

    def test_unread_comments_are_the_same_for_each_account(self):
        unread = dict(self.db.query("SELECT recipient_id, COUNT(*) FROM recommendation_comments "
                                    "WHERE read_at IS NULL GROUP BY recipient_id"))
        self.assertEqual(unread, {ALICE: 1})
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM recommendation_comments")[0], 3)
        recipients = [row[0] for row in self.db.query("SELECT recipient_id FROM recommendation_comments ORDER BY id")]
        self.assertEqual(recipients, [BOB, BOB, ALICE])

    def test_one_subscription_per_style_identified_by_its_name(self):
        rows = self.db.query("SELECT user_id, genre FROM release_subscriptions ORDER BY user_id, genre")
        self.assertEqual([tuple(row) for row in rows], [(ALICE, "noise rock"), (BOB, "shoegaze")])

    def test_notifications_are_copied_and_length_limits_left_to_the_code(self):
        self.assertEqual(self.db.one("SELECT title, body FROM notifications")[0:2], ("Maintenance", "Ce soir"))
        self.db.execute("INSERT INTO notifications (recipient_id, title, body, client_token, created_at) "
                        "VALUES (2, ?, 'x', 'n2', 700)", ("t" * 500,))

    def test_links_are_consistent(self):
        self.assertEqual(self.db.query("PRAGMA foreign_key_check"), [])
        self.assertEqual(self.db.version, len(MIGRATIONS))


if __name__ == "__main__":
    unittest.main()
