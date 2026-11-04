"""Filtre « français » des podcasts."""
import unittest

from pimedia.server.podcasts.directories import from_index, podcast_card
from pimedia.server.podcasts.feeds import FeedError, parse_feed
from pimedia.server.podcasts.relevance import normalize, rank
from pimedia.server.podcasts.language import LanguageResolver, is_french
from tests.support import AppTestCase
from tests.test_podcasts import FakeFetcher, FakeHttp, RSS


class FakeReader:
    def __init__(self, languages):
        self.languages, self.calls = languages, []

    def read(self, url):
        self.calls.append(url)
        answer = self.languages[url]
        if isinstance(answer, Exception):
            raise answer
        return {"language": answer}


class LanguageFunctionsTest(unittest.TestCase):
    def test_is_french(self):
        for code in ("fr", "fr-FR".lower(), "fr_ca"):
            self.assertTrue(is_french(code))
        for code in ("en", "en-us", "fra", "de"):
            self.assertFalse(is_french(code))

    def test_language_comes_from_index_and_feed(self):
        self.assertEqual(from_index({"url": "u", "title": "T", "language": "FR-fr"})["lang"], "fr-fr")
        self.assertEqual(podcast_card("u", "T")["lang"], "")
        feed = parse_feed(RSS.replace(b"<channel>", b"<channel><language>EN-US</language>", 1))
        self.assertEqual(feed["language"], "en-us")


class ResolverTest(unittest.TestCase):
    def test_keeps_french_drops_foreign_keeps_unknown(self):
        reader = FakeReader({"f1": "fr-FR".lower(), "f2": "en-us", "f3": "", "f4": FeedError("x")})
        resolver = LanguageResolver(reader)
        cards = [podcast_card(u, u.upper()) for u in ("f1", "f2", "f3", "f4")]
        cards.append(podcast_card("f5", "Anglais", lang="en"))
        cards.append(podcast_card("f6", "Français", lang="fr"))
        kept = [c["feed"] for c in resolver.french_only(cards)]
        self.assertEqual(sorted(kept), ["f1", "f3", "f4", "f6"])
        self.assertNotIn("f5", reader.calls)                  # langue déjà donnée par l'annuaire : pas de lecture de flux

    def test_each_feed_is_read_once(self):
        reader = FakeReader({"f1": "en"})
        resolver = LanguageResolver(reader)
        cards = [podcast_card("f1", "A")]
        resolver.french_only(cards)
        resolver.french_only(cards)
        self.assertEqual(reader.calls, ["f1"])


class RelevanceTest(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(normalize("  Été, Histoire!! "), " ete histoire ")

    def test_all_words_required_and_ranked(self):
        cards = [podcast_card("a", "Cuisine du monde", desc="recettes et histoire"),
                 podcast_card("b", "Histoire de France", desc="x"),
                 podcast_card("c", "Histoire du sport", desc="x"),
                 podcast_card("d", "Sport", author="Jean", desc="histoire du rugby"),
                 podcast_card("e", "Rien à voir")]
        self.assertEqual([c["feed"] for c in rank(cards, "histoire sport")], ["c", "d"])
        self.assertEqual([c["feed"] for c in rank(cards, "Histoire")], ["b", "c", "a", "d"])
        self.assertEqual([c["feed"] for c in rank(cards, "hist fran")], ["b"])       # début de mot, accents ignorés
        self.assertEqual(rank(cards, "  "), cards)


INDEX_FEEDS = {"feeds": [
    {"url": "http://93.184.216.34/fr.xml", "title": "Bonjour", "description": "salut", "language": "fr", "episodeCount": 10},
    {"url": "http://93.184.216.34/en.xml", "title": "Hello", "description": "salut", "language": "en", "episodeCount": 10}]}


class FrenchOnlyApiTest(AppTestCase):
    def setUp(self):
        super().setUp()
        service = self.app.podcasts
        http = FakeHttp({"podcastindex.org": INDEX_FEEDS})
        service.hub.itunes.http = http
        service.hub.index.http = http
        service.reader.fetcher = FakeFetcher()
        self.client.post_json("/podcast-api/key", {"key": "k", "secret": "s"})

    def titles(self):
        return [i["title"] for i in self.client.get("/podcast-api/search?q=salut", csrf=False).json()["items"]]

    def test_french_only_by_default_and_can_be_switched(self):
        self.assertTrue(self.client.get("/podcast-api/status", csrf=False).json()["french"])
        self.assertEqual(self.titles(), ["Bonjour"])
        response = self.client.post_json("/podcast-api/language", {"french": False})
        self.assertFalse(response.json()["french"])
        self.assertEqual(self.titles(), ["Bonjour", "Hello"])
        self.client.post_json("/podcast-api/language", {"french": True})
        self.assertEqual(self.titles(), ["Bonjour"])

    def test_setting_is_remembered_and_needs_csrf(self):
        self.client.post_json("/podcast-api/language", {"french": False})
        self.assertIs(self.app.config.get("podcast_french"), False)
        self.assertEqual(self.client.post_json("/podcast-api/language", {"french": True}, csrf=False).status, 403)


if __name__ == "__main__":
    unittest.main()
