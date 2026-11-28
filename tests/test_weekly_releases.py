"""Consultation anticipée et abonnements au travers du contrôleur et de SQLite."""
import json
from datetime import date, timedelta
from io import BytesIO
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlsplit

from pimedia.server.transport import Request
from pimedia.storage.database import Database
from pimedia.webapp.app import WebApplication
from pimedia.webapp.controllers.weekly_releases import WeeklyReleasesController
from pimedia.shared.providers.metadata import Pacer
from pimedia.shared.providers.musicbrainz.client import GENRE_CATALOG_TTL, MusicBrainz
from pimedia.webapp.schema import MIGRATIONS
from pimedia.webapp.storage.exploration import ExplorationRepository
from pimedia.webapp.storage.weekly_releases import ReleaseSubscriptions
from pimedia.webapp.weekly_releases.service import WeeklyReleases

GENRE = "noise rock"   # un style est identifié par son nom exact dans le catalogue MusicBrainz
GROUP = "aaaaaaaa-1111-4222-8333-444444444444"


class WeeklyTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        db = Database(Path(temp.name) / "web.db", MIGRATIONS)
        for user in ("alice", "bob"):
            db.execute("INSERT INTO users(username, subsonic_salt, subsonic_token, created_at, last_seen_at) "
                       "VALUES (?, '', '', 0, 0)", (user,))
        self.alice, self.bob = SimpleNamespace(id=1), SimpleNamespace(id=2)
        self.calls = []
        self.now = 100000
        self.catalog = "noise rock\ntechno\n"
        self.catalog_failure = None
        self.result = {"count": 1, "release-groups": [{"id": GROUP, "first-release-date": "2026-11-27",
                       "primary-type": "Album", "title": "A", "artist-credit": [{"name": "B"}]}]}
        self.cache = ExplorationRepository(db)
        self.repository = ReleaseSubscriptions(db)
        client = MusicBrainz(self.cache, self, clock=lambda: self.now, sleep=lambda delay: None, pacer=Pacer(0))
        self.controller = WeeklyReleasesController(WeeklyReleases(client, self.repository,
                                                                  today=lambda: date(2026, 11, 27)))

    def get_json(self, url, headers=None):
        self.calls.append(url)
        self.assertEqual(urlsplit(url).path, "/ws/2/release-group")
        return self.result

    def get_text(self, url):
        self.calls.append(url)
        parsed = urlsplit(url)
        self.assertEqual(parsed.path, "/ws/2/genre/all")
        self.assertEqual(parse_qs(parsed.query), {"fmt": ["txt"]})
        if self.catalog_failure:
            raise self.catalog_failure
        return self.catalog

    def test_full_catalog_uses_one_request_and_survives_a_failed_refresh(self):
        self.catalog += "".join(f"style {number}\n" for number in range(2225))
        initial = json.loads(self.controller.genres(None, self.alice).body)
        self.assertEqual(len(initial["genres"]), 2227)
        self.assertEqual(len(self.calls), 1)
        another = MusicBrainz(self.cache, self, clock=lambda: self.now, sleep=lambda delay: None, pacer=Pacer(0))
        self.assertEqual(len(another.release_genres()), 2227)
        self.assertEqual(len(self.calls), 1)
        self.now += GENRE_CATALOG_TTL - 1
        self.assertEqual(len(another.release_genres()), 2227)
        self.assertEqual(len(self.calls), 1)
        self.now += 1
        self.catalog_failure = HTTPError(self.calls[0], 503, "Unavailable", {"Retry-After": "60"}, None)
        self.assertEqual(json.loads(self.controller.genres(None, self.alice).body), initial)
        self.assertEqual(len(self.calls), 2)

    def test_announced_friday_and_cache(self):
        request = SimpleNamespace(param={"genre": GENRE, "monday": "2026-11-23"}.get)
        page = json.loads(self.controller.week(request, self.alice).body)
        self.assertEqual([row["date"] for row in page["albums"]], ["2026-11-27"])
        query = parse_qs(urlsplit(self.calls[-1]).query)["query"][0]
        self.assertIn('tag:"noise rock"', query)
        self.assertIn("firstreleasedate:[2026-11-23 TO 2026-11-29]", query)
        self.assertIn("(primarytype:album OR primarytype:ep)", query)
        self.controller.week(request, self.bob)
        self.assertEqual(len(self.calls), 2)
        self.now += 3601
        self.controller.week(request, self.bob)
        self.assertEqual(len(self.calls), 3)
        with self.assertRaises(ValueError):
            self.controller.week(SimpleNamespace(param={"genre": GENRE, "monday": "2026-11-27"}.get), self.alice)

    def test_filters_incomplete_and_out_of_week_dates_without_skipping_results(self):
        rows = self.result["release-groups"]
        album = rows[0]
        rows.extend(dict(album, **{"first-release-date": value})
                    for value in (None, "2026-11", "2026-11-99", "2026-11-30"))
        self.result["count"] = len(rows) + 1
        request = SimpleNamespace(param={"genre": GENRE, "monday": "2026-11-23"}.get)
        page = json.loads(self.controller.week(request, self.alice).body)
        self.assertEqual([row["date"] for row in page["albums"]], ["2026-11-27"])
        self.assertEqual(page["next"], len(rows))

    def test_personal_subscriptions(self):
        def followed(user):
            return json.loads(self.controller.genres(None, user).body)["followed"]
        for _ in range(2):
            self.controller.follow(None, self.alice, {"genre": GENRE, "enabled": True})
        self.assertEqual(followed(self.alice), [GENRE])
        self.assertEqual(followed(self.bob), [])
        with self.assertRaises(ValueError):
            self.controller.follow(None, self.alice, {"genre": GROUP, "enabled": True})
        self.controller.follow(None, self.alice, {"genre": GENRE, "enabled": False})
        self.assertEqual(followed(self.alice), [])

    def week(self, monday, offset=None):
        params = {"genre": GENRE, "monday": monday, "offset": offset}
        return self.controller.week(SimpleNamespace(param=lambda name, default=None: params.get(name) or default),
                                    self.alice)

    def test_week_far_in_past_or_future_is_refused_without_a_request(self):
        for monday in ("2025-11-17", "2027-12-06"):
            with self.subTest(monday=monday), self.assertRaises(ValueError):
                self.week(monday)
        self.assertEqual(self.calls, [])
        self.week("2025-12-01")

    def test_offset_must_be_a_bounded_multiple_of_the_page(self):
        for offset in ("5", str(WeeklyReleases.PAGE_SIZE * 11)):
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                self.week("2026-11-23", offset)
        self.assertEqual(self.calls, [])
        self.week("2026-11-23", str(WeeklyReleases.PAGE_SIZE * 10))

    def test_default_style_comes_from_the_server(self):
        self.assertEqual(json.loads(self.controller.genres(None, self.alice).body)["default"], "noise rock")

    def test_follow_and_unfollow_by_name_without_duplicates(self):
        self.controller.follow(None, self.alice, {"genre": GENRE, "enabled": True})
        self.controller.follow(None, self.alice, {"genre": GENRE, "enabled": True})
        self.assertEqual(self.repository.for_user(self.alice.id), ["noise rock"])
        genres = json.loads(self.controller.genres(None, self.alice).body)["genres"]
        self.assertIn({"name": "noise rock"}, genres)
        self.controller.follow(None, self.alice, {"genre": GENRE, "enabled": False})
        self.assertEqual(self.repository.for_user(self.alice.id), [])

    def test_http_routes_require_session_and_csrf(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        app = WebApplication("src", environ={"PI_MEDIA_WEB_SUBSONIC_URL": "http://127.0.0.1:4040"},
                             data_dir=temp.name)
        app.musicbrainz.http = self
        app.db.execute("INSERT INTO users(username, subsonic_salt, subsonic_token, created_at, last_seen_at) "
                       "VALUES ('alice', '', '', 0, 0)")
        app.accounts.user_for = lambda token: self.alice if token == "test-token" else None
        path = "/api/news/releases"
        cookie = {"Cookie": "pmw_session=test-token"}
        headers = dict(cookie, **{"X-Requested-With": "pmw"})

        def request(method, route, headers=None, body=None):
            payload = json.dumps(body).encode() if body is not None else b""
            headers = dict(headers or {}, **{"Content-Length": str(len(payload))})
            return app.http.handle(Request(method, route, headers, "127.0.0.1", BytesIO(payload)))

        self.assertEqual(request("GET", path + "/genres").status, 401)
        self.assertEqual(request("GET", path + "/genres", cookie).status, 200)
        body = {"genre": GENRE, "enabled": True}
        self.assertEqual(request("POST", path + "/follow", cookie, body).status, 403)
        self.assertEqual(request("POST", path + "/follow", headers, body).status, 200)
        self.assertEqual(json.loads(request("GET", path + "/genres", cookie).body)["followed"], [GENRE])
        this_monday = date.today() - timedelta(days=date.today().weekday())
        params = urlencode({"genre": GENRE, "monday": this_monday.isoformat()})
        reply = request("GET", path + "?" + params, cookie)
        self.assertEqual(reply.status, 200)
        self.assertEqual(json.loads(reply.body)["albums"][0]["id"], GROUP)
        # radar : lu en base, actualisation limitée (la synchronisation de fond n'est pas lancée ici)
        app.release_sync.spawn = lambda work: None
        radar = path + "/radar?" + urlencode({"monday": this_monday.isoformat()})
        self.assertEqual(request("GET", radar).status, 401)
        calls = len(self.calls)
        self.assertEqual(json.loads(request("GET", radar, cookie).body)["filters"][1]["key"], "style:" + GENRE)
        self.assertEqual(len(self.calls), calls)
        choices = path + "/sources/choices?kind=artist"
        self.assertEqual(request("GET", choices).status, 401)
        self.assertEqual(request("GET", choices, cookie).status, 200)
        self.assertEqual(request("GET", choices + "&offset=-1", cookie).status, 400)
        self.assertEqual(request("POST", path + "/refresh", cookie, {}).status, 403)
        self.assertEqual(request("POST", path + "/refresh", headers, {}).status, 200)
        refused = request("POST", path + "/refresh", headers, {})
        self.assertEqual((refused.status, json.loads(refused.body)["error"]), (429, "weekly.refresh_too_soon"))


class WeeklyReleaseMigrationTest(unittest.TestCase):
    def test_upgrade_from_22_preserves_notifications(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "old.db"
            old = Database(path, MIGRATIONS[:22])
            try:
                old.execute("INSERT INTO users(username, subsonic_salt, subsonic_token, created_at, last_seen_at) "
                            "VALUES ('alice', '', '', 0, 0)")
                old.execute("INSERT INTO notifications(recipient_id, sender_id, client_token, title, body, created_at) "
                            "VALUES (1, 1, 'migration-test', 'Title', 'kept', 1)")
            finally:
                old.close()

            upgraded = Database(path, MIGRATIONS)
            try:
                self.assertEqual(upgraded.version, len(MIGRATIONS))
                self.assertEqual(upgraded.query("SELECT body FROM notifications")[0]["body"], "kept")
                self.assertEqual(ReleaseSubscriptions(upgraded).for_user(1), [])
                self.assertEqual(upgraded.query("PRAGMA foreign_key_check"), [])
            finally:
                upgraded.close()
