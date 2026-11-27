"""La seule classe MusicBrainz : genres d'une édition, cache par préfixe, copie de secours, le Pi sans base du site."""
import copy
import os
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.parse

from pimedia.shared.providers.cache import CachedMetadata, MemoryStore
from pimedia.shared.providers.metadata import Pacer
from pimedia.shared.providers.musicbrainz import MusicBrainz
from pimedia.storage.database import Database
from pimedia.webapp.schema import MIGRATIONS
from pimedia.webapp.tags.sources import TagSources
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

    def get_json(self, url, headers=None):
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
        self.options = dict(clock=lambda: 100000, sleep=self.sleeps.append, pacer=Pacer(0))
        self.client = MusicBrainz(self.cache, self.http, **self.options)
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
        other = MusicBrainz(self.cache, self.http, **self.options)
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


class Catalog:
    """Catalogue des styles : texte brut, puis erreur choisie par le test."""
    def __init__(self):
        self.failure, self.calls = None, []

    def get_text(self, url, headers=None):
        self.calls.append(url)
        if self.failure:
            raise self.failure
        return "noise rock\nshoegaze\n"


class MusicBrainzClientTest(unittest.TestCase):
    def setUp(self):
        self.now, self.store, self.http = 100000, MemoryStore(), Catalog()
        self.client = MusicBrainz(self.store, self.http, clock=lambda: self.now, sleep=lambda s: None, pacer=Pacer(0))

    def test_403_on_genre_catalog_serves_yesterdays_copy(self):
        first = self.client.release_genres()
        self.now += 86400 + 1
        self.http.failure = urllib.error.HTTPError("https://musicbrainz.org", 403, "forbidden", {}, None)
        self.assertEqual(self.client.release_genres(), first)
        self.assertEqual(len(self.http.calls), 2)

    def test_cache_keys_are_prefixed_and_expire(self):
        self.store.save(CachedMetadata("musicbrainz:old", {"names": ["x"]}, self.now - 31 * 86400))
        self.store.save(CachedMetadata("discogs:old", {}, self.now - 31 * 86400))
        self.client.release_genres()
        self.assertEqual(sorted(self.store.entries), ["discogs:old", "musicbrainz:genre/all?fmt=txt"])

    def test_pi_uses_memory_store_without_webapp(self):
        code = ("import sys; from pimedia.shared.providers.cache import MemoryStore; "
                "from pimedia.shared.providers.musicbrainz import MusicBrainz; MusicBrainz(MemoryStore()); "
                "print(sorted(m for m in sys.modules if m.startswith('pimedia.webapp')))")
        source = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
        output = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True,
                                env=dict(os.environ, PYTHONPATH=source)).stdout
        self.assertEqual(output.strip(), "[]")


class MusicBrainzCacheMigrationTest(unittest.TestCase):
    def test_migration_27_purges_only_old_musicbrainz_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "webapp.db")
            old = Database(path, MIGRATIONS[:26])
            for key in ("https://musicbrainz.org/ws/2/genre/all?fmt=txt", "discogs:release/1", "label-lastfm:a"):
                old.execute("INSERT INTO music_metadata (cache_key, payload, fetched_at) VALUES (?, '{}', 1)", (key,))
            old.close()
            db = Database(path, MIGRATIONS)
            self.addCleanup(db.close)
            keys = sorted(row[0] for row in db.query("SELECT cache_key FROM music_metadata"))
            self.assertEqual(keys, ["discogs:release/1", "lastfm:a"])


if __name__ == "__main__":
    unittest.main()
