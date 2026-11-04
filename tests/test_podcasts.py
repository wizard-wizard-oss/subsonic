"""Tests des podcasts : fonctions pures, annuaires simulés, flux simulés, et accès (Pi seulement)."""
import hashlib
import os
import tempfile
import time
import unittest

from pimedia.server.podcasts.directories import (DirectoryError, DirectoryHub, from_index, from_itunes, index_auth_headers,
                                               is_active, merge_cards, podcast_card)
from pimedia.server.podcasts.feeds import FeedError, FeedReader, check_feed_url, parse_duration, parse_feed, plain_text
from pimedia.storage.database import Database
from pimedia.storage.podcasts import PodcastLibrary
from tests.support import AppTestCase

FEED_URL = "http://93.184.216.34/feed.xml"       # adresse publique (pas de DNS nécessaire)
RSS = """<?xml version="1.0"?>
<rss xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" version="2.0"><channel>
  <title>Histoire de tout</title><itunes:author>Marie</itunes:author>
  <description>&lt;p&gt;Un podcast &lt;b&gt;d'histoire&lt;/b&gt;.&lt;/p&gt;</description>
  <itunes:image href="http://93.184.216.34/cover.jpg"/>
  <item><title>Épisode 2</title><guid>g2</guid><pubDate>Tue, 06 Jan 2026 08:00:00 +0000</pubDate>
    <itunes:duration>1:02:03</itunes:duration><enclosure url="http://93.184.216.34/e2.mp3" type="audio/mpeg"/>
    <description>Deuxième épisode</description></item>
  <item><title>Épisode 1</title><guid>g1</guid><pubDate>Tue, 06 Jan 2025 08:00:00 +0000</pubDate>
    <itunes:duration>754</itunes:duration><enclosure url="http://93.184.216.34/e1.mp3" type="audio/mpeg"/></item>
  <item><title>Sans audio</title><guid>g0</guid></item>
</channel></rss>""".encode("utf-8")


class FakeHttp:
    """Remplace JsonHttp : réponses prévues par morceau d'adresse."""

    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def get(self, url, headers=None, timeout=12):
        self.calls.append((url, headers))
        for part, answer in self.routes.items():
            if part in url:
                if isinstance(answer, Exception):
                    raise answer
                return answer
        return {"results": [], "feeds": []}


class FakeFetcher:
    def __init__(self, data=RSS):
        self.data, self.calls = data, 0

    def fetch(self, url, timeout=15):
        self.calls += 1
        if isinstance(self.data, Exception):
            raise self.data
        return self.data


ITUNES_RESULTS = {"results": [
    {"feedUrl": FEED_URL, "collectionName": "Histoire de tout", "artistName": "Marie", "artworkUrl600": "http://x/a.jpg",
     "primaryGenreName": "History", "trackCount": 50},
    {"feedUrl": "", "collectionName": "Sans flux"},
    {"feedUrl": "http://93.184.216.34/autre.xml", "collectionName": "Autre histoire", "primaryGenreName": "History"}]}


# ---------- fonctions pures ----------
class FeedParsingTest(unittest.TestCase):
    def test_durations(self):
        self.assertEqual(parse_duration("1:02:03"), 3723)
        self.assertEqual(parse_duration("12:30"), 750)
        self.assertEqual(parse_duration("754"), 754)
        self.assertEqual(parse_duration("n'importe quoi"), 0)

    def test_feed_is_parsed_sorted_and_cleaned(self):
        feed = parse_feed(RSS)
        self.assertEqual((feed["title"], feed["author"]), ("Histoire de tout", "Marie"))
        self.assertEqual([e["title"] for e in feed["episodes"]], ["Épisode 2", "Épisode 1"])
        self.assertEqual(feed["episodes"][0]["duration"], 3723)
        self.assertEqual(feed["episodes"][0]["image"], "http://93.184.216.34/cover.jpg")
        self.assertNotIn("<", feed["desc"])
        self.assertNotEqual(feed["episodes"][0]["id"], feed["episodes"][1]["id"])

    def test_invalid_feeds_are_refused(self):
        for bad in (b"pas du xml", b"<html><body/></html>"):
            with self.assertRaises(FeedError):
                parse_feed(bad)

    def test_xml_entities_are_refused(self):
        bomb = b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;">]><rss><channel><title>&b;</title></channel></rss>'
        with self.assertRaises(FeedError):
            parse_feed(bomb)

    def test_plain_text_truncates(self):
        self.assertTrue(plain_text("mot " * 400, 50).endswith("…"))


