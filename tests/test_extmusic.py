"""Tests de la musique d'ailleurs : Jamendo, YouTube, playlists locales, réglages (Pi seulement)."""
import os
import tempfile
import unittest
from urllib.parse import urlencode

from pimedia.storage.database import Database
from pimedia.entities import Playlist, PlaylistSummary, Track
from pimedia.storage.playlists import LocalPlaylists
from pimedia.tracks import clean_track as clean_song
from pimedia.storage.videos import UnplayableVideos
from pimedia.server.extmusic.sources import (clean_channel, is_alternate_version, jamendo_track, parse_iso_duration, playable_details, song_parts,
                                            topic_first, youtube_track)
from tests.support import AppTestCase
from tests.test_podcasts import FakeHttp

JAMENDO_ANSWER = {"headers": {"status": "success"}, "results": [
    {"id": "11", "name": "Groove", "artist_name": "Fankel", "album_name": "Album", "duration": 272,
     "audio": "https://prod-1.storage.jamendo.com/?trackid=11&format=mp32", "image": "https://img/11.jpg"},
    {"id": "12", "name": "Sans audio", "audio": ""}]}
YOUTUBE_ANSWER = {"items": [
    {"id": {"videoId": "abc123"}, "snippet": {"title": "Daft Punk &amp; Co &#39;Live&#39;", "channelTitle": "Daft Punk - Topic",
                                              "thumbnails": {"medium": {"url": "https://i.ytimg.com/m.jpg"}}}},
    {"id": {}, "snippet": {"title": "Playlist sans vidéo"}}]}
VIDEOS_ANSWER = {"items": [
    {"id": "abc123", "status": {"embeddable": True, "privacyStatus": "public"}, "contentDetails": {"duration": "PT3M25S"}}]}


class SourceFunctionsTest(unittest.TestCase):
    def test_jamendo_track(self):
        track = jamendo_track(JAMENDO_ANSWER["results"][0])
        self.assertEqual((track["id"], track["title"], track["duration"]), ("jamendo-11", "Groove", 272))
        self.assertTrue(track["streamUrl"].startswith("https://"))
        self.assertIsNone(jamendo_track(JAMENDO_ANSWER["results"][1]))

    def test_youtube_track(self):
        track = youtube_track(YOUTUBE_ANSWER["items"][0])
        self.assertEqual((track["youtubeId"], track["title"], track["artist"]), ("abc123", "Daft Punk & Co 'Live'", "Daft Punk"))
        self.assertIsNone(youtube_track(YOUTUBE_ANSWER["items"][1]))

    def test_topic_channels_come_first_keeping_order(self):
        def item(video, channel):
            return {"id": {"videoId": video}, "snippet": {"channelTitle": channel}}
        items = [item("a", "BritneyVEVO"), item("b", "Britney Spears - Topic"), item("c", "Fan"), item("d", "X - Topic")]
        self.assertEqual([i["id"]["videoId"] for i in topic_first(items)], ["b", "d", "a", "c"])

    def test_iso_duration(self):
        self.assertEqual(parse_iso_duration("PT3M25S"), 205)
        self.assertEqual(parse_iso_duration("PT1H2M3S"), 3723)
        self.assertEqual(parse_iso_duration("P0D"), 0)
        self.assertEqual(parse_iso_duration(None), 0)

    def test_playable_details(self):
        def video(embeddable=True, privacy="public", **restriction):
            return {"status": {"embeddable": embeddable, "privacyStatus": privacy},
                    "contentDetails": {"duration": "PT1M", "regionRestriction": restriction}}
        self.assertEqual(playable_details(video(), "FR"), 60)
        self.assertIsNone(playable_details(video(embeddable=False), "FR"))
        self.assertIsNone(playable_details(video(privacy="private"), "FR"))
        self.assertIsNone(playable_details(video(blocked=["FR", "BE"]), "FR"))
        self.assertEqual(playable_details(video(blocked=["US"]), "FR"), 60)
        self.assertIsNone(playable_details(video(allowed=["US"]), "FR"))
        self.assertIsNone(playable_details({}, "FR"))                       # vidéo inconnue (supprimée) : écartée

    def test_alternate_versions(self):
        for title in ("Toxic (Live)", "Toxic - Live at Wembley 2004", "Oops [Live 2004]", "Toxic (Acoustic)",
                      "Toxic (Remix)", "Toxic (Cover by Fan)", "Toxic | Karaoke", "Toxic Live 1999",
                      "Toxic (MTV Unplugged)", "Toxic en concert", "Toxic (Instrumental)", "Toxic - Live"):
            self.assertTrue(is_alternate_version(title), title)
        for title in ("Toxic", "Toxic (Official Video)", "Oasis - Live Forever", "Live and Let Die",
                      "Kraftwerk - Tour de France", "Cover Me", "Toxic (Official Audio)", "Livin' on a Prayer"):
            self.assertFalse(is_alternate_version(title), title)

    def test_song_parts(self):
        self.assertEqual(song_parts("Britney Spears - Toxic (Official HD Video)", "BritneySpearsVEVO"), ("Britney Spears", "Toxic"))
        self.assertEqual(song_parts("Toxic [Official Audio]", "Britney Spears"), ("Britney Spears", "Toxic"))
        self.assertEqual(song_parts("(Official Video)", "X"), ("X", ""))

    def test_clean_channel(self):
        self.assertEqual(clean_channel("Björk - Topic"), "Björk")
        self.assertEqual(clean_channel("Artist Official"), "Artist Official")


