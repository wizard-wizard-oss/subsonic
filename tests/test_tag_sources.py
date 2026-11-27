"""Éditions pour les tags : source explicite, données conservées, aucun fichier musical ni appel réel."""
import copy
import unittest
import urllib.parse
from types import SimpleNamespace

from pimedia.webapp.discogs import Discogs
from pimedia.shared.providers.metadata import Pacer
from pimedia.shared.providers.musicbrainz import MusicBrainz
from pimedia.webapp.tag_sources import TagSources
from tests.fake_discogs import FakeDiscogs
from tests.fake_musicbrainz import ARTIST_CREDIT, EDITION, RELEASE


class MemoryCache:
    def __init__(self):
        self.entries = {}

    def get(self, key):
        return self.entries.get(key)

    def save(self, entry):
        self.entries[entry.key] = entry

    def expire(self, prefix, before):
        self.entries = {key: entry for key, entry in self.entries.items()
                        if not key.startswith(prefix) or entry.fetched_at >= before}


class EditionMusicBrainz:
    def __init__(self):
        self.calls = []
        self.failure = None
        self.editions = [dict(EDITION, **{"track-count": 3})]
        self.details = dict(EDITION, genres=[dict(name="Electronic", count=3), dict(name="Ambient", count=10)],
            media=[dict(position=1, format="CD", tracks=[
                dict(number="1", position=1, title="Edition title", length=181200,
                     **{"artist-credit": ARTIST_CREDIT}, recording=dict(title="Different recording title")),
                dict(number="2", position=2, title="Guest song", recording=dict(length=90000,
                     **{"artist-credit": [dict(name="Invité", artist=dict(name="Canonical guest"))]}))]),
                   dict(position=2, format="CD", tracks=[dict(number="A1", position=1, title="Bonus", length=0)])])

    def get_json(self, url, headers=None):
        self.calls.append(url)
        if self.failure:
            raise self.failure
        if urllib.parse.urlsplit(url).path.endswith("/release"):
            return copy.deepcopy(dict(releases=self.editions))
        return copy.deepcopy(self.details)


class EditionDiscogs(FakeDiscogs):
    def release(self, identity):
        raw = super().release(identity)
        raw.update(released="1976-10-11", country="Sweden", genres=["Electronic"], styles=["Ambient", "Experimental"],
                   formats=[dict(name="Vinyl", descriptions=["LP", "Album"])],
                   tracklist=[dict(type_="heading", title="Face A"),
                              dict(type_="track", position="A1", title="First", duration="3:04"),
                              dict(type_="index", title="Suite", artists=[dict(name="Guest")], sub_tracks=[
                                  dict(type_="track", position="2-03", title="Third", duration="1:02:03")])])
        return raw


