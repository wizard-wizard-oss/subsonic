"""Édition PC : favoris d'ailleurs de chaque personne (cœur, lien YouTube ou SoundCloud collé)."""
import unittest

from pimedia.server.podcasts.directories import DirectoryError
from pimedia.webapp.ext_favorites import parse_link, soundcloud_track
from pimedia.webapp.extmusic import ExtMusicError
from tests.test_podcasts import FakeHttp
from tests.test_webapp_ext import JAMENDO, KEYS, VIDEOS, YOUTUBE
from tests.webapp_support import WebAppTestCase

PLAYLIST = {"items": [{"contentDetails": {"videoId": v}} for v in ("otherone123", "abc123def45", "gonevideo01")]}
OEMBED = {"title": "Midnight City by M83", "author_name": "M83", "thumbnail_url": "https://i1.sndcdn.com/artworks-1-t500x500.jpg",
          "html": '<iframe src="https://w.soundcloud.com/player/?visual=true&url=https%3A%2F%2Fapi.soundcloud.com%2Ftracks%2F29912345&show_artwork=true"></iframe>'}
SET_OEMBED = {"title": "Ma sélection", "html": '<iframe src="https://w.soundcloud.com/player/?url=https%3A%2F%2Fapi.soundcloud.com%2Fplaylists%2F77"></iframe>'}


class LinkTest(unittest.TestCase):
    def test_youtube_links(self):
        for link in ("https://www.youtube.com/watch?v=abc123def45", "youtube.com/watch?v=abc123def45&list=PLxyz12345678",
                     "https://youtu.be/abc123def45?si=partage", "https://music.youtube.com/watch?v=abc123def45&feature=share",
                     "https://m.youtube.com/shorts/abc123def45", "https://www.youtube.com/embed/abc123def45"):
            self.assertEqual(parse_link(link), ("youtube_video", "abc123def45"), link)
        self.assertEqual(parse_link(" https://music.youtube.com/playlist?list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf "),
                         ("youtube_playlist", "PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf"))

    def test_soundcloud_links(self):
        self.assertEqual(parse_link("https://soundcloud.com/m83/midnight-city?utm_source=x"),
                         ("soundcloud", "https://soundcloud.com/m83/midnight-city"))
        self.assertEqual(parse_link("m.soundcloud.com/m83/midnight-city"), ("soundcloud", "https://soundcloud.com/m83/midnight-city"))
        self.assertEqual(parse_link("https://on.soundcloud.com/AbCd1"), ("soundcloud", "https://on.soundcloud.com/AbCd1"))

    def test_refused_links_say_why(self):
        for link, key in (("https://www.youtube.com/playlist?list=LL", "ext.playlist_private"),
                          ("https://music.youtube.com/playlist?list=LM", "ext.playlist_private"),
                          ("https://www.youtube.com/playlist?list=RDabc123def45", "ext.playlist_mix"),
                          ("https://soundcloud.com/m83/sets/hurry-up", "ext.soundcloud_not_track"),
                          ("https://soundcloud.com/m83", "ext.link_unknown"),
                          ("https://www.youtube.com/watch?v=<script>", "ext.link_unknown"),
                          ("https://evil.example/watch?v=abc123def45", "ext.link_unknown"),
                          ("javascript:alert(1)", "ext.link_unknown"), ("", "ext.link_unknown")):
            with self.assertRaises(ExtMusicError, msg=link) as caught:
                parse_link(link)
            self.assertEqual(caught.exception.args[0], key, link)

    def test_soundcloud_oembed(self):
        track = soundcloud_track(OEMBED, "https://soundcloud.com/m83/midnight-city")
        self.assertEqual((track["itemId"], track["title"], track["artist"], track["playUrl"]),
                         ("29912345", "Midnight City", "M83", "https://api.soundcloud.com/tracks/29912345"))
        self.assertIsNone(soundcloud_track(SET_OEMBED, "x"))
        newer = dict(OEMBED, html='<iframe src="https://w.soundcloud.com/player/?url=soundcloud%3Atracks%3A42"></iframe>',
                     thumbnail_url="https://evil.example/a.jpg")
        self.assertEqual((soundcloud_track(newer, "x")["itemId"], soundcloud_track(newer, "x")["imageUrl"]), ("42", ""))


