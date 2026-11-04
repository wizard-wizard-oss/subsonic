"""Import d'une playlist venue d'ailleurs : lecture (Deezer, CSV, Apple Music, M3U, texte), notes, pages HTTP."""
import plistlib
import unittest

from pimedia.server.extmusic.ytmusic import YouTubeMusicSearch
from pimedia.webapp.entities import ImportedTrack
from pimedia.webapp.import_readers import (MAX_TRACKS, DeezerReader, ImportFailed, NeedsChoice, deezer_playlist_id,
                                           read_file, seconds)
from pimedia.webapp.playlist_import import core_title, score, youtube_score
from tests.support import FakeYouTubeMusic
from tests.test_podcasts import FakeHttp
from tests.test_webapp_ext import KEYS, MUSIC_SONGS, VIDEOS
from tests.webapp_support import WebAppTestCase

EXPORTIFY = ('"Track URI","Track Name","Album Name","Artist Name(s)","Release Date","Duration (ms)","ISRC"\n'
             '"spotify:track:1","Dancing Queen","Arrival","ABBA","1976-10-11","230400","SEAYD7601020"\n'
             '"spotify:track:2","Get Lucky (feat. Pharrell Williams)","Random Access Memories","Daft Punk,Pharrell Williams",'
             '"2013","369626","USQX91300108"\n')
SEMICOLONS = "Track name;Artist name;Album;Duration\nWaterloo;ABBA;Waterloo;2:50\n;sans titre;;\n"
M3U = "#EXTM3U\n#EXTINF:235,Björk - Army of Me\nmusique/army.mp3\n#EXTINF:-1,Sans artiste\nx.mp3\n"
APPLE = plistlib.dumps({
    "Tracks": {"10": {"Track ID": 10, "Name": "Army of Me", "Artist": "Björk", "Album": "Post", "Total Time": 235000},
               "11": {"Track ID": 11, "Name": "Hyperballad", "Album Artist": "Björk"}},
    "Playlists": [{"Name": "Bibliothèque", "Master": True, "Playlist Items": [{"Track ID": 10}, {"Track ID": 11}]},
                  {"Name": "Islande", "Playlist Items": [{"Track ID": 11}, {"Track ID": 10}, {"Track ID": 99}]}]}).decode()
# Export de toute la bibliothèque (Fichier → Bibliothèque → Exporter la bibliothèque) : plusieurs playlists.
LIBRARY = plistlib.dumps({
    "Tracks": {"1": {"Name": "Dancing Queen", "Artist": "ABBA", "Total Time": 230000},
               "2": {"Name": "Army of Me", "Artist": "Björk", "Total Time": 235000}},
    "Playlists": [{"Name": "Bibliothèque", "Master": True, "Playlist Items": [{"Track ID": 1}, {"Track ID": 2}]},
                  {"Name": "Musique", "Distinguished Kind": 4, "Playlist Items": [{"Track ID": 1}, {"Track ID": 2}]},
                  {"Name": "Dossier", "Folder": True, "Playlist Items": [{"Track ID": 1}]},
                  {"Name": "Acid", "Playlist Items": [{"Track ID": 2}]},
                  {"Name": "Vide"},
                  {"Name": "Thomas", "Playlist Items": [{"Track ID": 1}, {"Track ID": 2}]}]}).decode()
DEEZER_PLAYLIST = {"id": 77, "title": "En mode 70"}
DEEZER_TRACKS = {"data": [
    {"title": "Dancing Queen", "duration": 231, "artist": {"name": "ABBA"}, "album": {"title": "Arrival"}},
    {"title": "Army Of Me (Remastered)", "duration": 236, "artist": {"name": "Bjork"}, "album": {"title": "Post"}},
    {"title": "One More Time", "duration": 320, "artist": {"name": "Daft Punk"}, "album": {"title": "Discovery"}},
    {"title": "Chanson Introuvable", "duration": 200, "artist": {"name": "Personne"}, "album": {"title": "Rien"}}]}


