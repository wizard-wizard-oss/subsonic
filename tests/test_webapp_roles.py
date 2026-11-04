"""Édition PC : chacun ne fait sur le site que ce que son compte Subsonic permet (droits lus par getUser).
Téléchargement d'un album (zip fait par Subsonic) ou d'un titre."""
from tests.webapp_support import WebAppTestCase


class RolesHttpTest(WebAppTestCase):
    def roles(self, client):
        return set(client.get("/api/me").json()["user"]["roles"])

    def test_rights_come_from_subsonic(self):
        alice, bob = self.client("alice", "secret"), self.client("bob", "pw2")
        self.assertTrue({"admin", "stream", "download", "playlist", "comment", "coverArt", "upload", "share"}
                        <= self.roles(alice))
        self.assertNotIn("admin", self.roles(bob))
        self.assertIn("download", self.roles(bob))

    def test_a_right_removed_in_subsonic_applies_at_the_next_page_load(self):
        bob = self.client("bob", "pw2")
        self.assertEqual(bob.get("/api/download?album=al2").status, 200)
        self.subsonic.roles["bob"] = {"downloadRole": False}
        self.assertNotIn("download", self.roles(bob))                         # sans se reconnecter
        refused = bob.get("/api/download?album=al2")
        self.assertEqual((refused.status, refused.json()["error"]), (403, "auth.missing_right"))

    def test_rights_are_kept_when_subsonic_does_not_answer(self):
        bob = self.client("bob", "pw2")
        self.subsonic.api_getUser = lambda h, p: h.reply(200, b"<html>", "text/html")
        self.assertIn("download", self.roles(bob))

    def test_download_an_album_or_a_song(self):
        bob = self.client("bob", "pw2")
        album = bob.get("/api/download?album=al1")
        self.assertEqual((album.status, album.body), (200, b"PK\x03\x04zip"))
        self.assertEqual(album.headers["content-disposition"], 'attachment; filename="dir-al1.zip"')
        song = bob.get("/api/download?song=s3")
        self.assertEqual((song.status, song.headers["content-type"]), (200, "audio/flac"))
        # Arrival a un dossier par disque : Subsonic zippe le dossier qui les contient
        self.assertEqual(self.subsonic.downloads, ["dir-al1", "s3"])
        for bad in ("", "?album=../x", "?album=zz", "?song="):
            self.assertIn(bob.get("/api/download" + bad).status, (400, 404), bad)

    def test_each_right_guards_its_actions(self):
        self.subsonic.roles["bob"] = {"streamRole": False, "playlistRole": False, "commentRole": False,
                                      "downloadRole": False}
        bob = self.client("bob", "pw2")
        for refused in (bob.get("/api/stream?id=s1"), bob.get("/api/download?song=s1"),
                        bob.post_json("/api/playlist/create", {"name": "Été"}),
                        bob.post_json("/api/rating", {"albumId": "al1", "rating": 4}),
                        bob.post_json("/api/chat/post", {"topic": "album:al1", "body": "Super"})):
            self.assertEqual((refused.status, refused.json()["error"]), (403, "auth.missing_right"))
        self.assertEqual(bob.post_json("/api/chat/post", {"topic": "general", "body": "Salut"}).status, 200)   # salon libre
        self.assertEqual(bob.get("/api/playlists").status, 200)                # lire reste permis
        self.assertEqual(self.subsonic.ratings, {})

    def test_everything_allowed_with_all_rights(self):
        alice = self.client("alice", "secret")
        self.assertEqual(alice.get("/api/stream?id=s1").status, 200)
        self.assertEqual(alice.post_json("/api/playlist/create", {"name": "Été"}).status, 200)
        self.assertEqual(alice.post_json("/api/chat/post", {"topic": "album:al1", "body": "Super"}).status, 200)
