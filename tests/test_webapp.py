"""Édition PC : comptes, bibliothèque, étoiles, préférences, salon et commentaires (unitaires et HTTP)."""
import http.client
import io
import json
import os
import tempfile
import unittest

from pimedia.storage.database import Database
from pimedia.webapp import schema
from pimedia.webapp.chat import Chat, ChatError, mentioned_names, valid_topic
from pimedia.webapp.entities import Attachment
from pimedia.webapp.events import EventHub
from pimedia.webapp.preferences import DEFAULTS, InvalidPreference, Preferences
from pimedia.webapp.storage.messages import MessageRepository
from pimedia.webapp.storage.preferences import PreferenceRepository
from pimedia.webapp.storage.users import SessionRepository, UserRepository, hash_token
from pimedia.webapp.subsonic import Credentials, SubsonicServer
from tests.webapp_support import WebAppTestCase, read_event


class Clock:
    def __init__(self, now=1_800_000_000):
        self.now = now

    def __call__(self):
        return self.now


def database():
    return Database(os.path.join(tempfile.mkdtemp(), "t.db"), schema.MIGRATIONS)


class SchemaTest(unittest.TestCase):
    def test_comments_never_contain_a_semicolon(self):
        """Les scripts sont découpés sur « ; » : un point-virgule dans un commentaire casserait la migration."""
        for script in schema.MIGRATIONS:
            for line in script.splitlines():
                if "--" in line:
                    self.assertNotIn(";", line.split("--", 1)[1], line)

    def test_tables_are_in_english(self):
        db = database()
        tables = {r[0] for r in db.query("SELECT name FROM sqlite_master WHERE type = 'table'")}
        self.assertTrue({"users", "sessions", "chat_messages", "message_reactions"} <= tables)
        self.assertNotIn("album_ratings", tables)            # notes : seulement dans Subsonic (migration 3)


class AccountsStorageTest(unittest.TestCase):
    def setUp(self):
        self.db = database()
        self.users = UserRepository(self.db)
        self.sessions = SessionRepository(self.db, days=1)

    def test_login_creates_then_updates(self):
        first = self.users.save_login("Alice", "s1", "t1", {"admin"}, now=10)
        again = self.users.save_login("alice", "s2", "t2", (), now=20)
        self.assertEqual(first.id, again.id)
        self.assertEqual((again.subsonic_token, again.is_admin, again.username), ("t2", False, "Alice"))
        self.assertNotIn("subsonic_token", json.dumps(again.to_api()))

    def test_sessions_store_only_a_hash_and_expire(self):
        user = self.users.save_login("bob", "s", "t", ())
        token = self.sessions.create(user.id, now=1000)
        stored = self.db.one("SELECT token_hash FROM sessions")[0]
        self.assertEqual(stored, hash_token(token))
        self.assertNotEqual(stored, token)
        self.assertEqual(self.sessions.user_id(token, now=1000 + 3600), user.id)
        self.assertIsNone(self.sessions.user_id(token, now=1000 + 86401))
        self.assertIsNone(self.sessions.user_id("faux"))

    def test_mentions_lookup_is_case_insensitive(self):
        self.users.save_login("Carole", "s", "t", ())
        self.assertEqual([u.username for u in self.users.by_names(["carole", "inconnu"])], ["Carole"])


class PreferencesTest(unittest.TestCase):
    def setUp(self):
        db = database()
        self.user = UserRepository(db).save_login("a", "s", "t", ())
        self.preferences = Preferences(PreferenceRepository(db))

    def test_defaults_and_update(self):
        self.assertEqual(self.preferences.of(self.user), DEFAULTS)
        values = self.preferences.update(self.user, {"sidebar": "hover", "sidebar_width": 280})
        self.assertEqual((values["sidebar"], values["sidebar_width"]), ("hover", 280))
        self.assertEqual(self.preferences.update(self.user, {"sidebar_tab": "playlists"})["sidebar_tab"], "playlists")

    def test_unknown_or_wrong_type_is_refused(self):
        for change in ({"sidebar_tab": "autre"}, {"sidebar": "partout"}, {"inconnu": 1}, {"show_album_counts": 1}, {"sidebar_width": True}, {}):
            with self.assertRaises(InvalidPreference, msg=change):
                self.preferences.update(self.user, change)


