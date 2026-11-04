"""Édition PC : changer la pochette d'un album (recherche Last.fm, image écrite en cover.jpg dans le dossier de l'album)."""
import os
import stat
import unittest

from pimedia.webapp.covers import CoverError, ImageDownloader, LastFmAlbums, image_extension, is_public_host
from tests.webapp_support import WebAppTestCase

JPEG = b"\xff\xd8\xff\xe0" + bytes(range(100))
PNG = b"\x89PNG\r\n\x1a\n" + bytes(range(100))


class FakeLastFm:
    """Répond comme Last.fm : album.getinfo (l'album exact) et album.search."""

    def __init__(self):
        self.urls = []
        self.down = False
        self.exact = {"name": "Arrival", "artist": "ABBA", "image": [
            {"#text": "https://img/exact-medium.png", "size": "medium"},
            {"#text": "https://img/exact-extralarge.png", "size": "extralarge"}]}
        self.found = [
            {"name": "Arrival", "artist": "Autre", "image": [{"#text": "https://img/autre.png", "size": "extralarge"}]},
            {"name": "Arrival", "artist": "ABBA", "image": [{"#text": "https://img/abba.png", "size": "extralarge"}]},
            {"name": "Sans image", "artist": "ABBA", "image": [{"#text": "", "size": "extralarge"}]},
            {"name": "Vide", "artist": "ABBA", "image": [
                {"#text": "https://img/2a96cbd8b46e442fc41c2b86b821562f.png", "size": "extralarge"}]}]

    def try_get(self, url, timeout=8):
        self.urls.append(url)
        if self.down:
            return None
        if "method=album.getinfo" in url:
            return {"album": self.exact}
        return {"results": {"albummatches": {"album": self.found}}}


class FakeDownloader:
    def __init__(self):
        self.data = JPEG
        self.fetched = []

    def fetch(self, url):
        self.fetched.append(url)
        if self.data is None:
            raise CoverError("cover.download_failed")
        return self.data


