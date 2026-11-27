"""Radar des sorties : sources par compte, sorties partagées, labels d'albums et migration des styles suivis."""
import tempfile
import unittest
from datetime import date
from pathlib import Path

from pimedia.storage.database import Database
from pimedia.webapp.schema import MIGRATIONS
from pimedia.webapp.storage.release_radar import AlbumLabels, RadarReleases, ReleaseSources
from pimedia.webapp.weekly_releases.entities import RadarRelease

RADAR_MIGRATION = 29   # première migration du radar (numérotée à partir de 1)


def add_user(db, name):
    db.execute("INSERT INTO users(username, subsonic_salt, subsonic_token, created_at, last_seen_at) "
               "VALUES (?, '', '', 0, 0)", (name,))


def release(identity, released_on, tags=()):
    return RadarRelease(identity, "Titre " + identity, "Artiste", released_on, "Album", tags)


class RadarStorageTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = Database(Path(temp.name) / "web.db", MIGRATIONS)
        self.addCleanup(self.db.close)
        for name in ("alice", "bob"):
            add_user(self.db, name)
        self.sources = ReleaseSources(self.db, clock=lambda: 1000)
        self.releases = RadarReleases(self.db)

    def test_hidden_trend_is_not_readded(self):
        source = self.sources.add(1, "label", "warp-id", "Warp", "trends")
        self.sources.hide(1, source.id)
        self.sources.add(1, "label", "warp-id", "Warp", "trends")
        self.assertEqual(self.sources.for_user(1), [])
        self.assertTrue(self.sources.for_user(1, include_hidden=True)[0].hidden)
        again = self.sources.add(1, "label", "warp-id", "Warp", "manual")
        self.assertFalse(again.hidden)
        self.assertEqual([(s.kind, s.origin) for s in self.sources.for_user(1)], [("label", "manual")])

    def test_hide_only_touches_own_sources(self):
        source = self.sources.add(1, "style", "techno", "techno", "manual")
        self.sources.hide(2, source.id)
        self.assertEqual(len(self.sources.for_user(1)), 1)

    def test_union_is_deduplicated_and_skips_hidden(self):
        self.sources.add(1, "label", "warp-id", "Warp", "manual")
        self.sources.add(2, "label", "warp-id", "Warp", "trends")
        hidden = self.sources.add(2, "style", "folk", "folk", "trends")
        self.sources.hide(2, hidden.id)
        self.assertEqual(self.sources.active_union(), [("label", "warp-id", "Warp")])

    def test_for_sources_filters_window_and_keeps_reason(self):
        self.releases.save("label", "warp-id", [release("a", date(2026, 11, 27), ("techno",)),
                                                release("b", date(2026, 12, 4))],
                           date(2026, 11, 13), date(2027, 1, 26))
        self.releases.save("style", "techno", [release("a", date(2026, 11, 27), ("techno",))],
                           date(2026, 11, 23), date(2026, 11, 29))
        found = self.releases.for_sources({("label", "warp-id"), ("style", "techno")},
                                          date(2026, 11, 23), date(2026, 11, 29))
        self.assertEqual(sorted((r.id, kind) for r, kind, _ in found), [("a", "label"), ("a", "style")])
        self.assertEqual(found[0][0].tags, ("techno",))
        self.assertEqual(self.releases.for_sources({("style", "folk")}, date(2026, 11, 23), date(2026, 11, 29)), [])

    def test_save_replaces_links_of_this_source_in_window_only(self):
        window = (date(2026, 11, 13), date(2027, 1, 26))
        self.releases.save("label", "warp-id", [release("a", date(2026, 11, 27)), release("b", date(2026, 12, 4))],
                           *window)
        self.releases.save("label", "warp-id", [release("b", date(2026, 12, 4))], *window)
        found = self.releases.for_sources({("label", "warp-id")}, *window)
        self.assertEqual([r.id for r, _, _ in found], ["b"])

    def test_sync_state_and_oldest_first(self):
        union = [("label", "a", "A"), ("label", "b", "B"), ("style", "c", "c")]
        self.releases.mark_synced("label", "a", 50)
        self.releases.mark_synced("style", "c", 10)
        self.releases.mark_failed("label", "b", 60)
        self.assertEqual([s[1] for s in self.releases.oldest_first(union)], ["b", "c", "a"])
        self.assertIsNone(self.releases.last_full_sync())
        self.releases.mark_full_sync(70)
        self.assertEqual(self.releases.last_full_sync(), 70)

    def test_purge_removes_old_releases_and_links(self):
        self.releases.save("label", "x", [release("old", date(2026, 9, 1)), release("new", date(2026, 11, 27))],
                           date(2026, 8, 1), date(2027, 1, 1))
        self.releases.purge(date(2026, 10, 1))
        found = self.releases.for_sources({("label", "x")}, date(2026, 8, 1), date(2027, 1, 1))
        self.assertEqual([r.id for r, _, _ in found], ["new"])
        self.assertEqual(self.db.query("PRAGMA foreign_key_check"), [])

    def test_album_label_not_found_is_remembered(self):
        labels = AlbumLabels(self.db)
        self.assertIsNone(labels.get("al-1"))
        labels.save("al-1", None, None, None, 5)
        self.assertEqual(labels.get("al-1"), {"label_id": None, "label_name": None, "release_id": None,
                                              "looked_up_at": 5})
        labels.save("al-1", "warp-id", "Warp", "rel-1", 6)
        self.assertEqual(labels.get("al-1")["label_name"], "Warp")


class RadarMigrationTest(unittest.TestCase):
    def test_migration_keeps_followed_styles(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "old.db"
            old = Database(path, MIGRATIONS[:RADAR_MIGRATION - 1])
            try:
                for name in ("alice", "bob"):
                    add_user(old, name)
                for user, genre in ((1, "noise rock"), (1, "techno"), (2, "techno")):
                    old.execute("INSERT INTO release_subscriptions(user_id, genre) VALUES (?, ?)", (user, genre))
            finally:
                old.close()
            upgraded = Database(path, MIGRATIONS)
            try:
                sources = ReleaseSources(upgraded)
                self.assertEqual([(s.kind, s.identity, s.name, s.origin) for s in sources.for_user(1)],
                                 [("style", "noise rock", "noise rock", "manual"),
                                  ("style", "techno", "techno", "manual")])
                self.assertEqual([s.identity for s in sources.for_user(2)], ["techno"])
                self.assertEqual(upgraded.query("PRAGMA foreign_key_check"), [])
                self.assertEqual(upgraded.query("SELECT name FROM sqlite_master WHERE name = 'release_subscriptions'"),
                                 [])
            finally:
                upgraded.close()


if __name__ == "__main__":
    unittest.main()