class ReadersTest(unittest.TestCase):
    def test_exportify_csv(self):
        name, tracks = read_file("Ma playlist.csv", "﻿" + EXPORTIFY)
        self.assertEqual(name, "Ma playlist")
        self.assertEqual(tracks, [ImportedTrack("Dancing Queen", "ABBA", "Arrival", 230),
                                  ImportedTrack("Get Lucky (feat. Pharrell Williams)", "Daft Punk", "Random Access Memories", 369)])

    def test_other_csv_with_semicolons_and_empty_rows(self):
        self.assertEqual(read_file("x.csv", SEMICOLONS)[1], [ImportedTrack("Waterloo", "ABBA", "Waterloo", 170)])

    def test_apple_music_export_takes_the_playlist_not_the_library(self):
        name, tracks = read_file("Islande.xml", APPLE)
        self.assertEqual(name, "Islande")
        self.assertEqual([(t.title, t.artist, t.duration) for t in tracks], [("Hyperballad", "Björk", 0), ("Army of Me", "Björk", 235)])

    def test_whole_library_export_asks_which_playlist(self):
        with self.assertRaises(NeedsChoice) as caught:
            read_file("Bibliothèque.xml", LIBRARY)
        self.assertEqual(caught.exception.playlists, [{"index": 0, "name": "Acid", "count": 1},
                                                      {"index": 1, "name": "Thomas", "count": 2},
                                                      {"index": 2, "name": "Musique", "count": 2}])   # celles d'Apple à la fin
        name, tracks = read_file("Bibliothèque.xml", LIBRARY, 1)
        self.assertEqual((name, [t.title for t in tracks]), ("Thomas", ["Dancing Queen", "Army of Me"]))
        for bad in (3, -1):
            with self.assertRaises(ImportFailed):
                read_file("Bibliothèque.xml", LIBRARY, bad)

    def test_m3u_and_plain_lines(self):
        self.assertEqual(read_file("a.m3u", M3U)[1], [ImportedTrack("Army of Me", "Björk", "", 235), ImportedTrack("Sans artiste")])
        self.assertEqual(read_file("a.txt", "ABBA - Waterloo\n\n# note\nSans tiret\n")[1],
                         [ImportedTrack("Waterloo", "ABBA"), ImportedTrack("Sans tiret")])

    def test_unreadable_files(self):
        for name, content, key in (("a.csv", "", "import.empty"), ("a.xml", "<plist><dict>", "import.unknown_format"),
                                   ("a.csv", "Uri,Title\n", "import.empty")):
            with self.assertRaises(ImportFailed) as caught:
                read_file(name, content)
            self.assertEqual(caught.exception.args[0], key)

    def test_long_playlists_are_cut(self):
        self.assertEqual(len(read_file("a.txt", "\n".join("A - T%d" % n for n in range(MAX_TRACKS + 50)))[1]), MAX_TRACKS)

    def test_seconds(self):
        self.assertEqual([seconds(v) for v in ("3:25", "205", "1:02:03", "abc", "")], [205, 205, 3723, 0, 0])

    def test_deezer_links(self):
        self.assertEqual(deezer_playlist_id("https://www.deezer.com/fr/playlist/908622995?utm=x"), "908622995")
        self.assertEqual(deezer_playlist_id(" https://deezer.com/playlist/12 "), "12")
        for bad in ("https://evil.example/playlist/1", "https://www.deezer.com/fr/album/1", "javascript:alert(1)"):
            with self.assertRaises(ImportFailed):
                deezer_playlist_id(bad)

    def test_deezer_reader_pages_errors_and_short_links(self):
        followed = []
        http = FakeHttp({"playlist/77/tracks?index=0": dict(DEEZER_TRACKS, next="..."), "playlist/77/tracks": DEEZER_TRACKS,
                         "playlist/77": DEEZER_PLAYLIST, "playlist/5": {"error": {"code": 800}}})
        reader = DeezerReader(http, lambda link: followed.append(link) or "https://www.deezer.com/fr/playlist/77?host=1")
        name, tracks = reader.read("https://link.deezer.com/s/abcDEF123")
        self.assertEqual((name, len(tracks), followed), ("En mode 70", 8, ["https://link.deezer.com/s/abcDEF123"]))   # 2 pages
        self.assertIn("index=4", http.calls[-1][0])
        with self.assertRaises(ImportFailed) as caught:
            reader.read("https://www.deezer.com/playlist/5")
        self.assertEqual(caught.exception.args[0], "import.not_found")


class ScoreTest(unittest.TestCase):
    def test_core_title_drops_versions_and_guests(self):
        self.assertEqual(core_title("Hey Jude (Remastered 2015)"), "hey jude")
        self.assertEqual(core_title("Get Lucky (feat. Pharrell Williams)"), "get lucky")
        self.assertEqual(core_title("Wonderwall - Remastered"), "wonderwall")
        self.assertEqual(core_title("Live Forever"), "live forever")

    def test_score(self):
        track = ImportedTrack("Hey Jude (Remastered 2015)", "The Beatles", "1", 429)
        self.assertGreaterEqual(score(track, {"title": "Hey Jude", "artist": "The Beatles", "duration": 431}), 0.85)
        self.assertLess(score(track, {"title": "Hey Jude (Live at Shea)", "artist": "The Beatles", "duration": 300}), 0.85)
        self.assertLess(score(track, {"title": "Hey Joe", "artist": "Jimi Hendrix", "duration": 210}), 0.6)
        self.assertGreaterEqual(score(ImportedTrack("Army of Me", "Bjork"), {"title": "Army Of Me", "artist": "Björk"}), 0.85)

    def test_youtube_score_reads_the_artist_in_the_title(self):
        track = ImportedTrack("Toxic", "Britney Spears", "", 199)
        self.assertGreaterEqual(youtube_score(track, {"title": "Britney Spears - Toxic (Official HD Video)",
                                                      "artist": "britneyspearsVEVO", "duration": 211}), 0.75)
        self.assertLess(youtube_score(track, {"title": "Toxic (cover acoustique)", "artist": "Fan", "duration": 180}), 0.75)


