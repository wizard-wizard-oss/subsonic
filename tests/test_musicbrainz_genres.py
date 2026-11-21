"""Genres d'une édition : repli sur son groupe, cache public partagé et enrichissement facultatif."""
import copy
import unittest
import urllib.parse

from pimedia.webapp.musicbrainz import MusicBrainzMetadata
from pimedia.webapp.tag_sources import TagSources
from tests.fake_musicbrainz import EDITION, RELEASE, identity
from tests.test_tag_sources import MemoryCache

GROUP = identity(20)


class MusicBrainzGenres:
    def __init__(self):
        self.calls = []
        self.release = dict(EDITION, genres=[], **{"release-group": {"id": GROUP}},
                            media=[dict(position=1, format="CD", tracks=[dict(position=1, number="1",
                                title="Original track", length=180000)])])
        self.group = dict(id=GROUP, genres=[dict(name="Electronic", count=2), dict(name="Ambient", count=7)])
        self.group_failure = None

    def get(self, url, timeout=8):
        self.calls.append(url)
        parsed = urllib.parse.urlsplit(url)
        if parsed.path == "/ws/2/release/" + RELEASE:
            return copy.deepcopy(self.release)
        if parsed.path == "/ws/2/release-group/" + GROUP:
            if self.group_failure:
                raise self.group_failure
            return copy.deepcopy(self.group)
        raise AssertionError("Unexpected MusicBrainz request")


class MusicBrainzGenresTest(unittest.TestCase):
    def setUp(self):
        self.cache, self.http, self.sleeps = MemoryCache(), MusicBrainzGenres(), []
        self.options = dict(clock=lambda: 100000, sleep=self.sleeps.append)
        self.client = MusicBrainzMetadata(self.cache, self.http, **self.options)
        self.sources = TagSources(self.client, None)

    def test_genres_present_only_on_release_group_are_exposed_with_tracks_preserved(self):
        result = self.sources.release("musicbrainz", RELEASE).to_api()
        self.assertEqual((result["genre"], result["genres"]), ("Ambient", ["Ambient", "Electronic"]))
        self.assertEqual((result["title"], result["tracks"][0]["title"]), ("Arrival", "Original track"))
        self.assertEqual(len(self.http.calls), 2)
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.http.calls[1]).query)
        self.assertEqual(query["inc"], ["genres"])
        self.assertFalse(any("/artist/" in url for url in self.http.calls))

    def test_release_genres_have_priority_and_do_not_need_an_extra_request(self):
        self.http.release["genres"] = [dict(name="Trip Hop", count=3)]
        self.assertEqual(self.client.release(RELEASE).genres, ("Trip Hop",))
        self.assertEqual(len(self.http.calls), 1)

    def test_negative_or_invalid_release_genres_do_not_prevent_the_group_fallback(self):
        self.http.release["genres"] = [dict(name="Rejected", count=-1), dict(name="", count=10),
                                       dict(name="Invalid vote", count="invalid")]
        self.http.release["release-group"]["genres"] = [dict(name="Also rejected", count=-2)]
        self.assertEqual(self.client.release(RELEASE).genres, ("Ambient", "Electronic"))
        self.assertEqual(len(self.http.calls), 2)

    def test_embedded_usable_group_genres_are_reused_without_an_extra_request(self):
        self.http.release["release-group"]["genres"] = [dict(name="Shoegaze", count=4)]
        self.assertEqual(self.client.release(RELEASE).genres, ("Shoegaze",))
        self.assertEqual(len(self.http.calls), 1)

    def test_group_genres_use_the_existing_cache_across_client_instances(self):
        self.assertEqual(self.client.release(RELEASE).genres, ("Ambient", "Electronic"))
        other = MusicBrainzMetadata(self.cache, self.http, **self.options)
        self.assertEqual(other.release(RELEASE).genres, ("Ambient", "Electronic"))
        self.assertEqual(len(self.http.calls), 2)
        self.assertEqual(len(self.cache.entries), 2)

    def test_unavailable_group_does_not_fail_or_remove_the_edition_tracks(self):
        self.http.group_failure = OSError("group unavailable")
        result = self.sources.release("musicbrainz", RELEASE).to_api()
        self.assertEqual((result["genre"], result["genres"]), ("", []))
        self.assertEqual((result["title"], result["tracks"][0]["title"]), ("Arrival", "Original track"))
        self.assertEqual(len(self.http.calls), 3)
        self.assertEqual(self.sleeps, [2])
        self.assertFalse(any("/artist/" in url for url in self.http.calls))
        self.client.release(RELEASE)
        self.assertEqual(len(self.http.calls), 3)

    def test_missing_group_or_invalid_group_id_never_triggers_an_artist_guess(self):
        for group in ({}, {"id": "https://private.example/"}, "malformed"):
            with self.subTest(group=group):
                self.setUp()
                self.http.release["release-group"] = group
                self.assertEqual(self.client.release(RELEASE).genres, ())
                self.assertEqual(len(self.http.calls), 1)

    def test_group_identity_mismatch_does_not_supply_unrelated_genres(self):
        self.http.group["id"] = identity(21)
        self.assertEqual(self.client.release(RELEASE).genres, ())

    def test_rejected_group_genres_leave_a_normal_edition_with_no_proposed_style(self):
        self.http.group["genres"] = [dict(name="Rejected", count=-1)]
        result = self.client.release(RELEASE)
        self.assertEqual(result.genres, ())
        self.assertEqual(result.tracks[0].title, "Original track")


if __name__ == "__main__":
    unittest.main()
