"""Galerie : pagination avant lecture des contenus, visuels communs et noms musicaux."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from pimedia.webapp.playlist_gallery.artwork import album_covers
from pimedia.webapp.playlist_gallery.service import PAGE_SIZE, PlaylistGallery


class PlaylistArtworkTest(unittest.TestCase):
    def test_four_distinct_albums_in_playlist_order(self):
        songs = [{"albumId": str(i), "coverId": "c" + str(i)} for i in [1, 1, 2, 3, 4, 5]]
        self.assertEqual(album_covers(songs), ["c1", "c2", "c3", "c4"])
        self.assertEqual(album_covers(songs), album_covers(songs))

    def test_single_album_empty_missing_and_external_images(self):
        self.assertEqual(album_covers([]), [])
        self.assertEqual(album_covers([{"albumId": "a"}]), [])
        self.assertEqual(album_covers([{"albumId": "a", "coverId": "c"}] * 8), ["c"])
        self.assertEqual(album_covers([{"ext": True, "imageUrl": "https://example.com/video.jpg"}]), [])

    def test_two_or_three_albums_fill_four_tiles_without_blank(self):
        self.assertEqual(album_covers([{"coverId": "a"}, {"coverId": "b"}]), ["a", "b", "a", "b"])
        self.assertEqual(album_covers([{"coverId": c} for c in "abc"]), ["a", "b", "c", "a"])


class PlaylistGalleryTest(unittest.TestCase):
    def setUp(self):
        self.user = SimpleNamespace(username="bob")
        self.playlists = Mock()
        self.cards = [{"id": str(i), "name": f"Liste {i:03}", "owner": "bob", "mine": True,
                       "songCount": 2, "duration": 30, "changed": "2026-11-28"} for i in range(PAGE_SIZE + 1)]
        self.playlists.all.return_value = self.cards
        self.playlists.get.side_effect = lambda user, id: dict(self.cards[int(id)],
            coverIds=["a", "b", "a", "b"], duration=50, songs=[{"duration": 20}, {"duration": 30}])
        self.gallery = PlaylistGallery(self.playlists)

    def test_only_visible_page_contents_are_loaded(self):
        first = self.gallery.page(self.user).to_api()
        self.assertEqual(len(first["playlists"]), PAGE_SIZE)
        self.assertTrue(first["hasMore"])
        self.assertEqual(self.playlists.get.call_count, PAGE_SIZE)
        second = self.gallery.page(self.user, page=1).to_api()
        self.assertEqual([p["id"] for p in second["playlists"]], [str(PAGE_SIZE)])
        self.assertFalse(second["hasMore"])
        self.assertNotIn("songs", first["playlists"][0])
        self.assertEqual(first["playlists"][0]["coverIds"], ["a", "b", "a", "b"])
        self.assertEqual(first["playlists"][0]["duration"], 50)
        self.playlists.all.assert_called_with(self.user)

    def test_normalized_search_preserves_display_and_recent_sort(self):
        self.cards[0].update(name="Été — Œuvres", changed="2026-11-29")
        found = self.gallery.page(self.user, query="ete oeuvres", sort="recent").to_api()
        self.assertEqual([p["name"] for p in found["playlists"]], ["Été — Œuvres"])
        self.assertEqual(self.gallery.page(self.user, sort="recent").to_api()["playlists"][0]["id"], "0")

    def test_invalid_parameters_are_rejected_before_subsonic(self):
        for args in ({"page": -1}, {"page": True}, {"sort": "unknown"}, {"query": []}):
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.gallery.page(self.user, **args)
        self.playlists.all.assert_not_called()