class UnplayableVideosTest(unittest.TestCase):
    def test_remembered_and_validated(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "pi-media.db")
            UnplayableVideos(Database(path)).add("abc123XYZ_-")
            self.assertIn("abc123XYZ_-", UnplayableVideos(Database(path)))
            with self.assertRaises(ValueError):
                UnplayableVideos(Database(path)).add("../../etc")


class LocalPlaylistsTest(unittest.TestCase):
    SONG = {"id": "s1", "title": "T", "artist": "A", "coverArt": "c1", "duration": 100}

    @staticmethod
    def tracks(*raw):
        return [Track.from_api(r) for r in raw]

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = os.path.join(self.dir.name, "pi-media.db")
        self.lists = LocalPlaylists(Database(self.path))

    def test_create_add_remove_persist(self):
        list_id = self.lists.create("Ma liste", self.tracks(self.SONG))
        self.assertEqual(self.lists.add(list_id, self.tracks(self.SONG, dict(self.SONG, id="s2"))), 1)        # doublon ignoré
        reloaded = LocalPlaylists(Database(self.path))
        playlist = reloaded.get(list_id)
        self.assertIsInstance(playlist, Playlist)
        self.assertEqual([t.id for t in playlist.tracks], ["s1", "s2"])
        self.assertEqual(reloaded.overview(), [PlaylistSummary(list_id, "Ma liste", 2)])
        reloaded.remove(list_id, 0)
        self.assertEqual([t.id for t in LocalPlaylists(Database(self.path)).get(list_id).tracks], ["s2"])
        reloaded.delete(list_id)
        self.assertEqual(LocalPlaylists(Database(self.path)).overview(), [])

    def test_mixes_subsonic_and_external_tracks(self):
        external = {"id": "yt-1", "title": "Vidéo", "youtubeId": "1", "ext": "youtube", "imageUrl": "https://i/x.jpg"}
        list_id = self.lists.create("Mix", self.tracks(self.SONG, external))
        self.assertEqual(self.lists.get(list_id).tracks[1].youtube_id, "1")
        self.assertEqual(self.lists.get(list_id).to_api()["songs"][1]["youtubeId"], "1")

    def test_unknown_fields_and_bad_urls_are_refused(self):
        self.assertNotIn("password", clean_song(dict(self.SONG, password="x", evil={"a": 1})))
        for bad in (dict(self.SONG, streamUrl="javascript:alert(1)"), dict(self.SONG, imageUrl="file:///etc/passwd"),
                    {"title": "sans id"}, "texte", {"id": "x"}):
            with self.assertRaises(ValueError):
                clean_song(bad)

    def test_favorites_toggle_persist_and_stay_out_of_playlists(self):
        video = {"id": "yt-1", "title": "V", "youtubeId": "1", "ext": "youtube"}
        self.assertEqual(self.lists.favorites(), [])
        self.assertTrue(self.lists.toggle_favorite(Track.from_api(video)))
        self.assertEqual([t.id for t in LocalPlaylists(Database(self.path)).favorites()], ["yt-1"])
        self.assertEqual(self.lists.overview(), [])                       # la liste réservée n'apparaît pas parmi les playlists
        self.assertFalse(self.lists.toggle_favorite(Track.from_api(video)))               # deuxième appel : retiré
        self.assertEqual(self.lists.favorites(), [])
        with self.assertRaises(ValueError):
            self.lists.toggle_favorite(Track.from_api({"title": "sans id"}))

    def test_errors(self):
        with self.assertRaises(ValueError):
            self.lists.create("   ")
        with self.assertRaises(KeyError):
            self.lists.get("inconnue")
        list_id = self.lists.create("L")
        with self.assertRaises(ValueError):
            self.lists.remove(list_id, 5)


