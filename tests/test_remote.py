"""Saisie depuis le téléphone : code du QR code, essais limités, serveur séparé qui ne fait que recevoir le texte."""
import json
import unittest
import urllib.error
import urllib.request
from urllib.parse import parse_qs, urlsplit

from pimedia.server.remote import MAX_FAILURES, MAX_SUGGESTIONS, MAX_TEXT, ArtistIndex, RemoteTyping
from tests.support import AppTestCase


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class RemoteTypingTest(unittest.TestCase):
    def test_text_needs_current_code_and_is_cleaned(self):
        typing = RemoteTyping()
        old = typing.code
        typing.receive(old, "Björk\n\x07" + "x" * 500)
        self.assertEqual(typing.snapshot()["text"], ("Björk" + "x" * 500)[:MAX_TEXT])
        typing.renew()
        with self.assertRaises(PermissionError):
            typing.receive(old, "ancien code")              # un QR code déjà scanné ne sert plus après un nouvel affichage
        with self.assertRaises(PermissionError):
            typing.receive(None, "sans code")

    def test_too_many_wrong_codes_lock_for_a_minute(self):
        clock = FakeClock()
        typing = RemoteTyping(clock)
        for _ in range(MAX_FAILURES):
            with self.assertRaises(PermissionError):
                typing.receive("faux", "x")
        with self.assertRaises(OverflowError):
            typing.receive(typing.code, "même le bon code attend")
        clock.now += 61
        typing.receive(typing.code, "ok")
        self.assertEqual(typing.snapshot()["text"], "ok")


ARTISTS = [{"id": "ar3", "name": "Björk"}, {"id": "ar9", "name": "Britney Spears"}, {"id": "ar5", "name": "The Bjorn Again"},
           {"id": "x"}, "pas un artiste"]


class SuggestionsTest(unittest.TestCase):
    def test_name_start_first_then_word_start_accents_ignored(self):
        index = ArtistIndex(ARTISTS)
        self.assertEqual([a["name"] for a in index.suggest("bjo")], ["Björk", "The Bjorn Again"])
        self.assertEqual(index.suggest("b"), [])
        self.assertEqual(len(ArtistIndex({"id": str(i), "name": "Bob %d" % i} for i in range(50)).suggest("bob")),
                         MAX_SUGGESTIONS)

    def test_only_a_suggested_artist_can_be_picked(self):
        typing = RemoteTyping()
        typing.share_artists(ARTISTS)
        self.assertEqual(typing.choose(typing.code, "ar9")["name"], "Britney Spears")
        self.assertEqual(typing.snapshot()["pickVersion"], 1)
        with self.assertRaises(LookupError):
            typing.choose(typing.code, "inconnu")
        with self.assertRaises(PermissionError):
            typing.choose("faux", "ar9")


class PhoneServerTest(AppTestCase):
    def setUp(self):
        super().setUp()
        self.phone = self.app.start_phone_server(0)
        self.addCleanup(self.phone.server.server_close)
        self.addCleanup(self.phone.server.shutdown)

    def phone_url(self, path):
        return "http://127.0.0.1:%d%s" % (self.phone.port, path)

    def post_phone(self, body, path="/tel/text"):
        status, _ = self.phone_answer(body, path)
        return status

    def phone_answer(self, body, path="/tel/text"):
        request = urllib.request.Request(self.phone_url(path), json.dumps(body).encode(),
                                         {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, None

    def test_qr_address_and_text_reach_the_pi(self):
        state = self.client.post_json("/ext/remote", {}).json()
        code = parse_qs(urlsplit(state["url"]).query)["c"][0]
        self.assertTrue(state["url"].endswith(":%d/tel?c=%s" % (self.phone.port, code)))
        self.assertEqual(self.post_phone({"code": code, "text": "Toxic"}), 200)
        after = self.client.get("/ext/remote", csrf=False).json()
        self.assertEqual((after["text"], after["version"]), ("Toxic", state["version"] + 1))

    def test_suggestions_on_the_phone_and_pick_opens_on_the_pi(self):
        self.assertEqual(self.client.post_json("/ext/remote/artists", {"artists": ARTISTS}).json()["count"], 3)
        code = parse_qs(urlsplit(self.client.post_json("/ext/remote", {}).json()["url"]).query)["c"][0]
        status, answer = self.phone_answer({"code": code, "text": "bri"})
        self.assertEqual((status, [a["name"] for a in answer["suggestions"]]), (200, ["Britney Spears"]))
        status, answer = self.phone_answer({"code": code, "id": "ar9"}, "/tel/pick")
        self.assertEqual(status, 200)
        self.assertEqual(self.client.get("/ext/remote", csrf=False).json()["pick"], {"id": "ar9", "name": "Britney Spears"})
        self.assertEqual(self.post_phone({"code": code, "id": "nope"}, "/tel/pick"), 404)
        self.assertEqual(self.client.post_json("/ext/remote/artists", {"artists": []}, csrf=False).status, 403)

    def test_phone_server_offers_nothing_else(self):
        with urllib.request.urlopen(self.phone_url("/tel"), timeout=5) as page:
            self.assertIn("default-src 'none'", page.headers["Content-Security-Policy"])
        for path in ("/", "/ext/remote", "/rest/ping.view", "/control/quit", "/static/js/core.js"):
            with self.assertRaises(urllib.error.HTTPError) as refused:
                urllib.request.urlopen(self.phone_url(path), timeout=5)
            self.assertEqual(refused.exception.code, 404, path)
        self.assertEqual(self.post_phone({"code": "faux", "text": "x"}), 403)

    def test_renewing_needs_the_csrf_header(self):
        self.assertEqual(self.client.post_json("/ext/remote", {}, csrf=False).status, 403)



if __name__ == "__main__":
    unittest.main()
