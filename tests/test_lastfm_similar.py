"""Artistes proches lus directement chez Last.fm (pas via Subsonic, limité à la bibliothèque)."""
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from pimedia.shared.providers.metadata import Pacer
from pimedia.storage.database import Database
from pimedia.webapp.providers.lastfm import LastFm
from pimedia.webapp.schema import MIGRATIONS
from pimedia.webapp.storage.exploration import ExplorationRepository

MBID = "00000000-0000-4000-8000-000000000001"


class LastFmSimilarTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        db = Database(Path(temp.name) / "web.db", MIGRATIONS)
        self.addCleanup(db.close)
        self.store, self.urls = ExplorationRepository(db), []
        self.response = {"similarartists": {"artist": [
            {"name": "Modeselektor", "mbid": MBID, "match": "0.91"},
            {"name": "Apparat", "mbid": "", "match": "0.80"},
            {"name": "", "match": "0.5"}]}}

    def lastfm(self, key="key"):
        return LastFm(self.store, key, self, clock=lambda: 1000, sleep=lambda delay: None, pacer=Pacer(0))

    def get_json(self, url, headers=None):
        self.urls.append(url)
        return self.response

    def test_similar_artists_parses_mbid_and_match(self):
        found = self.lastfm().similar_artists("Moderat", 5)
        self.assertEqual([(a.name, a.mbid, a.match) for a in found],
                         [("Modeselektor", MBID, 0.91), ("Apparat", None, 0.8)])
        query = parse_qs(urlsplit(self.urls[0]).query)
        self.assertEqual((query["method"], query["artist"], query["limit"]), (["artist.getsimilar"], ["Moderat"], ["5"]))

    def test_result_is_cached(self):
        self.lastfm().similar_artists("Moderat", 5)
        self.lastfm().similar_artists("Moderat", 5)
        self.assertEqual(len(self.urls), 1)

    def test_unknown_artist_returns_empty(self):
        self.response = {"error": 6, "message": "The artist you supplied could not be found"}
        self.assertEqual(self.lastfm().similar_artists("Inconnu", 5), ())

    def test_disabled_without_key_makes_no_call(self):
        self.assertEqual(self.lastfm(key="").similar_artists("Moderat", 5), ())
        self.assertEqual(self.urls, [])


class LastFmCoverTest(LastFmSimilarTest):
    def album(self, artist, name, url):
        return {"album": {"name": name, "artist": artist, "image": [
            {"size": "medium", "#text": url + "-64.jpg"}, {"size": "extralarge", "#text": url + "-300.jpg"}]}}

    def test_cover_of_this_exact_album(self):
        self.response = self.album("Red Axes", "Red Box", "https://lastfm.freetls.fastly.net/i/u/x")
        self.assertEqual(self.lastfm().album_cover("Red Axes", "Red Box"), "https://lastfm.freetls.fastly.net/i/u/x-300.jpg")
        self.assertEqual(parse_qs(urlsplit(self.urls[0]).query)["method"], ["album.getinfo"])

    def test_no_cover_for_another_album_a_blank_image_or_without_key(self):
        self.response = self.album("Simply Red", "Red Box", "https://lastfm.freetls.fastly.net/i/u/x")
        self.assertEqual(self.lastfm().album_cover("Red Axes", "Red Box"), "")
        self.response = self.album("Red Axes", "Red Box", "https://x/2a96cbd8b46e442fc41c2b86b821562f")
        self.assertEqual(self.lastfm().album_cover("Red Axes", "Red Box (bis)"), "")
        self.assertEqual(self.lastfm(key="").album_cover("Red Axes", "Red Box"), "")


if __name__ == "__main__":
    unittest.main()
