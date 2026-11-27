"""Tendances, version 2 : favoris seulement, styles dominants (lus par lots), styles génériques du sub sans favori,
labels des albums favoris, noms d'artistes résolus une fois, pannes qui ne retirent rien."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from pimedia.shared.providers.metadata import ProviderUnavailable
from pimedia.shared.providers.musicbrainz.entities import (AlbumLabel, MusicArtist, MusicLabel, ReleaseGenre,
                                                           Result)
from pimedia.shared.text import normalize
from pimedia.storage.database import Database
from pimedia.webapp.schema import MIGRATIONS
from pimedia.webapp.storage.release_radar import AlbumLabels, ArtistResolutions, RadarProfiles, ReleaseSources
from pimedia.webapp.weekly_releases.limits import TREND_RESOLVE_ATTEMPTS
from pimedia.webapp.weekly_releases.trends import Trends


def mbid(number):
    return "00000000-0000-4000-8000-%012d" % number


ARTISTS = {"A%d" % n: mbid(n) for n in range(1, 8)}
WARP = mbid(700)
TAGS = {mbid(1): ("techno", "electronic", "german"), mbid(2): ("techno", "electronic"),
        mbid(3): ("techno", "ambient", "electronic"), mbid(4): ("rock", "techno"), mbid(5): ("folk",),
        mbid(6): ("rock", "noise rock"), mbid(7): ("rock",)}
CATALOG = ("techno", "electronic", "ambient", "rock", "folk", "noise rock")


class FakeSubsonic:
    def __init__(self):
        self.endpoints = []
        self.starred = {"artist": [{"id": "ar1", "name": "A1", "musicBrainzId": mbid(1)}],
                        "album": [{"id": "al1", "name": "Disque", "artist": "A2"}],
                        "song": [{"title": "Morceau", "artist": "A3"}, {"title": "Autre", "artist": "A4"}]}
        self.frequent = [{"artist": "A6"}, {"artist": "A7"}, {"artist": "A4"}]

    def call(self, credentials, endpoint, params=()):
        self.endpoints.append(endpoint)
        if endpoint == "getStarred2":
            return {"starred2": self.starred}
        return {"albumList2": {"album": self.frequent}}


class FakeMusicBrainz:
    def __init__(self):
        self.searches, self.tag_calls, self.label_lookups, self.down = [], [], [], set()
        self.homonyms = {}

    def search_artists(self, name):
        self.searches.append(name)
        if "search" in self.down:
            raise ProviderUnavailable("explore.unavailable")
        ids = self.homonyms.get(name) or ([ARTISTS[name]] if name in ARTISTS else [])
        return Result(tuple(MusicArtist(identity, name) for identity in ids))

    def artists_tags(self, ids):
        self.tag_calls.append(tuple(ids))
        if "tags" in self.down:
            raise ProviderUnavailable("explore.unavailable")
        return {identity: TAGS.get(identity, ()) for identity in ids}

    def release_label(self, title, artist):
        self.label_lookups.append((title, artist))
        return AlbumLabel(MusicLabel(WARP, "Warp"), mbid(99))

    def release_genres(self):
        if "genres" in self.down:
            raise ProviderUnavailable("explore.unavailable")
        return tuple(ReleaseGenre(name) for name in CATALOG)


class TrendsTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        db = Database(Path(temp.name) / "web.db", MIGRATIONS)
        self.addCleanup(db.close)
        db.execute("INSERT INTO users(username, subsonic_salt, subsonic_token, created_at, last_seen_at) "
                   "VALUES ('alice', 's', 't', 0, 0)")
        self.user = SimpleNamespace(id=1, username="alice", subsonic_salt="s", subsonic_token="t")
        self.now = 1000
        self.subsonic, self.musicbrainz = FakeSubsonic(), FakeMusicBrainz()
        self.sources, self.profiles = ReleaseSources(db), RadarProfiles(db)
        self.labels, self.names = AlbumLabels(db), ArtistResolutions(db)
        self.trends = Trends(self.subsonic, self.musicbrainz, self.sources, self.labels, self.profiles, self.names,
                             clock=lambda: self.now)

    def kinds(self, kind):
        return {(s.identity, s.origin) for s in self.sources.for_user(1) if s.kind == kind}

    def test_only_favorites_are_read_and_become_artists(self):
        self.trends.refresh(self.user)
        self.assertEqual(self.subsonic.endpoints, ["getStarred2"])
        self.assertEqual(self.kinds("artist"), {(mbid(n), "trends") for n in (1, 2, 3, 4)})
        self.assertNotIn("A1", self.musicbrainz.searches)                 # son MBID vient de Subsonic
        self.assertEqual(self.profiles.basis(1), "favorites")

    def test_dominant_styles_need_three_artists_and_are_read_in_one_request(self):
        self.trends.refresh(self.user)
        self.assertEqual(len(self.musicbrainz.tag_calls), 1)
        # techno : 4 artistes ; electronic : 3 ; ambient, german, rock : moins de 3
        self.assertEqual(self.kinds("style"), {("techno", "trends"), ("electronic", "trends")})

    def test_at_most_five_dominant_styles_ranked_by_artists(self):
        for name, identity in ARTISTS.items():
            TAGS[identity] = ("a", "b", "c") if identity != mbid(7) else ("d",)
        try:
            self.subsonic.starred = {"artist": [{"name": n, "musicBrainzId": i} for n, i in ARTISTS.items()]}
            self.musicbrainz.release_genres = lambda: tuple(ReleaseGenre(x) for x in "abcd")
            self.trends.refresh(self.user)
            self.assertEqual({identity for identity, _ in self.kinds("style")}, {"a", "b", "c"})
        finally:
            TAGS.update({mbid(1): ("techno", "electronic", "german"), mbid(2): ("techno", "electronic"),
                         mbid(3): ("techno", "ambient", "electronic"), mbid(4): ("rock", "techno"),
                         mbid(5): ("folk",), mbid(6): ("rock", "noise rock"), mbid(7): ("rock",)})

    def test_without_favorites_styles_come_from_the_whole_sub(self):
        self.subsonic.starred = {}
        self.trends.refresh(self.user)
        self.assertIn("getAlbumList2", self.subsonic.endpoints)
        self.assertEqual(self.kinds("style"), {("rock", "trends")})          # A6, A7, A4
        self.assertEqual(self.kinds("artist"), set())                       # les artistes du sub ne sont pas « les siens »
        self.assertEqual(self.profiles.basis(1), "site")

    def test_album_label_is_looked_up_once(self):
        self.trends.refresh(self.user)
        self.trends.refresh(self.user)
        self.assertEqual(self.musicbrainz.label_lookups, [("Disque", "A2")])
        self.assertEqual(self.kinds("label"), {(WARP, "trends")})

    def test_a_resolved_name_is_remembered(self):
        self.trends.refresh(self.user)
        searches = len(self.musicbrainz.searches)
        self.trends.refresh(self.user)
        self.assertEqual(len(self.musicbrainz.searches), searches)

    def test_an_unknown_name_is_searched_again_after_a_month(self):
        self.subsonic.starred = {"song": [{"artist": "Inconnu"}]}
        self.trends.refresh(self.user)
        self.trends.refresh(self.user)
        self.assertEqual(self.musicbrainz.searches.count("Inconnu"), 1)
        self.now += 31 * 86400
        self.trends.refresh(self.user)
        self.assertEqual(self.musicbrainz.searches.count("Inconnu"), 2)

    def test_homonyms_without_mbid_are_ignored(self):
        self.subsonic.starred = {"song": [{"artist": "Air"}]}
        self.musicbrainz.homonyms["Air"] = [mbid(40), mbid(41)]
        self.trends.refresh(self.user)
        self.assertEqual(self.kinds("artist"), set())

    def test_hidden_trend_stays_hidden_after_refresh(self):
        self.trends.refresh(self.user)
        self.sources.hide(1, self.sources.get(1, "style", "techno").id)
        self.trends.refresh(self.user)
        self.assertTrue(self.sources.get(1, "style", "techno").hidden)

    def test_unstarred_artist_leaves_the_trends(self):
        self.trends.refresh(self.user)
        self.subsonic.starred["song"] = [{"artist": "A3"}]
        self.trends.refresh(self.user)
        self.assertNotIn((mbid(4), "trends"), self.kinds("artist"))

    def test_a_service_failure_removes_nothing(self):
        self.trends.refresh(self.user)
        before = {kind: self.kinds(kind) for kind in ("artist", "style")}
        self.musicbrainz.down = {"tags", "genres", "search"}
        self.names.save(normalize("A3"), None, self.now - 31 * 86400)        # nom à rechercher de nouveau
        self.trends.refresh(self.user)
        self.assertEqual({kind: self.kinds(kind) for kind in ("artist", "style")}, before)

    def test_name_resolution_attempts_are_bounded(self):
        self.subsonic.starred = {"song": [{"artist": "Inconnu %d" % n} for n in range(200)]}
        self.trends.refresh(self.user)
        self.assertEqual(len(self.musicbrainz.searches), TREND_RESOLVE_ATTEMPTS)


if __name__ == "__main__":
    unittest.main()
