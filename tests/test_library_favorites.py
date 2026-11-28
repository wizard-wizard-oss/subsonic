"""Règles de réunion des favoris, indépendantes du transport HTTP."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from pimedia.webapp.library.favorites import Favorites
from pimedia.webapp.library.folders import FolderNotFound
from pimedia.webapp.subsonic import SubsonicUnreachable


class FavoritesServiceTest(unittest.TestCase):
    def setUp(self):
        self.user = SimpleNamespace(username="bob", subsonic_salt="salt", subsonic_token="token")
        self.raw = {"getStarred": {"starred": {}}, "getStarred2": {"starred2": {}}}
        self.subsonic = Mock()
        self.subsonic.call.side_effect = lambda credentials, endpoint, params=(): self.raw.get(endpoint, {})
        self.library = Mock()
        self.library._with_site_data.side_effect = lambda user, albums: albums
        self.folders = Mock()
        self.favorites = Favorites(self.subsonic, self.library, self.folders)

    def test_duplicate_album_keeps_the_richer_tag_metadata(self):
        self.raw["getStarred2"]["starred2"] = {"album": {"id": "tag", "name": "Album", "genre": "Jazz", "songCount": 12}}
        self.raw["getStarred"]["starred"] = {"album": {"id": "directory", "title": "Album"}}
        self.folders.album_id_for_folder.return_value = "tag"
        data = self.favorites.page(self.user).to_api()
        self.assertEqual(len(data["albums"]), 1)
        self.assertEqual((data["albums"][0]["genre"], data["albums"][0]["songCount"]), ("Jazz", 12))

    def test_duplicate_song_keeps_tag_metadata_and_directory_only_songs_remain(self):
        self.raw["getStarred2"]["starred2"] = {"song": {
            "id": "track", "title": "Titre", "genre": "Disco / Pop", "size": 12_345_678, "suffix": "flac"}}
        self.raw["getStarred"]["starred"] = {"song": [
            {"id": "track", "title": "Titre", "size": 3_000_000},
            {"id": "directory-only", "title": "Autre titre", "genre": "Jazz"}]}
        songs = {song["id"]: song for song in self.favorites.page(self.user).songs}
        self.assertEqual(set(songs), {"track", "directory-only"})
        self.assertEqual((songs["track"]["genre"], songs["track"]["size"], songs["track"]["suffix"]),
                         ("Disco / Pop", 12_345_678, "flac"))
        self.assertEqual(songs["directory-only"]["genre"], "Jazz")

    def test_artist_without_resolvable_folder_is_not_discarded(self):
        self.raw["getStarred2"]["starred2"] = {"artist": {"id": "tag", "name": "Artiste"}}
        self.folders.artist_folder_id.side_effect = FolderNotFound("tag")
        self.assertEqual(self.favorites.page(self.user).artists, [{"id": "tag", "name": "Artiste"}])

    def test_each_source_uses_the_connected_account_and_failures_are_not_hidden(self):
        self.favorites.page(self.user)
        self.assertEqual([c.args[1] for c in self.subsonic.call.call_args_list], ["getStarred2", "getStarred"])
        self.assertTrue(all(c.args[0].username == "bob" for c in self.subsonic.call.call_args_list))
        self.subsonic.call.side_effect = SubsonicUnreachable()
        with self.assertRaises(SubsonicUnreachable):
            self.favorites.page(self.user)

    def test_removing_an_artist_clears_both_identities_with_one_request(self):
        self.folders.artist_id_for_folder.return_value = "tag-artist"
        state = self.favorites.set_favorite(self.user, "folder", "ffolder-artist", False)
        self.assertEqual(state.to_api(), {"starred": False})
        self.assertEqual(self.subsonic.call.call_args.args[1:],
                         ("unstar", [("id", "folder-artist"), ("artistId", "tag-artist")]))

    def test_removing_an_album_clears_both_identities_with_one_request(self):
        self.folders.folder_id.return_value = "ffolder-album"
        state = self.favorites.set_favorite(self.user, "album", "tag-album", False)
        self.assertEqual(state.to_api(), {"starred": False})
        self.assertEqual(self.subsonic.call.call_args.args[1:],
                         ("unstar", [("albumId", "tag-album"), ("id", "folder-album")]))

    def test_tag_only_favorites_can_be_removed_without_a_resolvable_folder(self):
        self.folders.artist_folder_id.side_effect = FolderNotFound("tag-artist")
        self.folders.folder_id.side_effect = FolderNotFound("tag-album")
        for kind, identity, key in (("artist", "tag-artist", "artistId"), ("album", "tag-album", "albumId")):
            with self.subTest(kind=kind):
                state = self.favorites.set_favorite(self.user, kind, identity, False)
                self.assertEqual(state.to_api(), {"starred": False})
                self.assertEqual(self.subsonic.call.call_args.args[1:], ("unstar", [(key, identity)]))
