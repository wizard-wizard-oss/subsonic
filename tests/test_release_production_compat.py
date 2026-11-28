"""Le radar conserve les pochettes et semaines anciennes déjà publiées en 1.24.2."""
import tempfile
import unittest
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from pimedia.storage.database import Database
from pimedia.webapp.schema import MIGRATIONS
from pimedia.webapp.storage.release_radar import RadarProfiles, RadarReleases, ReleaseSources
from pimedia.webapp.weekly_releases.limits import (FULL_SYNC_EVERY, OLD_WEEK_AGAIN_AFTER, PAST_REFRESH_EVERY,
                                                 RECENT_BEFORE, WINDOW_AFTER, WINDOW_BEFORE)
from pimedia.webapp.weekly_releases.sync import ReleaseSync, radar_release
from tests.test_release_sync import FakeMusicBrainz, FakeTrends, TODAY, album


class ProductionRadarCompatibilityTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.db = Database(Path(directory.name) / "site.db", MIGRATIONS)
        self.addCleanup(self.db.close)
        for name in ("alice", "bob"):
            self.db.execute("INSERT INTO users (username, subsonic_salt, subsonic_token, created_at, last_seen_at) "
                            "VALUES (?, '', '', 0, 0)", (name,))
        self.alice, self.bob = SimpleNamespace(id=1), SimpleNamespace(id=2)
        self.now = 1_000_000
        self.musicbrainz = FakeMusicBrainz()
        self.sources, self.releases = ReleaseSources(self.db), RadarReleases(self.db)
        self.sync = ReleaseSync(self.musicbrainz, self.musicbrainz, FakeTrends(), self.sources, self.releases,
                                RadarProfiles(self.db), users=lambda: [self.alice, self.bob],
                                today=lambda: TODAY, clock=lambda: self.now, spawn=lambda work: work())
        self.start, self.end = TODAY - WINDOW_BEFORE, TODAY + WINDOW_AFTER

    def test_cover_survives_projection_database_reads_and_a_source_without_artwork(self):
        known = radar_release(replace(album(1), cover="https://images.example/cover.jpg"))
        self.releases.save("style", "techno", [known], self.start, self.end)
        self.assertEqual(self.releases.window(self.start, self.end)[0].to_api()["cover"], known.cover)
        self.releases.save("style", "techno", [replace(known, cover="")], self.start, self.end)
        self.assertEqual(self.releases.window(self.start, self.end)[0].cover, known.cover)
        self.assertEqual(self.releases.for_sources({("style", "techno")}, self.start, self.end)[0][0].cover,
                         known.cover)

    def test_missing_cover_is_looked_up_once_even_when_no_image_is_found(self):
        missing, found = radar_release(album(1)), radar_release(album(2))
        known = replace(radar_release(album(3)), cover="https://images.example/known.jpg")
        self.releases.save("style", "techno", [missing, found, known], self.start, self.end)
        self.sync.lastfm = Mock(enabled=True)
        self.sync.lastfm.album_cover.side_effect = lambda artist, title: "" if title == missing.title else \
            "https://images.example/found.jpg"
        self.sync.fill_covers()
        self.sync.fill_covers()
        self.assertEqual(self.sync.lastfm.album_cover.call_count, 2)
        images = {release.id: release.cover for release in self.releases.window(self.start, self.end)}
        self.assertEqual(images, {missing.id: "", found.id: "https://images.example/found.jpg", known.id: known.cover})
        self.assertEqual(self.releases.without_cover(self.start, self.end, 10), [])

    def test_old_style_weeks_are_not_read_again_every_night(self):
        self.sources.add(1, "style", "techno", "techno", "manual")
        self.sync.sync_sources(self.sources.active_union())
        dates = [call[2] for call in self.musicbrainz.calls if call[0] == "style"]
        self.assertEqual(min(dates), self.start - timedelta(days=self.start.weekday()))
        self.musicbrainz.calls.clear()
        self.now += FULL_SYNC_EVERY
        self.sync.sync_sources(self.sources.active_union())
        recent = TODAY - RECENT_BEFORE
        dates = [call[2] for call in self.musicbrainz.calls if call[0] == "style"]
        self.assertEqual(min(dates), recent - timedelta(days=recent.weekday()))
        self.musicbrainz.calls.clear()
        self.now += PAST_REFRESH_EVERY
        self.sync.sync_sources(self.sources.active_union())
        dates = [call[2] for call in self.musicbrainz.calls if call[0] == "style"]
        self.assertEqual(min(dates), self.start - timedelta(days=self.start.weekday()))

    def test_old_week_cache_is_per_account_and_expires(self):
        self.sources.add(1, "style", "techno", "techno", "manual")
        self.sources.add(2, "style", "rock", "rock", "manual")
        self.musicbrainz.by_artist = ()
        old = self.start - timedelta(days=self.start.weekday() + 7)
        self.sync.sync_week(self.alice, old)
        first = list(self.musicbrainz.calls)
        self.assertEqual({call[1] for call in first if call[0] == "style"}, {"techno"})
        self.sync.sync_week(self.alice, old)
        self.assertEqual(self.musicbrainz.calls, first)
        self.musicbrainz.calls.clear()
        self.sync.sync_week(self.bob, old)
        self.assertEqual({call[1] for call in self.musicbrainz.calls if call[0] == "style"}, {"rock"})
        self.musicbrainz.calls.clear()
        self.now += OLD_WEEK_AGAIN_AFTER
        self.sync.sync_week(self.alice, old)
        self.assertEqual(self.musicbrainz.calls, first)
