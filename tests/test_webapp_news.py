"""Actualité de l'édition PC : lecture des flux RSS / Atom, ajout et retrait d'un flux, articles d'un artiste."""
import unittest

from pimedia.server.podcasts.feeds import FeedError
from pimedia.webapp.news import NewsError, clean_address, feed_links_in_page, parse_articles
from tests.webapp_support import WebAppTestCase

# flux WordPress typique : « media: » utilisé sans être déclaré (XML refusé tel quel)
RSS = b"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
<title>Webzine</title><link>https://webzine.example/</link>
<item><title>Fontaines D.C. : nouvel album en \xc3\xa9coute</title><link>https://webzine.example/fontaines</link>
<pubDate>Mon, 26 Oct 2026 10:00:00 +0000</pubDate><description><![CDATA[<p>Le groupe <b>revient</b>.</p>]]></description>
<media:content url="https://webzine.example/a.jpg"><media:description type="plain">photo</media:description></media:content></item>
<item><title>Bj\xc3\xb6rk en interview</title><link>https://webzine.example/bjork</link>
<pubDate>Sun, 25 Oct 2026 10:00:00 +0000</pubDate>
<description>Cet article Bj\xc3\xb6rk en interview est apparu en premier sur Webzine.</description></item>
<item><title>Les Fontainesques</title><link>https://webzine.example/autre</link>
<pubDate>Sat, 24 Oct 2026 10:00:00 +0000</pubDate></item>
<item><title>Lien dangereux</title><link>javascript:alert(1)</link></item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0" encoding="utf-8"?><feed xmlns="http://www.w3.org/2005/Atom">
<title>Blog Atom</title><link rel="alternate" href="https://atom.example/"/><link rel="self" href="https://atom.example/feed"/>
<entry><title>Chronique : Bj\xc3\xb6rk, Post</title><link rel="alternate" href="https://atom.example/post"/>
<published>2026-10-20T08:00:00Z</published><summary>Un classique.</summary></entry>
</feed>"""

PAGE = b"""<html><head><link rel="alternate" type="application/rss+xml" href="/comments/feed/">
<link rel="alternate" type="application/rss+xml" title="Flux" href="/feed/"></head><body>Bonjour</body></html>"""


class FakeFeeds:
    """Les sites des tests : adresse -> octets ; une adresse inconnue est injoignable."""

    def __init__(self, pages=None):
        self.pages = dict(pages or {})
        self.asked = []

    def fetch(self, url, timeout=15):
        self.asked.append(url)
        if url not in self.pages:
            raise FeedError("Flux injoignable")
        return self.pages[url]


def numbered_feed(count):
    items = "".join("<item><title>Article %d</title><link>https://many.example/%d</link>"
                    "<pubDate>Mon, 26 Oct 2026 %02d:%02d:00 +0000</pubDate></item>" % (n, n, n // 60, n % 60)
                    for n in range(count))
    return ("<rss><channel><title>Beaucoup</title>%s</channel></rss>" % items).encode()


class FeedReadingTest(unittest.TestCase):
    def test_rss_with_undeclared_prefixes(self):
        feed = parse_articles(RSS)
        self.assertEqual((feed["title"], feed["site"]), ("Webzine", "https://webzine.example/"))
        self.assertEqual([a["link"] for a in feed["articles"]],
                         ["https://webzine.example/fontaines", "https://webzine.example/bjork",
                          "https://webzine.example/autre"])           # le lien javascript: est écarté
        first = feed["articles"][0]
        self.assertEqual((first["title"], first["summary"]), ("Fontaines D.C. : nouvel album en écoute", "Le groupe revient ."))
        self.assertEqual(first["date"], 1793008800)
        self.assertEqual(feed["articles"][1]["summary"], "")             # « Cet article … apparu en premier sur … »

    def test_atom(self):
        feed = parse_articles(ATOM)
        self.assertEqual((feed["title"], feed["site"]), ("Blog Atom", "https://atom.example/"))
        self.assertEqual(feed["articles"], [{"title": "Chronique : Björk, Post", "link": "https://atom.example/post",
                                             "summary": "Un classique.", "date": 1792483200}])

    def test_what_is_not_a_feed_is_refused(self):
        for data in (PAGE, b"pas du xml", b"<html><body/></html>",
                     b'<!DOCTYPE r [<!ENTITY a "aaaa">]><rss><channel/></rss>'):
            with self.assertRaises(NewsError):
                parse_articles(data)

    def test_feeds_announced_by_a_page(self):
        self.assertEqual(feed_links_in_page(PAGE, "https://site.example/page"),
                         ["https://site.example/feed/", "https://site.example/comments/feed/"])

    def test_the_feed_of_the_section_comes_first(self):
        page = b"""<link rel="alternate" type="application/rss+xml" href="https://mag.example/feed/">
        <link rel="alternate" type="application/rss+xml" href="https://mag.example/comments/feed/">
        <link rel="alternate" type="application/rss+xml" href="https://mag.example/musique/feed/">"""
        self.assertEqual(feed_links_in_page(page, "https://mag.example/musique/")[0], "https://mag.example/musique/feed/")
        self.assertEqual(feed_links_in_page(page, "https://mag.example")[0], "https://mag.example/feed/")

    def test_addresses(self):
        self.assertEqual(clean_address(" noisemag.net "), "https://noisemag.net")
        self.assertEqual(clean_address("http://a.example/feed"), "http://a.example/feed")
        for bad in ("", "ftp://a.example", "a b.example", "x" * 501, "https://"):
            with self.assertRaises(NewsError):
                clean_address(bad)


class NewsHttpTest(WebAppTestCase):
    def setUp(self):
        super().setUp()
        self.sites = FakeFeeds({"https://webzine.example/feed/": RSS, "https://webzine.example": PAGE,
                                "https://atom.example/feed": ATOM, "https://html.example": b"<html>rien</html>"})
        self.app.news.fetcher = self.sites                              # jamais les vrais sites pendant les tests
        # flux de départ (Inrocks, Mowno, New Noise) : retirés pour partir d'une liste vide
        for feed in self.app.news.repository.feeds():
            self.app.news.repository.remove_feed(feed.id)

    def add(self, client, address):
        return client.post_json("/api/news/feed/add", {"address": address})

    def test_add_a_site_finds_its_feed_and_reads_it(self):
        bob = self.client("bob", "pw2")
        response = self.add(bob, "webzine.example")
        self.assertEqual(response.status, 200, response.body)
        feed = response.json()["feed"]
        self.assertEqual((feed["url"], feed["title"], feed["articles"], feed["canRemove"]),
                         ("https://webzine.example/feed/", "Webzine", 3, True))
        articles = bob.get("/api/news").json()
        self.assertEqual([a["title"] for a in articles["articles"]],
                         ["Fontaines D.C. : nouvel album en écoute", "Björk en interview", "Les Fontainesques"])
        self.assertEqual((articles["articles"][0]["feed"], articles["more"]), ("Webzine", False))
        self.assertEqual(self.add(bob, "https://webzine.example/feed/").json(), {"error": "news.already_followed"})
        self.assertEqual(self.add(bob, "https://html.example").json(), {"error": "news.no_feed_found"})
        self.assertEqual(self.add(bob, "https://ailleurs.example").json(), {"error": "news.unreachable"})
        self.assertEqual(self.add(bob, "ftp://x").json(), {"error": "news.invalid_address"})
        self.assertEqual(bob.post_json("/api/news/feed/add", {"address": "atom.example/feed"}, csrf=False).status, 403)
        self.assertEqual(self.client().get("/api/news").status, 401)

    def test_articles_about_an_artist(self):
        bob = self.client("bob", "pw2")
        self.add(bob, "webzine.example")
        self.add(bob, "https://atom.example/feed")
        about = lambda name: [a["link"] for a in bob.get("/api/news/artist?name=" + name).json()["articles"]]
        self.assertEqual(about("Fontaines%20D.C."), ["https://webzine.example/fontaines"])     # pas « Fontainesques »
        self.assertEqual(about("Bjork"), ["https://webzine.example/bjork", "https://atom.example/post"])
        self.assertEqual(about("Personne"), [])
        self.assertEqual(bob.get("/api/news/artist?name=").status, 400)

    def test_one_feed_and_more(self):
        self.sites.pages["https://many.example/feed"] = numbered_feed(45)
        bob = self.client("bob", "pw2")
        many = self.add(bob, "https://many.example/feed").json()["feed"]
        self.add(bob, "https://atom.example/feed")
        first = bob.get("/api/news?feed=%d" % many["id"]).json()
        self.assertEqual((len(first["articles"]), first["more"], first["articles"][0]["title"]), (40, True, "Article 44"))
        last = first["articles"][-1]
        rest = bob.get("/api/news?feed=%d&beforeDate=%d&beforeId=%d" % (many["id"], last["publishedAt"], last["id"])).json()
        self.assertEqual(([a["title"] for a in rest["articles"]], rest["more"]),
                         (["Article 4", "Article 3", "Article 2", "Article 1", "Article 0"], False))
        self.assertEqual(len(bob.get("/api/news").json()["articles"]), 40)       # tous les flux mélangés

    def test_who_can_remove_a_feed(self):
        bob, alice = self.client("bob", "pw2"), self.client("alice", "secret")
        by_bob = self.add(bob, "webzine.example").json()["feed"]
        by_alice = self.add(alice, "https://atom.example/feed").json()["feed"]
        seen_by_bob = {f["title"]: f["canRemove"] for f in bob.get("/api/news/feeds").json()["feeds"]}
        self.assertEqual(seen_by_bob, {"Blog Atom": False, "Webzine": True})
        self.assertTrue(all(f["canRemove"] for f in alice.get("/api/news/feeds").json()["feeds"]))   # l'admin
        self.assertEqual(bob.post_json("/api/news/feed/remove", {"id": by_alice["id"]}).json(), {"error": "news.not_yours"})
        self.assertEqual(alice.post_json("/api/news/feed/remove", {"id": by_bob["id"]}).status, 200)
        self.assertEqual([a["feed"] for a in bob.get("/api/news").json()["articles"]], ["Blog Atom"])   # articles oubliés
        self.assertEqual(bob.post_json("/api/news/feed/remove", {"id": 999}).json(), {"error": "news.unknown_feed"})
        self.assertEqual(bob.post_json("/api/news/feed/remove", {"id": "x"}).status, 400)

    def test_each_person_hides_the_feeds_they_do_not_want(self):
        bob, alice = self.client("bob", "pw2"), self.client("alice", "secret")
        webzine = self.add(bob, "webzine.example").json()["feed"]
        self.add(bob, "https://atom.example/feed")
        self.assertTrue(webzine["shown"])                                      # par défaut : tout le monde voit tout
        self.assertEqual(alice.post_json("/api/news/feed/show", {"id": webzine["id"], "shown": False}).status, 200)
        shown = lambda client: {f["title"]: f["shown"] for f in client.get("/api/news/feeds").json()["feeds"]}
        self.assertEqual(shown(alice), {"Blog Atom": True, "Webzine": False})
        self.assertEqual(shown(bob), {"Blog Atom": True, "Webzine": True})     # le flux reste à tout le monde
        feeds_of = lambda client, query="": {a["feed"] for a in client.get("/api/news" + query).json()["articles"]}
        self.assertEqual(feeds_of(alice), {"Blog Atom"})
        self.assertEqual(feeds_of(bob), {"Blog Atom", "Webzine"})
        self.assertEqual(feeds_of(alice, "?feed=%d" % webzine["id"]), {"Webzine"})   # choisi exprès : montré
        about = lambda client: [a["feed"] for a in client.get("/api/news/artist?name=Bjork").json()["articles"]]
        self.assertEqual((about(alice), about(bob)), (["Blog Atom"], ["Webzine", "Blog Atom"]))
        alice.post_json("/api/news/feed/show", {"id": webzine["id"], "shown": True})
        self.assertEqual(feeds_of(alice), {"Blog Atom", "Webzine"})
        self.assertEqual(alice.post_json("/api/news/feed/show", {"id": 999, "shown": False}).json(),
                         {"error": "news.unknown_feed"})
        self.assertEqual(alice.post_json("/api/news/feed/show", {"id": webzine["id"], "shown": "non"}).status, 400)

    def test_hourly_reading_keeps_old_articles_and_notes_problems(self):
        bob = self.client("bob", "pw2")
        self.add(bob, "https://atom.example/feed")
        self.add(bob, "webzine.example")
        self.sites.pages["https://atom.example/feed"] = ATOM.replace(b"</feed>", b"""<entry><title>Nouveau</title>
            <link href="https://atom.example/nouveau"/><updated>2026-10-26T12:00:00Z</updated></entry></feed>""")
        del self.sites.pages["https://webzine.example/feed/"]           # le webzine est en panne
        self.assertEqual(self.app.news.refresh(), 1)
        feeds = {f["title"]: f for f in bob.get("/api/news/feeds").json()["feeds"]}
        self.assertEqual((feeds["Blog Atom"]["articles"], feeds["Blog Atom"]["error"]), (2, ""))
        self.assertEqual((feeds["Webzine"]["articles"], feeds["Webzine"]["error"]), (3, "news.unreachable"))
        self.assertEqual(self.app.news.refresh(), 0)                     # déjà connus : rien en double


class StartingFeedsTest(WebAppTestCase):
    def test_the_site_starts_with_three_webzines_only_the_admin_removes(self):
        feeds = self.client("bob", "pw2").get("/api/news/feeds").json()["feeds"]
        self.assertEqual([(f["title"], f["canRemove"]) for f in feeds],
                         [("Les Inrocks – Musique", False), ("Mowno", False), ("New Noise", False)])
        self.assertIn("https://www.lesinrocks.com/musique/feed/", [f["url"] for f in feeds])
        self.assertTrue(all(f["canRemove"] for f in self.client("alice", "secret").get("/api/news/feeds").json()["feeds"]))


if __name__ == "__main__":
    unittest.main()
