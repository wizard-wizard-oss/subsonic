"""Parcours HTTP réels : compte, CSRF, reprise et favoris personnels."""
from tests.webapp_support import WebAppTestCase


class PersonalHomeHttpTest(WebAppTestCase):
    def test_history_is_private_idempotent_and_independent_of_scrobbling(self):
        alice, bob = self.client("alice", "secret"), self.client("bob", "pw2")
        body = dict(id="s1", requestId="a" * 32)
        self.assertEqual(self.client().post_json("/api/listening/history", body).status, 401)
        self.assertEqual(alice.post_json("/api/listening/history", body, csrf=False).status, 403)
        first = alice.post_json("/api/listening/history", body)
        self.assertEqual(first.status, 200)
        self.assertEqual(alice.post_json("/api/listening/history", body).json(), first.json())
        self.assertEqual(self.app.listening_history.page(self.app.users.by_name("bob")).entries, ())
        self.assertEqual(self.subsonic.scrobbles, [])
        mine = alice.get("/api/home/personal").json()
        self.assertEqual(mine["basis"], "history")
        self.assertEqual(mine["seed"]["id"], "s1")
        self.assertNotEqual(bob.get("/api/home/personal").json()["basis"], "history")

    def test_current_queue_song_is_used_without_creating_a_listen(self):
        alice = self.client("alice", "secret")
        alice.post_json("/api/play-queue/save", dict(ids=["s1", "s4"], current="s4", position=42))
        page = alice.get("/api/home/personal").json()
        self.assertEqual((page["basis"], page["seed"]["id"]), ("queue", "s4"))
        self.assertEqual(page["recent"], [])
        self.assertEqual(self.app.listening_history.page(self.app.users.by_name("alice")).entries, ())

    def test_a_queue_without_a_current_track_does_not_imply_a_listen(self):
        alice = self.client("alice", "secret")
        self.subsonic.play_queues["alice"] = dict(ids=["s1", "s4"], current="", position=0)
        self.assertEqual(alice.get("/api/home/personal").json()["basis"], "newest")

    def test_favorites_and_blank_account_use_distinct_sources(self):
        alice, bob = self.client("alice", "secret"), self.client("bob", "pw2")
        original = self.subsonic.api_getStarred2
        self.subsonic.api_getStarred2 = lambda h, p: original(h, p) if p["u"] == "alice" else h.reply_json({"starred2": {}})
        self.assertEqual(alice.get("/api/home/personal").json()["basis"], "newest")
        alice.post_json("/api/favorite", dict(kind="song", id="s1", on=True))
        page = alice.get("/api/home/personal").json()
        self.assertEqual(page["basis"], "favorites")
        self.assertEqual(page["seed"]["id"], "s1")
        self.assertNotEqual(bob.get("/api/home/personal").json()["basis"], "favorites")

    def test_invalid_reference_and_cursor_do_not_write_history(self):
        alice = self.client("alice", "secret")
        self.assertEqual(alice.post_json("/api/listening/history", dict(id="../s1", requestId="a" * 32)).status, 400)
        self.assertEqual(alice.post_json("/api/listening/history", dict(id="missing", requestId="a" * 32)).status, 404)
        self.assertEqual(alice.get("/api/home/personal?before=-1").status, 400)
        self.assertEqual(alice.get("/api/home/personal?before=bad").status, 400)