class CoverHttpTest(WebAppTestCase):
    def setUp(self):
        super().setUp()
        self.music = os.path.join(self.tmp, "Music")
        self.album = os.path.join(self.music, "ABBA", "Arrival")
        os.makedirs(os.path.join(self.album, "CD1"))
        self.app.covers.music_dir = self.music
        self.lastfm = FakeLastFm()
        self.app.covers.lastfm = LastFmAlbums(self.lastfm, "k3y")
        self.downloader = FakeDownloader()
        self.app.covers.downloader = self.downloader
        self.bob = self.client("bob", "pw2")

    def save(self, url="https://img/x.jpg", album="al1", client=None):
        return (client or self.bob).post_json("/api/cover/save", {"albumId": album, "url": url})

    def cover(self, name="cover.jpg"):
        path = os.path.join(self.album, name)
        if not os.path.exists(path):
            return None
        with open(path, "rb") as image:
            return image.read()

    def test_search_puts_the_exact_album_then_the_same_artist_first(self):
        covers = self.bob.get("/api/cover/search?artist=ABBA&album=Arrival").json()["covers"]
        self.assertEqual([c["url"] for c in covers],
                         ["https://img/exact-extralarge.png", "https://img/abba.png", "https://img/autre.png"])
        self.assertEqual(covers[0]["thumb"], "https://img/exact-medium.png")
        self.assertIn("api_key=k3y", self.lastfm.urls[0])

    def test_search_without_key_or_with_last_fm_down(self):
        self.lastfm.down = True
        response = self.bob.get("/api/cover/search?artist=ABBA&album=Arrival")
        self.assertEqual((response.status, response.json()["error"]), (400, "cover.search_failed"))
        self.app.covers.lastfm = LastFmAlbums(self.lastfm, "")
        response = self.bob.get("/api/cover/search?artist=ABBA&album=Arrival")
        self.assertEqual((response.status, response.json()["error"]), (400, "cover.no_lastfm"))
        self.assertEqual(self.bob.get("/api/cover/status").json(), {"search": False, "writable": True})
        self.assertEqual(self.bob.get("/api/cover/search?artist=&album=Arrival").json()["error"], "cover.bad_term")

    def test_save_writes_cover_jpg_in_the_album_folder(self):
        response = self.save()
        self.assertEqual((response.status, response.json()), (200, {"file": "cover.jpg"}))
        self.assertEqual(self.cover(), JPEG)
        self.assertEqual(self.downloader.fetched, ["https://img/x.jpg"])
        self.assertEqual(stat.S_IMODE(os.stat(os.path.join(self.album, "cover.jpg")).st_mode), 0o664)
        self.assertEqual(sorted(os.listdir(self.album)), ["CD1", "cover.jpg"])           # pas de reste « .part »

    def test_save_by_folder_id_works_too(self):
        self.assertEqual(self.save(album="fdir-al1").status, 200)
        self.assertEqual(self.cover(), JPEG)

    def test_old_cover_is_kept_aside(self):
        self.save()
        self.downloader.data = PNG
        self.assertEqual(self.save().json(), {"file": "cover.png"})
        self.assertEqual((self.cover("cover.png"), self.cover("cover.jpg"), self.cover("cover.jpg.bak")), (PNG, None, JPEG))

    def test_refused_image_leaves_the_old_cover(self):
        self.save()
        self.downloader.data = None
        response = self.save()
        self.assertEqual((response.status, response.json()["error"]), (400, "cover.download_failed"))
        self.assertEqual(self.cover(), JPEG)

    def test_images_of_the_sites_we_show_are_allowed_by_the_csp(self):
        """Les aperçus de Last.fm et la photo de Wikipédia viennent de ces hôtes (relevés sur les vraies API le 31/10/2026) ;
        sans eux dans img-src, le navigateur les bloque et les images restent vides."""
        policy = self.bob.get("/").headers["content-security-policy"]
        for host in ("lastfm-img.freetls.fastly.net", "thumb.wikimedia.org", "upload.wikimedia.org"):
            self.assertIn("https://" + host, policy.split("img-src")[1].split(";")[0])

    def test_needs_the_upload_right_and_the_csrf_header(self):
        self.subsonic.roles["bob"] = {"uploadRole": False}
        bob = self.client("bob", "pw2")
        for refused in (self.save(client=bob), bob.get("/api/cover/status"), bob.get("/api/cover/search?artist=a&album=b")):
            self.assertEqual((refused.status, refused.json()["error"]), (403, "auth.missing_right"))
        alice = self.client("alice", "secret")
        body = b'{"albumId": "al1", "url": "https://img/x.jpg"}'
        self.assertEqual(alice.request("POST", "/api/cover/save", body=body, csrf=False).status, 403)
        self.assertEqual(self.client().get("/api/cover/status").status, 401)
        self.assertEqual(self.downloader.fetched, [])

    def test_explains_why_it_cannot_work(self):
        self.app.covers.music_dir = ""
        self.assertEqual(self.save().json()["error"], "cover.off")
        self.app.covers.music_dir = self.music
        os.rmdir(os.path.join(self.album, "CD1"))
        os.rmdir(self.album)
        self.assertEqual(self.save().json()["error"], "cover.not_found")
        self.assertEqual(self.save(url="").status, 400)

    def test_never_writes_outside_the_music_folder(self):
        self.app.covers.folders.album_path = lambda user, album_id: "../../etc"
        self.assertEqual(self.save().json()["error"], "cover.not_found")
        self.app.covers.folders.album_path = lambda user, album_id: ""
        self.assertEqual(self.save().json()["error"], "cover.not_found")


class ImageDownloaderTest(unittest.TestCase):
    def test_image_types_by_signature(self):
        self.assertEqual((image_extension(JPEG), image_extension(PNG), image_extension(b"GIF89a"), image_extension(b"")),
                         ("jpg", "png", None, None))

    def test_only_public_addresses(self):
        def resolver(address):
            return lambda host, port: [(2, 1, 6, "", (address, 0))]
        for address in ("127.0.0.1", "10.0.0.5", "192.168.1.34", "169.254.169.254", "::1", "0.0.0.0"):
            self.assertFalse(is_public_host("x", resolver(address)), address)
        self.assertTrue(is_public_host("x", resolver("93.184.216.34")))
        self.assertFalse(is_public_host("x", lambda host, port: []))
        self.assertFalse(is_public_host("x", lambda host, port: (_ for _ in ()).throw(OSError())))

    def test_refuses_other_schemes_and_private_hosts(self):
        downloader = ImageDownloader(resolve=lambda host, port: [(2, 1, 6, "", ("127.0.0.1", 0))])
        for url in ("file:///etc/passwd", "ftp://example.com/a.jpg", "http://", "http://localhost/a.jpg", "javascript:alert(1)"):
            with self.assertRaises(CoverError, msg=url) as caught:
                downloader.fetch(url)
            self.assertEqual(caught.exception.args[0], "cover.bad_url")


if __name__ == "__main__":
    unittest.main()