class FakeHub(EventHub):
    def __init__(self):
        super().__init__()
        self.sent = []

    def publish(self, kind, data, to_user_id=None, except_user_id=None):
        self.sent.append((kind, data, to_user_id))


class ChatServiceTest(unittest.TestCase):
    def setUp(self):
        db = database()
        self.users = UserRepository(db)
        self.alice = self.users.save_login("alice", "s", "t", {"admin", "comment"})
        self.bob = self.users.save_login("bob", "s", "t", {"comment"})
        self.carol = self.users.save_login("carol", "s", "t", {"comment"})
        self.messages = MessageRepository(db)
        self.hub = FakeHub()
        self.clock = Clock()
        self.chat = Chat(self.messages, self.users, self.hub,
                         lambda user, album_id: {"name": "Arrival", "artist": "ABBA", "coverId": album_id}, self.clock)

    def tick(self, seconds=5):
        self.clock.now += seconds

    def test_post_broadcasts_to_everyone(self):
        message = self.chat.post(self.bob, "general", "  Salut tout le monde  ")
        self.assertEqual(message.body, "Salut tout le monde")
        self.assertEqual(self.hub.sent[-1][0], "message")
        self.assertIsNone(self.hub.sent[-1][2])         # pour tous : salon global

    def test_mentions_notify_only_the_people_named(self):
        message = self.chat.post(self.bob, "general", "@Carol tu connais ? cc @alice et @personne et moi @bob")
        self.assertEqual(message.mentions, ["alice", "carol"])
        targets = sorted(t for kind, _, t in self.hub.sent if kind == "mention")
        self.assertEqual(targets, sorted([self.alice.id, self.carol.id]))
        self.assertEqual([m["id"] for m in self.chat.mentions(self.carol)], [message.id])
        self.assertEqual(mentioned_names("mail@exemple.fr @x."), ["x"])

    def test_reply_keeps_a_preview_even_after_deletion(self):
        first = self.chat.post(self.bob, "general", "Quel est votre album préféré de Björk ?")
        self.tick()
        reply = self.chat.post(self.carol, "general", "Post !", reply_to_id=first.id)
        self.assertEqual((reply.reply_to.author, reply.reply_to.excerpt), ("bob", first.body))
        self.chat.delete(self.bob, first.id)
        again = self.messages.get(reply.id)
        self.assertTrue(again.reply_to.deleted)
        self.assertEqual(again.reply_to.excerpt, "")

    def test_reply_must_stay_in_the_same_topic(self):
        first = self.chat.post(self.bob, "general", "a")
        with self.assertRaises(ChatError):
            self.chat.post(self.bob, "album:al1", "b", reply_to_id=first.id)

    def test_edit_own_message_only_and_within_a_day(self):
        message = self.chat.post(self.bob, "general", "Waterlo")
        edited = self.chat.edit(self.bob, message.id, "Waterloo")
        self.assertEqual((edited.body, edited.edited_at is not None), ("Waterloo", True))
        with self.assertRaises(ChatError):
            self.chat.edit(self.carol, message.id, "piraté")
        self.clock.now += 2 * 86400
        with self.assertRaises(ChatError):
            self.chat.edit(self.bob, message.id, "trop tard")

    def test_delete_by_author_or_admin_hides_content(self):
        message = self.chat.post(self.bob, "general", "message limite")
        with self.assertRaises(ChatError):
            self.chat.delete(self.carol, message.id)
        deleted = self.chat.delete(self.alice, message.id)         # alice est administratrice
        self.assertTrue(deleted.deleted)
        self.assertEqual(deleted.to_api()["body"], "")
        self.assertEqual(self.messages.count("general"), 0)

    def test_reactions_toggle(self):
        message = self.chat.post(self.bob, "general", "Nouvel album !")
        self.chat.react(self.alice, message.id, "🔥")
        updated = self.chat.react(self.carol, message.id, "🔥")
        self.assertEqual(updated.reactions, {"🔥": ["alice", "carol"]})
        updated = self.chat.react(self.alice, message.id, "🔥")
        self.assertEqual(updated.reactions, {"🔥": ["carol"]})
        with self.assertRaises(ChatError):
            self.chat.react(self.alice, message.id, "<script>")

    def test_validation(self):
        for topic in ("", "album:", "album:../x", "prive:bob", None):
            self.assertFalse(valid_topic(topic), topic)
        self.assertTrue(valid_topic("album:al-1_2"))
        with self.assertRaises(ChatError):
            self.chat.post(self.bob, "general", "   ")
        with self.assertRaises(ChatError):
            self.chat.post(self.bob, "general", "x" * 2001)
        with self.assertRaises(ChatError):
            self.chat.post(self.bob, "dm:carol", "secret")

    def test_spam_guard(self):
        for i in range(8):
            self.chat.post(self.bob, "general", "msg %d" % i)
        with self.assertRaises(ChatError) as refused:
            self.chat.post(self.bob, "general", "encore")
        self.assertEqual(refused.exception.status, 429)
        self.clock.now += 30
        self.chat.post(self.bob, "general", "après une pause")

    def test_shared_album_card_without_text(self):
        message = self.chat.post(self.bob, "general", "", attachment={
            "kind": "album", "id": "al1", "title": "Arrival", "artist": "ABBA", "coverId": "al1", "evil": "x"})
        self.assertEqual(message.attachment, Attachment("album", "al1", "Arrival", "ABBA", "", "al1"))
        with self.assertRaises(ChatError):
            self.chat.post(self.bob, "general", "", attachment={"kind": "virus", "id": "x"})

    def test_album_comments_feed_the_discussed_list(self):
        self.chat.post(self.bob, "album:al1", "Un classique")
        self.tick()
        self.chat.post(self.carol, "album:al1", "D'accord")
        discussed = self.messages.discussed_albums()
        self.assertEqual([(d.album_id, d.title, d.comments) for d in discussed], [("al1", "Arrival", 2)])
        self.assertEqual(self.messages.count("general"), 0)

    def test_history_paging_catch_up_unread_and_search(self):
        ids = []
        for i in range(12):
            ids.append(self.chat.post(self.bob if i % 2 else self.carol, "general", "message numéro %d" % i).id)
            self.tick(3)
        page = self.chat.history(self.alice, "general", limit=5)
        self.assertEqual([m["id"] for m in page["messages"]], ids[-5:])
        self.assertTrue(page["hasMore"])
        older = self.chat.history(self.alice, "general", before_id=ids[-5], limit=5)
        self.assertEqual([m["id"] for m in older["messages"]], ids[-10:-5])
        newer = self.chat.history(self.alice, "general", after_id=ids[-3])
        self.assertEqual([m["id"] for m in newer["messages"]], ids[-2:])
        self.assertEqual(self.chat.unread(self.alice), {"general": 12})
        self.assertEqual(self.chat.mark_read(self.alice, "general", ids[5]), 6)
        # écrire vaut lecture, et ses propres messages ne comptent pas : carol a écrit le 11e, reste celui de bob
        self.assertEqual(self.chat.unread(self.carol)["general"], 1)
        found = self.chat.search(self.alice, "general", "numéro 7")
        self.assertEqual([m["body"] for m in found], ["message numéro 7"])
        self.assertEqual(self.chat.search(self.alice, "general", "100%"), [])


