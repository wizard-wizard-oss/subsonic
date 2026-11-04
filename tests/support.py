"""Outils communs aux tests d'intégration : application sur un dossier temporaire, client HTTP avec cookies."""
import http.client
import json
import os
import shutil
import tempfile
import threading
import unittest

from pimedia.envfile import EnvFile
from pimedia.server.app import Application
from pimedia.server.extmusic.ytmusic import YouTubeMusicSearch
from pimedia.server.podcasts.directories import DirectoryError
from tests.fake_subsonic import FakeSubsonic

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT = os.path.join(ROOT, "src")      # code de l'application


class Response:
    def __init__(self, raw):
        self.status = raw.status
        self.headers = {k.lower(): v for k, v in raw.getheaders()}
        self.body = raw.read()

    def json(self):
        return json.loads(self.body.decode("utf-8"))


class HttpClient:
    """Petit navigateur : garde le cookie de session et ajoute l'en-tête anti-CSRF si on le demande."""

    def __init__(self, port):
        self.port = port
        self.cookie = None

    def request(self, method, path, body=None, headers=None, csrf=True):
        headers = dict(headers or {})
        if csrf:
            headers.setdefault("X-Requested-With", "pm")
        if self.cookie:
            headers["Cookie"] = self.cookie
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        try:
            connection.request(method, path, body=body, headers=headers)
            response = Response(connection.getresponse())
        finally:
            connection.close()
        self._remember_cookie(response)
        return response

    def _remember_cookie(self, response):
        raw = response.headers.get("set-cookie")
        if raw:
            pair = raw.split(";")[0]
            self.cookie = pair if not pair.endswith("=") else None

    def get(self, path, **kwargs):
        return self.request("GET", path, **kwargs)

    def post_json(self, path, data, **kwargs):
        kwargs.setdefault("headers", {})["Content-Type"] = "application/json"
        return self.request("POST", path, body=json.dumps(data), **kwargs)


class FakeYouTubeMusic:
    """Remplace ytmusicapi : results[filtre] = résultats bruts (« songs », « videos ») ; sans results, en panne
    (la source se rabat alors sur l'API officielle, comme avant). Recherches notées."""

    def __init__(self, results=None):
        self.results, self.terms = results, []

    def __call__(self, region):                 # client_factory de YouTubeMusicSearch
        self.region = region
        return self

    def search(self, term, filter, limit):
        self.terms.append((term, filter))
        if self.results is None:
            raise DirectoryError("YouTube Music en panne")
        return self.results.get(filter, [])[:limit]


def youtube_music_down():
    """YouTube Music simulé en panne : aucun test ne joint le vrai YouTube."""
    return YouTubeMusicSearch(FakeYouTubeMusic())


class AppTestCase(unittest.TestCase):
    """Lance un faux Subsonic et l'application pour chaque test."""

    EXTRA_ENV = {}

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="pm-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.subsonic = FakeSubsonic().start()
        self.addCleanup(self.subsonic.stop)
        self.app = self._build_app()
        self.server = self.app.make_server()
        threading.Thread(target=self.server.serve_forever, args=(0.02,), daemon=True).start()
        self.addCleanup(self._stop_server)
        self.client = self.new_client()

    def _stop_server(self):
        self.server.shutdown()
        self.server.server_close()

    def _build_app(self):
        app_dir = os.path.join(self.tmp, "app")
        os.makedirs(app_dir)
        os.symlink(os.path.join(PROJECT, "web"), os.path.join(app_dir, "web"))
        os.symlink(os.path.join(PROJECT, "i18n"), os.path.join(app_dir, "i18n"))
        self.write_config(app_dir)
        environ = {"PI_MEDIA_CACHE": os.path.join(self.tmp, "cache"), "PI_MEDIA_PORT": "0"}
        app = Application(app_dir, environ)
        app.extmusic.sources["youtube"].music = youtube_music_down()
        app.cache.load()
        return app

    def write_config(self, app_dir):
        """Réglages du Pi de test dans le .env (comme sur un vrai Pi)."""
        values = dict({"SUBSONIC_URL": self.subsonic.url, "SUBSONIC_USER": "alice", "SUBSONIC_PASS": "secret"}, **self.EXTRA_ENV)
        EnvFile(os.path.join(app_dir, ".env")).set(**values)

    def new_client(self):
        return HttpClient(self.server.server_address[1])
