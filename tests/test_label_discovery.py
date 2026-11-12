"""Sources distinctes, rééditions, variété, classement sourcé et parcours HTTP du label."""
import json
import os
import random
import tempfile
import threading
import unittest
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from types import SimpleNamespace

from pimedia.storage.database import Database
from pimedia.webapp.config import WebConfig
from pimedia.webapp.discogs import Discogs, discogs_id
from pimedia.webapp.discogs_catalogs import CatalogError, DiscogsCatalogs, group_editions
from pimedia.webapp.discogs_entities import DiscogsEdition, DiscogsTrack
from pimedia.webapp.discogs_exploration import DiscogsExploration
from pimedia.webapp.exploration_entities import CachedMetadata
from pimedia.webapp.label_discovery import LabelDiscovery, playable_tracks, varied_albums
from pimedia.webapp.lastfm import LastFm
from pimedia.webapp.music_metadata import CACHE_SECONDS, MusicSourceError
from pimedia.webapp.schema import MIGRATIONS
from pimedia.webapp.storage.exploration import ExplorationRepository
from tests.fake_discogs import FakeDiscogs, FakeLastFm, edition
from tests.webapp_support import WebAppTestCase


class LabelSourcesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Database(os.path.join(self.tmp.name, "test.db"), MIGRATIONS)
        self.addCleanup(self.db.close)
        self.repository = ExplorationRepository(self.db)
        self.now = 100000
        self.http, self.fm_http = FakeDiscogs(), FakeLastFm()
        options = dict(clock=lambda: self.now, sleep=lambda seconds: None)
        self.discogs = Discogs(self.repository, "discogs-secret", self.http, **options)
        self.lastfm = LastFm(self.repository, "lastfm-secret", self.fm_http, **options)
        self.catalogs = DiscogsCatalogs(self.discogs)
        self.discovery = LabelDiscovery(self.catalogs, self.discogs, self.lastfm, None, random.Random(42))

    def catalog(self):
        first = self.catalogs.page("label", "7", 1)
        for page in range(2, first.pages + 1):
            self.catalogs.page("label", "7", page)
        return self.catalogs.complete("label", "7")

    def test_sources_return_typed_objects_and_keep_homonyms(self):
        found = self.discogs.search("artist", "ABBA")
        self.assertEqual([i.id for i in found.identities], ["7", "8"])
        self.assertEqual(found.identities[0].kind, "artist")
        self.assertEqual(self.lastfm.album("ABBA", "Arrival").listeners, 100)
        self.assertIn("Discogs token=", self.http.calls[0][1]["Authorization"])

    def test_company_identity_keeps_the_label_explicitly_linked_by_discogs(self):
        details = self.discogs.label("8")
        self.assertTrue(details.company_only)
        self.assertEqual([(l.id, l.name) for l in details.labels], [("7", "Polar")])
        self.assertFalse(self.discogs.label("7").company_only)
        serialized = self.repository.get("discogs:labels/8?|v2").data
        self.assertNotIn("profile", serialized)
        self.assertNotIn("contact_info", serialized)

    def test_company_details_refresh_the_old_name_only_cache(self):
        self.repository.save(CachedMetadata("discogs:labels/8?", {"id": "8", "name": "Polar Records", "kind": "label"}, self.now))
        self.assertTrue(self.discogs.label("8").company_only)
        self.assertEqual(len(self.http.calls), 1)
        self.assertNotIn("|v2", self.http.calls[0][0])

    def test_company_is_rejected_before_loading_hundreds_of_catalog_pages(self):
        with self.assertRaisesRegex(CatalogError, "discovery.company_only"):
            self.catalogs.page("label", "8", 1)
        with self.assertRaisesRegex(CatalogError, "discovery.company_only"):
            self.discovery.discover("8")
        with self.assertRaisesRegex(CatalogError, "discovery.company_only"):
            self.discovery.ranking("8", "discogs", 0)
        self.assertEqual(len(self.http.calls), 1)

    def test_company_links_accept_numeric_source_references_and_never_guess_a_name(self):
        raw = dict(id=8, name="A company", profile="Use only as a company. Label: [l7].",
                   sublabels=[dict(id=7, name="A label"), dict(id=9, name="Another label")])
        self.assertEqual([l["id"] for l in Discogs._label_data(raw)["labels"]], ["7"])
        raw["profile"] = "Label operated by a company."
        self.assertFalse(Discogs._label_data(raw)["company_only"])

    def test_no_secrets_or_unused_data_in_cache(self):
        self.catalog()
        self.discogs.release("101")
        self.lastfm.album("ABBA", "Arrival")
        rows = self.db.query("SELECT cache_key, payload FROM music_metadata")
        serialized = json.dumps([dict(r) for r in rows])
        for forbidden in ("secret", "excluded", "contact_info", "wiki", "Authorization", "api_key"):
            self.assertNotIn(forbidden, serialized)

    def test_cache_expires_without_touching_musicbrainz(self):
        self.discogs.identity("label", "7")
        self.repository.save(CachedMetadata("musicbrainz", {}, 1))
        self.now += CACHE_SECONDS + 1
        self.discogs.identity("label", "7")
        self.assertEqual(len(self.http.calls), 2)
        self.assertIsNotNone(self.repository.get("musicbrainz"))

    def test_cached_reads_and_new_instances_do_not_fetch_again(self):
        self.discogs.release("101")
        again = Discogs(self.repository, "another-secret", self.http, clock=lambda: self.now)
        self.assertEqual(again.release("101").votes, 20)
        self.assertEqual(len(self.http.calls), 1)

    def test_cached_metadata_does_not_wait_for_an_unrelated_analysis_request(self):
        self.discogs.release("101")
        entered, release = threading.Event(), threading.Event()
        original = self.http.release
        def slow(identity):
            if identity == 104:
                entered.set()
                release.wait(5)
            return original(identity)
        self.http.release = slow
        with ThreadPoolExecutor(2) as pool:
            pending = pool.submit(self.discogs.release, "104")
            try:
                self.assertTrue(entered.wait(1))
                cached = pool.submit(self.discogs.release, "101")
                self.assertEqual(cached.result(timeout=1).id, "101")
            finally:
                release.set()
            self.assertEqual(pending.result(timeout=1).id, "104")

    def test_disabled_source_never_fetches(self):
        self.discogs.api_key = ""
        with self.assertRaisesRegex(MusicSourceError, "discovery.disabled"):
            self.discogs.search("label", "Polar")
        self.assertEqual(self.http.calls, [])

    def test_invalid_ids_and_pages_never_fetch(self):
        for value in ("0", "-1", "1/2", "https://example.org", "1?token=x", True):
            with self.assertRaises(ValueError):
                discogs_id(value)
        for page in (0, -1, True, 1001):
            with self.assertRaises(ValueError):
                self.catalogs.page("label", "7", page)
        self.assertEqual(self.http.calls, [])

    def test_rate_limit_cools_down_without_logging_secret(self):
        self.http.fail = urllib.error.HTTPError("https://api.discogs.com", 429, "secret", {"Retry-After": "120"}, None)
        for _ in range(2):
            with self.assertRaisesRegex(MusicSourceError, "discovery.rate_limited"):
                self.discogs.identity("label", "7")
        self.assertEqual(len(self.http.calls), 1)

    def test_expired_data_is_not_used_when_source_is_down(self):
        self.discogs.identity("label", "7")
        self.now += CACHE_SECONDS + 1
        self.http.fail = OSError("secret")
        with self.assertRaisesRegex(MusicSourceError, "discovery.unavailable"):
            self.discogs.identity("label", "7")
        self.assertIsNone(self.discogs.cached("labels/7?"))

    def test_complete_catalog_requires_all_pages(self):
        self.catalogs.page("label", "7", 1)
        with self.assertRaisesRegex(MusicSourceError, "discovery.load_catalog"):
            self.discovery.discover("7")

    def test_reissues_across_pages_are_grouped_before_ranking(self):
        albums = self.catalog()
        self.assertEqual(len(albums), 3)
        arrival = next(a for a in albums if a.title == "Arrival")
        self.assertEqual([e.id for e in arrival.editions], ["101", "102"])
        self.assertEqual(arrival.year, 1976)
        scores = self.discovery.ranking("7", "discogs", 0).scores
        self.assertEqual([s.album.title for s in scores], ["Arrival", "Discovery"])
        self.assertEqual((scores[0].edition, scores[0].value, scores[0].votes), ("101", 4, 20))

    def test_unrated_releases_are_in_discovery_and_not_in_rated_top(self):
        self.catalog()
        self.assertIn("Rare", [a.title for a in self.discovery.discover("7")])
        self.assertNotIn("Rare", [s.album.title for s in self.discovery.ranking("7", "discogs", 0).scores])

    def foreign_first_edition(self, both=False):
        release = self.http.release
        def checked(identity):
            data = release(identity)
            if identity == 101 or both and identity == 102:
                data["labels"] = [{"id": 99, "name": "Other label"}]
            return data
        self.http.release = checked

    def test_company_associations_are_excluded_without_breaking_ranking_or_tracks(self):
        self.catalog()
        self.foreign_first_edition(both=True)
        ranking = self.discovery.ranking("7", "discogs", 0)
        self.assertEqual((ranking.excluded, [s.album.title for s in ranking.scores]), (1, ["Discovery"]))
        tracks = self.discovery.tracks(None, "7", "m11", "top")
        self.assertEqual((tracks.eligible, tracks.tracks), (False, []))
        ranking = self.discovery.ranking("7", "lastfm_listeners", 0)
        self.assertEqual(ranking.excluded, 1)
        self.assertEqual(len(self.fm_http.calls), 2)

    def test_representative_is_the_first_edition_actually_released_by_the_label(self):
        self.catalog()
        self.foreign_first_edition()
        ranking = self.discovery.ranking("7", "discogs", 0)
        self.assertEqual((ranking.scores[0].edition, ranking.scores[0].album.year), ("102", 2020))
        self.assertEqual(ranking.excluded, 0)

    def test_lastfm_ranks_the_identified_catalog_with_two_criteria(self):
        self.catalog()
        listeners = self.discovery.ranking("7", "lastfm_listeners", 0)
        plays = self.discovery.ranking("7", "lastfm_plays", 0)
        self.assertEqual(listeners.scores[0].album.title, "Discovery")
        self.assertNotEqual(plays.scores[0].album.title, "Discovery")
        self.assertEqual(len(self.fm_http.calls), 3)

    def test_rank_batches_are_bounded_and_cannot_skip_uncached_scores(self):
        self.http.editions += [edition(i, i, "Album " + str(i), "Artiste", 1990) for i in range(110, 115)]
        self.catalog()
        with self.assertRaisesRegex(MusicSourceError, "discovery.rank_restart"):
            self.discovery.ranking("7", "discogs", 5)
        first = self.discovery.ranking("7", "discogs", 0)
        self.assertEqual((first.analyzed, first.total), (5, 8))
        second = self.discovery.ranking("7", "discogs", first.analyzed)
        self.assertEqual(second.analyzed, 8)
        release_calls = [url for url, _ in self.http.calls if "/releases/" in url]
        self.assertEqual(len(release_calls), 8)

    def test_fallback_groups_exact_names_but_keeps_distinct_masters(self):
        base = DiscogsEdition("1", "", "Dissidænce", "Œdipe", 2000, "CD", "")
        editions = [base, replace(base, id="2", title="Dissidaence", artist="Oedipe", year=2020)]
        self.assertEqual(len(group_editions(editions)), 1)
        self.assertEqual(len(group_editions([replace(e, master=e.id) for e in editions])), 2)

    def test_diversity_spreads_artists_and_periods_without_scores(self):
        albums = self.catalog()
        seed = albums[0]
        pool = [replace(seed, id=str(i), year=1970) for i in range(20)]
        pool += [replace(seed, id="rare", artist="Autre", year=2000)]
        selected = varied_albums(pool, random.Random(1), 2)
        self.assertEqual({a.artist for a in selected}, {seed.artist, "Autre"})
        outputs = {tuple(a.id for a in varied_albums(pool, random.Random(i), 3)) for i in range(5)}
        self.assertGreater(len(outputs), 1)

    def test_track_headings_are_excluded_and_subtracks_expanded(self):
        track = DiscogsTrack("Song", "Artist", "3:00", "track")
        index = DiscogsTrack("Suite", "", "", "index", (track,))
        heading = DiscogsTrack("Face A", "", "", "heading")
        self.assertEqual(list(playable_tracks([heading, index])), [track])

    def test_lastfm_does_not_attribute_a_different_album(self):
        stats = self.lastfm._popularity({"album": {"name": "Wrong", "artist": "ABBA", "listeners": "999"}}, "ABBA", "Arrival")
        self.assertEqual(stats.listeners, 0)

    def test_configuration_reads_server_token(self):
        with open(os.path.join(self.tmp.name, ".env"), "w") as output:
            output.write("DISCOGS_API_KEY=local-secret\n")
        self.assertEqual(WebConfig.load(self.tmp.name, {}).discogs_api_key, "local-secret")
        self.assertEqual(WebConfig.load(self.tmp.name, {"PI_MEDIA_WEB_DISCOGS_API_KEY": "process-secret"}).discogs_api_key,
                         "process-secret")

    def test_discogs_editions_and_credits_require_explicit_choice(self):
        folders = SimpleNamespace(album=lambda user, identity: {"artist": "ABBA", "name": "Arrival"})
        exploration = DiscogsExploration(self.discogs, folders)
        choice = exploration.album(None, "local")
        self.assertEqual(([e.id for e in choice.editions], choice.selected, choice.people), (["101", "102"], "", ()))
        result = exploration.album(None, "local", "101")
        self.assertEqual([(c.name, c.role) for c in result.people], [("ABBA", "artist"), ("Musicien test", "Drums")])
        self.assertEqual(result.labels[0].name, "Polar")
        with self.assertRaises(ValueError):
            exploration.album(None, "local", "103")
        self.assertFalse(any("/releases/103?" in url for url, _ in self.http.calls))

    def test_discogs_artist_links_separate_members_and_groups(self):
        group = self.discogs.artist("7")
        person = self.discogs.artist("9")
        self.assertEqual([i.id for i in group.members], ["9"])
        self.assertEqual([i.id for i in person.groups], ["7"])
        self.assertEqual(self.discogs.identity("artist", "7").name, "ABBA")
        self.assertEqual(len(self.http.calls), 2)