class ExtFavoritesHttpTest(WebAppTestCase):
    environ = KEYS

    def setUp(self):
        super().setUp()
        self.http = FakeHttp({"jamendo.com": JAMENDO, "youtube/v3/videos": VIDEOS, "youtube/v3/search": YOUTUBE,
                              "youtube/v3/playlistItems": PLAYLIST, "soundcloud.com/oembed": OEMBED})
        for source in self.app.extmusic.service.sources.values():
            source.http = self.http
        self.app.ext_favorites.http = self.http

    def favorites(self, client):
        return client.get("/api/ext/favorites").json()["items"]

    def link(self, client, link):
        return client.post_json("/api/ext/link", {"link": link})

    def test_a_youtube_playlist_is_imported_in_its_order_for_this_person_only(self):
        bob, alice = self.client("bob", "pw2"), self.client("alice", "secret")
        result = self.link(bob, "https://www.youtube.com/playlist?list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf").json()
        self.assertEqual(result, {"kind": "playlist", "added": 2, "already": 0, "skipped": 1})     # une vidéo disparue
        items = self.favorites(bob)
        self.assertEqual([(i["id"], i["ext"], i["artist"], i["duration"]) for i in items],
                         [("yt-otherone123", "youtube", "Daft Punk", 320), ("yt-abc123def45", "youtube", "Daft Punk", 320)])
        self.assertEqual(self.favorites(alice), [])                                   # chacun les siens
        again = self.link(bob, "https://www.youtube.com/playlist?list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf").json()
        self.assertEqual((again["added"], again["already"]), (0, 2))
        stored = self.app.db.one("SELECT title FROM ext_favorites WHERE item_id = 'abc123def45'")["title"]
        self.assertEqual(stored, "")                     # titres YouTube : seulement dans youtube_videos, relus tous les 30 jours

    def test_a_video_forgotten_by_the_monthly_recheck_leaves_the_favorites(self):
        bob = self.client("bob", "pw2")
        self.assertEqual(self.link(bob, "https://youtu.be/abc123def45").json()["kind"], "video")
        self.app.extmusic.videos.forget(["abc123def45"])
        self.assertEqual(self.favorites(bob), [])

    def test_known_videos_cost_no_quota(self):
        bob = self.client("bob", "pw2")
        bob.get("/api/ext/search?src=youtube&q=daft")
        calls = len(self.http.calls)
        self.link(bob, "https://www.youtube.com/watch?v=abc123def45")
        self.assertEqual(len(self.http.calls), calls)

    def test_soundcloud_track_by_link(self):
        bob = self.client("bob", "pw2")
        result = self.link(bob, "https://soundcloud.com/m83/midnight-city").json()
        self.assertEqual((result["kind"], result["added"]), ("track", 1))
        item = self.favorites(bob)[0]
        self.assertEqual((item["id"], item["title"], item["soundcloudUrl"], item["pageUrl"]),
                         ("sc-29912345", "Midnight City", "https://api.soundcloud.com/tracks/29912345",
                          "https://soundcloud.com/m83/midnight-city"))
        self.http.routes["soundcloud.com/oembed"] = SET_OEMBED
        self.assertEqual(self.link(bob, "https://soundcloud.com/m83/likes").json()["error"], "ext.soundcloud_not_track")
        self.http.routes["soundcloud.com/oembed"] = DirectoryError("HTTP Error 404: Not Found")
        self.assertEqual(self.link(bob, "https://soundcloud.com/m83/prive").json()["error"], "ext.link_not_found")
        self.http.routes["soundcloud.com/oembed"] = DirectoryError("timed out")
        self.assertEqual(self.link(bob, "https://soundcloud.com/m83/panne").json()["error"], "ext.unreachable")

    def test_heart_adds_and_removes(self):
        bob = self.client("bob", "pw2")
        video = bob.get("/api/ext/search?src=youtube&q=daft").json()["items"][0]
        jamendo = bob.get("/api/ext/search?src=jamendo&q=groove").json()["items"][0]
        for item in (video, jamendo):
            self.assertEqual(bob.post_json("/api/ext/favorite", {"item": item, "on": True}).status, 200)
        self.assertEqual({i["id"] for i in self.favorites(bob)}, {video["id"], "jamendo-11"})
        kept = next(i for i in self.favorites(bob) if i["ext"] == "jamendo")
        self.assertEqual((kept["streamUrl"], kept["title"]), (jamendo["streamUrl"], "Groove"))
        bob.post_json("/api/ext/favorite", {"item": video, "on": False})
        self.assertEqual([i["id"] for i in self.favorites(bob)], ["jamendo-11"])
        forged = dict(jamendo, streamUrl="https://evil.example/son.mp3")
        self.assertEqual(bob.post_json("/api/ext/favorite", {"item": forged, "on": True}).json()["error"], "request.invalid")
        self.assertEqual(bob.post_json("/api/ext/favorite", {"item": {"ext": "spotify"}, "on": True}).status, 400)
        no_csrf = bob.post_json("/api/ext/favorite", {"item": video, "on": True}, csrf=False)
        self.assertEqual(no_csrf.status, 403)

    def test_private_playlist_and_limits(self):
        bob = self.client("bob", "pw2")
        self.http.routes["youtube/v3/playlistItems"] = DirectoryError("HTTP Error 404: Not Found")
        self.assertEqual(self.link(bob, "https://www.youtube.com/playlist?list=PLprivee12345").json()["error"],
                         "ext.playlist_private")
        self.http.routes["youtube/v3/playlistItems"] = {"items": []}
        self.assertEqual(self.link(bob, "https://www.youtube.com/playlist?list=PLvide1234567").json()["error"],
                         "ext.playlist_empty")
        for n in range(28):
            self.link(bob, "https://soundcloud.com/m83/titre%d" % n)
        self.assertEqual(self.link(bob, "https://soundcloud.com/m83/encore").json()["error"], "ext.too_many_links")
        self.assertEqual(self.link(self.client("alice", "secret"), "https://soundcloud.com/m83/x").status, 200)
        self.assertEqual(self.client().get("/api/ext/favorites").status, 401)


