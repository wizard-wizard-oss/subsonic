"""Édition PC : musique d'ailleurs (Jamendo, YouTube) avec une clé par source dans le .env du site."""
import json
import types

from pimedia.server.extmusic.ytmusic import YouTubeMusicSearch
from pimedia.server.podcasts.directories import DirectoryError
from pimedia.webapp.app import WebApplication
from pimedia.webapp.extmusic import OFFICIAL_SEARCHES_PER_HOUR, YOUTUBE_SEARCHES_PER_HOUR
from tests.support import FakeYouTubeMusic, youtube_music_down
from tests.test_podcasts import FakeHttp
from tests.webapp_support import PROJECT, WebAppTestCase

BOB = types.SimpleNamespace(username="bob")
KEYS = {"PI_MEDIA_WEB_EXT_JAMENDO_ID": "jamendo-secret", "PI_MEDIA_WEB_EXT_YOUTUBE_KEY": "youtube-secret"}
JAMENDO = {"headers": {"status": "success"}, "results": [
    {"id": "11", "name": "Groove", "artist_name": "Fankel", "album_name": "Album", "duration": 272,
     "audio": "https://prod-1.storage.jamendo.com/?trackid=11&format=mp32", "image": "https://usercontent.jamendo.com/11.jpg"},
    {"id": "12", "name": "Sans audio", "audio": ""}]}
YOUTUBE = {"items": [
    {"id": {"videoId": "abc123def45"}, "snippet": {"title": "Daft Punk - One More Time (Official Audio)",
                                                   "channelTitle": "Daft Punk - Topic",
                                                   "thumbnails": {"medium": {"url": "https://i.ytimg.com/a.jpg"}}}},
    {"id": {"videoId": "liveversion"}, "snippet": {"title": "One More Time (Live at Bercy)", "channelTitle": "Fan"}},
    {"id": {"videoId": "otherone123"}, "snippet": {"title": "Daft Punk - One More Time", "channelTitle": "Daft Punk"}}]}
VIDEOS = {"items": [
    {"id": item["id"]["videoId"], "snippet": item["snippet"], "status": {"embeddable": True, "privacyStatus": "public"},
     "contentDetails": {"duration": "PT5M20S"}} for item in YOUTUBE["items"]]}

MUSIC_SONGS = [{"title": "One More Time", "videoId": "abc123def45", "duration_seconds": 320,
                "artists": [{"name": "Daft Punk", "id": "UC1"}], "album": {"name": "Discovery"}},
               {"title": "One More Time (Live at Bercy)", "videoId": "liveversion", "artists": [{"name": "Fan", "id": "UC9"}]}]

