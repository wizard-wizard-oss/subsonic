"""Radar lu en base, version 2 : semaine, filtres, « Mes artistes » par MBID, « Autour de… » (proches Last.fm parmi les
sorties ListenBrainz gardées), ordre par date, bibliothèque, sources, origine des styles et actualisation."""
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from pimedia.shared.providers.musicbrainz.entities import MusicArtist, MusicLabel, ReleaseGenre, Result
from pimedia.storage.database import Database
from pimedia.webapp.controllers.replies import error_reply
from pimedia.webapp.controllers.weekly_releases import WeeklyReleasesController
from pimedia.webapp.providers.lastfm import SimilarArtist
from pimedia.webapp.schema import MIGRATIONS
from pimedia.webapp.storage.release_radar import RadarProfiles, RadarReleases, ReleaseSources
from pimedia.webapp.storage.weekly_releases import ReleaseSubscriptions
from pimedia.webapp.weekly_releases.entities import RadarError, RadarRelease
from pimedia.webapp.weekly_releases.limits import REFRESH_COOLDOWN
from pimedia.webapp.weekly_releases.radar import RadarService
from pimedia.webapp.weekly_releases.service import WeeklyReleases

TODAY, MONDAY = date(2026, 11, 27), "2026-11-23"
WEEK = (date(2026, 11, 23), date(2026, 11, 29))


def mbid(number):
    return "00000000-0000-4000-8000-%012d" % number


WARP, MODERAT, APPARAT = mbid(700), mbid(800), mbid(801)


class FakeMusicBrainz:
    def __init__(self):
        self.calls = []

    def release_genres(self):
        return (ReleaseGenre("techno"), ReleaseGenre("noise rock"))

    def search_labels(self, name):
        self.calls.append(("labels", name))
        return Result((MusicLabel(WARP, "Warp", "GB"),))

    def search_artists(self, name):
        self.calls.append(("artists", name))
        return Result((MusicArtist(MODERAT, "Moderat"),))


class FakeLastFm:
    enabled = True

    def __init__(self):
        self.calls = []

    def similar_artists(self, name, limit):
        self.calls.append(name)
        return (SimilarArtist("Apparat", APPARAT, 0.9), SimilarArtist("Sans Identité", None, 0.5))


class FakeSync:
    def __init__(self):
        self.new, self.refreshed = [], []

    def sync_new_source(self, source):
        self.new.append(source.identity)

    def refresh_user(self, user):
        self.refreshed.append(user.id)
        return 1000 + REFRESH_COOLDOWN


def release(number, day=27, artist="Artiste", artists=()):
    return RadarRelease(mbid(number), "Album %d" % number, artist, date(2026, 11, day), "Album", (), artists)


class RadarServiceTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        db = Database(Path(temp.name) / "web.db", MIGRATIONS)
        self.addCleanup(db.close)
        for name in ("alice", "bob"):
            db.execute("INSERT INTO users(username, subsonic_salt, subsonic_token, created_at, last_seen_at) "
                       "VALUES (?, '', '', 0, 0)", (name,))
        self.alice, self.bob = SimpleNamespace(id=1), SimpleNamespace(id=2)
        self.musicbrainz, self.lastfm, self.sync = FakeMusicBrainz(), FakeLastFm(), FakeSync()
        self.sources, self.releases, self.profiles = ReleaseSources(db), RadarReleases(db), RadarProfiles(db)
        self.local_calls = []
        styles = WeeklyReleases(self.musicbrainz, ReleaseSubscriptions(db), today=lambda: TODAY)
        self.radar = RadarService(self.musicbrainz, self.lastfm, self.sources, self.releases, self.profiles,
                                  self.sync, styles, local=self.local, today=lambda: TODAY, clock=lambda: 1000)
        self.controller = WeeklyReleasesController(styles, self.radar)
        self.releases.save("label", WARP, [release(1), release(2, day=24)], *WEEK)
        self.releases.save("style", "techno", [release(1), release(3)], *WEEK)
        self.releases.save("fresh", "listenbrainz", [release(4, artist="Moderat", artists=(MODERAT,)),
                                                     release(5, artist="Apparat", artists=(APPARAT,)),
                                                     release(6, artist="Sans identité"),
                                                     release(7, artist="Autre", artists=(mbid(999),))], *WEEK)
        self.releases.mark_synced("label", WARP, 900)

    def local(self, user, title, artist):
        self.local_calls.append(title)
        albums = [{"id": "al9", "coverId": "c9", "folderId": "f9"}] if title == "Album 3" else []
        return {"albums": albums, "songs": []}

    def follow_all(self, user_id=1):
        self.sources.add(user_id, "label", WARP, "Warp", "manual")
        self.sources.add(user_id, "style", "techno", "techno", "trends")
        self.sources.add(user_id, "artist", MODERAT, "Moderat", "trends")

    @staticmethod
    def request(**params):
        return SimpleNamespace(param=lambda name, default=None: params.get(name, default))

    def week(self, user, filter_key="all", monday=MONDAY):
        return json.loads(self.controller.radar(self.request(monday=monday, filter=filter_key), user).body)

    def around(self, user, **params):
        return json.loads(self.controller.around(self.request(monday=MONDAY, **params), user).body)

    def test_radar_reads_database_without_external_call(self):
        self.follow_all()
        page = self.week(self.alice)
        self.assertEqual((self.musicbrainz.calls, self.lastfm.calls), ([], []))
        self.assertEqual({card["id"] for card in page["cards"]}, {mbid(1), mbid(2), mbid(3), mbid(4)})
        self.assertEqual(page["updatedAt"], 900)

    def test_radar_filters_and_counts(self):
        self.follow_all()
        page = self.week(self.alice)
        self.assertEqual({f["key"]: f["count"] for f in page["filters"]},
                         {"all": 4, "style:techno": 2, "labels": 2, "artists": 1})
        self.assertEqual({c["id"] for c in self.week(self.alice, "labels")["cards"]}, {mbid(1), mbid(2)})
        self.assertEqual([c["id"] for c in self.week(self.alice, "artists")["cards"]], [mbid(4)])
        with self.assertRaises(ValueError):
            self.week(self.alice, "discoveries")

    def test_cards_by_date_with_reasons_and_local_match(self):
        self.follow_all()
        cards = self.week(self.alice)["cards"]
        self.assertEqual([c["id"] for c in cards], [mbid(2), mbid(1), mbid(3), mbid(4)])
        first = next(card for card in cards if card["id"] == mbid(1))
        self.assertEqual({(r["kind"], r["name"]) for r in first["reasons"]}, {("label", "Warp"), ("style", "techno")})
        self.assertEqual(cards[-1]["reasons"][0]["name"], "Moderat")
        local = next(card for card in cards if card["id"] == mbid(3))["local"]
        self.assertEqual(local, {"id": "al9", "coverId": "c9", "folderId": "f9"})
        self.week(self.alice)
        self.assertEqual(len(self.local_calls), 4)                       # gardé quelques minutes

    def test_around_an_artist_finds_its_neighbours_by_mbid_or_name(self):
        page = self.around(self.alice, name="Moderat", mbid=MODERAT)
        self.assertEqual(self.lastfm.calls, ["Moderat"])
        self.assertEqual({c["id"] for c in page["cards"]}, {mbid(5), mbid(6)})
        self.assertEqual({r["via"] for c in page["cards"] for r in c["reasons"]}, {"Moderat"})
        self.assertEqual(page["around"], "Moderat")

    def test_around_needs_a_name_and_lastfm(self):
        with self.assertRaises(ValueError):
            self.around(self.alice, name="")
        self.lastfm.enabled = False
        with self.assertRaises(RadarError) as raised:
            self.around(self.alice, name="Moderat")
        self.assertEqual(error_reply(raised.exception).status, 503)

    def test_a_card_whose_folder_is_missing_does_not_break_the_week(self):
        self.follow_all()
        self.radar.local = lambda user, title, artist: (_ for _ in ()).throw(LookupError("dossier"))
        self.assertEqual({card["local"] for card in self.week(self.alice)["cards"]}, {None})

    def test_out_of_window_week(self):
        self.follow_all()
        page = self.week(self.alice, monday="2027-03-01")
        self.assertTrue(page["outOfWindow"])
        self.assertEqual(page["cards"], [])
        with self.assertRaises(ValueError):
            self.week(self.alice, monday="2026-11-24")                   # pas un lundi

    def test_account_without_sources(self):
        page = self.week(self.bob)
        self.assertEqual((page["empty"], page["cards"]), ("no-sources", []))
        self.assertEqual(page["defaultStyle"], "noise rock")

    def test_the_page_says_when_styles_come_from_the_whole_sub(self):
        self.follow_all()
        self.assertIsNone(self.week(self.alice)["basis"])
        self.profiles.set_basis(1, "site")
        self.assertEqual(self.week(self.alice)["basis"], "site")

    def test_settings(self):
        self.follow_all()
        self.assertEqual(json.loads(self.controller.sources(None, self.bob).body)["sources"], [])
        mine = json.loads(self.controller.sources(None, self.alice).body)
        self.assertEqual({(s["kind"], s["origin"]) for s in mine["sources"]},
                         {("label", "manual"), ("style", "trends"), ("artist", "trends")})
        self.assertEqual((mine["kinds"], mine["addable"], mine["aroundAvailable"], mine["refreshCooldown"]),
                         (["style", "label", "artist"], ["style", "label", "artist"], True, REFRESH_COOLDOWN))

    def test_add_source_validates_and_syncs_at_once(self):
        self.controller.add_source(None, self.alice, {"kind": "label", "identity": WARP, "name": "Warp"})
        self.controller.add_source(None, self.alice, {"kind": "style", "identity": "techno", "name": "techno"})
        self.controller.add_source(None, self.alice, {"kind": "artist", "identity": MODERAT, "name": "Moderat"})
        self.assertEqual(self.sync.new, [WARP, "techno", MODERAT])
        for bad in ({"kind": "style", "identity": "inconnu", "name": "x"}, {"kind": "label", "identity": "x"},
                    {"kind": "similar", "identity": APPARAT, "name": "Apparat"}, {"kind": "label", "identity": WARP}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.controller.add_source(None, self.alice, bad)

    def test_hide_source(self):
        self.follow_all()
        warp = self.sources.get(1, "label", WARP)
        self.controller.hide_source(None, self.bob, {"id": warp.id})      # pas la sienne : sans effet
        self.assertFalse(self.sources.get(1, "label", WARP).hidden)
        self.controller.hide_source(None, self.alice, {"id": warp.id})
        self.assertNotIn(mbid(2), {c["id"] for c in self.week(self.alice)["cards"]})

    def test_search(self):
        def search(kind, query):
            return json.loads(self.controller.search(self.request(kind=kind, q=query), self.alice).body)["results"]
        self.assertEqual(search("label", "Warp")[0]["id"], WARP)
        self.assertEqual(search("artist", "Moderat")[0]["id"], MODERAT)
        for kind, query in (("style", "x"), ("label", ""), ("label", "x" * 301)):
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                search(kind, query)

    def test_refresh(self):
        reply = json.loads(self.controller.refresh(None, self.alice, {}).body)
        self.assertEqual(reply["refreshAfter"], 1000 + REFRESH_COOLDOWN)
        self.assertEqual(self.sync.refreshed, [1])

    def test_refresh_after_is_sent_with_the_week(self):
        self.follow_all()
        self.assertIsNone(self.week(self.alice)["refreshAfter"])
        self.profiles.request_refresh(1, 950)
        self.assertEqual(self.week(self.alice)["refreshAfter"], 950 + REFRESH_COOLDOWN)

    def test_refresh_too_soon_is_a_429(self):
        self.sync.refresh_user = lambda user: (_ for _ in ()).throw(RadarError("weekly.refresh_too_soon", 429))
        with self.assertRaises(RadarError) as raised:
            self.controller.refresh(None, self.alice, {})
        self.assertEqual(error_reply(raised.exception).status, 429)


if __name__ == "__main__":
    unittest.main()