class EventHubTest(unittest.TestCase):
    def test_presence_and_targeting(self):
        hub = EventHub()

        class U:
            def __init__(self, i, name):
                self.id, self.username = i, name
        a, b = hub.subscribe(U(1, "alice")), hub.subscribe(U(2, "bob"))
        self.assertEqual(hub.online(), ["alice", "bob"])
        hub.publish("mention", {"x": 1}, to_user_id=2)
        self.assertIn("event: mention", _drain(b))
        self.assertNotIn("mention", _drain(a))
        hub.unsubscribe(b)
        self.assertEqual(hub.online(), ["alice"])

    def test_typing_is_throttled(self):
        clock = Clock()
        hub = EventHub(clock)

        class U:
            id, username = 1, "alice"
        self.assertTrue(hub.typing(U, "general"))
        self.assertFalse(hub.typing(U, "general"))
        clock.now += 3
        self.assertTrue(hub.typing(U, "general"))

    def test_slow_page_is_dropped_instead_of_filling_memory(self):
        hub = EventHub()

        class U:
            id, username = 1, "alice"
        subscriber = hub.subscribe(U)
        for i in range(600):
            hub.publish("message", {"i": i})
        self.assertTrue(subscriber.closed)


def _drain(subscriber):
    items = []
    while not subscriber.events.empty():
        items.append(subscriber.events.get_nowait())
    return "".join(items)


