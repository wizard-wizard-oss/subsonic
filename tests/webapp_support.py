"""Outils des tests de l'édition PC : faux Subsonic (API ID3) + site sur un dossier temporaire."""
import http.client
import os
import shutil
import tempfile
import threading
import unittest
import urllib.parse

from pimedia.webapp.app import WebApplication
from pimedia.webapp.avatars import GravatarUnreachable
from tests.fake_subsonic import PNG, FakeSubsonicFull
from tests.fake_musicbrainz import FakeMusicBrainz
from tests.support import HttpClient, youtube_music_down

PROJECT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")


class FakeGravatar:
    """gravatar.com pour les tests : une photo par adresse (en minuscules), None sans photo ; « down » : injoignable."""

    def __init__(self):
        self.photos = {"alice@exemple.fr": PNG + b"gravatar"}
        self.asked = []
        self.down = False

    def fetch(self, email):
        self.asked.append(email)
        if self.down:
            raise GravatarUnreachable()
        return self.photos.get(email.strip().lower())


class FakeLyricsSites:
    """LRCLIB et lyrics.ovh simulés : chaque adresse demandée est notée."""
    LRC = "[00:01.00]Première ligne\n[00:04.50]Deuxième ligne"

    def __init__(self):
        self.urls = []

    def try_get(self, url, timeout=8):
        self.urls.append(url)
        address = urllib.parse.urlsplit(url)
        query = urllib.parse.parse_qs(address.query)
        title = query.get("track_name", [""])[0]
        if address.hostname == "lrclib.net" and query.get("artist_name") == ["Guy Marchand"]:
            durations = {"Destinée": 275, "Delirium": 180}
            if title in durations:
                song = {"trackName": title, "artistName": "Guy Marchand", "duration": durations[title],
                        "syncedLyrics": self.LRC, "plainLyrics": "Première ligne\nDeuxième ligne"}
                return song if address.path.endswith("/get") else [song]
        if "lrclib.net/api/get" in url and ("Army+of+Me" in url or "Knowing+Me" in url):
            return {"trackName": title, "artistName": query["artist_name"][0],
                    "syncedLyrics": self.LRC, "plainLyrics": "Première ligne\nDeuxième ligne", "duration": 235}
        if "lyrics.ovh" in url and "Waterloo" in url:
            return {"lyrics": "My my, at Waterloo"}
        return None


class FakeInfoSites:
    """Wikipédia et MusicBrainz simulés : ABBA a une page en français (avec photo), Björk aucune (sa biographie vient
    alors de Last.fm, par Subsonic) ; « Arrival » est sorti en 1976 ; « Dancing Queen » a sa page. Adresses notées."""
    PHOTO = "https://upload.wikimedia.org/abba.jpg"
    ABBA = {"type": "standard", "description": "groupe de musique pop suédois",
            "extract": "ABBA est un groupe de pop suédois formé à Stockholm en 1972.\nIl remporte l'Eurovision en 1974.",
            "thumbnail": {"source": PHOTO},
            "content_urls": {"desktop": {"page": "https://fr.wikipedia.org/wiki/ABBA"}}}
    SONG = {"type": "standard", "description": "chanson d'ABBA",
            "extract": "Dancing Queen est une chanson du groupe ABBA, sortie en 1976 sur l'album Arrival. "
                       "C'est le seul numéro un du groupe aux États-Unis, en avril 1977."}

    def __init__(self):
        self.urls = []

    def get(self, url, timeout=8):
        self.urls.append(url)
        if "wikipedia.org/api/rest_v1/page/summary/ABBA" in url and "fr." in url:
            return self.ABBA
        if "/summary/Dancing" in url:
            return self.SONG
        if "w/api.php" in url and "Dancing+Queen" in url:
            return {"query": {"search": [{"title": "Dancing Queen"}]}}
        if "musicbrainz.org" in url and "Arrival" in url:
            return {"release-groups": [{"title": "Arrival", "score": 100, "first-release-date": "1976-10-11"}]}
        raise OSError("introuvable : " + url)

    def try_get(self, url, timeout=8):
        try:
            return self.get(url, timeout)
        except OSError:
            return None


def use_fake_info_sites(app):
    """Biographies et anecdotes : Wikipédia et MusicBrainz simulés (un seul faux pour les deux)."""
    app.facts.wikipedia.fetcher = app.facts.musicbrainz.fetcher = FakeInfoSites()
    return app.facts.wikipedia.fetcher


class WebClient(HttpClient):
    def request(self, method, path, body=None, headers=None, csrf=True):
        headers = dict(headers or {})
        if csrf:
            headers["X-Requested-With"] = "pmw"
        return super().request(method, path, body=body, headers=headers, csrf=False)

    def login(self, username="alice", password="secret"):
        return self.post_json("/api/login", {"username": username, "password": password})


class WebAppTestCase(unittest.TestCase):
    environ = {}                      # réglages en plus (ex. clés YouTube / Jamendo)

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="pmw-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.subsonic = FakeSubsonicFull().start()
        self.addCleanup(self.subsonic.stop)
        self.app = WebApplication(PROJECT, environ=dict(self.environ, PI_MEDIA_WEB_SUBSONIC_URL=self.subsonic.url),
                                  data_dir=self.tmp)
        self.app.lyrics.finder.fetcher = FakeLyricsSites()          # jamais les vrais sites pendant les tests
        self.app.exploration.metadata.fetcher = FakeMusicBrainz()
        self.app.exploration.metadata.sleep = lambda seconds: None
        use_fake_info_sites(self.app)
        self.app.extmusic.youtube.music = youtube_music_down()      # ni YouTube Music
        self.app.avatars.gravatar = FakeGravatar()                  # ni gravatar.com
        self.server = self.app.make_server("127.0.0.1", 0)
        threading.Thread(target=self.server.serve_forever, args=(0.02,), daemon=True).start()
        self.addCleanup(self._stop)
        self.port = self.server.server_address[1]

    def _stop(self):
        self.server.shutdown()
        self.server.server_close()

    def client(self, username=None, password=None):
        client = WebClient(self.port)
        if username:
            response = client.login(username, password)
            assert response.status == 200, response.body
        return client

    def open_events(self, client):
        """Connexion SSE ouverte (lecture ligne à ligne)."""
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        connection.request("GET", "/api/events", headers={"Cookie": client.cookie})
        response = connection.getresponse()
        self.addCleanup(connection.close)
        return response


def read_event(response, kind, limit=50):
    """Lit le flux jusqu'au premier événement « kind » ; renvoie ses données (JSON)."""
    import json
    current = None
    for _ in range(limit * 4):
        line = response.fp.readline().decode("utf-8").rstrip("\n")
        if line.startswith("event: "):
            current = line[7:]
        elif line.startswith("data: ") and current == kind:
            return json.loads(line[6:])
    raise AssertionError("événement %s non reçu" % kind)
