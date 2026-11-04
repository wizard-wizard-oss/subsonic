"""Recherche YouTube par YouTube Music (ytmusicapi simulé) et repli sur l'API officielle."""
import unittest

from pimedia.server.extmusic.sources import YouTubeSource
from pimedia.server.extmusic.ytmusic import VIDEO_SLOTS, YouTubeMusicSearch, mix, music_track
from pimedia.server.podcasts.directories import DirectoryError
from tests.support import FakeYouTubeMusic
from tests.test_podcasts import FakeHttp

SONG = {"resultType": "song", "title": "Get Lucky", "videoId": "4D7u5KF7SP8", "duration_seconds": 370,
        "artists": [{"name": "Daft Punk", "id": "UC1"}, {"name": "Pharrell Williams", "id": "UC2"},
                    {"name": "1,9 Md lectures", "id": None}],
        "album": {"name": "Random Access Memories", "id": "MPREb"}}
VIDEO = {"resultType": "video", "title": "Get Lucky (Official Audio)", "videoId": "5NV6Rdv1a3I", "duration_seconds": 249,
         "artists": [{"name": "Daft Punk", "id": "UC1"}, {"name": "882 M de vues", "id": None}], "album": None}
LIVE = dict(SONG, title="Get Lucky (Live at Coachella)", videoId="liveversion")
VIDEOS = {"items": [{"id": v, "status": {"embeddable": True, "privacyStatus": "public"},
                     "contentDetails": {"duration": "PT4M"}} for v in ("4D7u5KF7SP8", "5NV6Rdv1a3I", "officiel123")]}
OFFICIAL = {"items": [{"id": {"videoId": "officiel123"}, "snippet": {"title": "Get Lucky", "channelTitle": "Daft Punk - Topic"}}]}
CONFIG = {"ext_youtube_key": "cle", "ext_youtube_region": "BE"}


def track(video):
    return {"youtubeId": video}


class MusicTrackTest(unittest.TestCase):
    def test_song_keeps_real_artists_album_and_a_thumbnail_the_page_accepts(self):
        song = music_track(SONG)
        self.assertEqual((song["id"], song["title"], song["artist"], song["album"], song["duration"], song["ext"]),
                         ("yt-4D7u5KF7SP8", "Get Lucky", "Daft Punk, Pharrell Williams", "Random Access Memories", 370, "youtube"))
        self.assertEqual(song["imageUrl"], "https://i.ytimg.com/vi/4D7u5KF7SP8/mqdefault.jpg")

    def test_video_without_album_and_result_without_video(self):
        self.assertEqual((music_track(VIDEO)["artist"], music_track(VIDEO)["album"]), ("Daft Punk", ""))
        self.assertIsNone(music_track({"title": "Un album", "browseId": "MPRE"}))

    def test_mix_keeps_room_for_videos_without_duplicates(self):
        songs = [track("s%d" % n) for n in range(20)]
        videos = [track("v1"), track("s0")]
        mixed = [t["youtubeId"] for t in mix(songs, videos, 20)]
        self.assertEqual(mixed[:20 - VIDEO_SLOTS], ["s%d" % n for n in range(20 - VIDEO_SLOTS)])
        self.assertEqual(mixed[20 - VIDEO_SLOTS], "v1")
        self.assertEqual((len(mixed), len(set(mixed))), (20, 20))
        self.assertEqual([t["youtubeId"] for t in mix([], videos, 20)], ["v1", "s0"])


class YouTubeMusicSearchTest(unittest.TestCase):
    def test_songs_then_videos_for_the_region(self):
        fake = FakeYouTubeMusic({"songs": [SONG], "videos": [VIDEO]})
        found = YouTubeMusicSearch(fake).search("get lucky", 20, "BE")
        self.assertEqual([t["youtubeId"] for t in found], ["4D7u5KF7SP8", "5NV6Rdv1a3I"])
        self.assertEqual((fake.terms, fake.region), ([("get lucky", "songs"), ("get lucky", "videos")], "BE"))

    def test_any_library_failure_becomes_a_directory_error(self):
        class Broken:
            def search(self, term, filter, limit):
                raise KeyError("contents")              # YouTube a changé le format de ses pages
        with self.assertRaises(DirectoryError):
            YouTubeMusicSearch(lambda region: Broken()).search("x", 20, "FR")
        with self.assertRaises(DirectoryError):
            YouTubeMusicSearch(FakeYouTubeMusic()).search("x", 20, "FR")


class YouTubeSourceTest(unittest.TestCase):
    def source(self, music, guard=None):
        self.http = FakeHttp({"youtube/v3/videos": VIDEOS, "youtube/v3/search": OFFICIAL})
        return YouTubeSource(self.http, CONFIG, music, guard)

    def official_searches(self):
        return sum("youtube/v3/search" in url for url, _ in self.http.calls)

    def test_youtube_music_first_and_videos_still_checked(self):
        source = self.source(YouTubeMusicSearch(FakeYouTubeMusic({"songs": [SONG, LIVE], "videos": [VIDEO]})))
        found = source.search("get lucky")
        self.assertEqual([(t["youtubeId"], t["duration"]) for t in found], [("4D7u5KF7SP8", 240), ("5NV6Rdv1a3I", 240)])
        self.assertEqual(self.official_searches(), 0)                        # aucune recherche à 100 unités
        self.assertTrue(any("youtube/v3/videos" in url for url, _ in self.http.calls))   # illisible ici : écartée

    def test_no_result_is_an_answer_not_a_failure(self):
        source = self.source(YouTubeMusicSearch(FakeYouTubeMusic({})))
        self.assertEqual(source.search("rien"), [])
        self.assertEqual(self.official_searches(), 0)

    def test_official_api_when_youtube_music_is_down_or_absent(self):
        for music in (YouTubeMusicSearch(FakeYouTubeMusic()), None):
            source = self.source(music)
            self.assertEqual([t["youtubeId"] for t in source.search("get lucky")], ["officiel123"])
            self.assertEqual(self.official_searches(), 1)

    def test_the_guard_can_refuse_the_official_search(self):
        def refuse():
            raise ValueError("ext.too_many_searches")
        source = self.source(YouTubeMusicSearch(FakeYouTubeMusic()), refuse)
        with self.assertRaises(ValueError):
            source.search("get lucky")
        self.assertEqual(self.official_searches(), 0)
        working = self.source(YouTubeMusicSearch(FakeYouTubeMusic({"songs": [SONG]})), refuse)
        self.assertEqual(len(working.search("get lucky")), 1)              # YouTube Music n'est pas limité ici


if __name__ == "__main__":
    unittest.main()
