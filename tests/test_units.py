"""Tests unitaires : fonctions pures et petites classes, sans réseau."""
import io
import tempfile
import unittest
import zipfile

from pimedia.server.cache import JsonCache
from pimedia.shared.external import clean_title, first_artist, sentences
from pimedia.server.folders import as_list, merge_artists, normalize_name, to_album
from pimedia.server.policy import CachePolicy
from pimedia.server.transport import Request, Router
from pimedia.server.webfiles import etag_matches


class NamesTest(unittest.TestCase):
    def test_normalize_ignores_case_accents_the_and_punctuation(self):
        self.assertEqual(normalize_name("The Beatles"), normalize_name("beatles"))
        self.assertEqual(normalize_name("THÉ\tBeatles"), normalize_name("Beatles"))
        self.assertEqual(normalize_name("Björk"), normalize_name("BJORK"))
        self.assertEqual(normalize_name("AC/DC"), "acdc")

    def test_merge_artists_joins_ids_of_the_same_name(self):
        merged = merge_artists([{"id": "1", "name": "ABBA"}, {"id": "2", "name": "Abba"}, {"id": "3", "name": "Björk"}])
        self.assertEqual([a["id"] for a in merged], ["1|2", "3"])

    def test_merge_does_not_repeat_an_id(self):
        merged = merge_artists([{"id": "1", "name": "A"}, {"id": "1", "name": "a"}])
        self.assertEqual(merged[0]["id"], "1")

    def test_as_list(self):
        self.assertEqual(as_list(None), [])
        self.assertEqual(as_list({"a": 1}), [{"a": 1}])
        self.assertEqual(as_list([1, 2]), [1, 2])

    def test_to_album_drops_missing_fields(self):
        album = to_album({"id": "x", "title": "T", "parent": "p"})
        self.assertEqual(album["name"], "T")
        self.assertEqual(album["coverArt"], "x")
        self.assertNotIn("year", album)


class TextTest(unittest.TestCase):
    def test_clean_title_removes_noise(self):
        self.assertEqual(clean_title("Song (Remastered 2011)"), "Song")
        self.assertEqual(clean_title("Song - Live at Wembley"), "Song")
        self.assertEqual(clean_title("Song feat. Someone"), "Song")
        self.assertEqual(clean_title("Plain"), "Plain")

    def test_first_artist_keeps_daft(self):
        self.assertEqual(first_artist("Daft Punk"), "Daft Punk")
        self.assertEqual(first_artist("A feat. B"), "A")

    def test_sentences_filters_by_length_and_strips_html(self):
        text = "<b>Court.</b> " + "Ceci est une phrase assez longue pour être retenue par le filtre. " * 1
        found = sentences(text, 5)
        self.assertEqual(len(found), 1)
        self.assertNotIn("<", found[0])


def build_zip(entries):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in entries:
            archive.writestr(name, data)
    return zipfile.ZipFile(io.BytesIO(buffer.getvalue()))


class PolicyTest(unittest.TestCase):
    def test_ttls(self):
        policy = CachePolicy()
        self.assertEqual(policy.ttl_for("stream", {}), 0)
        self.assertEqual(policy.ttl_for("getAlbumList2", {"type": "random"}), 0)
        self.assertEqual(policy.ttl_for("getAlbumList2", {"type": "recent"}), 30)
        self.assertGreater(policy.ttl_for("getArtists", {}), 86400)

    def test_star_invalidates_starred(self):
        rule = CachePolicy().stale_rule("star", {})
        self.assertTrue(rule({"ep": "getStarred2"}))
        self.assertFalse(rule({"ep": "getArtists"}))

    def test_read_only_calls_invalidate_nothing(self):
        self.assertIsNone(CachePolicy().stale_rule("getArtists", {}))


class JsonCacheTest(unittest.TestCase):
    def test_roundtrip_expiry_and_invalidate(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = JsonCache(directory)
            cache.load()
            cache.put("k1", "getArtists", [], 100, "application/json", b"{}")
            cache.put("k2", "getAlbum", [("id", "1")], -1, "application/json", b"{}")
            self.assertEqual(cache.get("k1").body, b"{}")
            self.assertIsNone(cache.get("k2"))
            self.assertIsNotNone(cache.get("k2", allow_stale=True))
            cache.invalidate(lambda meta: meta["ep"] == "getArtists")
            self.assertIsNone(cache.get("k1"))

    def test_index_is_rebuilt_from_disk(self):
        with tempfile.TemporaryDirectory() as directory:
            first = JsonCache(directory)
            first.load()
            first.put("k", "getArtists", [], 100, "application/json", b"[1]")
            second = JsonCache(directory)
            second.load()
            self.assertEqual(second.get("k").body, b"[1]")


class TransportTest(unittest.TestCase):
    def request(self, target="/", headers=None, peer="127.0.0.1"):
        return Request("GET", target, headers or {}, peer, io.BytesIO())

    def test_params_and_local_caller(self):
        request = self.request("/x?a=1&b=2")
        self.assertEqual(request.param("b"), "2")
        self.assertEqual(request.param("missing", "d"), "d")
        self.assertTrue(request.is_local)
        self.assertFalse(self.request(peer="192.168.1.20").is_local)

    def test_router_exact_and_prefix(self):
        router = Router()
        router.add("GET", "/me", "me")
        router.add_prefix("GET", "/rest/", "rest")
        self.assertEqual(router.find("GET", "/me"), "me")
        self.assertEqual(router.find("GET", "/rest/ping.view"), "rest")
        self.assertIsNone(router.find("POST", "/me"))
        self.assertIsNone(router.find("GET", "/other"))

    def test_etag_matching(self):
        self.assertTrue(etag_matches('"a", "b"', '"b"'))
        self.assertTrue(etag_matches("*", '"x"'))
        self.assertFalse(etag_matches("", '"x"'))


if __name__ == "__main__":
    unittest.main()
