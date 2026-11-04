"""Ajouts depuis le téléphone : fichier envoyé, lien partagé."""
import io
import json
import os
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from urllib.parse import parse_qs, urlsplit

from pimedia.entities import Track
from pimedia.server.links import LinkError, LinkResolver
from pimedia.server.phone_files import PhoneFiles, UploadError, title_from_filename
from pimedia.server.podcasts.directories import DirectoryError
from pimedia.server.transport import parse_range
from pimedia.tracks import clean_track
from tests.support import AppTestCase


class PhoneFilesTest(unittest.TestCase):
    def setUp(self):
        self.files = PhoneFiles(os.path.join(tempfile.mkdtemp(prefix="pm-files-"), "phone-files"))

    def test_save_and_read_back(self):
        name, title = self.files.save(io.BytesIO(b"ID3" + b"x" * 1000), 1003, "03 - Mon_titre préféré.mp3")
        self.assertEqual(title, "Mon titre préféré")
        self.assertTrue(name.endswith(".mp3"))
        with open(self.files.path_of(name), "rb") as f:
            self.assertEqual(len(f.read()), 1003)
        self.assertEqual(self.files.content_type(name), "audio/mpeg")

    def test_refusals(self):
        with self.assertRaises(UploadError):
            self.files.save(io.BytesIO(b"x"), 1, "virus.exe")
        with self.assertRaises(UploadError):
            self.files.save(io.BytesIO(b""), 0, "vide.flac")
        with self.assertRaises(UploadError):
            self.files.save(io.BytesIO(b"court"), 1000, "coupé.flac")            # envoi interrompu
        self.assertEqual(os.listdir(self.files.directory), [])                  # aucun reste
        for bad in ("../../etc/passwd", "abc.mp3", "", None):
            self.assertIsNone(self.files.path_of(bad))

    def test_purge_old_files(self):
        name, _ = self.files.save(io.BytesIO(b"x" * 10), 10, "a.ogg")
        old = time.time() - 8 * 86400
        os.utime(self.files.path_of(name), (old, old))
        self.files.purge()
        self.assertIsNone(self.files.path_of(name))

    def test_titles(self):
        self.assertEqual(title_from_filename("12. Song.flac"), "Song")
        self.assertEqual(title_from_filename(".flac"), "Titre envoyé")


class SmallPiecesTest(unittest.TestCase):
    def test_ranges(self):
        self.assertEqual(parse_range("bytes=0-99", 1000), (0, 99))
        self.assertEqual(parse_range("bytes=900-", 1000), (900, 999))
        self.assertEqual(parse_range("bytes=-100", 1000), (900, 999))
        self.assertEqual(parse_range("bytes=990-5000", 1000), (990, 999))
        for bad in ("", "bytes=5-2", "bytes=a-b", "items=0-1", "bytes=0-1,5-6", "bytes=2000-"):
            self.assertIsNone(parse_range(bad, 1000), bad)

    def test_phone_file_addresses_are_the_only_local_ones(self):
        self.assertEqual(clean_track({"id": "u", "title": "T", "streamUrl": "/phone-files/0123456789abcdef.mp3"})["streamUrl"],
                         "/phone-files/0123456789abcdef.mp3")
        for bad in ("/etc/passwd", "/phone-files/../config", "file:///x", "/rest/deleteUser"):
            with self.assertRaises(ValueError, msg=bad):
                clean_track({"id": "u", "title": "T", "streamUrl": bad})
        with self.assertRaises(ValueError):
            clean_track({"id": "u", "title": "T", "imageUrl": "/phone-files/0123456789abcdef.mp3"})


class FakeHttp:
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def get(self, url, headers=None, timeout=12):
        self.calls.append(url)
        for part, answer in self.routes.items():
            if part in url:
                if isinstance(answer, Exception):
                    raise answer
                return answer
        raise DirectoryError("inconnu")


LIBRARY = [Track.from_api({"id": "s9", "title": "L.A. Woman", "artist": "The Doors"}),
           Track.from_api({"id": "s8", "title": "Riders on the Storm", "artist": "The Doors"})]


