"""Lance l'édition PC avec un faux Subsonic, pour les parcours dans un navigateur simulé (jsdom).
Usage : python3 -m tests.e2e_webapp_harness [secondes]   (affiche le port, puis attend)"""
import os
import sys
import tempfile
import threading
import time
import urllib.error

from pimedia.webapp.app import WebApplication
from pimedia.server.transport import ThreadedServer
from pimedia.webapp.covers import LastFmAlbums
from tests.fake_subsonic import FakeSubsonicFull
from tests.fake_musicbrainz import FakeMusicBrainz
from tests.fake_discogs import FakeDiscogs, FakeLastFm as FakeDiscoveryLastFm
from tests.support import PROJECT, youtube_music_down
from tests.test_podcasts import FakeHttp
from tests.test_webapp_covers import FakeDownloader, FakeLastFm
from tests.test_webapp_ext import JAMENDO, KEYS, VIDEOS, YOUTUBE
from tests.test_playlist_import import DEEZER_PLAYLIST, DEEZER_TRACKS
from tests.test_webapp_ext_favorites import OEMBED, PLAYLIST
from tests.test_webapp_news import ATOM, PAGE, RSS, FakeFeeds
from tests.webapp_support import FakeGravatar, FakeLyricsSites, use_fake_info_sites


def slow_then_failing_once(answer):
    """Première liste des artistes lente puis ratée (Subsonic débordé, réponse qui n'est pas du JSON) :
    la barre doit dire qu'elle patiente, puis proposer de réessayer."""
    calls = []

    def api(h, p):
        calls.append(p)
        if len(calls) > 1:
            return answer(h, p)
        time.sleep(0.6)
        h.reply(200, b"<html>Gateway Timeout</html>", "text/html")
    return api


def main():
    # Let jsdom load all application scripts without overflowing the local TCP backlog.
    ThreadedServer.request_queue_size = 128
    fake = FakeSubsonicFull().start()
    fake.api_getIndexes = slow_then_failing_once(fake.api_getIndexes)
    music = tempfile.mkdtemp(prefix="pmw-music-")                 # Incoming y est créé au premier passage
    app = WebApplication(PROJECT, environ=dict(KEYS, PI_MEDIA_WEB_SUBSONIC_URL=fake.url, PI_MEDIA_WEB_MUSIC_DIR=music),
                         data_dir=tempfile.mkdtemp(prefix="pmw-e2e-"))
    app.lyrics.finder.fetcher = FakeLyricsSites()
    app.exploration.metadata.fetcher = FakeMusicBrainz()
    app.discogs.api_key = "discogs-test"
    app.lastfm.api_key = "lastfm-test"
    app.discogs.http, app.lastfm.http = FakeDiscogs(), FakeDiscoveryLastFm()
    app.discogs.sleep = app.lastfm.sleep = lambda seconds: None
    app.exploration.metadata.sleep = lambda seconds: None
    app.exploration.metadata.fetcher.failures = [urllib.error.HTTPError(
        "https://musicbrainz.org", 503, "busy", {}, None)]
    use_fake_info_sites(app)
    app.avatars.gravatar = FakeGravatar()
    covers_music = tempfile.mkdtemp(prefix="pmw-covers-")        # musique à part (l'envoi de zip range déjà « Abba/Arrival »)
    os.makedirs(os.path.join(covers_music, "ABBA", "Arrival", "CD1"))
    app.covers.music_dir = covers_music
    app.covers.lastfm = LastFmAlbums(FakeLastFm(), "k3y")        # ni Last.fm ni le net pour les pochettes
    app.covers.downloader = FakeDownloader()
    app.news.fetcher = FakeFeeds({"https://webzine.example": PAGE, "https://webzine.example/feed/": RSS,
                                  "https://atom.example/feed": ATOM})
    ext_http = FakeHttp({"jamendo.com": JAMENDO, "youtube/v3/videos": VIDEOS, "youtube/v3/search": YOUTUBE,
                         "youtube/v3/playlistItems": PLAYLIST, "soundcloud.com/oembed": OEMBED})
    for source in app.extmusic.service.sources.values():          # Jamendo, YouTube et SoundCloud simulés
        source.http = ext_http
    app.ext_favorites.http = ext_http
    app.extmusic.youtube.music = youtube_music_down()
    app.imports.reader.http = FakeHttp({"playlist/77/tracks": DEEZER_TRACKS, "playlist/77": DEEZER_PLAYLIST})   # Deezer simulé
    server = app.make_server(os.environ.get("PI_MEDIA_DEMO_BIND", "127.0.0.1"),
                             int(os.environ.get("PI_MEDIA_DEMO_PORT", 0)))
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    print(server.server_address[1], flush=True)
    time.sleep(float(sys.argv[1]) if len(sys.argv) > 1 else 120)


if __name__ == "__main__":
    main()
