"""Page des playlists et mosaïque commune au détail via les vraies couches HTTP."""
from tests.webapp_support import WebAppTestCase


class PlaylistGalleryHttpTest(WebAppTestCase):
    def test_gallery_and_detail_use_the_same_four_covers(self):
        alice = self.client("alice", "secret")
        playlist = alice.post_json("/api/playlist/create", {"name": "<Été>", "songIds": ["s1", "s2", "s4"]}).json()["playlist"]
        detail = alice.get("/api/playlist?id=" + playlist["id"]).json()
        self.assertEqual(len(detail["coverIds"]), 4)
        data = alice.get("/api/playlists/page?q=ete").json()
        self.assertEqual(data["playlists"][0]["coverIds"], detail["coverIds"])
        self.assertEqual(data["playlists"][0]["name"], "<Été>")
        self.assertFalse(data["hasMore"])
        self.assertEqual(self.client("bob", "pw2").get("/api/playlists/page").json()["playlists"], [])

    def test_auth_validation_empty_and_public_community(self):
        self.assertEqual(self.client().get("/api/playlists/page").status, 401)
        alice = self.client("alice", "secret")
        for query in ("page=-1", "page=no", "sort=no"):
            self.assertEqual(alice.get("/api/playlists/page?" + query).status, 400)
        alice.post_json("/api/playlist/create", {"name": "Commune", "community": True})
        card = self.client("bob", "pw2").get("/api/playlists/page").json()["playlists"][0]
        self.assertTrue(card["community"])
        self.assertFalse(card["mine"])
        self.assertEqual(card["coverIds"], [])
