"""Sorties récentes et à venir lues chez ListenBrainz, en direct (sans cache), et tags d'artistes MusicBrainz groupés."""
import tempfile
import unittest
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from pimedia.shared.providers.metadata import Pacer, ProviderUnavailable
from pimedia.shared.providers.musicbrainz.client import MusicBrainz
from pimedia.storage.database import Database
from pimedia.webapp.providers.listenbrainz import ListenBrainz
from pimedia.webapp.schema import MIGRATIONS
from pimedia.webapp.storage.exploration import ExplorationRepository

TODAY = date(2026, 11, 27)


def mbid(number):
    return "00000000-0000-4000-8000-%012d" % number


def fresh(number, day, kind="Album", artists=(1,), name="Artiste"):
    return {"release_group_mbid": mbid(number), "release_name": "Disque %d" % number, "artist_credit_name": name,
            "artist_mbids": [mbid(900 + a) for a in artists], "release_date": day,
            "release_group_primary_type": kind, "release_tags": ["techno"]}


class ListenBrainzTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = Database(Path(temp.name) / "web.db", MIGRATIONS)
        self.addCleanup(self.db.close)
        self.urls, self.down = [], False
        self.client = ListenBrainz(ExplorationRepository(self.db), self, sleep=lambda delay: None, pacer=Pacer(0))

    def get_json(self, url, headers=None):
        self.urls.append(url)
        if self.down:
            raise OSError("ListenBrainz")
        query = parse_qs(urlsplit(url).query)
        if query["past"] == ["true"]:
            return {"payload": {"releases": [fresh(1, "2026-11-20"), fresh(2, "2026-11-21", kind="Single"),
                                             fresh(3, "2026-11-25", artists=(1, 2)), fresh(3, "2026-11-22", artists=(1, 2))]}}
        return {"payload": {"releases": [fresh(4, "2027-01-10", kind="EP"), {"release_name": "sans identifiant"}]}}

    def test_two_requests_cover_the_window_and_keep_albums_and_eps(self):
        page = self.client.fresh_releases(TODAY, date(2026, 11, 13), date(2027, 1, 26))
        self.assertEqual(len(self.urls), 2)
        past, future = (parse_qs(urlsplit(url).query) for url in self.urls)
        self.assertEqual((past["release_date"], past["days"], past["future"]), (["2026-11-27"], ["14"], ["false"]))
        self.assertEqual((future["days"], future["past"]), (["60"], ["false"]))
        self.assertEqual({(r.id, r.kind) for r in page}, {(mbid(1), "Album"), (mbid(3), "Album"), (mbid(4), "EP")})

    def test_one_entry_per_release_group_at_its_earliest_date_with_its_artists(self):
        found = {r.id: r for r in self.client.fresh_releases(TODAY, date(2026, 11, 13), date(2027, 1, 26))}
        self.assertEqual(found[mbid(3)].released_on, date(2026, 11, 22))
        self.assertEqual(found[mbid(3)].artist_ids, (mbid(901), mbid(902)))
        self.assertEqual(found[mbid(3)].tags, ("techno",))

    def test_nothing_is_kept_in_the_metadata_cache(self):
        self.client.fresh_releases(TODAY, date(2026, 11, 13), date(2027, 1, 26))
        self.client.fresh_releases(TODAY, date(2026, 11, 13), date(2027, 1, 26))
        self.assertEqual(len(self.urls), 4)
        self.assertEqual(self.db.query("SELECT * FROM music_metadata WHERE cache_key LIKE 'listenbrainz:%'"), [])

    def test_failure_is_a_provider_error(self):
        self.down = True
        with self.assertRaises(ProviderUnavailable):
            self.client.fresh_releases(TODAY, date(2026, 11, 13), date(2027, 1, 26))


class GroupedArtistTagsTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        db = Database(Path(temp.name) / "web.db", MIGRATIONS)
        self.addCleanup(db.close)
        self.urls = []
        self.client = MusicBrainz(ExplorationRepository(db), self, clock=lambda: 1000, sleep=lambda d: None,
                                  pacer=Pacer(0))

    def get_json(self, url, headers=None):
        self.urls.append(url)
        return {"artists": [{"id": mbid(1), "name": "A", "tags": [{"name": "rock", "count": 2},
                                                                  {"name": "noise rock", "count": 9}]},
                            {"id": mbid(2), "name": "B"}, {"id": "pas-un-mbid", "tags": [{"name": "x", "count": 1}]}]}

    def test_tags_of_many_artists_in_one_request(self):
        found = self.client.artists_tags([mbid(1), mbid(2)])
        self.assertEqual(len(self.urls), 1)
        query = parse_qs(urlsplit(self.urls[0]).query)["query"][0]
        self.assertIn("arid:" + mbid(1), query)
        self.assertIn("arid:" + mbid(2), query)
        self.assertEqual(found, {mbid(1): ("noise rock", "rock"), mbid(2): ()})


if __name__ == "__main__":
    unittest.main()
