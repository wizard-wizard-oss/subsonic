"""Exploration musicale : identité, crédits, cache, panne, frontières HTTP et disponibilité par compte."""
import os
import tempfile
import threading
import unittest
import urllib.error
from types import SimpleNamespace

from pimedia.shared.text import normalize
from pimedia.shared.external import MusicBrainzPacer
from pimedia.storage.database import Database
from pimedia.webapp.exploration import Exploration, ExplorationUnavailable, MusicBrainzMetadata
from pimedia.webapp.schema import MIGRATIONS
from pimedia.webapp.storage.exploration import ExplorationRepository
from tests.fake_musicbrainz import (EDITION, GROUP, LABEL, MEMBER, OTHER_RELEASE, PRODUCER, RELEASE, SIDE_GROUP,
                                   FakeMusicBrainz)
from tests.webapp_support import WebAppTestCase


class MetadataTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Database(os.path.join(self.temp.name, "test.db"), MIGRATIONS)
        self.addCleanup(self.db.close)
        self.repository = ExplorationRepository(self.db)
        self.http = FakeMusicBrainz()
        self.now = 100
        self.sleeps = []
        self.metadata = MusicBrainzMetadata(self.repository, self.http, clock=lambda: self.now, sleep=self.sleeps.append)
        self.folders = SimpleNamespace(album=lambda user, album_id: {"name": "Arrival", "artist": "ABBA"})
        self.service = Exploration(self.metadata, self.folders, None)

    def test_editions_require_an_explicit_choice(self):
        result = self.service.album(None, "local")
        self.assertEqual([e.id for e in result.editions], [RELEASE, OTHER_RELEASE])
        self.assertEqual((result.selected, result.labels, result.people), ("", [], []))
        self.assertEqual(len(self.http.urls), 1)

    def test_release_and_recording_credits_deduplicated(self):
        result = self.service.album(None, "local", RELEASE)
        self.assertEqual(result.labels[0].id, LABEL)
        self.assertEqual({(p.id, p.role, p.detail) for p in result.people},
                         {(GROUP, "artist", ""), (PRODUCER, "producer", ""), (MEMBER, "musician", "guitar")})

    def test_inexact_titles_and_other_artists_are_not_matched(self):
        self.http.editions = [dict(EDITION, title="Arrival live"), dict(EDITION, **{
            "artist-credit": [{"name": "Other", "artist": {"name": "Other"}}]})]
        self.assertEqual(self.service.album(None, "local").editions, [])

    def test_editions_match_the_complete_collaboration_credit_without_choosing(self):
        self.folders.album = lambda user, album_id: {"name": "Cendre", "artist": "Fennesz + Sakamoto"}
        credits = [{"name": "Fennesz", "artist": {"name": "Fennesz"}, "joinphrase": " + "},
                   {"name": "Sakamoto", "artist": {"name": "Ryuichi Sakamoto"}}]
        edition = dict(EDITION, title="Cendre", **{"artist-credit": credits})
        self.http.editions = [edition, dict(edition, id=OTHER_RELEASE),
                              dict(edition, id=LABEL, title="Cendre live"),
                              dict(edition, id=PRODUCER, **{"artist-credit": [credits[0], {
                                  "name": "Other", "artist": {"name": "Other"}}]})]
        result = self.service.album(None, "local")
        self.assertEqual([e.id for e in result.editions], [RELEASE, OTHER_RELEASE])
        self.assertEqual([e.artist for e in result.editions], ["Fennesz + Sakamoto"] * 2)
        self.assertEqual((result.selected, result.labels, result.people), ("", [], []))
        self.assertEqual(len(self.http.urls), 1)

    def test_editions_accept_credited_and_canonical_artist_names(self):
        self.http.editions = [dict(EDITION, **{"artist-credit": [
            {"name": "Prodigy", "artist": {"name": "The Prodigy"}}]})]
        for artist in ("Prodigy", "The Prodigy"):
            with self.subTest(artist=artist):
                self.folders.album = lambda user, album_id: {"name": "Arrival", "artist": artist}
                result = self.service.album(None, "local")
                self.assertEqual([e.id for e in result.editions], [RELEASE])
                self.assertEqual(result.editions[0].artist, "Prodigy")

    def test_editions_without_artist_credits_are_not_matched(self):
        self.http.editions = [{"id": RELEASE, "title": "Arrival"},
                              dict(EDITION, **{"artist-credit": None}),
                              dict(EDITION, **{"artist-credit": []})]
        self.assertEqual(self.service.album(None, "local").editions, [])

    def test_vitalic_ligature_matches_without_confusing_episodes_or_the_box_set(self):
        self.folders.album = lambda user, album_id: {"name": "Dissidaence Episode 2", "artist": "Vitalic"}
        credits = [{"name": "Vitalic", "artist": {"name": "Vitalic", "id": GROUP}}]
        self.http.editions = [dict(EDITION, title="Dissidænce Episode 2", **{"artist-credit": credits}),
                              dict(EDITION, id=OTHER_RELEASE, title="Dissidænce Episode 1 & 2",
                                   **{"artist-credit": credits}),
                              dict(EDITION, id=LABEL, title="Dissidænce Episode 1", **{"artist-credit": credits})]
        result = self.service.album(None, "local")
        self.assertEqual([edition.id for edition in result.editions], [RELEASE])
        self.assertEqual(result.editions[0].title, "Dissidænce Episode 2")
        self.assertEqual(result.selected, "")

    def test_ligatures_in_artist_names_and_local_matches(self):
        self.assertEqual(normalize("ŒUVRES"), normalize("Oeuvres"))
        self.assertEqual(normalize("DISSIDÆNCE"), normalize("Dissidaence"))
        self.folders.album = lambda user, album_id: {"name": "Arrival", "artist": "Oedipe"}
        self.http.editions = [dict(EDITION, **{"artist-credit": [{"artist": {"name": "Œdipe"}}]})]
        self.assertEqual(len(self.service.album(None, "local").editions), 1)
        self.service.library = SimpleNamespace(search=lambda user, query: {
            "albums": [{"id": "local", "name": "Dissidaence Episode 2", "artist": "Vitalic"}], "songs": []})
        self.assertEqual(self.service.local(None, "Dissidænce Episode 2", "Vitalic")["albums"][0]["id"], "local")

    def test_cannot_choose_a_release_outside_candidates(self):
        with self.assertRaises(ValueError):
            self.service.album(None, "local", LABEL)
        self.assertEqual(len(self.http.urls), 1)

    def test_cache_survives_new_service_and_expires(self):
        self.metadata.get("label/" + LABEL)
        fresh = MusicBrainzMetadata(self.repository, self.http, clock=lambda: self.now)
        fresh.get("label/" + LABEL)
        self.assertEqual(len(self.http.urls), 1)
        self.now += 8 * 86400
        fresh.get("label/" + LABEL)
        self.assertEqual(len(self.http.urls), 2)

    def test_failure_is_not_cached_and_retries_back_off(self):
        self.http.down = True
        for _ in range(3):
            with self.assertRaises(ExplorationUnavailable):
                self.metadata.get("label/" + LABEL)
        self.assertEqual(len(self.http.urls), 2)
        self.assertEqual(self.sleeps, [2])
        self.now += 61
        self.http.down = False
        self.assertEqual(self.metadata.get("label/" + LABEL).data["name"], "Polar")

    def test_cached_data_still_available_during_outage(self):
        self.metadata.get("label/" + LABEL)
        self.http.down = True
        with self.assertRaises(ExplorationUnavailable):
            self.metadata.get("artist/" + GROUP)
        self.assertEqual(self.metadata.get("label/" + LABEL).data["name"], "Polar")

    def test_transient_503_recovers_without_an_error_for_the_reader(self):
        self.http.failures = [urllib.error.HTTPError("https://musicbrainz.org", 503, "busy", {}, None)]
        response = self.metadata.get("label/" + LABEL)
        self.assertEqual(response.data["name"], "Polar")
        self.assertFalse(response.stale)
        self.assertEqual((len(self.http.urls), self.sleeps), (2, [2]))

    def test_one_failed_request_does_not_block_another_entity(self):
        self.http.down = True
        with self.assertRaises(ExplorationUnavailable):
            self.metadata.get("label/" + LABEL)
        self.http.down = False
        self.assertEqual(self.metadata.get("artist/" + GROUP).data["name"], "ABBA")
        with self.assertRaises(ExplorationUnavailable):
            self.metadata.get("label/" + LABEL)
        self.assertEqual(len(self.http.urls), 3)

    def test_retry_after_is_respected_without_a_long_sleep(self):
        self.http.failures = [urllib.error.HTTPError("https://musicbrainz.org", 503, "busy",
                                                     {"Retry-After": "120"}, None)]
        with self.assertRaises(ExplorationUnavailable):
            self.metadata.get("label/" + LABEL)
        self.now += 61
        with self.assertRaises(ExplorationUnavailable):
            self.metadata.get("label/" + LABEL)
        self.assertEqual((len(self.http.urls), self.sleeps), (1, []))
        self.now += 60
        self.assertEqual(self.metadata.get("label/" + LABEL).data["name"], "Polar")

    def test_stale_cache_survives_an_outage_without_resetting_its_age(self):
        self.metadata.get("label/" + LABEL)
        self.now += 8 * 86400
        self.http.down = True
        result = self.metadata.get("label/" + LABEL)
        self.assertTrue(result.stale)
        self.assertEqual(result.data["name"], "Polar")
        self.assertTrue(self.metadata.get("label/" + LABEL).stale)
        self.assertEqual(len(self.http.urls), 3)
        entry = self.db.one("SELECT fetched_at FROM music_metadata")
        self.assertEqual(entry[0], 100)
        self.now += 61
        self.http.down = False
        self.assertFalse(self.metadata.get("label/" + LABEL).stale)

    def test_cache_older_than_thirty_days_is_not_presented_as_usable(self):
        self.metadata.get("label/" + LABEL)
        self.now += 31 * 86400
        self.http.down = True
        with self.assertRaises(ExplorationUnavailable):
            self.metadata.get("label/" + LABEL)

    def test_deleted_entity_is_not_retried_or_served_from_stale_cache(self):
        self.metadata.get("label/" + LABEL)
        self.now += 8 * 86400
        self.http.failures = [urllib.error.HTTPError("https://musicbrainz.org", 404, "missing", {}, None)]
        with self.assertRaises(ExplorationUnavailable):
            self.metadata.get("label/" + LABEL)
        self.assertEqual((len(self.http.urls), self.sleeps), (2, []))

    def test_album_and_profile_mark_stale_results(self):
        self.service.album(None, "local", RELEASE)
        self.service.profile("label", LABEL)
        self.now += 8 * 86400
        self.http.down = True
        self.assertTrue(self.service.album(None, "local", RELEASE).to_api()["stale"])
        self.assertTrue(self.service.profile("label", LABEL).to_api()["stale"])

    def test_group_members_and_members_other_groups(self):
        group = self.service.profile("artist", GROUP)
        member = self.service.profile("artist", MEMBER)
        self.assertEqual((group.relations[0].id, group.relations[0].role), (MEMBER, "member"))
        self.assertEqual((member.relations[0].id, member.relations[0].role), (GROUP, "group"))
        self.assertEqual(group.relations[0].begin, "1972")
        self.assertTrue(group.relations[0].ended)
        self.assertEqual(group.works[-1].role, "producer")

    def test_connections_only_fetch_relationships_and_preserve_members_periods(self):
        band = self.service.connections(GROUP)
        self.assertEqual([(r.id, r.role) for r in band.relations], [(MEMBER, "member")])
        person = self.service.connections(MEMBER)
        self.assertEqual({r.id for r in person.relations}, {GROUP, SIDE_GROUP})
        periods = [r for r in person.relations if r.id == SIDE_GROUP]
        self.assertEqual([r.begin for r in periods], ["1980", "1990"])
        self.assertTrue(periods[0].ended)
        self.assertFalse(periods[1].ended)
        self.assertEqual(len(self.http.urls), 2)
        self.assertTrue(all("inc=artist-rels" in url and "recording-rels" not in url for url in self.http.urls))

    def test_only_musical_relations_are_exposed_and_exact_duplicates_are_removed(self):
        relation = {"type": "member of band", "direction": "backward",
                    "artist": {"id": MEMBER, "name": "Musicien"}, "begin": "1972"}
        relations = Exploration._connections({"relations": [relation, relation,
            {"type": "married", "artist": {"id": PRODUCER, "name": "Vie privée"}},
            {"type": "collaboration", "direction": "forward", "artist": {"id": SIDE_GROUP, "name": "Projet"}},
            {"type": "instrumental supporting musician", "direction": "backward",
             "artist": {"id": PRODUCER, "name": "Invité"}, "attributes": ["guitar"]}]})
        self.assertEqual({(r.id, r.role) for r in relations},
                         {(MEMBER, "member"), (SIDE_GROUP, "project"), (PRODUCER, "supporting_member")})
        self.assertEqual(len(relations), 3)

    def test_homonyms_are_returned_without_choosing_one(self):
        self.http.artists.append({"id": SIDE_GROUP, "name": "ABBA tribute"})
        choices = self.service.artists(" ABBA ")
        self.assertEqual([(a.id, a.type) for a in choices.artists], [(GROUP, "Group"), (PRODUCER, "Person")])
        self.assertEqual(len(self.http.urls), 1)

    def test_connection_cache_and_stale_fallback(self):
        self.service.connections(GROUP)
        self.service.connections(GROUP)
        self.assertEqual(len(self.http.urls), 1)
        self.now += 8 * 86400
        self.http.down = True
        self.assertTrue(self.service.connections(GROUP).to_api()["stale"])

    def test_invalid_connection_and_artist_name_never_reach_the_source(self):
        for name in ("", "  ", "x" * 301):
            with self.assertRaises(ValueError):
                self.service.artists(name)
        with self.assertRaises(ValueError):
            self.service.connections("https://private.example")
        self.assertEqual(self.http.urls, [])

    def test_label_catalog_is_paginated(self):
        profile = self.service.profile("label", LABEL)
        self.assertTrue(profile.more)
        self.assertEqual(profile.next_offset, 1)  # une seule édition renvoyée malgré limit=25 : ne rien sauter
        self.assertFalse(self.service.profile("label", LABEL, profile.next_offset).more)
        self.assertIn("offset=1", self.http.urls[-1])

    def test_invalid_identity_kind_and_page_never_reach_network(self):
        for kind, value, page in (("artist", "https://localhost/", 0), ("url", GROUP, 0),
                                  ("artist", GROUP, -1), ("label", LABEL, 25001)):
            with self.assertRaises(ValueError):
                self.service.profile(kind, value, page)
        self.assertEqual(self.http.urls, [])

    def test_local_matches_are_separate_for_each_account(self):
        seen = []
        def search(user, query):
            seen.append(user)
            return {"albums": [{"id": user, "name": "Arrival", "artist": "ABBA"},
                               {"id": "wrong", "name": "Arrival Live", "artist": "ABBA"}], "songs": []}
        self.service.library = SimpleNamespace(search=search)
        self.assertEqual(self.service.local("alice", "Arrival", "ABBA")["albums"][0]["id"], "alice")
        self.assertEqual(self.service.local("bob", "Arrival", "ABBA")["albums"][0]["id"], "bob")
        self.assertEqual(seen, ["alice", "bob"])

    def test_pacer_spaces_requests_even_across_callers(self):
        now, sleeps = [0], []
        def sleep(delay):
            sleeps.append(delay)
            now[0] += delay
        pacer = MusicBrainzPacer(clock=lambda: now[0], sleep=sleep)
        for _ in range(3):
            pacer.wait()
        self.assertEqual(len(sleeps), 2)
        self.assertGreaterEqual(sum(sleeps), 2)

    def test_concurrent_requests_only_fetch_once(self):
        # Les connexions SQLite sont propres à chaque fil, comme dans le serveur HTTP.
        barrier = threading.Barrier(4)
        errors = []
        def request():
            try:
                barrier.wait(timeout=5)
                self.metadata.get("label/" + LABEL)
            except Exception as error:
                errors.append(error)
            finally:
                self.db.close()
        workers = [threading.Thread(target=request) for _ in range(4)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=5)
        self.assertFalse(any(worker.is_alive() for worker in workers))
        self.assertEqual(errors, [])
        self.assertEqual(len(self.http.urls), 1)

    def test_migration_preserves_an_existing_database(self):
        path = os.path.join(self.temp.name, "old.db")
        old = Database(path, MIGRATIONS[:14])
        old.execute("INSERT INTO users (username, subsonic_salt, subsonic_token, is_admin, created_at, last_seen_at) "
                    "VALUES ('existing', 'salt', 'token', 0, 1, 1)")
        old.close()
        upgraded = Database(path, MIGRATIONS)
        self.addCleanup(upgraded.close)
        self.assertEqual(upgraded.version, len(MIGRATIONS))
        self.assertEqual(upgraded.one("SELECT username FROM users")[0], "existing")
        self.assertEqual(upgraded.query("SELECT * FROM music_metadata"), [])