class LinkResolverTest(unittest.TestCase):
    def resolver(self, routes, library=LIBRARY, youtube=()):
        self.http = FakeHttp(routes)
        return LinkResolver(self.http, lambda text: [t for t in library if any(w in t.title.lower() for w in text.lower().split())],
                            lambda text: list(youtube))

    def test_youtube_link_prefers_the_library(self):
        r = self.resolver({"youtube.com/oembed": {"title": "The Doors - L.A. Woman (Official Audio)", "author_name": "The Doors - Topic"}})
        for link in ("https://www.youtube.com/watch?v=abcdefghijk", "https://youtu.be/abcdefghijk?si=x",
                     "https://music.youtube.com/watch?v=abcdefghijk&list=1"):
            track, source = r.resolve(link)
            self.assertEqual((track.id, source), ("s9", "library"))
        self.assertNotIn("youtu.be/abcdefghijk?si", self.http.calls[0])      # jamais l'adresse donnée par le téléphone

    def test_youtube_link_not_in_library_plays_the_video(self):
        r = self.resolver({"youtube.com/oembed": {"title": "Inédit live", "author_name": "Quelqu'un"}})
        track, source = r.resolve("https://www.youtube.com/shorts/abcdefghijk")
        self.assertEqual((track.youtube_id, source), ("abcdefghijk", "youtube"))

    def test_deezer_apple_spotify(self):
        r = self.resolver({"api.deezer.com/track/3135556": {"title": "Riders on the Storm", "artist": {"name": "The Doors"}},
                           "itunes.apple.com/lookup?id=1440": {"results": [{"trackName": "L.A. Woman", "artistName": "The Doors"}]},
                           "open.spotify.com/oembed": {"title": "Riders on the Storm"}})
        self.assertEqual(r.resolve("https://www.deezer.com/fr/track/3135556")[0].id, "s8")
        self.assertEqual(r.resolve("https://music.apple.com/fr/album/l-a-woman/1440?i=1440")[0].id, "s9")
        self.assertEqual(r.resolve("https://open.spotify.com/track/7ap?si=abc")[0].id, "s8")

    def test_youtube_search_when_not_in_library(self):
        found = Track.from_api({"id": "yt-zz", "youtubeId": "zzzzzzzzzzz", "title": "Toxic", "ext": "youtube"})
        r = self.resolver({"api.deezer.com": {"title": "Toxic", "artist": {"name": "Britney Spears"}}}, youtube=[found])
        self.assertEqual(r.resolve("https://deezer.com/track/1")[0].id, "yt-zz")

    def test_refusals(self):
        r = self.resolver({"api.deezer.com": {"title": "Introuvable", "artist": {"name": "X"}}})
        for bad in ("pas un lien", "ftp://x", "https://example.com/track/1", "https://www.youtube.com/watch?v=court"):
            with self.assertRaises(LinkError, msg=bad):
                r.resolve(bad)
        with self.assertRaises(LinkError):
            r.resolve("https://deezer.com/track/1")                         # ni bibliothèque ni YouTube
        broken = self.resolver({"api.deezer.com": DirectoryError("panne")})
        with self.assertRaises(LinkError):
            broken.resolve("https://deezer.com/track/1")


class PhoneUploadApiTest(AppTestCase):
    def setUp(self):
        super().setUp()
        self.phone_server = self.app.start_phone_server(0)
        self.addCleanup(self.phone_server.server.server_close)
        self.addCleanup(self.phone_server.server.shutdown)
        url = self.client.post_json("/ext/remote", {}).json()["url"]
        self.code = parse_qs(urlsplit(url).query)["c"][0]

    def upload(self, data, filename, code=None):
        request = urllib.request.Request("http://127.0.0.1:%d/tel/upload" % self.phone_server.port, data=data, method="POST",
                                         headers={"X-Code": code or self.code, "X-File-Name": urllib.request.quote(filename),
                                                  "X-Mode": "end", "Content-Type": "application/octet-stream"})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read() or b"{}")

    def test_upload_then_screen_plays_it_with_seeking(self):
        status, answer = self.upload(b"fLaC" + bytes(range(256)) * 40, "Ma chanson.flac")
        self.assertEqual((status, answer["added"]), (200, "Ma chanson"))
        request = self.client.post_json("/queue/take", {}).json()["requests"][0]
        self.assertEqual((request["mode"], request["track"]["ext"]), ("end", "upload"))
        url = request["track"]["streamUrl"]
        self.assertTrue(url.startswith("/phone-files/"))
        whole = self.client.get(url, csrf=False)
        self.assertEqual((whole.status, len(whole.body), whole.headers["content-type"]), (200, 4 + 256 * 40, "audio/flac"))
        part = self.client.get(url, headers={"Range": "bytes=4-7"}, csrf=False)
        self.assertEqual((part.status, part.body, part.headers["content-range"]), (206, bytes([0, 1, 2, 3]), "bytes 4-7/10244"))
        self.assertEqual(self.app.hifi.resolve(url), "http://127.0.0.1:%d%s" % (self.app.bound_port, url))   # lisible par mpv

    def test_upload_refusals(self):
        self.assertEqual(self.upload(b"MZ", "programme.exe")[0], 400)
        self.assertEqual(self.upload(b"fLaC", "x.flac", code="faux")[0], 403)
        self.assertEqual(self.client.get("/phone-files/../pi-media.db", csrf=False).status, 404)
        self.assertEqual(self.client.post_json("/queue/take", {}).json()["requests"], [])


if __name__ == "__main__":
    unittest.main()