class ExtMusicPiTest(AppTestCase):
    def setUp(self):
        super().setUp()
        self.http = FakeHttp({"jamendo.com": JAMENDO_ANSWER, "youtube/v3/videos": VIDEOS_ANSWER, "googleapis.com": YOUTUBE_ANSWER})
        for source in self.app.extmusic.sources.values():
            source.http = self.http

    def get(self, path, **params):
        return self.client.get("%s?%s" % (path, urlencode(params)), csrf=False)

    def post(self, name, data, **kwargs):
        return self.client.post_json("/ext/" + name, data, **kwargs)

    def test_everything_is_off_by_default(self):
        status = self.get("/ext/status").json()
        for name in ("jamendo", "youtube"):
            self.assertEqual(status[name], {"configured": False, "on": False, "enabled": False})
        self.assertEqual(self.get("/ext/search", src="jamendo", q="rock").status, 502)

    def test_cannot_switch_on_without_key(self):
        response = self.post("settings", {"youtube_on": True})
        self.assertEqual(response.status, 400)
        self.assertIn("clé", response.json()["error"])

    def test_jamendo_search_after_activation(self):
        self.assertEqual(self.post("settings", {"jamendo_id": "abcd1234", "jamendo_on": True}).status, 200)
        items = self.get("/ext/search", src="jamendo", q="groove").json()["items"]
        self.assertEqual([i["title"] for i in items], ["Groove"])
        url = self.http.calls[-1][0]
        self.assertIn("client_id=abcd1234", url)
        self.get("/ext/search", src="jamendo", q="groove")
        self.assertEqual(len(self.http.calls), 1)                 # deuxième recherche : cache

    def test_youtube_search_and_off_switch(self):
        self.post("settings", {"youtube_key": "KEY", "youtube_on": True})
        items = self.get("/ext/search", src="youtube", q="daft").json()["items"]
        self.assertEqual((items[0]["youtubeId"], items[0]["duration"]), ("abc123", 205))
        self.assertIn("videoEmbeddable=true", self.http.calls[-2][0])
        self.post("settings", {"youtube_on": False})
        self.assertEqual(self.get("/ext/search", src="youtube", q="daft").status, 502)
        self.assertTrue(self.get("/ext/status").json()["youtube"]["configured"])      # la clé reste enregistrée

    def test_unplayable_youtube_videos_are_dropped_with_durations_added(self):
        self.http.routes["youtube/v3/videos"] = {"items": [
            {"id": "abc123", "status": {"embeddable": False}, "contentDetails": {"duration": "PT1M"}}]}
        self.post("settings", {"youtube_key": "KEY", "youtube_on": True})
        self.assertEqual(self.get("/ext/search", src="youtube", q="daft").json()["items"], [])

    def test_youtube_keeps_results_if_the_check_fails(self):
        from pimedia.server.podcasts.directories import DirectoryError
        self.http.routes["youtube/v3/videos"] = DirectoryError("panne")
        self.post("settings", {"youtube_key": "KEY", "youtube_on": True})
        self.assertEqual(len(self.get("/ext/search", src="youtube", q="daft").json()["items"]), 1)

    def test_refused_video_disappears_from_results(self):
        self.post("settings", {"youtube_key": "KEY", "youtube_on": True})
        self.assertEqual(len(self.get("/ext/search", src="youtube", q="daft").json()["items"]), 1)
        self.assertEqual(self.post("unplayable", {"id": "abc123"}).status, 200)
        self.assertEqual(self.get("/ext/search", src="youtube", q="daft").json()["items"], [])     # même depuis le cache
        self.assertEqual(self.post("unplayable", {"id": "<script>"}).status, 400)

    def test_live_versions_hidden_by_default_and_option(self):
        self.http.routes["googleapis.com"] = {"items": [
            {"id": {"videoId": "abc123"}, "snippet": {"title": "Toxic (Live)", "channelTitle": "X"}}]}
        self.post("settings", {"youtube_key": "KEY", "youtube_on": True})
        self.assertTrue(self.get("/ext/status").json()["studio"])
        self.assertEqual(self.get("/ext/search", src="youtube", q="toxic").json()["items"], [])
        self.post("settings", {"studio": False})
        self.assertEqual([i["title"] for i in self.get("/ext/search", src="youtube", q="toxic").json()["items"]], ["Toxic (Live)"])

    def test_alternative_version_for_a_refused_video(self):
        self.http.routes["googleapis.com"] = {"items": [
            {"id": {"videoId": "vevo1"}, "snippet": {"title": "Britney Spears - Toxic (Official HD Video)", "channelTitle": "BritneySpearsVEVO"}},
            {"id": {"videoId": "other"}, "snippet": {"title": "Oops I Did It Again", "channelTitle": "Britney Spears - Topic"}},
            {"id": {"videoId": "topic1"}, "snippet": {"title": "Toxic", "channelTitle": "Britney Spears - Topic"}}]}
        self.http.routes["youtube/v3/videos"] = {"items": [
            {"id": i, "status": {"embeddable": True}, "contentDetails": {"duration": "PT3M"}} for i in ("vevo1", "other", "topic1")]}
        self.post("settings", {"youtube_key": "KEY", "youtube_on": True})
        self.post("unplayable", {"id": "vevo1"})
        found = self.get("/ext/alternative", id="vevo1", title="Britney Spears - Toxic (Official HD Video)", artist="BritneySpearsVEVO").json()
        self.assertEqual(found["item"]["youtubeId"], "topic1")               # même chanson, pas « Oops »
        none = self.get("/ext/alternative", id="x", title="Chanson introuvable", artist="Personne").json()
        self.assertIsNone(none["item"])

    def test_status_never_reveals_keys(self):
        self.post("settings", {"youtube_key": "SECRETKEY", "jamendo_id": "SECRETID"})
        self.assertNotIn(b"SECRET", self.get("/ext/status").body)

    def test_short_query_and_unknown_source(self):
        self.post("settings", {"jamendo_id": "x", "jamendo_on": True})
        self.assertEqual(self.get("/ext/search", src="jamendo", q="a").json(), {"items": []})
        self.assertEqual(self.get("/ext/search", src="nope", q="abc").status, 502)

    def test_playlist_lifecycle(self):
        song = {"id": "s1", "title": "T", "artist": "A", "coverArt": "c"}
        list_id = self.post("create", {"name": "Soirée", "songs": [song]}).json()["id"]
        self.post("add", {"id": list_id, "songs": [{"id": "yt-1", "title": "V", "youtubeId": "1", "ext": "youtube"}]})
        shown = self.get("/ext/playlist", id=list_id).json()
        self.assertEqual([s["id"] for s in shown["songs"]], ["s1", "yt-1"])
        self.assertEqual(self.get("/ext/playlists").json()["lists"], [{"id": list_id, "name": "Soirée", "count": 2}])
        self.post("remove", {"id": list_id, "index": 0})
        self.assertEqual(len(self.get("/ext/playlist", id=list_id).json()["songs"]), 1)
        self.post("delete", {"id": list_id})
        self.assertEqual(self.get("/ext/playlist", id=list_id).status, 404)

    def test_favorites_api(self):
        video = {"id": "yt-9", "title": "Clip", "youtubeId": "9", "ext": "youtube"}
        self.assertEqual(self.post("favorite", {"song": video}).json()["starred"], True)
        self.assertEqual([s["id"] for s in self.get("/ext/favorites").json()["songs"]], ["yt-9"])
        self.assertEqual(self.get("/ext/playlists").json()["lists"], [])
        self.assertEqual(self.post("favorite", {"song": video}).json()["starred"], False)
        self.assertEqual(self.post("favorite", {"song": {"id": "x"}}).status, 400)
        self.assertEqual(self.post("favorite", {"song": video}, csrf=False).status, 403)

    def test_writes_need_csrf_header_and_valid_data(self):
        self.assertEqual(self.post("create", {"name": "x"}, csrf=False).status, 403)
        self.assertEqual(self.post("create", {"name": ""}).status, 400)
        self.assertEqual(self.post("add", {"id": "inconnue", "songs": []}).status, 404)
        self.assertEqual(self.post("add", {"id": "x", "songs": "pas une liste"}).status, 400)



if __name__ == "__main__":
    unittest.main()