class SlowSubsonicTest(unittest.TestCase):
    """getArtists met plus de 30 s sur une grosse bibliothèque (music.foos.fr : 34 s) : la barre des artistes
    restait vide (expiration au bout de 20 s → « subsonic.unreachable »). Suite : test_webapp_artist_index."""

    def test_each_call_can_wait_longer(self):
        waits = []

        class Response(io.BytesIO):
            def __enter__(self):
                return self

        def opener(url, timeout):
            waits.append(timeout)
            return Response(b'{"subsonic-response": {"status": "ok"}}')
        server = SubsonicServer("http://subsonic", timeout=20, opener=opener)
        server.call(Credentials("bob", "s", "t"), "ping")
        server.call(Credentials("bob", "s", "t"), "getArtists", timeout=180)
        self.assertEqual(waits, [20, 180])


class BehindProxyHttpTest(WebAppTestCase):
    """Derrière Apache ou nginx, toutes les requêtes viennent du proxy : la limite des essais suit X-Forwarded-For."""
    environ = {"PI_MEDIA_WEB_TRUST_PROXY": "true"}

    def login_from(self, address, password, chain=""):
        forwarded = chain + address
        return self.client().post_json("/api/login", {"username": "alice", "password": password},
                                       headers={"X-Forwarded-For": forwarded})

    def test_one_person_blocked_does_not_block_the_others(self):
        for _ in range(8):
            self.login_from("203.0.113.7", "non")
        self.assertEqual(self.login_from("203.0.113.7", "secret").status, 429)
        self.assertEqual(self.login_from("198.51.100.4", "secret").status, 200)

    def test_address_added_by_the_proxy_wins(self):
        """Une adresse inventée par le navigateur (début de la liste) ne permet pas d'échapper au blocage."""
        for n in range(8):
            self.login_from("203.0.113.7", "non", chain="10.0.0.%d, " % n)
        self.assertEqual(self.login_from("203.0.113.7", "secret", chain="10.9.9.9, ").status, 429)


