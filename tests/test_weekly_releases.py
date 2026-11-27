"""Consultation anticipée et abonnements au travers du contrôleur et de SQLite."""
import json
from io import BytesIO
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

from pimedia.server.transport import Request
from pimedia.storage.database import Database
from pimedia.webapp.app import WebApplication
from pimedia.webapp.controllers.weekly_releases import WeeklyReleasesController
from pimedia.webapp.musicbrainz import MusicBrainzMetadata
from pimedia.webapp.schema import MIGRATIONS
from pimedia.webapp.storage.exploration import ExplorationRepository
from pimedia.webapp.storage.weekly_releases import ReleaseSubscriptions
from pimedia.webapp.weekly_releases import WeeklyReleases

GENRE = "8e5474b7-f445-49a7-866d-0f8e34b0a519"
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
        self.result = {"count": 1, "release-groups": [{"id": GROUP, "first-release-date": "2026-11-27",
                       "primary-type": "Album", "title": "A", "artist-credit": [{"name": "B"}]}]}
        client = MusicBrainzMetadata(ExplorationRepository(db), self, clock=lambda: self.now)
        self.controller = WeeklyReleasesController(WeeklyReleases(client, ReleaseSubscriptions(db)))

    def get(self, url):
        self.calls.append(url)
        if "genre/all" in url:
            return {"genre-count": 1, "genres": [{"id": GENRE, "name": "noise rock"}]}
        return self.result

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

    def test_http_routes_require_session_and_csrf(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        app = WebApplication("src", environ={"PI_MEDIA_WEB_SUBSONIC_URL": "http://127.0.0.1:4040"},
                             data_dir=temp.name)
        app.musicbrainz.fetcher = self
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
        reply = request("GET", path + f"?genre={GENRE}&monday=2026-11-23", cookie)
        self.assertEqual(reply.status, 200)
        self.assertEqual(json.loads(reply.body)["albums"][0]["id"], GROUP)


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
                self.assertEqual(upgraded.version, 23)
                self.assertEqual(upgraded.query("SELECT body FROM notifications")[0]["body"], "kept")
                self.assertEqual(ReleaseSubscriptions(upgraded).for_user(1), [])
                self.assertEqual(upgraded.query("PRAGMA foreign_key_check"), [])
            finally:
                upgraded.close()
