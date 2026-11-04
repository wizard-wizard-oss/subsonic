"""Démonstration de l'édition PC : bibliothèque inventée, pochettes dessinées, quelques messages.
Sert aux captures d'écran. Usage : python3 -m tests.demo_webapp [secondes]   (affiche le port)
Adresse et port fixes (conteneur Docker) : PI_MEDIA_DEMO_BIND=0.0.0.0 PI_MEDIA_DEMO_PORT=8200."""
import colorsys
import hashlib
import io
import os
import sys
import tempfile
import threading
import time

from PIL import Image, ImageDraw

from pimedia.webapp.app import WebApplication
from tests import fake_subsonic
from tests.fake_subsonic import FakeSubsonicFull
from tests.support import PROJECT

DEMO = {   # artiste -> [(album, année, genre)]
    "Aurore Boréale": [("Lumières du Nord", 2019, "Électro"), ("Polaris", 2022, "Électro")],
    "Bastien Lune": [("Café des rêves", 2016, "Chanson"), ("Minuit passé", 2021, "Chanson")],
    "Cobalt Orchestra": [("Symphonie bleue", 2014, "Classique")],
    "Delta Groove": [("Basse fréquence", 2018, "Funk"), ("Night Drive", 2023, "Funk")],
    "Échos du Sud": [("Mistral", 2020, "Folk")],
    "Fanfare Nova": [("Parade", 2017, "Jazz"), ("Cuivres", 2024, "Jazz")],
    "Gaïa Sound": [("Terre ferme", 2015, "Ambient")],
    "Hélios": [("Soleil noir", 2021, "Rock")],
}
TITLES = ["Ouverture", "Le grand départ", "Sous la pluie", "Lignes de fuite", "Retour au calme", "Dernière danse",
          "Horizon", "Fin de partie"]


def build_library():
    artists, songs, album_songs = {}, {}, {}
    for a, (name, albums) in enumerate(DEMO.items()):
        artist_id = "ar%d" % (a + 10)
        cards = []
        for b, (title, year, genre) in enumerate(albums):
            album_id = "al%d%d" % (a + 10, b)
            ids = []
            for t in range(6 + (a + b) % 3):
                song_id = "%s-%d" % (album_id, t)
                songs[song_id] = {"id": song_id, "title": TITLES[(t + a) % len(TITLES)], "artist": name,
                                  "track": t + 1, "discNumber": 1, "duration": 150 + (t * 37 + a * 11) % 180,
                                  "bitRate": 1411}
                ids.append(song_id)
            album_songs[album_id] = ids
            cards.append({"id": album_id, "name": title, "artist": name, "artistId": artist_id, "year": year,
                          "coverArt": album_id, "songCount": len(ids), "genre": genre})
        artists[artist_id] = {"id": artist_id, "name": name, "albumCount": len(cards), "album": cards}
    return artists, songs, album_songs


def cover_png(item_id, size):
    """Pochette abstraite, différente pour chaque album (dégradé + formes)."""
    digest = hashlib.sha1(item_id.encode()).digest()
    size = max(64, min(int(size or 300), 600))
    hue = digest[0] / 255
    top = tuple(int(c * 255) for c in colorsys.hsv_to_rgb(hue, 0.55, 0.85))
    bottom = tuple(int(c * 255) for c in colorsys.hsv_to_rgb((hue + 0.15) % 1, 0.7, 0.35))
    image = Image.new("RGB", (size, size))
    draw = ImageDraw.Draw(image)
    for y in range(size):
        k = y / size
        draw.line([(0, y), (size, y)], fill=tuple(int(top[i] * (1 - k) + bottom[i] * k) for i in range(3)))
    for i in range(3):
        r = size * (0.15 + digest[i + 1] / 255 * 0.3)
        x, y = size * digest[i + 4] / 255, size * digest[i + 7] / 255
        draw.ellipse([x - r, y - r, x + r, y + r], outline=(255, 255, 255), width=max(2, size // 90))
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


class DemoSubsonic(FakeSubsonicFull):
    def __init__(self, address=fake_subsonic.LOCAL_ANY_PORT):
        super().__init__(address)
        self.users.update({"carole": "pw3", "malik": "pw4"})
        albums = [al for a in fake_subsonic.ID3_ARTISTS.values() for al in a["album"]]
        self.newest_albums = [al["id"] for al in sorted(albums, key=lambda al: -al["year"])]
        for n, album in enumerate(albums):        # écoutes et étoiles posées « avant » sur Subsonic
            fake_subsonic.PLAY_COUNTS[album["id"]] = (n * 7919) % 20000
            for k, user in enumerate(("carole", "malik")):
                if (n + k) % 3:
                    self.ratings[(user, fake_subsonic.album_folder(album["id"]))] = 1 + (n * 3 + k) % 5

        groups = {}                               # un dossier par artiste (getIndexes)
        for artist in fake_subsonic.ID3_ARTISTS.values():
            groups.setdefault(artist["name"][0].upper().replace("É", "E"), []).append(
                {"id": "dir-" + artist["id"], "name": artist["name"]})
        self.indexes = [{"name": k, "artist": v} for k, v in sorted(groups.items())]

    def api_stream(self, h, p):
        """Une seconde de silence en WAV : le lecteur du navigateur peut vraiment la lire."""
        rate, seconds = 8000, 1
        data = b"\x80" * (rate * seconds)
        header = (b"RIFF" + (36 + len(data)).to_bytes(4, "little") + b"WAVEfmt " + (16).to_bytes(4, "little") +
                  (1).to_bytes(2, "little") + (1).to_bytes(2, "little") + rate.to_bytes(4, "little") +
                  rate.to_bytes(4, "little") + (1).to_bytes(2, "little") + (8).to_bytes(2, "little") +
                  b"data" + len(data).to_bytes(4, "little"))
        h.reply(200, header + data, "audio/wav")

    def api_getCoverArt(self, h, p):
        h.reply(200, cover_png(p.get("id", ""), p.get("size")), "image/png")


def start_demo_subsonic(address=fake_subsonic.LOCAL_ANY_PORT):
    """Faux Subsonic garni de la bibliothèque inventée, démarré (comptes : alice / secret, bob / pw2…)."""
    artists, songs, album_songs = build_library()
    fake_subsonic.ID3_ARTISTS.clear()
    fake_subsonic.ID3_ARTISTS.update(artists)
    fake_subsonic.SONGS.update(songs)
    fake_subsonic.ID3_SONGS.clear()
    fake_subsonic.ID3_SONGS.update(album_songs)
    return DemoSubsonic(address).start()


def main():
    fake = start_demo_subsonic()
    app = WebApplication(PROJECT, environ={"PI_MEDIA_WEB_SUBSONIC_URL": fake.url},
                         data_dir=tempfile.mkdtemp(prefix="pmw-demo-"))
    server = app.make_server(os.environ.get("PI_MEDIA_DEMO_BIND", "127.0.0.1"),
                             int(os.environ.get("PI_MEDIA_DEMO_PORT", "0")))
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    print(server.server_address[1], flush=True)
    time.sleep(float(sys.argv[1]) if len(sys.argv) > 1 else 300)


if __name__ == "__main__":
    main()