class ExplorationHttpTest(WebAppTestCase):
    def setUp(self):
        super().setUp()
        self.http = FakeMusicBrainz()
        self.app.exploration.metadata.fetcher = self.http

    def test_authentication_on_every_route(self):
        for route in ("album?id=al1", "profile?kind=label&id=" + LABEL, "local?title=Arrival",
                      "connections?id=" + GROUP, "artists?name=ABBA"):
            self.assertEqual(self.client().get("/api/explore/" + route).status, 401)
        self.assertEqual(self.http.urls, [])

    def test_group_member_other_projects_http_path(self):
        bob = self.client("bob", "pw2")
        matches = bob.get("/api/explore/artists?name=ABBA")
        self.assertEqual(len(matches.json()["artists"]), 2)
        band = bob.get("/api/explore/connections?id=" + GROUP)
        self.assertEqual(band.status, 200)
        member = band.json()["relations"][0]
        self.assertEqual((member["id"], member["role"]), (MEMBER, "member"))
        person = bob.get("/api/explore/connections?id=" + member["id"])
        self.assertEqual({r["id"] for r in person.json()["relations"]}, {GROUP, SIDE_GROUP})
        self.assertEqual(bob.get("/api/explore/connections?id=bad").status, 400)
        self.assertEqual(bob.get("/api/explore/artists?name=").status, 400)

    def test_album_to_label_to_local_album(self):
        bob = self.client("bob", "pw2")
        response = bob.get("/api/explore/album?id=al1&release=" + RELEASE)
        self.assertEqual(response.status, 200, response.body)
        self.assertEqual(response.json()["labels"][0]["name"], "Polar")
        response = bob.get("/api/explore/profile?kind=label&id=" + LABEL)
        self.assertEqual(response.json()["works"][0]["title"], "Arrival")
        response = bob.get("/api/explore/local?title=Arrival&artist=ABBA")
        self.assertEqual([a["id"] for a in response.json()["albums"]], ["al1"])

    def test_vitalic_editions_are_returned_through_the_authenticated_route(self):
        self.app.exploration.folders = SimpleNamespace(album=lambda user, album_id: {
            "name": "Dissidaence Episode 2", "artist": "Vitalic"})
        self.http.editions = [dict(EDITION, title="Dissidænce Episode 2", **{
            "artist-credit": [{"name": "Vitalic", "artist": {"id": GROUP, "name": "Vitalic"}}]})]
        response = self.client("bob", "pw2").get("/api/explore/album?id=al1")
        self.assertEqual(response.status, 200)
        self.assertEqual([e["title"] for e in response.json()["editions"]], ["Dissidænce Episode 2"])

    def test_bad_input_is_refused(self):
        bob = self.client("bob", "pw2")
        for route in ("profile?kind=artist&id=bad", "profile?kind=label&id=" + LABEL + "&offset=-1",
                      "local?title=", "album?id=al1&release=bad"):
            self.assertEqual(bob.get("/api/explore/" + route).status, 400, route)
        self.assertEqual(self.http.urls, [])

    def test_unknown_local_album_does_not_query_musicbrainz(self):
        bob = self.client("bob", "pw2")
        self.assertEqual(bob.get("/api/explore/album?id=unknown").status, 404)
        self.assertEqual(self.http.urls, [])

    def test_failure_keeps_the_local_album_available(self):
        bob = self.client("bob", "pw2")
        self.http.down = True
        response = bob.get("/api/explore/album?id=al1")
        self.assertEqual((response.status, response.json()["error"]), (503, "explore.unavailable"))
        self.assertEqual(bob.get("/api/album?id=al1").status, 200)

    def test_stale_album_credits_still_return_200_during_an_outage(self):
        bob = self.client("bob", "pw2")
        path = "/api/explore/album?id=al1&release=" + RELEASE
        self.assertEqual(bob.get(path).status, 200)
        now = self.app.exploration.metadata.clock()
        self.app.exploration.metadata.clock = lambda: now + 8 * 86400
        self.http.down = True
        response = bob.get(path)
        self.assertEqual(response.status, 200, response.body)
        self.assertTrue(response.json()["stale"])
        self.assertEqual(response.json()["labels"][0]["name"], "Polar")