class LabelHttpTest(WebAppTestCase):
    environ = {"PI_MEDIA_WEB_DISCOGS_API_KEY": "discogs-secret", "PI_MEDIA_WEB_LASTFM_API_KEY": "lastfm-secret"}

    def setUp(self):
        super().setUp()
        self.http = FakeDiscogs()
        self.app.discogs.http, self.app.lastfm.http = self.http, FakeLastFm()
        self.app.discogs.sleep = self.app.lastfm.sleep = lambda seconds: None

    def catalog(self, client):
        for page in (1, 2):
            self.assertEqual(client.get("/api/discogs/catalog?kind=label&id=7&page=" + str(page)).status, 200)

    def test_routes_require_session_and_reject_invalid_parameters(self):
        paths = ("/api/discogs/status", "/api/discogs/search", "/api/discogs/catalog", "/api/labels/discover",
                 "/api/labels/ranking", "/api/labels/tracks", "/api/discogs/album", "/api/discogs/identity")
        for path in paths:
            self.assertEqual(self.client().get(path).status, 401)
        bob = self.client("bob", "pw2")
        for path in ("/api/discogs/search?kind=other&name=x", "/api/discogs/catalog?kind=label&id=0",
                     "/api/discogs/catalog?kind=label&id=7&page=0", "/api/labels/ranking?id=7&source=unknown"):
            self.assertEqual(bob.get(path).status, 400)
        self.assertEqual(self.http.calls, [])

    def test_company_page_proposes_a_musical_label_instead_of_an_empty_selection(self):
        bob = self.client("bob", "pw2")
        identity = bob.get("/api/discogs/identity?kind=label&id=8").json()
        self.assertEqual((identity["companyOnly"], identity["labels"][0]["id"]), (True, "7"))
        for path in ("/api/discogs/catalog?kind=label&id=8", "/api/labels/discover?id=8",
                     "/api/labels/ranking?id=8&source=discogs", "/api/labels/tracks?id=8&album=m11&mode=top"):
            response = bob.get(path)
            self.assertEqual((response.status, response.json()["error"]), (400, "discovery.company_only"))
        self.assertEqual(len(self.http.calls), 1)
        self.catalog(bob)
        self.assertGreater(len(bob.get("/api/labels/tracks?id=7&album=m11&mode=top").json()["tracks"]), 0)

    def test_label_tracks_use_library_first_and_keep_missing_tracks(self):
        bob = self.client("bob", "pw2")
        self.catalog(bob)
        result = bob.get("/api/labels/tracks?id=7&album=m11&mode=top").json()
        self.assertEqual([r["status"] for r in result["tracks"]], ["found", "found"])
        self.assertEqual([r["choices"][0]["id"] for r in result["tracks"]], ["s1", "s2"])
        missing = bob.get("/api/labels/tracks?id=7&album=m12&mode=top").json()["tracks"]
        self.assertEqual((missing[0]["status"], missing[0]["track"]["title"]), ("missing", "One More Time"))
        self.assertEqual(bob.get("/api/labels/tracks?id=7&album=outside&mode=top").status, 400)

    def test_artist_discography_and_public_responses_never_return_tokens(self):
        bob = self.client("bob", "pw2")
        for path in ("/api/discogs/status", "/api/discogs/search?kind=artist&name=ABBA",
                     "/api/discogs/catalog?kind=artist&id=7"):
            response = bob.get(path)
            self.assertEqual(response.status, 200)
            self.assertNotIn(b"secret", response.body)
        self.assertEqual(bob.get("/api/discogs/catalog?kind=artist&id=7").json()["identity"]["kind"], "artist")

    def test_unavailable_source_has_i18n_error_and_does_not_break_local_music(self):
        bob = self.client("bob", "pw2")
        self.http.fail = OSError("secret")
        response = bob.get("/api/discogs/search?kind=label&name=Polar")
        self.assertEqual((response.status, response.json()["error"]), (503, "discovery.unavailable"))
        self.assertNotIn(b"secret", response.body)
        self.assertEqual(bob.get("/api/album?id=al1").status, 200)

    def test_album_credits_do_not_accept_another_album_edition(self):
        bob = self.client("bob", "pw2")
        result = bob.get("/api/discogs/album?id=al1&release=101")
        self.assertEqual(result.status, 200)
        self.assertEqual(result.json()["people"][1]["name"], "Musicien test")
        self.assertEqual(bob.get("/api/discogs/album?id=al1&release=103").status, 400)
        self.assertEqual(bob.get("/api/discogs/identity?kind=artist&id=9").json()["groups"][0]["name"], "ABBA")
        self.assertNotIn(b"secret", result.body)

    def test_library_matches_are_never_reused_between_accounts(self):
        bob, alice = self.client("bob", "pw2"), self.client("alice", "secret")
        self.catalog(bob)
        self.app.imports.match_all = lambda user, tracks: [dict(choices=[{"id": user.username}], status="found") for t in tracks]
        first = bob.get("/api/labels/tracks?id=7&album=m11&mode=top").json()
        second = alice.get("/api/labels/tracks?id=7&album=m11&mode=top").json()
        self.assertEqual(first["tracks"][0]["choices"][0]["id"], "bob")
        self.assertEqual(second["tracks"][0]["choices"][0]["id"], "alice")
        stored = json.dumps([dict(row) for row in self.app.db.query("SELECT payload FROM music_metadata")])
        self.assertNotIn('"choices"', stored)