class ExtFavoritesWithoutYouTubeKeyTest(WebAppTestCase):
    def test_soundcloud_needs_no_key_but_youtube_does(self):
        self.app.ext_favorites.http = FakeHttp({"soundcloud.com/oembed": OEMBED})
        bob = self.client("bob", "pw2")
        self.assertEqual(bob.post_json("/api/ext/link", {"link": "https://youtu.be/abc123def45"}).json()["error"], "ext.disabled")
        self.assertEqual(bob.post_json("/api/ext/link", {"link": "https://soundcloud.com/m83/midnight-city"}).status, 200)


class PlaylistWithExtTracksTest(WebAppTestCase):
    """Titres d'ailleurs dans une playlist Subsonic : gardés par le site, montrés à leur place ; Subsonic (et donc les
    applications Subsonic) ne voit que ses propres titres."""
    environ = KEYS

    def setUp(self):
        super().setUp()
        self.http = FakeHttp({"jamendo.com": JAMENDO, "youtube/v3/videos": VIDEOS, "youtube/v3/search": YOUTUBE,
                              "soundcloud.com/oembed": OEMBED})
        for source in self.app.extmusic.service.sources.values():
            source.http = self.http
        self.app.ext_favorites.http = self.http
        self.bob, self.alice = self.client("bob", "pw2"), self.client("alice", "secret")
        self.video = self.bob.get("/api/ext/search?src=youtube&q=daft").json()["items"][0]
        self.bob.post_json("/api/ext/link", {"link": "https://soundcloud.com/m83/midnight-city"})
        self.sound = self.bob.get("/api/ext/favorites").json()["items"][0]

    def playlist(self, client, playlist_id):
        return client.get("/api/playlist?id=" + playlist_id).json()

    def add(self, client, playlist_id, items):
        return client.post_json("/api/playlist/add-ext", {"id": playlist_id, "items": items})

    def test_ext_tracks_keep_their_place_between_subsonic_songs(self):
        pid = self.bob.post_json("/api/playlist/create", {"name": "Mélange", "songIds": ["s1"]}).json()["playlist"]["id"]
        self.assertEqual(self.add(self.bob, pid, [self.video]).json()["added"], 1)
        self.bob.post_json("/api/playlist/add", {"id": pid, "songIds": ["s3"]})
        self.assertEqual(self.add(self.bob, pid, [self.sound, self.video]).json()["added"], 1)     # déjà là : une fois
        songs = self.playlist(self.bob, pid)["songs"]
        self.assertEqual([(s["id"], s.get("ext"), s["position"]) for s in songs],
                         [("s1", None, 0), (self.video["id"], "youtube", None), ("s3", None, 1),
                          (self.sound["id"], "soundcloud", None)])
        self.assertEqual(self.subsonic.playlists[pid]["songs"], ["s1", "s3"])          # Subsonic : seulement les siens
        self.assertEqual([p["songCount"] for p in self.bob.get("/api/playlists").json()["playlists"]], [4])
        self.bob.post_json("/api/playlist/remove-ext", {"id": pid, "extIds": [songs[1]["extId"]]})
        self.assertEqual([s["id"] for s in self.playlist(self.bob, pid)["songs"]], ["s1", "s3", self.sound["id"]])
        self.bob.post_json("/api/playlist/delete", {"id": pid})
        self.assertEqual(self.app.db.one("SELECT COUNT(*) FROM playlist_ext_tracks")[0], 0)

    def test_the_owner_moves_ext_tracks_and_subsonic_songs_together(self):
        pid = self.bob.post_json("/api/playlist/create", {"name": "Mélange", "songIds": ["s1", "s3"]}).json()["playlist"]["id"]
        self.add(self.bob, pid, [self.video, self.sound])                           # s1 s3 vidéo son
        songs = self.playlist(self.bob, pid)["songs"]
        video, sound = songs[2]["extId"], songs[3]["extId"]
        order = [{"extId": sound}, {"position": 1}, {"extId": video}, {"position": 0}]
        self.assertEqual(self.bob.post_json("/api/playlist/reorder", {"id": pid, "order": order}).status, 200)
        self.assertEqual([s["id"] for s in self.playlist(self.bob, pid)["songs"]],
                         [self.sound["id"], "s3", self.video["id"], "s1"])
        self.assertEqual(self.subsonic.playlists[pid]["songs"], ["s3", "s1"])
        order = [{"extId": video}, {"extId": sound}, {"position": 0}, {"position": 1}]  # à la même place : leur ordre
        self.bob.post_json("/api/playlist/reorder", {"id": pid, "order": order})
        self.assertEqual([s["id"] for s in self.playlist(self.bob, pid)["songs"]],
                         [self.video["id"], self.sound["id"], "s3", "s1"])
        self.bob.post_json("/api/playlist/add", {"id": pid, "songIds": ["s4"]})
        jamendo = self.bob.get("/api/ext/search?src=jamendo&q=groove").json()["items"][0]
        self.add(self.bob, pid, [jamendo])                                          # un ajout va toujours au bout
        self.assertEqual([s["id"] for s in self.playlist(self.bob, pid)["songs"]][-2:], ["s4", jamendo["id"]])
        forgotten = self.bob.post_json("/api/playlist/reorder", {"id": pid, "order": order})   # sans le dernier ajout
        self.assertEqual(forgotten.json()["error"], "playlist.changed")

    def test_same_rights_as_subsonic_songs(self):
        private = self.bob.post_json("/api/playlist/create", {"name": "Perso"}).json()["playlist"]["id"]
        refused = self.add(self.alice, private, [self.video])                        # invisible pour les autres
        self.assertEqual((refused.status, refused.json()["error"]), (502, "subsonic.error"))   # comme pour les titres Subsonic
        shared = self.bob.post_json("/api/playlist/create", {"name": "À tous", "community": True}).json()["playlist"]["id"]
        self.add(self.bob, shared, [self.sound])
        self.assertEqual(self.add(self.alice, shared, [self.video]).json()["added"], 1)
        songs = self.playlist(self.alice, shared)["songs"]
        self.assertEqual([s["addedBy"] for s in songs], ["bob", "alice"])
        mine, bobs = songs[1]["extId"], songs[0]["extId"]
        self.assertEqual(self.alice.post_json("/api/playlist/remove-ext", {"id": shared, "extIds": [bobs]}).json()["error"],
                         "playlist.not_yours")
        self.assertEqual(self.alice.post_json("/api/playlist/remove-ext", {"id": shared, "extIds": [mine]}).status, 200)
        self.assertEqual(self.bob.post_json("/api/playlist/remove-ext", {"id": shared, "extIds": [bobs]}).status, 200)

    def test_what_the_page_sends_is_checked(self):
        pid = self.bob.post_json("/api/playlist/create", {"name": "X"}).json()["playlist"]["id"]
        for forged in (dict(self.sound, soundcloudUrl="https://evil.example/tracks/1"),
                       dict(self.sound, pageUrl="https://evil.example/m83/x"),
                       dict(self.video, id="yt-<script>"), {"ext": "spotify", "id": "x"}):
            self.assertEqual(self.add(self.bob, pid, [forged]).status, 400, forged)
        self.assertEqual(self.add(self.bob, pid, []).status, 400)
        self.assertEqual(self.app.db.one("SELECT COUNT(*) FROM playlist_ext_tracks")[0], 0)