class ExtMusicHttpTest(WebAppTestCase):
    environ = KEYS

    def setUp(self):
        super().setUp()
        self.http = FakeHttp({"jamendo.com": JAMENDO, "youtube/v3/videos": VIDEOS, "youtube/v3/search": YOUTUBE})
        for source in self.app.extmusic.service.sources.values():
            source.http = self.http

    def search(self, client, source, term):
        return client.get("/api/ext/search?src=%s&q=%s" % (source, term))

    def test_sources_come_from_the_site_env_and_keys_never_leave_the_server(self):
        bob = self.client("bob", "pw2")
        status = bob.get("/api/ext/status")
        self.assertEqual(status.json(), {"jamendo": True, "youtube": True})
        found = self.search(bob, "jamendo", "groove")
        for response in (status, found, self.search(bob, "youtube", "daft")):
            self.assertNotIn(b"secret", response.body)

    def test_jamendo_and_youtube_results(self):
        bob = self.client("bob", "pw2")
        jamendo = self.search(bob, "jamendo", "groove").json()["items"]
        self.assertEqual([(t["title"], t["ext"]) for t in jamendo], [("Groove", "jamendo")])        # sans son : écarté
        youtube = self.search(bob, "youtube", "one+more+time").json()["items"]
        self.assertEqual([(t["youtubeId"], t["artist"], t["duration"]) for t in youtube],
                         [("abc123def45", "Daft Punk", 320), ("otherone123", "Daft Punk", 320)])   # live écarté
        self.assertEqual(self.search(bob, "youtube", "x").json()["items"], [])                     # trop court

    def test_youtube_music_answers_without_quota(self):
        self.app.extmusic.youtube.music = YouTubeMusicSearch(FakeYouTubeMusic({"songs": MUSIC_SONGS}))
        found = self.search(self.client("bob", "pw2"), "youtube", "one+more+time").json()["items"]
        self.assertEqual([(t["youtubeId"], t["artist"], t["album"], t["duration"]) for t in found],
                         [("abc123def45", "Daft Punk", "Discovery", 320)])                # live écarté
        self.assertEqual(self.youtube_searches(), 0)

    def test_searches_are_limited_per_person(self):
        self.app.extmusic.youtube.music = YouTubeMusicSearch(FakeYouTubeMusic({"songs": MUSIC_SONGS}))
        bob, alice = self.client("bob", "pw2"), self.client("alice", "secret")
        for n in range(YOUTUBE_SEARCHES_PER_HOUR):
            self.assertEqual(self.search(bob, "youtube", "titre%d" % n).status, 200)
        self.assertEqual(self.search(bob, "youtube", "titre0").status, 200)          # déjà cherché : gratuit
        refused = self.search(bob, "youtube", "encore")
        self.assertEqual((refused.status, refused.json()["error"]), (400, "ext.too_many_searches"))
        self.assertEqual(self.search(alice, "youtube", "encore").status, 200)        # les autres ne sont pas bloqués
        self.assertEqual(self.search(bob, "jamendo", "encore").status, 200)          # Jamendo n'a pas cette limite

    def test_official_api_is_a_fallback_limited_for_the_whole_site(self):
        bob, alice = self.client("bob", "pw2"), self.client("alice", "secret")       # YouTube Music en panne
        for n in range(OFFICIAL_SEARCHES_PER_HOUR):
            self.assertEqual(self.search(bob if n % 2 else alice, "youtube", "titre%d" % n).status, 200)
        self.assertEqual(self.youtube_searches(), OFFICIAL_SEARCHES_PER_HOUR)
        refused = self.search(alice, "youtube", "encore")
        self.assertEqual((refused.status, refused.json()["error"]), (400, "ext.too_many_searches"))
        self.assertEqual(self.search(alice, "youtube", "titre0").status, 200)        # déjà cherché : gratuit
        self.app.extmusic.youtube.music = YouTubeMusicSearch(FakeYouTubeMusic({"songs": MUSIC_SONGS}))
        self.assertEqual(self.search(alice, "youtube", "encore").status, 200)        # YouTube Music revenu

    def test_refused_video_is_hidden_and_another_version_is_proposed(self):
        bob = self.client("bob", "pw2")
        other = bob.post_json("/api/ext/alternative", {"id": "abc123def45", "title": "Daft Punk - One More Time (Official Audio)",
                                                       "artist": "Daft Punk"}).json()["item"]
        self.assertEqual(other["youtubeId"], "otherone123")
        alice = self.client("alice", "secret")
        ids = [t["youtubeId"] for t in self.search(alice, "youtube", "one+more+time").json()["items"]]
        self.assertEqual(ids, ["otherone123"])                                      # plus proposée à personne
        self.assertEqual(bob.post_json("/api/ext/unplayable", {"id": "<script>"}).status, 400)
        self.assertEqual(bob.post_json("/api/ext/unplayable", {"id": "otherone123"}).status, 200)
        nothing = bob.post_json("/api/ext/alternative", {"id": "otherone123", "title": "One More Time"}).json()
        self.assertIsNone(nothing["item"])                                          # rien de sûr : on passera au suivant

    def test_player_errors_that_say_nothing_about_the_video_change_nothing(self):
        bob = self.client("bob", "pw2")
        searches = self.youtube_searches()
        for code in ("153", "5", "2", "youtube-unreachable"):
            answer = bob.post_json("/api/ext/alternative", {"id": "abc123def45", "title": "One More Time", "code": code})
            self.assertIsNone(answer.json()["item"])
            self.assertEqual(bob.post_json("/api/ext/unplayable", {"id": "abc123def45", "code": code}).status, 200)
        self.assertEqual(self.youtube_searches(), searches)                       # aucune recherche lancée
        ids = [t["youtubeId"] for t in self.search(bob, "youtube", "one+more+time").json()["items"]]
        self.assertIn("abc123def45", ids)                                           # toujours proposée à tous
        self.assertEqual(bob.post_json("/api/ext/alternative", {"id": "<x>", "code": "153"}).status, 400)

    def restarted_site(self):
        """Le même site relancé : nouvelle application, même dossier de données."""
        app = WebApplication(PROJECT, environ=dict(KEYS, PI_MEDIA_WEB_SUBSONIC_URL=self.subsonic.url), data_dir=self.tmp)
        for source in app.extmusic.service.sources.values():
            source.http = self.http
        app.extmusic.youtube.music = youtube_music_down()
        return app.extmusic

    def youtube_searches(self):
        return sum("youtube/v3/search" in url for url, _ in self.http.calls)

    def test_youtube_searches_are_kept_for_good_even_after_a_restart(self):
        bob = self.client("bob", "pw2")
        self.search(bob, "youtube", "daft")
        self.search(self.client("alice", "secret"), "youtube", "Daft")              # autre personne : gratuit
        self.assertEqual(self.youtube_searches(), 1)
        self.assertEqual(len(self.restarted_site().search(BOB, "youtube", "daft")), 2)
        self.assertEqual(self.youtube_searches(), 1)                                 # toujours rien de redemandé
        self.app.db.execute("UPDATE ext_searches SET searched_at = searched_at - ?", (400 * 86400,))
        self.search(bob, "youtube", "daft")
        self.assertEqual(self.youtube_searches(), 1)                                 # même vieille : gardée
        stored = self.app.db.one("SELECT results FROM ext_searches WHERE search_key = 'youtube:daft'")["results"]
        self.assertNotIn("Daft Punk", stored)                                        # seulement les vidéos, pas leurs titres

    def test_jamendo_searches_are_kept_90_days(self):
        bob = self.client("bob", "pw2")
        self.search(bob, "jamendo", "groove")
        self.search(bob, "jamendo", "groove")
        jamendo = lambda: sum("jamendo.com" in url for url, _ in self.http.calls)
        self.assertEqual(jamendo(), 1)
        self.app.db.execute("UPDATE ext_searches SET searched_at = searched_at - ?", (91 * 86400,))
        self.search(bob, "jamendo", "groove")
        self.assertEqual(jamendo(), 2)                                               # trop vieille : refaite

    def test_videos_already_found_are_proposed_without_quota(self):
        bob = self.client("bob", "pw2")
        self.assertEqual(bob.get("/api/ext/known?q=one+more").json()["items"], [])
        self.search(bob, "youtube", "daft")
        calls = len(self.http.calls)
        bob.post_json("/api/ext/played", {"id": "otherone123"})
        found = self.client("alice", "secret").get("/api/ext/known?q=ONE+MORE").json()["items"]
        self.assertEqual([(i["youtubeId"], i["title"], i["duration"], i["playedHere"]) for i in found],
                         [("otherone123", "Daft Punk - One More Time", 320, 1),       # déjà lue ici : en tête
                          ("abc123def45", "Daft Punk - One More Time (Official Audio)", 320, 0)])
        self.assertEqual(len(self.http.calls), calls)                                # rien demandé à YouTube
        self.assertEqual(bob.get("/api/ext/known?q=punk").json()["items"][0]["artist"], "Daft Punk")   # chaîne aussi
        self.assertEqual(bob.get("/api/ext/known?q=ore").json()["items"], [])         # début de mot seulement
        bob.post_json("/api/ext/unplayable", {"id": "abc123def45"})
        self.assertEqual([i["youtubeId"] for i in bob.get("/api/ext/known?q=one").json()["items"]], ["otherone123"])

    def test_kept_videos_are_rechecked_after_30_days_and_vanished_ones_forgotten(self):
        bob = self.client("bob", "pw2")
        self.search(bob, "youtube", "daft")
        site = self.app.extmusic
        self.assertEqual(site.recheck(), 0)                                          # rien d'assez vieux
        self.app.db.execute("UPDATE youtube_videos SET checked_at = checked_at - ?", (31 * 86400,))
        renamed = dict(VIDEOS["items"][0], snippet=dict(VIDEOS["items"][0]["snippet"], title="One More Time (Remastered)"))
        self.http.routes["youtube/v3/videos"] = {"items": [renamed]}                 # les autres ont été supprimées
        searches = self.youtube_searches()
        self.assertEqual(site.recheck(), 2)                                          # dont la version live, gardée aussi
        self.assertEqual(self.youtube_searches(), searches)                          # relue sans nouvelle recherche
        found = self.search(bob, "youtube", "daft").json()["items"]
        self.assertEqual([(i["youtubeId"], i["title"]) for i in found], [("abc123def45", "One More Time (Remastered)")])
        self.assertEqual(self.app.db.one("SELECT results FROM ext_searches WHERE search_key = 'youtube:daft'")["results"],
                         '["abc123def45"]')
        self.assertEqual(site.recheck(), 0)                                          # relue : tranquille 30 jours
        self.http.routes["youtube/v3/videos"] = {"items": []}
        self.app.db.execute("UPDATE youtube_videos SET checked_at = checked_at - ?", (31 * 86400,))
        site.recheck()
        self.search(bob, "youtube", "daft")
        self.assertEqual(self.youtube_searches(), searches + 1)                     # plus rien de lisible : refaite

    def test_youtube_searches_kept_before_the_upgrade_are_still_used(self):
        old = [dict(i, playedHere=0) for i in self.app.extmusic.youtube.search("daft")]
        self.app.db.execute("INSERT INTO ext_searches (search_key, results, searched_at) VALUES ('youtube:old', ?, 1)",
                            (json.dumps(old),))
        searches = self.youtube_searches()
        self.assertEqual(len(self.search(self.client("bob", "pw2"), "youtube", "old").json()["items"]), 2)
        self.assertEqual(self.youtube_searches(), searches)
        self.assertEqual(len(self.app.extmusic.videos.stale(0)), 3)                 # à relire dès que possible (live compris)

    def test_refusals_are_kept_with_their_code_and_played_videos_come_first(self):
        bob = self.client("bob", "pw2")
        bob.post_json("/api/ext/unplayable", {"id": "abc123def45", "code": 150})
        site = self.restarted_site()
        self.assertEqual(site.videos.error_code("abc123def45"), "150")
        self.assertEqual([i["youtubeId"] for i in site.search(BOB, "youtube", "daft")], ["otherone123"])
        bob.post_json("/api/ext/played", {"id": "abc123def45"})                    # finalement lue : plus refusée
        bob.post_json("/api/ext/played", {"id": "otherone123"})
        bob.post_json("/api/ext/played", {"id": "otherone123"})
        found = self.search(bob, "youtube", "daft").json()["items"]
        self.assertEqual([(i["youtubeId"], i["playedHere"]) for i in found], [("otherone123", 2), ("abc123def45", 1)])
        self.assertEqual(bob.post_json("/api/ext/played", {"id": "x"}).status, 400)

    def test_a_refused_video_is_tried_again_after_90_days(self):
        bob = self.client("bob", "pw2")
        bob.post_json("/api/ext/unplayable", {"id": "abc123def45", "code": 101})
        self.assertEqual(len(self.search(bob, "youtube", "daft").json()["items"]), 1)
        self.app.db.execute("UPDATE youtube_videos SET refused_at = refused_at - ?", (91 * 86400,))
        self.assertEqual(len(self.search(bob, "youtube", "daft").json()["items"]), 2)

    def test_errors(self):
        bob = self.client("bob", "pw2")
        self.assertEqual(self.search(bob, "spotify", "x").json()["error"], "ext.disabled")
        self.http.routes["jamendo.com"] = DirectoryError("panne")
        self.assertEqual(self.search(bob, "jamendo", "panne").json()["error"], "ext.unreachable")
        self.assertEqual(self.client().get("/api/ext/status").status, 401)

    def test_page_may_load_the_official_youtube_and_soundcloud_players_and_nothing_else(self):
        policy = self.client().get("/").headers["content-security-policy"]
        self.assertIn("script-src 'self' https://www.youtube.com https://w.soundcloud.com;", policy)
        self.assertIn("frame-src https://www.youtube-nocookie.com https://www.youtube.com https://w.soundcloud.com;", policy)
        self.assertIn("connect-src 'self';", policy)


class ExtMusicWithoutKeysTest(WebAppTestCase):
    def test_sources_are_off_without_keys(self):
        bob = self.client("bob", "pw2")
        self.assertEqual(bob.get("/api/ext/status").json(), {"jamendo": False, "youtube": False})
        self.assertEqual(bob.get("/api/ext/search?src=youtube&q=daft").json()["error"], "ext.disabled")
