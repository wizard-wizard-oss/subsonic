"""Cartes de candidats : métadonnées de recherche, pochettes autorisées et anciens caches compatibles."""
import unittest
import urllib.parse
from types import SimpleNamespace

from pimedia.webapp.discogs import Discogs
from pimedia.webapp.discogs_entities import DiscogsEdition
from pimedia.webapp.musicbrainz import MusicBrainzMetadata
from pimedia.webapp.tag_sources import SourceCandidate, TagSources
from tests.fake_discogs import FakeDiscogs, edition
from tests.test_tag_sources import EditionMusicBrainz, MemoryCache


class TagCandidatesTest(unittest.TestCase):
    def setUp(self):
        self.cache, self.http = MemoryCache(), FakeDiscogs()
        self.options = dict(clock=lambda: 100000, sleep=lambda seconds: None)
        self.client = Discogs(self.cache, "secret-token", self.http, **self.options)
        self.mb_http = EditionMusicBrainz()
        self.mb = MusicBrainzMetadata(self.cache, self.mb_http, **self.options)
        self.sources = TagSources(self.mb, self.client)
        self.http.editions = [edition(39001571, 10, "Trentemøller", "Trentemøller", 2026,
            thumb="https://i.discogs.com/example-cover.jpg", country="Denmark", track_count=10,
            genre=["Rock"], style=["Shoegaze", "Indie Rock", "Post-Punk"])]

    def test_discogs_candidates_expose_search_cover_genres_styles_and_edition_details(self):
        result = self.sources.search("discogs", "Trentemøller", "Trentemøller").to_api()
        candidate = result["candidates"][0]
        self.assertEqual((candidate["id"], candidate["title"], candidate["artist"]),
                         ("39001571", "Trentemøller", "Trentemøller"))
        self.assertEqual(candidate["coverUrl"], "https://i.discogs.com/example-cover.jpg")
        self.assertEqual(candidate["genres"], ["Rock"])
        self.assertEqual(candidate["styles"], ["Shoegaze", "Indie Rock", "Post-Punk"])
        self.assertEqual((candidate["date"], candidate["country"], candidate["trackCount"]), ("2026", "Denmark", 10))
        self.assertEqual(candidate["url"], "https://www.discogs.com/release/39001571")
        self.assertEqual(len(self.http.calls), 1)
        self.assertEqual(self.mb_http.calls, [])
        self.assertEqual(urllib.parse.urlsplit(self.http.calls[0][0]).path, "/database/search")

    def test_plural_classification_fields_are_also_preserved_as_typed_tuples(self):
        item = self.http.editions[0]
        item.update(genres=["Electronic"], styles=["Ambient"])
        candidate = self.client.search_releases("Trentemøller", "Trentemøller")[0]
        self.assertEqual((candidate.genres, candidate.styles), (("Electronic",), ("Ambient",)))

    def test_missing_or_single_classifications_do_not_become_individual_characters(self):
        self.http.editions[0].update(genre="Rock", style="Shoegaze")
        candidate = self.sources.search("discogs", "Trentemøller", "Trentemøller").to_api()["candidates"][0]
        self.assertEqual((candidate["genres"], candidate["styles"]), (["Rock"], ["Shoegaze"]))
        self.http.editions[0].update(genre=None, style=None)
        self.cache.entries.clear()
        candidate = self.sources.search("discogs", "Trentemøller", "Trentemøller").to_api()["candidates"][0]
        self.assertEqual((candidate["genres"], candidate["styles"]), ([], []))

    def test_untrusted_or_invalid_cover_urls_are_not_returned(self):
        urls = ["http://i.discogs.com/image.jpg", "https://other.example/image.jpg", "https://localhost/image.jpg",
                "https://i.discogs.com.other.example/image.jpg", "https://user:secret@i.discogs.com/image.jpg",
                "https://i.discogs.com/image.jpg?token=secret", "https://i.discogs.com/image.jpg#fragment"]
        self.http.editions = [edition(index + 1, 0, "Album", "Artist", 2026, thumb=url)
                              for index, url in enumerate(urls)]
        result = self.sources.search("discogs", "Artist", "Album").to_api()
        self.assertEqual([candidate["coverUrl"] for candidate in result["candidates"]], [""] * len(urls))
        self.assertEqual(len(self.http.calls), 1)

    def test_musicbrainz_candidate_does_not_invent_artwork_or_fetch_each_edition(self):
        candidate = self.sources.search("musicbrainz", "ABBA", "Arrival").to_api()["candidates"][0]
        self.assertEqual((candidate["coverUrl"], candidate["genres"], candidate["styles"]), ("", [], []))
        self.assertEqual(len(self.mb_http.calls), 1)
        self.assertEqual(self.http.calls, [])

    def test_old_source_candidate_constructor_remains_valid(self):
        result = SourceCandidate("1", "Album", "Artist", "2026", "FR", "CD", 10, "url").to_api()
        self.assertEqual((result["coverUrl"], result["genres"], result["styles"]), ("", [], []))

    def test_search_refreshes_old_projection_and_reuses_the_rich_cache(self):
        params = dict(type="release", q="Trentemøller Trentemøller", per_page=25)
        key = "discogs:database/search?" + urllib.parse.urlencode(sorted(params.items()))
        self.cache.save(SimpleNamespace(key=key + "|v2", data={"editions": []}, fetched_at=100000))
        for _ in range(2):
            result = self.sources.search("discogs", "Trentemøller", "Trentemøller")
            self.assertEqual(result.candidates[0].styles, ("Shoegaze", "Indie Rock", "Post-Punk"))
        self.assertEqual(len(self.http.calls), 1)
        self.assertIn(key + "|v3", self.cache.entries)
        self.assertFalse(any("secret" in str(entry.data) for entry in self.cache.entries.values()))

    def test_exact_edition_search_keeps_its_original_selection_and_new_metadata(self):
        self.http.editions.append(edition(39001217, 10, "Other album", "Trentemøller", 2026))
        candidates = self.client.editions("Trentemøller", "Trentemøller")
        self.assertEqual([candidate.id for candidate in candidates], ["39001571"])
        self.assertEqual(candidates[0].styles, ("Shoegaze", "Indie Rock", "Post-Punk"))

    def test_old_catalogue_projection_without_classifications_still_loads(self):
        self.client.catalog("artist", "7")
        entry = next(iter(self.cache.entries.values()))
        for row in entry.data["editions"]:
            row.pop("genres", None)
            row.pop("styles", None)
        result = self.client.catalog("artist", "7")
        self.assertEqual((result.editions[0].genres, result.editions[0].styles), ((), ()))
        self.assertEqual(len(self.http.calls), 1)
        old_constructor = DiscogsEdition("1", "", "Album", "Artist", 2026, "CD", "")
        self.assertEqual((old_constructor.genres, old_constructor.styles), ((), ()))


if __name__ == "__main__":
    unittest.main()
