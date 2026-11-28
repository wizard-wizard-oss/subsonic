"""Accueil personnel : priorité des sources, isolation et historique conservé sans purge."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from pimedia.storage.database import Database
from pimedia.webapp.schema import MIGRATIONS
from pimedia.webapp.personal_home.entities import Album, Seed
from pimedia.webapp.personal_home.service import PersonalHome
from pimedia.webapp.personal_home.history import ListeningHistory
from pimedia.webapp.storage.listening_history import ListeningHistoryRepository
from pimedia.webapp.listen_later.entities import ListeningTarget
from tests.test_database_migrations import fill


class PersonalHomeTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.db = Database(Path(directory.name) / "site.db", MIGRATIONS)
        self.addCleanup(self.db.close)
        for name in ("alice", "bob"):
            self.db.execute("INSERT INTO users(username, subsonic_salt, subsonic_token, created_at, last_seen_at) "
                            "VALUES (?, '', '', 0, 0)", (name,))
        self.alice, self.bob = SimpleNamespace(id=1), SimpleNamespace(id=2)
        self.repository = ListeningHistoryRepository(self.db)
        self.songs = {"s1": Seed("s1", "First", "ar1", "Artist", "a1", "Album", "Rock", "c1"),
                      "s2": Seed("s2", "Second", "ar2", "Other", "a2", "Other album", "Jazz", "c2")}
        targets = SimpleNamespace(library_key="library", resolve=lambda user, kind, source, identity:
                                  ListeningTarget(kind, source, "library", identity, "Song", "Artist"))
        self.history = ListeningHistory(self.repository, targets, clock=lambda: 100)
        self.queue_seed = self.songs["s2"]
        self.favorite_seeds = (self.songs["s1"],)
        self.calls = []
        self.catalog = SimpleNamespace(song=lambda user, identity: self.songs.get(identity),
            current=self.current, favorites=self.favorites, suggestions=self.suggestions,
            album=lambda user, identity: Album(identity, identity, "Artist", "ar1", "cover"))
        self.home = PersonalHome(self.history, self.catalog)

    def current(self, user):
        self.calls.append("queue")
        return self.queue_seed

    def favorites(self, user):
        self.calls.append("favorites")
        return self.favorite_seeds

    def suggestions(self, user, seed):
        self.calls.append(seed.genre)
        return (Album("new", "Suggested", "Band", "ar3", "cover"),)

    def record(self, user=None, identity="s1", token="a"):
        return self.history.record(user or self.alice, identity, token * 32)

    def test_history_precedes_the_queue_and_is_private(self):
        self.record()
        result = self.home.page(self.alice)
        self.assertEqual(result.basis, "history")
        self.assertEqual(result.seed.artist, "Artist")
        self.assertNotIn("favorites", self.calls)
        self.assertEqual(self.home.page(self.bob).basis, "queue")

    def test_queue_then_favorites_then_newest_without_inventing_plays(self):
        self.assertEqual(self.home.page(self.alice).basis, "queue")
        self.queue_seed = None
        self.assertEqual(self.home.page(self.alice).basis, "favorites")
        self.favorite_seeds = ()
        result = self.home.page(self.alice)
        self.assertEqual((result.basis, result.seed, result.suggestions), ("newest", None, ()))
        self.assertEqual(self.history.page(self.alice).entries, ())

    def test_deleted_history_reference_does_not_block_fallback(self):
        self.record()
        self.songs.pop("s1")
        self.assertEqual(self.home.page(self.alice).basis, "queue")

    def test_one_event_per_request_but_repeat_listens_are_kept(self):
        self.record()
        self.record()
        self.record(token="b")
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM listening_history")[0], 2)
        self.record(self.bob)
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM listening_history")[0], 3)
        self.assertEqual(len(self.history.page(self.alice).entries), 1)

    def test_conflicting_request_is_rejected_without_overwriting_history(self):
        self.record()
        with self.assertRaises(ValueError):
            self.record(identity="s2")
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM listening_history")[0], 1)

    def test_request_cannot_be_reused_in_a_different_library(self):
        self.record()
        target = ListeningTarget("song", "subsonic", "another-library", "s1", "Another song")
        with self.assertRaises(ValueError):
            self.repository.add(self.alice.id, target, "a" * 32, 200)

    def test_history_paginates_and_keeps_old_events(self):
        self.record()
        self.db.execute("UPDATE listening_history SET played_at = 1")
        for index in range(1, 18):
            self.history.record(self.alice, "song%d" % index, "%032x" % index)
        first = self.history.page(self.alice)
        self.assertIsNotNone(first.next_before)
        second = self.history.page(self.alice, first.next_before)
        self.assertFalse({e.song_id for e in first.entries} & {e.song_id for e in second.entries})
        self.assertIn("s1", {e.song_id for e in second.entries})
        self.assertEqual(self.db.query("PRAGMA foreign_key_check"), [])

    def test_invalid_request_never_creates_an_event(self):
        for token in (None, "", "x" * 32):
            with self.assertRaises(ValueError):
                self.history.record(self.alice, "s1", token)
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM listening_history")[0], 0)


class HistoryMigrationTest(unittest.TestCase):
    def test_upgrade_from_published_v31_keeps_existing_rows_and_children(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "site.db"
            db = Database(path, MIGRATIONS[:31])
            fill(db)
            self.assertIsNone(db.one("SELECT name FROM sqlite_master WHERE name = 'listening_history'"))
            db.execute("INSERT INTO radar_releases "
                       "(id, title, artist, released_on, kind, cover, cover_checked_at) "
                       "VALUES ('release', 'Disque', 'Artiste', '2026-11-27', 'Album', 'https://images.example/cover.jpg', 100)")
            db.execute("INSERT INTO radar_release_artists VALUES ('release', 'artist')")
            db.execute("INSERT INTO radar_release_sources VALUES ('release', 'style', 'rock')")
            db.execute("INSERT INTO radar_sync "
                       "(source_kind, source_identity, synced_at, past_synced_at) VALUES ('style', 'rock', 100, 90)")
            tables = [row[0] for row in db.query("SELECT name FROM sqlite_master WHERE type = 'table'")]
            before = {name: [tuple(row) for row in db.query('SELECT * FROM "' + name + '"')] for name in tables}
            db.close()
            db = Database(path, MIGRATIONS)
            try:
                for name, rows in before.items():
                    self.assertEqual([tuple(row) for row in db.query('SELECT * FROM "' + name + '"')], rows, name)
                self.assertEqual(db.query("PRAGMA foreign_key_check"), [])
                self.assertEqual(db.version, 32)
                self.assertEqual(db.one("SELECT COUNT(*) FROM listening_history")[0], 0)
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