class ImportHttpTest(WebAppTestCase):
    environ = KEYS

    def setUp(self):
        super().setUp()
        self.http = FakeHttp({"youtube/v3/videos": VIDEOS, "playlist/77/tracks": DEEZER_TRACKS, "playlist/77": DEEZER_PLAYLIST})
        for source in self.app.extmusic.service.sources.values():
            source.http = self.http
        self.app.imports.reader.http = self.http
        self.app.extmusic.youtube.music = YouTubeMusicSearch(FakeYouTubeMusic({"songs": MUSIC_SONGS}))
        self.bob = self.client("bob", "pw2")

    def test_link_to_playlist_in_order_with_youtube_in_its_place(self):
        read = self.bob.post_json("/api/import/read", {"link": "https://www.deezer.com/fr/playlist/77"}).json()
        self.assertEqual((read["name"], len(read["tracks"])), ("En mode 70", 4))
        results = self.bob.post_json("/api/import/match", {"tracks": read["tracks"]}).json()["results"]
        self.assertEqual([(r["status"], [c["id"] for c in r["choices"]][:1]) for r in results],
                         [("found", ["s1"]), ("found", ["s4"]), ("missing", []), ("missing", [])])
        missing = [r["track"] for r in results if r["status"] == "missing"]
        found = self.bob.post_json("/api/import/youtube", {"tracks": missing}).json()
        self.assertEqual(([i and i["youtubeId"] for i in found["items"]], found["stopped"]), (["abc123def45", None], None))
        entries = [{"songId": "s1"}, {"item": found["items"][0]}, {"songId": "s4"}]
        playlist = self.bob.post_json("/api/import/create", {"name": "En mode 70", "entries": entries}).json()["playlist"]
        songs = self.bob.get("/api/playlist?id=" + playlist["id"]).json()["songs"]
        self.assertEqual([s.get("youtubeId") or s["id"] for s in songs], ["s1", "abc123def45", "s4"])

    def test_choose_a_playlist_in_a_whole_library_export(self):
        choose = self.bob.post_json("/api/import/read", {"name": "Bibliothèque.xml", "content": LIBRARY}).json()
        self.assertEqual([p["name"] for p in choose["choose"]], ["Acid", "Thomas", "Musique"])
        read = self.bob.post_json("/api/import/read", {"name": "Bibliothèque.xml", "content": LIBRARY, "playlist": 1}).json()
        self.assertEqual((read["name"], len(read["tracks"])), ("Thomas", 2))
        for bad in ("1", True, 9):
            reply = self.bob.post_json("/api/import/read", {"name": "b.xml", "content": LIBRARY, "playlist": bad})
            self.assertEqual((reply.status, reply.json()["error"]), (400, "request.invalid"))

    def test_file_and_bad_requests(self):
        read = self.bob.post_json("/api/import/read", {"name": "liste.csv", "content": EXPORTIFY}).json()
        self.assertEqual(read["tracks"][0], {"title": "Dancing Queen", "artist": "ABBA", "album": "Arrival", "duration": 230})
        for path, body, key in (("/api/import/read", {"link": "https://evil.example/x"}, "import.bad_link"),
                                ("/api/import/read", {}, "request.invalid"),
                                ("/api/import/match", {"tracks": [{"title": "x"}] * 26}, "request.invalid"),
                                ("/api/import/match", {"tracks": [{"title": ""}]}, "request.invalid"),
                                ("/api/import/create", {"name": "x", "entries": []}, "import.nothing_chosen"),
                                ("/api/import/create", {"name": "x", "entries": [{"songId": "../x"}]}, "request.invalid")):
            reply = self.bob.post_json(path, body)
            self.assertEqual((reply.status, reply.json()["error"]), (400, key), path)

    def test_youtube_search_stops_at_the_personal_limit(self):
        budget = self.app.extmusic.budget
        budget.limit = 1
        tracks = [{"title": "One More Time", "artist": "Daft Punk"}, {"title": "Autre", "artist": "Quelqu'un"}]
        found = self.bob.post_json("/api/import/youtube", {"tracks": tracks}).json()
        self.assertEqual((len(found["items"]), found["stopped"]), (1, "ext.too_many_searches"))


if __name__ == "__main__":
    unittest.main()