class UrlGuardTest(unittest.TestCase):
    def test_refuses_local_and_odd_addresses(self):
        for url in ("http://127.0.0.1/x", "http://localhost/x", "http://192.168.1.10/x", "http://10.0.0.5/x",
                    "http://169.254.169.254/latest", "ftp://93.184.216.34/x", "file:///etc/passwd", "javascript:alert(1)", ""):
            with self.assertRaises(FeedError, msg=url):
                check_feed_url(url)

    def test_accepts_public_address(self):
        check_feed_url(FEED_URL)


class DirectoryFunctionsTest(unittest.TestCase):
    def test_index_auth_is_sha1_of_key_secret_date(self):
        headers = index_auth_headers("KEY", "SECRET", now=1700000000)
        self.assertEqual(headers["Authorization"], hashlib.sha1(b"KEYSECRET1700000000").hexdigest())
        self.assertEqual((headers["X-Auth-Key"], headers["X-Auth-Date"]), ("KEY", "1700000000"))

    def test_abandoned_or_empty_feeds_are_dropped(self):
        now = time.time()
        self.assertTrue(is_active({"newestItemPublishTime": now - 86400, "episodeCount": 40}))
        self.assertFalse(is_active({"newestItemPublishTime": now - 900 * 86400}))
        self.assertFalse(is_active({"episodeCount": 1}))
        self.assertTrue(is_active({}))                  # information absente : on garde

    def test_cards_from_both_directories(self):
        card = from_itunes(ITUNES_RESULTS["results"][0])
        self.assertEqual((card["feed"], card["genre"], card["count"]), (FEED_URL, "History", 50))
        card = from_index({"url": "http://f", "title": "T", "artwork": "http://i", "categories": {"1": "News", "2": "Sports", "3": "X"}})
        self.assertEqual((card["image"], card["genre"]), ("http://i", "News, Sports"))

    def test_merge_removes_duplicates_and_unusable_cards(self):
        a = podcast_card("http://f1", "Alpha")
        b = podcast_card("http://f2", "alpha")          # même titre, autre flux
        c = podcast_card("http://f3", "Beta")
        d = podcast_card("", "Sans flux")
        self.assertEqual([x["title"] for x in merge_cards([a, c], [b, d])], ["Alpha", "Beta"])


# ---------- bibliothèque ----------
class LibraryTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = os.path.join(self.dir.name, "pi-media.db")
        self.library = PodcastLibrary(Database(self.path))

    def episode(self, pos, dur=1000, ident="e1"):
        return {"id": ident, "feed": "f", "title": "T", "podcast": "P", "audio": "http://a", "pos": pos, "dur": dur}

    def test_subscriptions_persist(self):
        self.library.subscribe("f", "Titre", "img", "auteur")
        self.assertTrue(PodcastLibrary(Database(self.path)).is_subscribed("f"))
        self.library.unsubscribe("f")
        self.assertFalse(PodcastLibrary(Database(self.path)).is_subscribed("f"))

    def test_partial_listening_can_be_resumed(self):
        self.library.save_progress(self.episode(300))
        self.assertEqual(self.library.resume_list()[0].position_s, 300)

    def test_finished_episode_is_marked_played_and_not_resumed(self):
        self.library.save_progress(self.episode(980))
        self.assertTrue(self.library.progress_of("e1").played)
        self.assertEqual(self.library.resume_list(), [])

    def test_barely_started_episode_is_not_listed(self):
        self.library.save_progress(self.episode(5))
        self.assertEqual(self.library.resume_list(), [])

    def test_hidden(self):
        self.library.hide("f")
        self.assertTrue(PodcastLibrary(Database(self.path)).is_hidden("f"))

    def test_forget_and_resume_order(self):
        self.library.save_progress(self.episode(300, ident="old"))
        self.library.save_progress(self.episode(400, ident="new"))
        self.assertEqual([e.episode_id for e in self.library.resume_list()], ["new", "old"])
        self.library.forget("new")
        self.assertEqual([e.episode_id for e in PodcastLibrary(Database(self.path)).resume_list()], ["old"])


# ---------- annuaires et lecteur de flux ----------
class FakeIndex:
    def __init__(self, enabled, cards=None, error=None):
        self.enabled, self.cards, self.error = enabled, cards or [], error

    def search(self, term):
        if self.error:
            raise self.error
        return self.cards

    def trending(self, category):
        return self.search(category)


