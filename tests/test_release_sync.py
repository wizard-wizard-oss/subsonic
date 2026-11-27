"""Synchronisation de fond du radar : au démarrage, chaque nuit, à l'ajout d'une source et sur demande (limitée)."""
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from pimedia.shared.providers.metadata import ProviderUnavailable
from pimedia.shared.providers.musicbrainz.entities import WeeklyRelease, WeeklyReleasePage
from pimedia.storage.database import Database
from pimedia.webapp.schema import MIGRATIONS
from pimedia.webapp.storage.release_radar import RadarProfiles, RadarReleases, ReleaseSources
from pimedia.webapp.weekly_releases.entities import RadarError, RadarRelease
from pimedia.webapp.weekly_releases.limits import FULL_SYNC_EVERY, REFRESH_COOLDOWN, WINDOW_AFTER, WINDOW_BEFORE
from pimedia.webapp.weekly_releases.sync import ReleaseSync

TODAY = date(2026, 11, 27)
START, END = TODAY - WINDOW_BEFORE, TODAY + WINDOW_AFTER


def mbid(number):
    return "00000000-0000-4000-8000-%012d" % number


def album(number, day=TODAY, artist_ids=()):
    return WeeklyRelease(mbid(number), "Album %d" % number, "Artiste", day, "Album", ("techno",), artist_ids)


class FakeMusicBrainz:
    def __init__(self):
        self.calls, self.down = [], False
        self.by_label = {mbid(700): (album(1),)}
        self.by_artist = (album(2, artist_ids=(mbid(800),)), album(3, artist_ids=(mbid(801),)))

    def _call(self, *args):
        self.calls.append(args)
        if self.down:
            raise ProviderUnavailable("explore.unavailable")

    def weekly_groups(self, genre, monday, sunday, limit, offset):
        self._call("style", genre, monday, offset)
        found = tuple(a for a in (album(4, monday + timedelta(days=4)),) if START <= a.released_on <= END)
        return WeeklyReleasePage(found if offset == 0 else (), None, False)

    def label_groups(self, label_id, start, end):
        self._call("label", label_id, start, end)
        return WeeklyReleasePage(self.by_label.get(label_id, ()), None, False)

    def groups_by_artists(self, ids, start, end, offset=0):
        self._call("artists", tuple(ids), offset)
        return WeeklyReleasePage(tuple(a for a in self.by_artist if set(a.artist_ids) & set(ids)), None, False)


class FakeTrends:
    def __init__(self, log=None):
        self.refreshed, self.log, self.failure, self.adds = [], log, None, []

    def refresh(self, user):
        if self.failure:
            raise self.failure
        self.refreshed.append(user.id)
        if self.log is not None:
            self.log.append("trends")
        for add in self.adds:
            add()


class ReleaseSyncTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = Database(Path(temp.name) / "web.db", MIGRATIONS)
        self.addCleanup(self.db.close)
        for name in ("alice", "bob"):
            self.db.execute("INSERT INTO users(username, subsonic_salt, subsonic_token, created_at, last_seen_at) "
                            "VALUES (?, '', '', 0, 0)", (name,))
        self.alice, self.bob = SimpleNamespace(id=1), SimpleNamespace(id=2)
        self.now = datetime(2026, 11, 27, 12, 0).timestamp()
        self.musicbrainz, self.trends = FakeMusicBrainz(), FakeTrends()
        self.sources, self.releases = ReleaseSources(self.db), RadarReleases(self.db)
        self.profiles = RadarProfiles(self.db)
        self.sync = ReleaseSync(self.musicbrainz, self.trends, self.sources, self.releases, self.profiles,
                                users=lambda: [self.alice, self.bob], today=lambda: TODAY, clock=lambda: self.now,
                                spawn=lambda work: work())

    def found(self, kind, identity):
        return {r.id for r, _, _ in self.releases.for_sources({(kind, identity)}, START, END)}

    def test_startup_syncs_when_never_synced(self):
        self.sources.add(1, "label", mbid(700), "Warp", "manual")
        self.assertTrue(self.sync.tick())
        self.assertEqual(self.trends.refreshed, [1, 2])
        self.assertEqual(self.found("label", mbid(700)), {mbid(1)})
        self.assertEqual(self.releases.last_full_sync(), int(self.now))

    def test_startup_skips_recent_sync(self):
        self.releases.mark_full_sync(self.now - 3600)
        self.assertFalse(self.sync.tick())
        self.assertEqual(self.musicbrainz.calls, [])

    def test_resyncs_after_a_day_or_after_the_night_hour(self):
        self.releases.mark_full_sync(self.now - FULL_SYNC_EVERY)
        self.assertTrue(self.sync.tick())
        self.releases.mark_full_sync(datetime(2026, 11, 26, 23, 0).timestamp())
        self.now = datetime(2026, 11, 27, 4, 30).timestamp()
        self.assertTrue(self.sync.tick())

    def test_shared_label_costs_one_call(self):
        self.sources.add(1, "label", mbid(700), "Warp", "manual")
        self.sources.add(2, "label", mbid(700), "Warp", "trends")
        self.sync.sync_all()
        self.assertEqual(len([c for c in self.musicbrainz.calls if c[0] == "label"]), 1)

    def test_style_queries_each_week_of_window(self):
        self.sources.add(1, "style", "techno", "techno", "manual")
        self.sync.sync_all()
        mondays = {c[2] for c in self.musicbrainz.calls if c[0] == "style"}
        self.assertEqual(min(mondays), START - timedelta(days=START.weekday()))
        self.assertEqual(max(mondays), END - timedelta(days=END.weekday()))
        self.assertEqual(len(mondays), 12)            # 74 jours à cheval sur 12 semaines du calendrier
        self.assertTrue(self.found("style", "techno"))

    def test_artists_are_grouped_and_results_go_to_the_right_source(self):
        self.sources.add(1, "artist", mbid(800), "Moderat", "trends")
        self.sources.add(2, "similar", mbid(801), "Apparat", "discovery", "Moderat")
        self.sync.sync_all()
        self.assertEqual(len([c for c in self.musicbrainz.calls if c[0] == "artists"]), 1)
        self.assertEqual(self.found("artist", mbid(800)), {mbid(2)})
        self.assertEqual(self.found("similar", mbid(801)), {mbid(3)})

    def test_failure_keeps_previous_releases(self):
        self.sources.add(1, "label", mbid(700), "Warp", "manual")
        self.sync.sync_all()
        self.musicbrainz.down = True
        self.sync.sync_all()
        self.assertEqual(self.found("label", mbid(700)), {mbid(1)})
        row = self.db.one("SELECT synced_at, failed_at FROM radar_sync WHERE source_identity = ?", (mbid(700),))
        self.assertEqual((row["synced_at"], row["failed_at"]), (int(self.now), int(self.now)))

    def test_refresh_cooldown(self):
        self.sources.add(1, "label", mbid(700), "Warp", "manual")
        self.assertEqual(self.sync.refresh_user(self.alice), int(self.now) + REFRESH_COOLDOWN)
        self.assertEqual(self.trends.refreshed, [1])
        self.now += REFRESH_COOLDOWN - 1
        with self.assertRaises(RadarError) as raised:
            self.sync.refresh_user(self.alice)
        self.assertEqual(raised.exception.status, 429)
        self.sync.refresh_user(self.bob)                     # chaque compte a sa propre limite
        self.now += 1
        self.sync.refresh_user(self.alice)

    def test_new_source_is_synced_at_once(self):
        source = self.sources.add(1, "label", mbid(700), "Warp", "manual")
        self.sync.sync_new_source(source)
        self.assertEqual(self.found("label", mbid(700)), {mbid(1)})

    def test_run_survives_an_unexpected_error(self):
        def broken(*args):
            raise RuntimeError("bug imprévu")
        self.musicbrainz._call = broken
        self.sources.add(1, "label", mbid(700), "Warp", "manual")
        errors, sleeps = [], []

        def stop(seconds):
            sleeps.append(seconds)
            raise StopIteration
        self.sync.log, self.sync.sleep = errors.append, stop
        with self.assertRaises(StopIteration):
            self.sync.run()
        self.assertEqual(len(sleeps), 1)                 # la boucle continue : elle va dormir puis revérifier
        self.assertIn("bug imprévu", errors[0])
        self.assertTrue(self.sync.due())                  # rien n'a été marqué comme synchronisé

    def test_an_account_in_error_does_not_stop_the_others(self):
        errors = []
        self.sync.log = errors.append
        self.trends.failure = RuntimeError("compte cassé")
        self.assertTrue(self.sync.tick())
        self.assertEqual(len(errors), 2)
        self.assertIn("compte cassé", errors[0])

    def test_existing_sources_are_synced_before_trends_then_new_ones(self):
        log = []
        self.musicbrainz._call = lambda *args: log.append(args[0])
        self.trends.log = log
        self.sources.add(1, "label", mbid(700), "Warp", "manual")
        self.trends.adds = [lambda: self.sources.add(1, "artist", mbid(800), "Moderat", "trends")]
        self.sync.sync_all()
        self.assertEqual(log, ["label", "trends", "trends", "artists"])
        self.assertEqual(self.found("artist", mbid(800)), {mbid(2)})

    def test_requests_share_one_worker_and_are_deduplicated(self):
        spawned = []
        self.sync.spawn = spawned.append
        source = self.sources.add(1, "label", mbid(700), "Warp", "manual")
        self.sync.sync_new_source(source)
        self.sync.sync_new_source(source)
        self.sync.refresh_user(self.alice)
        self.assertEqual(len(spawned), 1)
        spawned[0]()
        self.assertEqual(len([c for c in self.musicbrainz.calls if c[0] == "label"]), 2)   # ajout, puis ↻
        self.assertEqual(self.trends.refreshed, [1])
        self.sync.sync_new_source(source)
        self.assertEqual(len(spawned), 2)                     # le travail précédent est fini : un nouveau fil

    def test_purge_removes_old_releases(self):
        old = RadarRelease(mbid(9), "Ancien", "Artiste", TODAY - timedelta(days=60), "Album", ())
        self.releases.save("label", "x", [old], START - timedelta(days=90), END)
        self.sync.sync_all()
        self.assertEqual(self.releases.for_sources({("label", "x")}, START - timedelta(days=90), END), [])


if __name__ == "__main__":
    unittest.main()