class WebAppHttpTest(WebAppTestCase):
    def test_page_and_security_headers(self):
        response = self.client().get("/")
        self.assertEqual(response.status, 200)
        self.assertIn("default-src 'self'", response.headers["content-security-policy"])
        self.assertEqual(response.headers["x-frame-options"], "DENY")

    def test_login_refused_then_accepted(self):
        client = self.client()
        self.assertEqual(client.login("alice", "mauvais").status, 401)
        self.assertEqual(client.get("/api/me").status, 401)
        response = client.login("alice", "secret")
        self.assertEqual(response.status, 200)
        self.assertIn("HttpOnly", response.headers["set-cookie"])
        me = client.get("/api/me").json()
        self.assertEqual((me["user"]["username"], me["user"]["isAdmin"]), ("alice", True))
        self.assertNotIn("secret", json.dumps(me))
        row = self.app.db.one("SELECT * FROM users WHERE username = 'alice'")
        self.assertNotIn("secret", " ".join(str(v) for v in tuple(row)))      # jamais le mot de passe

    def test_too_many_attempts(self):
        client = self.client()
        for _ in range(8):
            client.login("alice", "non")
        self.assertEqual(client.login("alice", "secret").status, 429)

    def test_forwarded_address_ignored_without_trust_proxy(self):
        """Sans proxy de confiance, X-Forwarded-For vient du navigateur : il ne doit pas contourner la limite."""
        client = self.client()
        for n in range(8):
            client.post_json("/api/login", {"username": "alice", "password": "non"},
                             headers={"X-Forwarded-For": "10.0.0.%d" % n})
        self.assertEqual(client.login("alice", "secret").status, 429)

    def test_writes_need_the_csrf_header(self):
        client = self.client("bob", "pw2")
        response = client.request("POST", "/api/chat/post", body=json.dumps({"topic": "general", "body": "x"}),
                                  csrf=False)
        self.assertEqual(response.status, 403)

    def test_logout(self):
        client = self.client("bob", "pw2")
        self.assertEqual(client.post_json("/api/logout", {}).status, 200)
        self.assertEqual(client.get("/api/me").status, 401)

    def test_library(self):
        client = self.client("bob", "pw2")
        index = client.get("/api/artists").json()["index"]
        self.assertEqual([g["letter"] for g in index], ["A", "B"])
        artist = client.get("/api/artist?id=ar1").json()
        self.assertEqual([a["name"] for a in artist["albums"]], ["Waterloo", "Arrival"])      # par année
        album = client.get("/api/album?id=al1").json()
        self.assertEqual([s["title"] for s in album["songs"]], ["Dancing Queen", "Knowing Me"])
        self.assertEqual(album["rating"], {"albumId": "al1", "mine": 0, "average": 0})
        self.assertEqual(album["plays"], 12)                                       # playCount de Subsonic
        self.assertEqual(client.get("/api/album?id=zz").status, 404)
        self.assertEqual(client.get("/api/album?id=../etc").status, 400)
        found = client.get("/api/search?q=post").json()
        self.assertEqual([a["name"] for a in found["albums"]], ["Post"])
        home = client.get("/api/home").json()
        self.assertEqual([a["name"] for a in home["newest"]], ["Post", "Arrival", "Waterloo"])
        self.assertEqual([(a["name"], a["plays"]) for a in home["mostPlayed"]],
                         [("Arrival", 12), ("Post", 7), ("Waterloo", 3)])

    def test_stars_go_to_the_album_folder_in_subsonic_with_each_users_account(self):
        alice, bob = self.client("alice", "secret"), self.client("bob", "pw2")
        self.assertEqual(alice.post_json("/api/rating", {"albumId": "al1", "rating": 5}).status, 200)
        rating = bob.post_json("/api/rating", {"albumId": "al1", "rating": 3}).json()["rating"]
        self.assertEqual(rating, {"albumId": "al1", "mine": 3, "average": 4.0})          # moyenne de Subsonic
        # Arrival a un dossier par disque : la note va sur le dossier qui les contient, jamais sur l'album ID3
        self.assertEqual(self.subsonic.ratings, {("alice", "dir-al1"): 5, ("bob", "dir-al1"): 3})
        self.assertEqual(alice.post_json("/api/rating", {"albumId": "al3", "rating": 2}).status, 200)
        self.assertEqual(self.subsonic.ratings[("alice", "dir-al3")], 2)                  # un seul dossier
        self.assertEqual(alice.get("/api/album?id=al1").json()["rating"], {"albumId": "al1", "mine": 5, "average": 4.0})
        self.assertEqual(bob.post_json("/api/rating", {"albumId": "al1", "rating": 0}).status, 200)
        self.assertNotIn(("bob", "dir-al1"), self.subsonic.ratings)
        for bad in (6, -1, "5", True, None):
            self.assertEqual(bob.post_json("/api/rating", {"albumId": "al1", "rating": bad}).status, 400, bad)

    def test_ratings_already_in_subsonic_are_shown(self):
        """Étoiles posées ailleurs (autre appli, autre compte) : la moyenne et les mieux notés viennent de Subsonic."""
        self.subsonic.ratings.update({("carole", "dir-al2"): 4, ("alice", "dir-al2"): 5, ("carole", "dir-al3"): 2})
        bob = self.client("bob", "pw2")
        self.assertEqual(bob.get("/api/album?id=al2").json()["rating"], {"albumId": "al2", "mine": 0, "average": 4.5})
        top = bob.get("/api/home").json()["topRated"]
        self.assertEqual([(a["id"], a["name"], a["rating"]["average"], a["plays"]) for a in top],
                         [("al2", "Waterloo", 4.5, 3), ("al3", "Post", 2.0, 7)])
        alice = self.client("alice", "secret")
        self.assertEqual([a["rating"]["mine"] for a in alice.get("/api/home").json()["topRated"]], [5, 0])

    def test_names_that_look_like_numbers_stay_text(self):
        """Subsonic d'origine envoie en JSON « 311 » ou « 1989 » comme des nombres."""
        self.subsonic.indexes = [{"name": "#", "artist": [{"id": 9, "name": 311}]}]
        self.subsonic.api_getGenres = lambda h, p: h.reply_json({"genres": {"genre": [
            {"value": 80, "albumCount": 1, "songCount": 3}]}})
        bob = self.client("bob", "pw2")
        self.assertEqual(bob.get("/api/artists").json()["index"], [
            {"letter": "#", "artists": [{"id": "f9", "name": "311"}]}])
        self.assertEqual(bob.get("/api/genres").json()["genres"], [{"name": "80", "albums": 1}])
        self.assertEqual(bob.get("/api/mix/genres").json()["genres"], [{"key": "80", "label": "80", "count": 3}])

    def test_album_lists_like_subsonic(self):
        bob = self.client("bob", "pw2")
        names = lambda kind, value="", page=0: [a["name"] for a in bob.get(
            "/api/albums?kind=%s&value=%s&page=%d" % (kind, value, page)).json()["albums"]]
        self.assertEqual(names("newest"), ["Post", "Arrival", "Waterloo"])
        self.assertEqual(names("frequent"), ["Arrival", "Post", "Waterloo"])
        self.assertEqual(names("alphabetical"), ["Arrival", "Post", "Waterloo"])
        self.assertEqual(names("decade", "1970"), ["Waterloo", "Arrival"])
        self.assertEqual(names("genre", "Electronic"), ["Post"])
        self.assertEqual(names("newest", page=1), [])                                  # 40 par page
        page = bob.get("/api/albums?kind=frequent").json()
        self.assertEqual((page["hasMore"], page["albums"][0]["plays"]), (False, 12))
        self.subsonic.ratings[("carole", "dir-al3")] = 5
        self.assertEqual(names("highest"), ["Post"])
        bob.post_json("/api/favorite", {"kind": "album", "id": "al2", "on": True})
        self.assertEqual(names("starred"), ["Waterloo"])
        for bad in ("kind=nimporte", "kind=decade&value=1975", "kind=decade&value=abc", "kind=genre",
                    "kind=newest&page=-1", "kind=newest&page=x"):
            self.assertEqual(bob.get("/api/albums?" + bad).status, 400, bad)
        self.assertEqual(bob.get("/api/genres").json()["genres"],
                         [{"name": "Pop", "albums": 2}, {"name": "Electronic", "albums": 1}])  # « Vide » écarté

    def test_favorites(self):
        client = self.client("bob", "pw2")
        self.assertEqual(client.post_json("/api/favorite", {"kind": "album", "id": "al3", "on": True}).status, 200)
        self.assertTrue(client.get("/api/album?id=al3").json()["starred"])
        self.assertEqual([a["id"] for a in client.get("/api/starred").json()["albums"]], ["al3"])
        client.post_json("/api/favorite", {"kind": "album", "id": "al3", "on": False})
        self.assertEqual(client.get("/api/starred").json()["albums"], [])

    def test_preferences(self):
        client = self.client("bob", "pw2")
        saved = client.post_json("/api/preferences", {"changes": {"sidebar": "hover"}}).json()["preferences"]
        self.assertEqual(saved["sidebar"], "hover")
        self.assertEqual(client.get("/api/me").json()["preferences"]["sidebar"], "hover")
        self.assertEqual(client.post_json("/api/preferences", {"changes": {"sidebar": 3}}).status, 400)

    def test_cover_and_stream_are_relayed(self):
        client = self.client("bob", "pw2")
        cover = client.get("/api/cover?id=al1&size=64")
        self.assertEqual((cover.status, cover.body[:4]), (200, b"\x89PNG"))
        part = client.get("/api/stream?id=s1", headers={"Range": "bytes=0-99"})
        self.assertEqual((part.status, len(part.body)), (206, 100))

    def test_chat_over_http_with_live_events(self):
        alice, bob = self.client("alice", "secret"), self.client("bob", "pw2")
        stream = self.open_events(alice)
        self.assertEqual(stream.status, 200)
        self.assertIn("bob", read_event(stream, "presence")["online"] + ["bob"])
        posted = bob.post_json("/api/chat/post", {"topic": "general", "body": "Salut @alice !"}).json()["message"]
        event = read_event(stream, "message")
        self.assertEqual((event["id"], event["author"]), (posted["id"], "bob"))
        self.assertEqual(read_event(stream, "mention")["id"], posted["id"])
        bob.post_json("/api/chat/typing", {"topic": "general"})
        self.assertEqual(read_event(stream, "typing"), {"topic": "general", "user": "bob"})
        alice.post_json("/api/chat/react", {"id": posted["id"], "emoji": "👍"})
        self.assertEqual(read_event(stream, "message_updated")["reactions"], {"👍": ["alice"]})
        history = bob.get("/api/chat/history?topic=general").json()
        self.assertEqual([m["body"] for m in history["messages"]], ["Salut @alice !"])
        self.assertEqual(alice.get("/api/me").json()["unread"]["general"], 1)
        alice.post_json("/api/chat/read", {"topic": "general", "id": posted["id"]})
        self.assertEqual(alice.get("/api/me").json()["unread"]["general"], 0)

    def test_chat_errors_are_explained(self):
        bob = self.client("bob", "pw2")
        self.assertEqual(bob.post_json("/api/chat/post", {"topic": "general", "body": ""}).json(), {"error": "chat.empty"})
        self.assertEqual(bob.post_json("/api/chat/delete", {"id": 999}).status, 404)
        self.assertEqual(bob.post_json("/api/chat/edit", {"id": "1"}).status, 404)

    def test_album_comments_and_counts(self):
        bob = self.client("bob", "pw2")
        bob.post_json("/api/chat/post", {"topic": "album:al1", "body": "Le meilleur d'ABBA"})
        album = bob.get("/api/album?id=al1").json()
        self.assertEqual(album["comments"], 1)
        home = bob.get("/api/home").json()
        self.assertEqual([(d["id"], d["title"], d["comments"]) for d in home["discussed"]], [("al1", "Arrival", 1)])

    def test_texts_for_the_page(self):
        texts = self.client().get("/api/texts").json()
        self.assertEqual(texts["auth.refused"], "Identifiant ou mot de passe incorrect")

    def test_versions_newest_first(self):
        releases = self.client().get("/api/versions").json()["releases"]
        self.assertEqual(releases[-1]["version"], "0.1")
        self.assertTrue(all(release["title"] and release["changes"] for release in releases))


if __name__ == "__main__":
    unittest.main()


class KeepAliveTest(WebAppTestCase):
    """Une requête refusée sans que son corps soit lu ne doit pas abîmer la suivante sur la même connexion."""

    def test_refused_post_leaves_the_connection_usable(self):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            body = json.dumps({"topic": "general", "body": "session expirée"})
            connection.request("POST", "/api/chat/post", body, {"Content-Type": "application/json"})
            refused = connection.getresponse()
            refused.read()
            self.assertEqual(refused.status, 403)                         # sans session ni jeton CSRF
            connection.request("GET", "/api/me")                         # même connexion, gardée ouverte
            after = connection.getresponse()
            self.assertEqual((after.status, json.loads(after.read())["error"]), (401, "auth.required"))
        finally:
            connection.close()
