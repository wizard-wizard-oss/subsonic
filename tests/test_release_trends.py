"""Tendances (favoris et marque-pages), labels des albums, styles du profil, découvertes Last.fm, tri selon les goûts."""
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from pimedia.shared.providers.musicbrainz.entities import (AlbumLabel, MusicArtist, MusicLabel, ReleaseGenre,
                                                           Result)
from pimedia.shared.text import normalize
from pimedia.storage.database import Database
from pimedia.webapp.providers.lastfm import SimilarArtist
from pimedia.webapp.schema import MIGRATIONS
from pimedia.webapp.storage.release_radar import AlbumLabels, RadarProfiles, ReleaseSources
from pimedia.webapp.weekly_releases import taste
from pimedia.webapp.weekly_releases.entities import RadarCard, RadarRelease
from pimedia.webapp.weekly_releases.trends import Trends


def mbid(number):
    return "00000000-0000-4000-8000-%012d" % number


MODERAT, BURIAL, BOOKMARKED, APPARAT, DAFT, WARP = (mbid(n) for n in range(1, 7))
KNOWN = {"Moderat": MODERAT, "Burial": BURIAL, "Bookmarked": BOOKMARKED, "Apparat": APPARAT, "Daft Punk": DAFT}


class FakeSubsonic:
    def __init__(self):
        self.endpoints = []
        self.starred = {"artist": [{"id": "ar1", "name": "Moderat", "musicBrainzId": MODERAT}],
                        "album": [{"id": "al1", "name": "III", "artist": "Moderat"}],
                        "song": [{"title": "Archangel", "artist": "Burial"}]}

    def call(self, credentials, endpoint, params=()):
        self.endpoints.append(endpoint)
        return {"starred2": self.starred}


class FakeMusicBrainz:
    def __init__(self):
        self.searches, self.label_lookups = [], []

    def search_artists(self, name):
        self.searches.append(name)
        return Result(tuple(MusicArtist(KNOWN[name], name) for _ in [0] if name in KNOWN))

    def release_label(self, title, artist):
        self.label_lookups.append((title, artist))
        return AlbumLabel(MusicLabel(WARP, "Monkeytown"), mbid(99))

    def artist_tags(self, artist_id):
        return {MODERAT: ("techno", "electronic", "german"), BURIAL: ("dubstep", "electronic")}.get(artist_id, ())

    def release_genres(self):
        return (ReleaseGenre("techno"), ReleaseGenre("electronic"), ReleaseGenre("dubstep"))


class FakeLastFm:
    enabled = True

    def __init__(self):
        self.calls = []

    def similar_artists(self, name, limit):
        self.calls.append(name)
        if name != "Moderat":
            return ()
        return (SimilarArtist("Daft Punk", DAFT, 0.9), SimilarArtist("Apparat", None, 0.8),
                SimilarArtist("Inconnu", None, 0.7), SimilarArtist("Burial", BURIAL, 0.6))


class TrendsTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        db = Database(Path(temp.name) / "web.db", MIGRATIONS)
        self.addCleanup(db.close)
        db.execute("INSERT INTO users(username, subsonic_salt, subsonic_token, created_at, last_seen_at) "
                   "VALUES ('alice', 's', 't', 0, 0)")
        self.user = SimpleNamespace(id=1, username="alice", subsonic_salt="s", subsonic_token="t")
        self.subsonic, self.musicbrainz, self.lastfm = FakeSubsonic(), FakeMusicBrainz(), FakeLastFm()
        self.sources, self.profiles, self.labels = ReleaseSources(db), RadarProfiles(db), AlbumLabels(db)
        self.bookmarks = [SimpleNamespace(kind="artist", title="Bookmarked", artist="")]
        self.trends = Trends(self.subsonic, self.musicbrainz, self.lastfm, self.sources, self.labels, self.profiles,
                             bookmarks=lambda user: self.bookmarks, library_artists=lambda user: {normalize("Daft Punk")},
                             clock=lambda: 1000)

    def kinds(self, kind):
        return {(s.identity, s.name, s.origin, s.via) for s in self.sources.for_user(1) if s.kind == kind}

    def test_trends_use_only_personal_signals(self):
        self.trends.refresh(self.user)
        self.assertEqual(set(self.subsonic.endpoints), {"getStarred2"})
        self.assertEqual({identity for identity, *_ in self.kinds("artist")}, {MODERAT, BURIAL, BOOKMARKED})
        self.assertNotIn("Moderat", self.musicbrainz.searches)    # son MBID vient déjà de Subsonic

    def test_hidden_trend_stays_hidden_after_refresh(self):
        self.trends.refresh(self.user)
        burial = self.sources.get(1, "artist", BURIAL)
        self.sources.hide(1, burial.id)
        self.trends.refresh(self.user)
        self.assertTrue(self.sources.get(1, "artist", BURIAL).hidden)

    def test_album_label_is_looked_up_once(self):
        self.trends.refresh(self.user)
        self.trends.refresh(self.user)
        self.assertEqual(self.musicbrainz.label_lookups, [("III", "Moderat")])
        self.assertEqual(self.kinds("label"), {(WARP, "Monkeytown", "trends", None)})
        self.assertEqual(self.labels.get("al1")["label_id"], WARP)

    def test_styles_come_from_the_profile_and_the_catalog(self):
        self.trends.refresh(self.user)
        tags, _ = self.profiles.get(1)
        self.assertGreater(tags["electronic"], tags["german"])
        self.assertEqual({identity for identity, *_ in self.kinds("style")}, {"techno", "electronic", "dubstep"})

    def test_discoveries_skip_library_and_followed_artists_and_keep_via(self):
        self.trends.refresh(self.user)
        self.assertEqual(self.kinds("similar"), {(APPARAT, "Apparat", "discovery", "Moderat")})

    def test_discoveries_off_makes_no_lastfm_call(self):
        self.profiles.set_discoveries(1, False)
        self.trends.refresh(self.user)
        self.assertEqual(self.lastfm.calls, [])
        self.assertEqual(self.kinds("similar"), set())

    def test_unstarred_artist_leaves_the_trends(self):
        self.trends.refresh(self.user)
        self.subsonic.starred["song"] = []
        self.trends.refresh(self.user)
        self.assertNotIn(BURIAL, {identity for identity, *_ in self.kinds("artist")})

    def test_manual_source_is_not_duplicated_by_trends(self):
        self.sources.add(1, "artist", MODERAT, "Moderat", "manual")
        self.trends.refresh(self.user)
        self.assertEqual(self.sources.get(1, "artist", MODERAT).origin, "manual")


class TasteTest(unittest.TestCase):
    def card(self, identity, tags, day=27, score=None):
        release = RadarRelease(identity, identity, "Artiste", date(2026, 11, day), "Album", tags)
        return RadarCard(release, (), taste.score(tags, {"techno": 3, "electronic": 1}) if score is None else score)

    def test_score_prefers_matching_tags(self):
        profile = {"techno": 3}
        self.assertGreater(taste.score(("techno",), profile), taste.score(("folk",), profile))
        self.assertEqual(taste.score((), profile), 0)
        self.assertEqual(taste.score(("techno",), {}), 0)

    def test_rank_by_score_then_date_then_title(self):
        cards = [self.card("b", ("folk",), 25), self.card("a", ("folk",), 25), self.card("c", ("techno",), 28),
                 self.card("d", ("folk",), 24)]
        self.assertEqual([c.release.id for c in taste.rank(cards)], ["c", "d", "a", "b"])


if __name__ == "__main__":
    unittest.main()
