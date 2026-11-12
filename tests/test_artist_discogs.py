"""Choix durables, accès privés, actualisation ciblée et images sans dépendance à la biographie."""
import copy
import os
import tempfile
from unittest.mock import patch

from pimedia.storage.database import Database
from pimedia.webapp.artist_discogs import ArtistDiscogsLinks
from pimedia.webapp.artist_portraits import public_image
from pimedia.webapp.schema import MIGRATIONS
from pimedia.webapp.storage.artist_links import ArtistLinkRepository
from tests.fake_discogs import FakeDiscogs
from tests.webapp_support import FakeInfoSites, WebAppTestCase


class ArtistDiscogsTest(WebAppTestCase):
    environ = {"PI_MEDIA_WEB_DISCOGS_API_KEY": "test-key"}

    def setUp(self):
        super().setUp()
        self.source = FakeDiscogs()
        self.app.discogs.http = self.source
        self.app.discogs.sleep = lambda seconds: None
        self.bob = self.client("bob", "pw2")

    def choose(self, identity="7", artist="ar1", client=None):
        return (client or self.bob).post_json("/api/discogs/artist-link", {"artistId": artist, "discogsArtistId": identity})

    def test_choice_survives_cache_expiry_and_another_database_connection(self):
        link = self.choose().json()
        self.assertEqual(link["artistId"], "fdir-ar1")
        self.app.discogs.repository.expire("discogs:", 10**12)
        self.source.fail = OSError("offline")
        self.assertEqual(self.bob.get("/api/discogs/artist-link?id=ar1").json()["link"], link)
        db = Database(self.app.db.path, MIGRATIONS)
        self.addCleanup(db.close)
        service = ArtistDiscogsLinks(ArtistLinkRepository(db), self.app.folders, self.app.artist_indexes,
                                    self.app.discogs, self.app.discogs_catalogs, self.subsonic.url)
        user = self.app.users.by_name("bob")
        self.assertEqual(service.get(user, "fdir-ar1").to_api(), link)

    def test_folder_and_id3_accesses_replace_the_same_choice(self):
        self.assertEqual(self.choose().status, 200)
        self.assertEqual(self.choose("8", "fdir-ar1").status, 200)
        found = self.bob.get("/api/discogs/artist-link?id=ar1").json()["link"]
        self.assertEqual(found["discogsArtistId"], "8")
        self.assertEqual(self.app.db.one("SELECT COUNT(*) FROM artist_discogs_links")[0], 1)

    def test_choices_are_separate_between_accounts_and_libraries(self):
        self.choose()
        alice = self.client("alice", "secret")
        self.assertIsNone(alice.get("/api/discogs/artist-link?id=ar1").json()["link"])
        self.choose("8", client=alice)
        self.assertEqual(self.bob.get("/api/discogs/artist-link?id=ar1").json()["link"]["discogsArtistId"], "7")
        other = ArtistDiscogsLinks(self.app.artist_discogs.repository, self.app.folders, self.app.artist_indexes,
                                  self.app.discogs, self.app.discogs_catalogs, self.subsonic.url + "/other")
        self.assertIsNone(other.get(self.app.users.by_name("bob"), "ar1"))

    def test_same_names_on_different_local_artists_are_not_a_key(self):
        with patch.object(self.app.folders, "artist", side_effect=lambda user, identity:
                          {"id": identity, "name": "Homonyme", "id3Id": ""}), \
             patch.object(self.app.artist_indexes, "for_user", return_value=[{"artists": [{"id": "first"}, {"id": "second"}]}]):
            self.choose("7", "first")
            self.choose("8", "second")
            self.assertEqual(self.bob.get("/api/discogs/artist-link?id=first").json()["link"]["discogsArtistId"], "7")
            self.assertEqual(self.bob.get("/api/discogs/artist-link?id=second").json()["link"]["discogsArtistId"], "8")

    def test_writes_require_csrf_and_all_routes_require_a_session(self):
        for path in ("/api/discogs/artist-link?id=ar1", "/api/artist/image?id=ar1"):
            self.assertEqual(self.client().get(path).status, 401)
        body = {"artistId": "ar1", "discogsArtistId": "7"}
        self.assertEqual(self.bob.post_json("/api/discogs/artist-link", body, csrf=False).status, 403)
        self.assertEqual(self.client().post_json("/api/discogs/artist-link", body).status, 401)
        self.assertEqual(self.bob.post_json("/api/discogs/artist-refresh", body, csrf=False).status, 403)
        for body in ({}, {"artistId": 12}, {"artistId": "ar1", "discogsArtistId": "../x"}):
            self.assertEqual(self.bob.post_json("/api/discogs/artist-link", body).status, 400)

    def test_lost_library_access_blocks_read_write_and_image(self):
        self.choose()
        count = len(self.source.calls)
        with patch.object(self.app.artist_indexes, "for_user", return_value=[]):
            self.assertEqual(self.bob.get("/api/discogs/artist-link?id=ar1").status, 404)
            self.assertEqual(self.choose("8").status, 404)
            self.assertEqual(self.bob.get("/api/artist/image?id=ar1").status, 404)
        self.assertEqual(len(self.source.calls), count)

    def test_failed_choice_keeps_previous_identity(self):
        self.choose()
        self.source.fail = OSError("offline")
        self.assertEqual(self.choose("8").status, 503)
        self.assertEqual(self.bob.get("/api/discogs/artist-link?id=ar1").json()["link"]["discogsArtistId"], "7")

    def test_refresh_keeps_choice_and_only_discards_other_pages_of_its_catalogue(self):
        self.choose()
        self.bob.get("/api/discogs/catalog?kind=artist&id=7&page=1")
        self.bob.get("/api/discogs/catalog?kind=artist&id=7&page=2")
        self.bob.get("/api/discogs/catalog?kind=label&id=7&page=1")
        self.source.editions[0]["title"] = "Refreshed"
        result = self.bob.post_json("/api/discogs/artist-refresh", {"artistId": "ar1"})
        self.assertEqual(result.status, 200)
        self.assertIn("Refreshed", [a["title"] for a in result.json()["albums"]])
        self.assertIsNone(self.app.discogs.catalog("artist", "7", 2, cached=True))
        self.assertIsNotNone(self.app.discogs.catalog("label", "7", 1, cached=True))
        self.assertEqual(self.bob.get("/api/discogs/artist-link?id=ar1").json()["link"]["discogsArtistId"], "7")

    def test_failed_refresh_keeps_the_previous_cached_page_and_choice(self):
        self.choose()
        before = self.bob.get("/api/discogs/catalog?kind=artist&id=7&page=1").json()
        self.source.fail = OSError("offline")
        self.assertEqual(self.bob.post_json("/api/discogs/artist-refresh", {"artistId": "ar1"}).status, 503)
        self.assertEqual(self.bob.get("/api/discogs/catalog?kind=artist&id=7&page=1").json(), before)
        self.assertIsNotNone(self.bob.get("/api/discogs/artist-link?id=ar1").json()["link"])

    def test_image_works_without_a_biography_and_without_discogs(self):
        with patch.object(self.app.facts, "artist_bio", return_value={}):
            self.assertEqual(self.bob.get("/api/artist/bio?name=ABBA&id=ar1").json(), {})
            image = self.bob.get("/api/artist/image?id=ar1").json()
            self.assertEqual(image["imageUrl"], FakeInfoSites.PHOTO)
            self.assertEqual(image["source"], "wikipedia")

    def test_biography_does_not_require_an_image(self):
        page = copy.deepcopy(FakeInfoSites.ABBA)
        del page["thumbnail"]
        with patch.object(self.app.facts.wikipedia, "artist_page", return_value=page):
            self.assertTrue(self.bob.get("/api/artist/bio?name=ABBA&id=ar1").json()["text"])
            self.assertEqual(self.bob.get("/api/artist/image?id=ar1").json()["imageUrl"], "")

    def test_known_homonym_without_image_does_not_use_another_wikipedia_artist(self):
        self.choose("8")
        self.assertEqual(self.bob.get("/api/artist/image?id=ar1").json()["imageUrl"], "")

    def test_selected_discogs_picture_is_projected_without_profile_or_contacts(self):
        self.choose()
        image = self.bob.get("/api/artist/image?id=ar1").json()
        self.assertEqual(image["source"], "discogs")
        self.assertEqual(image["imageUrl"], "https://i.discogs.com/artist-test.jpg")
        cached = self.app.discogs.repository.get("discogs:artists/7?|v2").data
        self.assertNotIn("profile", cached)
        self.assertNotIn("contact_info", cached)

    def test_subsonic_image_does_not_depend_on_its_biography(self):
        original = self.app.subsonic.call
        def call(credentials, method, params=(), **options):
            if method == "getArtistInfo2":
                return {"artistInfo2": {"largeImageUrl": "https://lastfm.freetls.fastly.net/artist.jpg"}}
            return original(credentials, method, params, **options)
        with patch.object(self.app.subsonic, "call", side_effect=call):
            result = self.bob.get("/api/artist/image?id=ar1").json()
            self.assertEqual(result["source"], "subsonic")

    def test_migration_preserves_existing_rows_and_deletes_links_with_user(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "migration.db")
            old = Database(path, MIGRATIONS[:15])
            old.execute("INSERT INTO music_metadata VALUES ('kept', '{}', 1)")
            old.close()
            new = Database(path, MIGRATIONS)
            self.assertEqual(new.version, len(MIGRATIONS))
            self.assertIsNotNone(new.one("SELECT * FROM music_metadata WHERE cache_key = 'kept'"))
            new.close()
        self.choose()
        self.app.db.execute("DELETE FROM users WHERE username = 'bob'")
        self.assertEqual(self.app.db.one("SELECT COUNT(*) FROM artist_discogs_links")[0], 0)

    def test_private_or_malformed_image_urls_are_not_returned(self):
        for url in ("https://[", "http://lastfm.freetls.fastly.net/a.jpg", "https://example.org/a.jpg",
                    "https://secret@lastfm.freetls.fastly.net/a.jpg", "https://lastfm.freetls.fastly.net/a.jpg?token=secret"):
            self.assertEqual(public_image(url), "")