class TagSourcesTest(unittest.TestCase):
    def setUp(self):
        self.cache = MemoryCache()
        self.mb_http, self.discogs_http = EditionMusicBrainz(), EditionDiscogs()
        options = dict(clock=lambda: 100000, sleep=lambda seconds: None)
        self.mb = MusicBrainz(self.cache, self.mb_http, pacer=Pacer(0), **options)
        self.discogs = Discogs(self.cache, "secret-token", self.discogs_http, **options)
        self.sources = TagSources(self.mb, self.discogs)

    def test_client_is_extracted_without_a_second_transport(self):
        self.assertEqual(self.sources.status(), {"musicbrainz": True, "discogs": True})

    def test_musicbrainz_search_preserves_candidates_when_tags_have_a_typo(self):
        result = self.sources.search("musicbrainz", " ABBA ", "Arival").to_api()
        self.assertEqual((result["source"], result["candidates"][0]["title"]), ("musicbrainz", "Arrival"))
        self.assertEqual(result["candidates"][0]["trackCount"], 3)
        self.assertEqual(result["candidates"][0]["url"], "https://musicbrainz.org/release/" + RELEASE)
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.mb_http.calls[0]).query)["query"][0]
        self.assertIn("Arival~1", query)
        self.assertEqual(self.discogs_http.calls, [])

    def test_search_criteria_cannot_add_a_musicbrainz_operator(self):
        self.sources.search("musicbrainz", 'ABBA" OR artist:*', "Arrival")
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.mb_http.calls[0]).query)["query"][0]
        self.assertNotIn("artist:*", query)
        self.assertNotIn('OR artist:', query)

    def test_musicbrainz_detail_preserves_discs_credits_and_release_specific_titles(self):
        result = self.sources.release("musicbrainz", RELEASE).to_api()
        self.assertEqual((result["date"], result["year"], result["format"]), ("1976-10-11", "1976", "CD"))
        self.assertEqual(result["genres"], ["Ambient", "Electronic"])
        self.assertEqual(result["styles"], [])
        self.assertEqual(result["genre"], "Ambient")
        self.assertEqual([track["disc"] for track in result["tracks"]], [1, 1, 2])
        self.assertEqual([track["track"] for track in result["tracks"]], [1, 2, 1])
        self.assertEqual(result["tracks"][0]["title"], "Edition title")
        self.assertEqual(result["tracks"][1]["artist"], "Invité")
        self.assertEqual([track["duration"] for track in result["tracks"]], [181, 90, 0])
        self.assertEqual(result["tracks"][2]["position"], "A1")
        self.assertEqual(self.discogs_http.calls, [])

    def test_musicbrainz_search_and_detail_reuse_existing_public_cache(self):
        for _ in range(2):
            self.sources.search("musicbrainz", "ABBA", "Arrival")
            self.sources.release("musicbrainz", RELEASE)
        self.assertEqual(len(self.mb_http.calls), 2)

    def test_discogs_search_is_tolerant_and_leaves_the_existing_exact_search_unchanged(self):
        result = self.sources.search(" Discogs ", "ABBA", "Arival").to_api()
        self.assertIn("Arrival", [candidate["title"] for candidate in result["candidates"]])
        self.assertEqual(self.discogs.editions("ABBA", "Arival"), ())
        self.assertEqual(self.mb_http.calls, [])

    def test_discogs_detail_preserves_styles_positions_and_suite_guest_artist(self):
        result = self.sources.release("discogs", "101").to_api()
        self.assertEqual(result["genres"], ["Electronic"])
        self.assertEqual(result["styles"], ["Ambient", "Experimental"])
        self.assertEqual(result["genre"], "Ambient")
        self.assertEqual((result["date"], result["country"], result["format"]),
                         ("1976-10-11", "Sweden", "Vinyl, LP, Album"))
        self.assertEqual(len(result["tracks"]), 2)
        first, third = result["tracks"]
        self.assertEqual((first["position"], first["track"], first["disc"], first["duration"]), ("A1", None, None, 184))
        self.assertEqual((third["track"], third["disc"], third["artist"], third["duration"]), (3, 2, "Guest", 3723))
        self.assertEqual(self.mb_http.calls, [])

    def test_discogs_detail_uses_a_new_projection_cache_and_reuses_it(self):
        self.cache.save(SimpleNamespace(key="discogs:releases/101?|v3", data={"old": True}, fetched_at=100000))
        for _ in range(2):
            self.assertEqual(self.sources.release("discogs", "101").styles, ("Ambient", "Experimental"))
        self.assertEqual(len(self.discogs_http.calls), 1)
        self.assertIn("discogs:releases/101?|v4", self.cache.entries)

    def test_a_disabled_source_does_not_fall_back_to_the_other_one(self):
        self.discogs.api_key = ""
        self.assertFalse(self.sources.status()["discogs"])
        with self.assertRaisesRegex(ValueError, "tags.source_disabled"):
            self.sources.search("discogs", "ABBA", "Arrival")
        self.assertEqual((self.mb_http.calls, self.discogs_http.calls), ([], []))

    def test_bad_inputs_never_reach_a_provider(self):
        cases = [lambda: self.sources.search("other", "ABBA", "Arrival"),
                 lambda: self.sources.search("musicbrainz", [], "Arrival"),
                 lambda: self.sources.search("musicbrainz", "", "Arrival"),
                 lambda: self.sources.search("discogs", "ABBA", "a" * 301),
                 lambda: self.sources.search("discogs", "ABBA", "line\nbreak"),
                 lambda: self.sources.release("musicbrainz", "https://localhost/"),
                 lambda: self.sources.release("discogs", "../101")]
        for call in cases:
            with self.subTest(call=call), self.assertRaisesRegex(ValueError, "tags.bad_"):
                call()
        self.assertEqual((self.mb_http.calls, self.discogs_http.calls), ([], []))

    def test_source_errors_are_public_keys_without_secrets_or_automatic_fallback(self):
        self.mb_http.failure = OSError("private URL and credentials")
        with self.assertRaisesRegex(ValueError, "^tags.source_unavailable$"):
            self.sources.search("musicbrainz", "ABBA", "Arrival")
        self.assertEqual(self.discogs_http.calls, [])
        self.discogs_http.fail = OSError("secret-token")
        with self.assertRaisesRegex(ValueError, "^tags.source_unavailable$"):
            self.sources.release("discogs", "101")

    def test_mismatched_release_identity_is_rejected(self):
        self.mb_http.details["id"] = "00000000-0000-4000-8000-000000000099"
        with self.assertRaisesRegex(ValueError, "tags.source_unavailable"):
            self.sources.release("musicbrainz", RELEASE)


if __name__ == "__main__":
    unittest.main()