class FakeItunes:
    def __init__(self, cards=None, error=None):
        self.cards, self.error = cards or [], error

    def search(self, term):
        if self.error:
            raise self.error
        return self.cards


class HubTest(unittest.TestCase):
    CARD_A = podcast_card("http://a", "A")
    CARD_B = podcast_card("http://b", "B")

    def test_index_is_skipped_without_key(self):
        hub = DirectoryHub(FakeItunes([self.CARD_A]), FakeIndex(False, [self.CARD_B]))
        self.assertEqual([c["title"] for c in hub.search("x")], ["A"])

    def test_both_directories_are_merged(self):
        hub = DirectoryHub(FakeItunes([self.CARD_A]), FakeIndex(True, [self.CARD_B]))
        self.assertEqual([c["title"] for c in hub.search("x")], ["B", "A"])

    def test_one_failing_directory_is_tolerated(self):
        hub = DirectoryHub(FakeItunes([self.CARD_A]), FakeIndex(True, error=DirectoryError("panne")))
        self.assertEqual([c["title"] for c in hub.search("x")], ["A"])

    def test_all_failing_is_an_error_but_cache_survives(self):
        hub = DirectoryHub(FakeItunes([self.CARD_A]), FakeIndex(False))
        hub.search("x")
        hub.itunes.error = DirectoryError("panne")
        hub.cache.ttl = -1
        hub.cache._items = {k: (0, v[1]) for k, v in hub.cache._items.items()}      # tout est périmé
        self.assertEqual(len(hub.search("x")), 1)                                   # ancienne version servie
        with self.assertRaises(DirectoryError):
            hub.search("autre")


class FeedReaderTest(unittest.TestCase):
    def test_feed_is_cached(self):
        fetcher = FakeFetcher()
        reader = FeedReader(fetcher)
        reader.read(FEED_URL)
        reader.read(FEED_URL)
        self.assertEqual(fetcher.calls, 1)

    def test_stale_feed_served_when_network_fails(self):
        fetcher = FakeFetcher()
        reader = FeedReader(fetcher)
        reader.read(FEED_URL)
        reader.cache._items[FEED_URL] = (0, reader.cache._items[FEED_URL][1])
        fetcher.data = FeedError("coupé")
        self.assertEqual(reader.read(FEED_URL)["title"], "Histoire de tout")


