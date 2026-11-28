"""Images des flux, conservation des articles et relais d'images protégé."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from pimedia.storage.database import Database
from pimedia.webapp.schema import MIGRATIONS
from pimedia.webapp.news import parse_articles
from pimedia.server.podcasts.feeds import FeedError, FeedFetcher
from tests.fake_subsonic import PNG
from tests.test_database_migrations import fill
from tests.webapp_support import WebAppTestCase


def feed_with(content):
    return ('<rss xmlns:media="http://search.yahoo.com/mrss/" '
            'xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel><title>Journal</title>'
            '<item><title>Un disque</title><link>https://journal.example/articles/disque</link>' + content +
            '</item></channel></rss>').encode()


class ArticleImagesTest(unittest.TestCase):
    def image(self, content):
        return parse_articles(feed_with(content))["articles"][0]["image"]

    def test_media_thumbnail_content_and_image_enclosure(self):
        for content in ('<media:thumbnail url="/photo.jpg"/>',
                        '<media:content url="/photo.jpg" medium="image"/>',
                        '<enclosure url="/photo.jpg" type="image/jpeg"/>'):
            with self.subTest(content=content):
                self.assertEqual(self.image(content), "https://journal.example/photo.jpg")

    def test_images_in_wordpress_description_and_encoded_content(self):
        for tag in ("description", "content:encoded"):
            content = '<%s><![CDATA[<p><img src="../image.webp" onerror="bad()"></p>Texte]]></%s>' % (tag, tag)
            self.assertEqual(self.image(content), "https://journal.example/image.webp")

    def test_undeclared_media_prefix_and_atom_xhtml(self):
        rss = feed_with('<media:content url="https://cdn.example/a.jpg"/>').replace(
            b'xmlns:media="http://search.yahoo.com/mrss/" ', b'')
        self.assertEqual(parse_articles(rss)["articles"][0]["image"], "https://cdn.example/a.jpg")
        atom = b'''<feed xmlns="http://www.w3.org/2005/Atom"><title>Journal</title><entry><title>Disque</title>
            <link href="https://journal.example/a"/><content type="xhtml"><div xmlns="http://www.w3.org/1999/xhtml">
            <img src="/atom.png"/></div></content></entry></feed>'''
        self.assertEqual(parse_articles(atom)["articles"][0]["image"], "https://journal.example/atom.png")

    def test_unsafe_images_and_audio_are_ignored(self):
        for address in ("javascript:alert(1)", "data:image/svg+xml,bad", "file:///etc/passwd",
                        "http://127.0.0.1/a", "http://[::1]/a", "http://localhost/a", "https://user:pw@a.example/a"):
            with self.subTest(address=address):
                self.assertEqual(self.image('<media:thumbnail url="%s"/>' % address), "")
        self.assertEqual(self.image('<enclosure url="https://cdn.example/a.mp3" type="audio/mpeg"/>'), "")

    def test_missing_images_and_tracking_pixels_keep_the_article(self):
        self.assertEqual(self.image(""), "")
        content = '<description><![CDATA[<img src="/pixel.gif" width="1" height="1"><img src="/photo.jpg">]]></description>'
        self.assertEqual(self.image(content), "https://journal.example/photo.jpg")


class FakeHttp:
    def __init__(self):
        self.calls = []
        self.data = PNG

    def get_bytes(self, url, **options):
        self.calls.append((url, options))
        return self.data


class FeedImagesProviderTest(unittest.TestCase):
    def test_small_images_also_have_a_bounded_number_of_cache_entries(self):
        http = FakeHttp()
        provider = FeedFetcher(http=http, pacer=SimpleNamespace(wait=lambda: None))
        for index in range(65):
            provider.image("https://cdn.example/%s.png" % index)
        provider.image("https://cdn.example/0.png")
        self.assertEqual(len(http.calls), 66)

    def test_image_is_checked_and_cached_with_public_redirects(self):
        http = FakeHttp()
        provider = FeedFetcher(http=http)
        first = provider.image("https://cdn.example/photo.png")
        second = provider.image("https://cdn.example/photo.png")
        self.assertEqual((first.mime, first.data), ("image/png", PNG))
        self.assertEqual(second, first)
        self.assertEqual(len(http.calls), 1)
        self.assertTrue(http.calls[0][1]["public_only"])

    def test_html_and_oversized_images_are_refused(self):
        http = FakeHttp()
        provider = FeedFetcher(http=http)
        for data in (b'<svg onload="bad()"/>', PNG + b"x" * (5 * 1024 * 1024)):
            http.data = data
            with self.assertRaises(FeedError):
                provider.image("https://cdn.example/bad")


class NewsImageMigrationTest(unittest.TestCase):
    def test_upgrade_from_32_preserves_all_rows_and_children(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "site.db"
            before = Database(path, MIGRATIONS[:32])
            fill(before)
            before.execute("INSERT INTO news_articles(feed_id,link,title,summary,published_at,words) "
                           "VALUES (1,'https://journal.example/a','Titre','Texte',100,' titre ')")
            before.execute("INSERT INTO news_hidden_feeds(user_id,feed_id) VALUES (1,1)")
            tables = [row[0] for row in before.query("SELECT name FROM sqlite_master WHERE type='table'")]
            snapshots = {name: [dict(row) for row in before.query('SELECT * FROM "' + name + '"')] for name in tables}
            before.close()
            after = Database(path, MIGRATIONS)
            self.addCleanup(after.close)
            self.assertEqual(after.one("SELECT image_url FROM news_articles")[0], "")
            for table, rows in snapshots.items():
                current = [dict(row) for row in after.query('SELECT * FROM "' + table + '"')]
                self.assertEqual([{key: row[key] for key in old} for row, old in zip(current, rows)], rows, table)
                self.assertEqual(len(current), len(rows), table)
            self.assertEqual(after.query("PRAGMA foreign_key_check"), [])


class NewsImageHttpTest(WebAppTestCase):
    def setUp(self):
        super().setUp()
        self.http = FakeHttp()
        self.app.news.fetcher = FeedFetcher(http=self.http)
        for feed in self.app.news.repository.feeds():
            self.app.news.repository.remove_feed(feed.id)

    def test_image_relay_is_bound_to_a_stored_article_and_requires_a_session(self):
        client = self.client("bob", "pw2")
        self.http.data = feed_with('<media:thumbnail url="https://cdn.example/a.png"/>')
        self.assertEqual(client.post_json("/api/news/feed/add", {"address": "https://journal.example/feed"}).status, 200)
        article = client.get("/api/news").json()["articles"][0]
        self.assertTrue(article["imageUrl"].startswith("/api/news/image?id="))
        self.http.data = PNG
        image = client.get(article["imageUrl"])
        self.assertEqual((image.status, image.body), (200, PNG))
        self.assertTrue(image.headers["content-type"].startswith("image/png"))
        self.assertEqual(client.get("/api/news/image?id=999999").status, 404)
        self.assertEqual(self.client().get(article["imageUrl"]).status, 401)

    def test_refresh_enriches_existing_articles_without_changing_identity_or_date(self):
        client = self.client("bob", "pw2")
        self.http.data = feed_with("")
        client.post_json("/api/news/feed/add", {"address": "https://journal.example/feed"})
        before = client.get("/api/news").json()["articles"][0]
        self.http.data = feed_with('<media:thumbnail url="https://cdn.example/a.png"/>')
        self.assertEqual(self.app.news.refresh(), 0)
        after = client.get("/api/news").json()["articles"][0]
        self.assertEqual((after["id"], after["publishedAt"]), (before["id"], before["publishedAt"]))
        self.assertTrue(after["imageUrl"])
