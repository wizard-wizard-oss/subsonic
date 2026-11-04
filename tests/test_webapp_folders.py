"""Édition PC : pages artiste et album tirées des dossiers (getMusicDirectory), pas des tags ID3."""
import unittest

from pimedia.webapp.artist_index import parse_index
from pimedia.webapp.library import mac_leftover, visible
from tests.webapp_support import WebAppTestCase


class FolderPagesTest(WebAppTestCase):
    def setUp(self):
        super().setUp()
        self.bob = self.client("bob", "pw2")

    def test_artist_page_lists_the_album_folders(self):
        artist = self.bob.get("/api/artist?id=fdir-ar1").json()
        self.assertEqual((artist["id"], artist["name"], artist["id3Id"]), ("fdir-ar1", "ABBA", "ar1"))
        self.assertEqual([(a["id"], a["name"], a["year"], a["artistId"]) for a in artist["albums"]],
                         [("fdir-al2", "Waterloo", 1974, "fdir-ar1"), ("fdir-al1", "Arrival", 1976, "fdir-ar1")])

    def test_macos_leftovers_are_never_shown(self):
        """Dossier « __MACOSX » (copié depuis un Mac) : ni album dans une page artiste, ni « ._ » parmi les titres."""
        real = self.subsonic._folder
        def with_leftovers(folder_id, user):
            folder = real(folder_id, user)
            if folder_id == "dir-ar1":
                folder = dict(folder, child=folder["child"] + [{"id": "dir-mac", "isDir": True, "title": "__MACOSX",
                                                                "path": "ABBA/__MACOSX"}])
            elif folder_id == "dir-al1":
                folder = dict(folder, child=folder["child"] + [dict(folder["child"][0], id="mac-s", title="._01 Intro",
                                                                    path="ABBA/Arrival/._01 Intro.mp3")])
            return folder
        self.subsonic._folder = with_leftovers
        self.assertEqual([a["name"] for a in self.bob.get("/api/artist?id=fdir-ar1").json()["albums"]], ["Waterloo", "Arrival"])
        self.assertNotIn("mac-s", [s["id"] for s in self.bob.get("/api/album?id=fdir-al1").json()["songs"]])

    def test_an_album_without_cover_takes_the_one_of_its_discs(self):
        """« Compilations/70's Funk/Disc 1/Folder.jpg » : l'image n'est que dans le dossier du disque."""
        real = self.subsonic._folder
        def cover_in_discs(folder_id, user):
            folder = real(folder_id, user)
            if folder_id == "dir-ar1":
                folder = dict(folder, child=[dict(c, coverArt=None) if c["id"] == "dir-al1" else c for c in folder["child"]])
            elif folder_id == "dir-al1":
                folder = dict(folder, child=[dict(c, coverArt="dir-al1-cd2") if c["id"] == "dir-al1-cd2" else c
                                             for c in folder["child"]])
            return folder
        self.subsonic._folder = cover_in_discs
        albums = {a["name"]: a["coverId"] for a in self.bob.get("/api/artist?id=fdir-ar1").json()["albums"]}
        self.assertEqual(albums["Arrival"], "dir-al1-cd2")                          # cd1 n'en a pas, cd2 oui
        self.assertTrue(albums["Waterloo"])                                         # ceux qui en ont une la gardent

    def test_a_tag_link_opens_the_folder_page(self):
        """Liens venus des listes d'albums, de la recherche, d'un titre : identifiant ID3, ramené au dossier."""
        self.assertEqual(self.bob.get("/api/artist?id=ar1").json()["id"], "fdir-ar1")
        self.assertEqual(self.bob.get("/api/album?id=al1").json()["folderId"], "fdir-al1")

    def test_folder_names_win_over_tags(self):
        rename = self.subsonic._folder
        self.subsonic._folder = lambda folder_id, user: dict(rename(folder_id, user), name="Dälek") \
            if folder_id == "dir-ar1" else rename(folder_id, user)
        self.assertEqual(self.bob.get("/api/artist?id=fdir-ar1").json()["name"], "Dälek")
        self.assertEqual(self.bob.get("/api/album?id=fdir-al1").json()["artist"], "Dälek")

    def test_album_page_reads_the_folder_and_its_discs(self):
        album = self.bob.get("/api/album?id=fdir-al1").json()
        self.assertEqual((album["id"], album["folderId"], album["name"], album["artist"], album["artistId"]),
                         ("al1", "fdir-al1", "Arrival", "ABBA", "fdir-ar1"))      # id ID3 : commentaires, note, favori
        self.assertEqual([s["id"] for s in album["songs"]], ["s1", "s2"])         # CD1 puis CD2
        self.assertEqual(album["duration"], 470)
        self.assertIn("rating", album)
        self.assertIn("comments", album)

    def test_unknown_folder_is_not_found(self):
        self.assertEqual(self.bob.get("/api/artist?id=fdir-nope").status, 404)
        self.assertEqual(self.bob.get("/api/album?id=fdir-nope").status, 404)

    def test_artist_heart_stars_the_folder(self):
        answer = self.bob.post_json("/api/favorite", {"kind": "folder", "id": "fdir-ar1", "on": True})
        self.assertEqual(answer.json(), {"starred": True})
        self.assertEqual(self.subsonic.starred_folders, {"dir-ar1"})
        self.assertTrue(self.bob.get("/api/artist?id=fdir-ar1").json()["starred"])
        self.assertEqual(self.bob.post_json("/api/favorite", {"kind": "folder", "id": "ar1", "on": True}).status, 400)


class MacLeftoversTest(unittest.TestCase):
    def test_what_counts_as_a_leftover(self):
        for raw in ({"title": "__MACOSX", "isDir": True}, {"name": "__MACOSX"}, {"path": "Compilations/__MACOSX/x/._a.jpg"},
                    {"path": "Mogwai/The Hawk Is Howling/._04 Local Authority.mp3", "title": "Local Authority"}):
            self.assertTrue(mac_leftover(raw), raw)
        for raw in ({"title": "Le grand départ", "path": "Bastien Lune/Minuit passé/01.mp3"}, {"name": "MACOSX fan club"}, {}):
            self.assertFalse(mac_leftover(raw), raw)
        self.assertEqual(visible([{"name": "Post"}, {"name": "__MACOSX"}]), [{"name": "Post"}])
        self.assertEqual(visible(None), [])

    def test_the_artist_list_skips_them(self):
        raw = {"indexes": {"index": [{"name": "#", "artist": [{"id": 9, "name": "__MACOSX"}]},
                                     {"name": "C", "artist": [{"id": 1, "name": "Compilations"}, {"id": 2, "name": "Incoming"}]}]}}
        self.assertEqual(parse_index(raw, hidden=("incoming",)),
                         [{"letter": "C", "artists": [{"id": "f1", "name": "Compilations"}]}])
