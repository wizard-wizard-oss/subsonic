"""Lance l'application (mode Pi) avec de faux annuaires, pour tester la page Podcasts dans un navigateur simulé.
Usage : python3 -m tests.e2e_harness   (affiche le port, puis attend)"""
import json
import os
import sys
import tempfile
import threading
import time

from pimedia.server.app import Application
from tests.fake_subsonic import FakeSubsonic
from tests.test_podcasts import FakeFetcher, FakeHttp, ITUNES_RESULTS
from tests.support import PROJECT, ROOT, youtube_music_down
from tests.test_guests import FakeSystem
from pimedia.server.transport import Reply
from tests.test_extmusic import JAMENDO_ANSWER, VIDEOS_ANSWER, YOUTUBE_ANSWER


def main():
    tmp = tempfile.mkdtemp(prefix="pm-e2e-")
    fake = FakeSubsonic().start()
    app_dir = os.path.join(tmp, "app")
    os.makedirs(app_dir)
    os.symlink(os.path.join(PROJECT, "web"), os.path.join(app_dir, "web"))
    os.symlink(os.path.join(PROJECT, "i18n"), os.path.join(app_dir, "i18n"))
    with open(os.path.join(app_dir, "config.json"), "w") as f:
        json.dump({"subsonic_url": fake.url, "subsonic_user": "alice", "subsonic_pass": "secret"}, f)
    app = Application(app_dir, {"PI_MEDIA_CACHE": os.path.join(tmp, "cache"), "PI_MEDIA_PORT": "0"})
    app.cache.load()
    http = FakeHttp({"itunes.apple.com": ITUNES_RESULTS})
    app.podcasts.hub.itunes.http = http
    app.podcasts.hub.index.http = http
    app.podcasts.reader.fetcher = FakeFetcher()
    ext_http = FakeHttp({"jamendo.com": JAMENDO_ANSWER, "youtube/v3/videos": VIDEOS_ANSWER, "googleapis.com": YOUTUBE_ANSWER})
    for source in app.extmusic.sources.values():
        source.http = ext_http
    app.extmusic.sources["youtube"].music = youtube_music_down()      # ni YouTube Music
    guests = FakeSystem()                      # invités AirPlay/Bluetooth simulés, pilotés par /__test/guest
    app.guests.system = guests

    def set_guest(request):
        body = request.json_body()
        guests.streams = body.get("streams", [])
        guests.player_states = body.get("players", {})
        app.guests._cached = None
        return Reply.json({"played": guests.played})
    app.http.router.add("POST", "/__test/guest", set_guest)
    mpv_socket = os.path.join(tmp, "mpv.sock")      # lecture haute fidélité : faux mpv qui parle le même protocole
    app.hifi.mpv.socket_path = mpv_socket
    app.hifi.mpv.command = [sys.executable, os.path.join(ROOT, "tests", "fake_mpv.py"), "--input-ipc-server=" + mpv_socket]

    def mpv_test(request):
        app.hifi.mpv.call(request.json_body().get("cmd", "test-finish"))
        return Reply.json({"ok": True})
    app.http.router.add("POST", "/__test/mpv", mpv_test)
    app.start_phone_server(0)                 # saisie depuis le téléphone, sur un port libre
    server = app.make_server()
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    print(server.server_address[1], flush=True)
    time.sleep(float(sys.argv[1]) if len(sys.argv) > 1 else 120)


if __name__ == "__main__":
    main()
