"""Transport HTTP unique des services externes : en-têtes, délai, taille, type et adresses publiques."""
import json
import unittest
import urllib.request
from email.message import Message

from pimedia.shared.external import USER_AGENT
from pimedia.shared.providers.http import HttpClient


class FakeResponse:
    def __init__(self, body, content_type="application/json"):
        self.body = body
        self.headers = Message()
        self.headers["Content-Type"] = content_type

    def read(self, size=-1):
        return self.body if size < 0 else self.body[:size]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class Opener:
    def __init__(self, response):
        self.response, self.requests = response, []

    def __call__(self, request, timeout):
        self.requests.append((request, timeout))
        return self.response


def public(host, port):
    return [(None, None, None, None, ("93.184.216.34", 0))]


def private(host, port):
    return [(None, None, None, None, ("192.168.1.10", 0))]


class HttpClientTest(unittest.TestCase):
    def test_json_sends_user_agent_and_timeout(self):
        opener = Opener(FakeResponse(json.dumps({"ok": True}).encode()))
        self.assertEqual(HttpClient(opener=opener, timeout=7).get_json("https://api.test/x", {"X-Key": "k"}),
                         {"ok": True})
        request, timeout = opener.requests[0]
        self.assertEqual(timeout, 7)
        self.assertEqual(request.get_header("User-agent"), USER_AGENT)
        self.assertEqual(request.get_header("Accept"), "application/json")
        self.assertEqual(request.get_header("X-key"), "k")

    def test_text_rejects_html(self):
        opener = Opener(FakeResponse(b"<html>", "text/html"))
        with self.assertRaises(ValueError):
            HttpClient(opener=opener).get_text("https://api.test/genres")
        self.assertEqual(HttpClient(opener=Opener(FakeResponse(b"rock\n", "text/plain"))).get_text("https://a.test"),
                         "rock\n")

    def test_body_over_max_bytes_is_refused(self):
        opener = Opener(FakeResponse(b"x" * 11))
        with self.assertRaises(ValueError):
            HttpClient(opener=opener, max_bytes=10).get_bytes("https://img.test/a.jpg")

    def test_bytes_public_only_refuses_private_hosts(self):
        client = HttpClient(opener=Opener(FakeResponse(b"img")), resolve=private)
        with self.assertRaises(ValueError):
            client.get_bytes("http://router.local/cover.jpg", public_only=True)
        for url in ("ftp://img.test/a.jpg", "file:///etc/passwd", "https:///nohost"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                HttpClient(resolve=public).get_bytes(url, public_only=True)

    def test_bytes_public_only_refuses_private_redirect(self):
        client = HttpClient(resolve=lambda host, port: public(host, port) if host == "img.test" else private(host, port))
        handler = client.public_redirects()
        request = urllib.request.Request("https://img.test/a.jpg")
        with self.assertRaises(ValueError):
            handler.redirect_request(request, None, 302, "Found", {}, "http://192.168.1.1/admin")


if __name__ == "__main__":
    unittest.main()