# ---------- intégration, mode Pi ----------
class PodcastPiTest(AppTestCase):
    def setUp(self):
        super().setUp()
        service = self.app.podcasts
        self.http = FakeHttp({"itunes.apple.com": ITUNES_RESULTS})
        service.hub.itunes.http = self.http
        service.hub.index.http = self.http
        service.reader.fetcher = FakeFetcher()

    def api(self, name, **params):
        from urllib.parse import urlencode
        return self.client.get("/podcast-api/%s?%s" % (name, urlencode(params)), csrf=False)

    def test_page_is_served_with_assets(self):
        page = self.client.get("/podcasts")
        self.assertEqual(page.status, 200)
        self.assertNotIn(b"{{V}}", page.body)
        self.assertIn(b"pod-app.js", page.body)
        self.assertEqual(self.client.get("/static/js/pod-app.js").status, 200)

    def test_status_lists_themes_and_sources(self):
        status = self.api("status").json()
        self.assertEqual(status["sources"], {"itunes": True, "podcastindex": False})
        self.assertIn("histoire", [t["key"] for t in status["themes"]])

    def test_search_theme_and_short_queries(self):
        items = self.api("search", q="histoire").json()["items"]
        self.assertEqual([i["title"] for i in items], ["Histoire de tout", "Autre histoire"])
        self.assertEqual(self.api("search", q="h").json(), {"items": []})
        self.assertEqual(len(self.api("theme", id="histoire").json()["items"]), 2)
        self.assertEqual([i["title"] for i in self.api("search", q="histoire tout").json()["items"]], ["Histoire de tout"])
        self.assertEqual(self.api("search", q="histoire chocolat").json()["items"], [])
        self.assertEqual(self.api("theme", id="inconnu").status, 502)

    def test_show_lists_episodes(self):
        show = self.api("show", feed=FEED_URL).json()
        self.assertEqual(len(show["episodes"]), 2)
        self.assertFalse(show["subscribed"])

    def test_show_refuses_private_addresses(self):
        self.assertEqual(self.api("show", feed="http://127.0.0.1:8099/rest/ping").status, 502)
        self.assertEqual(self.api("show", feed="http://192.168.0.1/x").status, 502)

    def test_similar_excludes_the_podcast_itself(self):
        items = self.api("similar", feed=FEED_URL, genre="History", title="x").json()["items"]
        self.assertEqual([i["title"] for i in items], ["Autre histoire"])

    def test_subscribe_progress_resume(self):
        post = lambda name, data: self.client.post_json("/podcast-api/" + name, data)
        self.assertEqual(post("subscribe", {"feed": FEED_URL, "title": "Histoire de tout"}).status, 200)
        self.assertTrue(self.api("show", feed=FEED_URL).json()["subscribed"])
        episode = self.api("show", feed=FEED_URL).json()["episodes"][0]
        post("progress", {"id": episode["id"], "feed": FEED_URL, "title": "Épisode 2", "podcast": "Histoire de tout",
                          "audio": episode["audio"], "pos": 600, "dur": 3723})
        home = self.api("home").json()
        self.assertEqual(home["resume"][0]["pos"], 600)
        self.assertEqual(self.api("show", feed=FEED_URL).json()["episodes"][0]["pos"], 600)
        self.assertEqual(post("unsubscribe", {"feed": FEED_URL}).status, 200)
        self.assertFalse(self.api("show", feed=FEED_URL).json()["subscribed"])

    def test_episode_can_be_removed_from_resume_list(self):
        post = lambda name, data, **kw: self.client.post_json("/podcast-api/" + name, data, **kw)
        episode = self.api("show", feed=FEED_URL).json()["episodes"][0]
        post("progress", {"id": episode["id"], "feed": FEED_URL, "title": "Épisode 2", "podcast": "Histoire de tout",
                          "audio": episode["audio"], "pos": 600, "dur": 3723})
        self.assertEqual(len(self.api("home").json()["resume"]), 1)
        self.assertEqual(post("forget", {"id": episode["id"]}, csrf=False).status, 403)
        self.assertEqual(post("forget", {"id": episode["id"]}).status, 200)
        self.assertEqual(self.api("home").json()["resume"], [])
        self.assertEqual(self.api("show", feed=FEED_URL).json()["episodes"][0]["pos"], 0)      # position oubliée
        self.assertEqual(post("forget", {"id": "inconnu"}).status, 200)                        # sans effet, sans erreur

    def test_hidden_podcast_disappears_from_results(self):
        self.client.post_json("/podcast-api/hide", {"feed": FEED_URL})
        titles = [i["title"] for i in self.api("search", q="histoire").json()["items"]]
        self.assertEqual(titles, ["Autre histoire"])

    def test_writes_need_the_csrf_header(self):
        response = self.client.post_json("/podcast-api/subscribe", {"feed": FEED_URL, "title": "x"}, csrf=False)
        self.assertEqual(response.status, 403)

    def test_incomplete_progress_is_refused(self):
        self.assertEqual(self.client.post_json("/podcast-api/progress", {"id": "x"}).status, 400)

    def test_key_can_be_saved_and_enables_podcast_index(self):
        saved = self.client.post_json("/podcast-api/key", {"key": "K", "secret": "S"}).json()
        self.assertTrue(saved["sources"]["podcastindex"])
        self.assertEqual(self.app.config.get("podcastindex_key"), "K")
        self.http.routes["podcastindex.org"] = {"feeds": [{"url": "http://93.184.216.34/idx.xml", "title": "Via Index",
                                                         "episodeCount": 20}]}
        self.api("search", q="nouveau")
        called = [h for u, h in self.http.calls if "podcastindex.org" in u][0]
        self.assertEqual(called["X-Auth-Key"], "K")
        cleared = self.client.post_json("/podcast-api/key", {"key": "", "secret": ""}).json()
        self.assertFalse(cleared["sources"]["podcastindex"])

    def test_key_needs_both_values_in_ui_but_api_stores_what_it_gets(self):
        self.assertEqual(self.client.post_json("/podcast-api/key", {"key": "K", "secret": ""}).status, 200)
        self.assertFalse(self.api("status").json()["sources"]["podcastindex"])


# ---------- le mode serveur n'a aucun podcast ----------
if __name__ == "__main__":
    unittest.main()
