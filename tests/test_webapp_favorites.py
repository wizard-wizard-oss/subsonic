"""Favoris Subsonic : les deux identités de catalogue restent accessibles."""
from tests.webapp_support import WebAppTestCase


class FavoritesTest(WebAppTestCase):
    def setUp(self):
        super().setUp()
        self.bob = self.client("bob", "pw2")
        self.subsonic.api_getStarred = lambda h, p: h.reply_json({"starred": {
            "artist": {"id": "dir-ar1", "name": "ABBA"},
            "album": [{"id": "dir-al1", "title": "Arrival", "artist": "ABBA", "starred": "date"}],
            "song": {"id": "s1", "title": "Dancing Queen"}}})

    def test_folder_favorites_and_tag_favorites_are_combined(self):
        self.bob.post_json("/api/favorite", {"kind": "album", "id": "al3", "on": True})
        data = self.bob.get("/api/starred").json()
        self.assertEqual({a["id"] for a in data["albums"]}, {"al1", "al3"})
        self.assertEqual(data["artists"], [{"id": "fdir-ar1", "name": "ABBA"}])
        self.assertEqual([s["id"] for s in data["songs"]], ["s1"])
        self.assertFalse(data["hasMore"])
        self.assertEqual(self.bob.get("/api/album?id=al1").status, 200)
        self.assertEqual(self.bob.get("/api/artist?id=fdir-ar1").status, 200)

    def test_same_album_artist_and_song_only_appear_once(self):
        self.subsonic.api_getStarred2 = lambda h, p: h.reply_json({"starred2": {
            "artist": {"id": "ar1", "name": "ABBA"},
            "album": {"id": "al1", "name": "Arrival", "artist": "ABBA"},
            "song": {"id": "s1", "title": "Dancing Queen"}}})
        data = self.bob.get("/api/starred").json()
        self.assertEqual([a["id"] for a in data["albums"]], ["al1"])
        self.assertEqual([a["id"] for a in data["artists"]], ["fdir-ar1"])
        self.assertEqual([s["id"] for s in data["songs"]], ["s1"])

    def test_pagination_has_no_arbitrary_total_limit(self):
        self.subsonic.api_getStarred = lambda h, p: h.reply_json({"starred": {}})
        self.subsonic.api_getStarred2 = lambda h, p: h.reply_json({"starred2": {
            "album": [{"id": str(i), "name": str(i)} for i in range(85)]}})
        pages = [self.bob.get("/api/starred?page=" + str(page)).json() for page in range(3)]
        self.assertEqual([len(p["albums"]) for p in pages], [40, 40, 5])
        self.assertEqual([p["hasMore"] for p in pages], [True, True, False])
        self.assertEqual([a["id"] for p in pages for a in p["albums"]], [str(i) for i in range(85)])
        self.assertEqual(self.bob.get("/api/starred?page=-1").status, 400)

    def test_empty_and_macos_favorites(self):
        self.subsonic.api_getStarred = lambda h, p: h.reply_json({"starred": {
            "artist": {"id": "mac", "name": "__MACOSX"},
            "album": {"id": "mac", "title": "._Arrival"}}})
        data = self.bob.get("/api/starred").json()
        self.assertEqual((data["artists"], data["albums"], data["songs"]), ([], [], []))

    def test_folder_album_heart_can_be_removed(self):
        self.subsonic.starred_folders.add("dir-al1")
        original = self.subsonic._folder
        def folder(folder_id, user):
            raw = original(folder_id, user)
            return dict(raw, starred="date" if folder_id in self.subsonic.starred_folders else None)
        self.subsonic._folder = folder
        self.subsonic.api_getStarred = lambda h, p: h.reply_json({"starred": {"album": [
            {"id": "dir-al1", "title": "Arrival"}] if "dir-al1" in self.subsonic.starred_folders else []}})
        self.assertTrue(self.bob.get("/api/album?id=al1").json()["starred"])
        self.assertEqual(self.bob.post_json("/api/favorite", {"kind": "album", "id": "al1", "on": False}).status, 200)
        self.assertNotIn("dir-al1", self.subsonic.starred_folders)
        self.assertEqual(self.bob.get("/api/starred").json()["albums"], [])

    def test_tag_artist_heart_is_visible_on_its_folder_page(self):
        self.subsonic.api_getArtist = lambda h, p: h.reply_json({"artist": {
            "id": "ar1", "name": "ABBA", "starred": "date", "album": [{"id": "al1"}]}})
        self.assertTrue(self.bob.get("/api/artist?id=fdir-ar1").json()["starred"])
