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

    def test_portrait_parallelism_is_supplied_to_the_page(self):
        data = self.favorites.page(self.user).to_api()
        self.assertGreater(data["portraitParallelism"], 1)

    def test_duplicate_album_keeps_the_richer_tag_metadata(self):
        self.raw["getStarred2"]["starred2"] = {"album": {"id": "tag", "name": "Album", "genre": "Jazz", "songCount": 12}}
        self.raw["getStarred"]["starred"] = {"album": {"id": "directory", "title": "Album"}}
        self.folders.album_id_for_folder.return_value = "tag"
        data = self.favorites.page(self.user).to_api()
        self.assertEqual(len(data["albums"]), 1)
        self.assertEqual((data["albums"][0]["genre"], data["albums"][0]["songCount"]), ("Jazz", 12))

    def test_new_tag_only_album_precedes_old_directory_favorites(self):
        self.raw["getStarred"]["starred"] = {"album": [
            {"id": "dir%d" % i, "title": "Ancien album %d" % i, "starred": "2026-01-01T00:00:00Z"}
            for i in range(225)]}
        self.raw["getStarred2"]["starred2"] = {"album": {
            "id": "14192", "name": "Towards Rebirth", "artist": "Ripper", "starred": "2026-11-28T13:27:56.960Z"}}
        self.folders.album_id_for_folder.side_effect = lambda user, identity: identity.replace("dir", "al")
        first = self.favorites.page(self.user).to_api()
        self.assertEqual((first["albums"][0]["id"], first["albums"][0]["name"]), ("14192", "Towards Rebirth"))
        self.assertEqual(first["pagination"]["albums"], {"total": 226, "hasMore": True})

    def test_duplicate_album_uses_newest_favorite_date_but_tag_metadata(self):
        self.raw["getStarred"]["starred"] = {"album": [
            {"id": "other-directory", "title": "Autre album", "starred": "2026-11-28T12:00:00Z"},
            {"id": "directory", "title": "Libellé dossier", "starred": "2026-11-29T00:00:00Z"}]}
        self.raw["getStarred2"]["starred2"] = {"album": {
            "id": "tag", "name": "Libellé tags", "genre": "Jazz", "songCount": 12,
            "starred": "2026-11-27T12:00:00Z"}}
        self.folders.album_id_for_folder.side_effect = lambda user, identity: {
            "directory": "tag", "other-directory": "other"}[identity]
        albums = self.favorites.page(self.user).albums
        self.assertEqual([album["id"] for album in albums], ["tag", "other"])
        self.assertEqual((albums[0]["name"], albums[0]["genre"], albums[0]["songCount"]), ("Libellé tags", "Jazz", 12))

    def test_missing_or_invalid_dates_keep_their_stable_order(self):
        self.raw["getStarred2"]["starred2"] = {"album": [
            {"id": "missing", "name": "Sans date"}, {"id": "invalid", "name": "Date invalide", "starred": "date"},
            {"id": "valid", "name": "Daté", "starred": "2026-11-28T13:27:56.960Z"},
            {"id": "boolean", "name": "Date booléenne", "starred": True}]}
        self.assertEqual([album["id"] for album in self.favorites.page(self.user).albums],
                         ["valid", "missing", "invalid", "boolean"])

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

    def test_each_category_exposes_its_own_total_and_continuation(self):
        self.raw["getStarred"]["starred"] = {
            "artist": [{"id": "ar%d" % i, "name": "Artiste %d" % i} for i in range(69)],
            "album": [{"id": "dir%d" % i, "title": "Reaper" if i == 224 else "Album %d" % i}
                      for i in range(225)],
            "song": [{"id": "s%d" % i, "title": "Titre %d" % i} for i in range(794)]}
        self.raw["getStarred2"]["starred2"] = {
            "artist": [{"id": "ar%d" % i, "name": "Artiste %d" % i} for i in range(2)],
            "album": [{"id": "al%d" % i, "name": "Album %d" % i} for i in range(11)],
            "song": self.raw["getStarred"]["starred"]["song"]}
        self.folders.album_id_for_folder.side_effect = lambda user, identity: identity.replace("dir", "al")
        self.folders.artist_folder_id.side_effect = lambda user, identity: "f" + identity
        first = self.favorites.page(self.user).to_api()
        self.assertEqual(first["pagination"], {
            "artists": {"total": 69, "hasMore": True}, "albums": {"total": 225, "hasMore": True},
            "songs": {"total": 794, "hasMore": True}})
        second = self.favorites.page(self.user, 1).to_api()
        self.assertEqual(second["pagination"]["artists"], {"total": 69, "hasMore": False})
        albums_last = self.favorites.page(self.user, 5).to_api()
        self.assertEqual(albums_last["pagination"]["albums"], {"total": 225, "hasMore": False})
        self.assertEqual(len(albums_last["albums"]), 25)
        self.assertEqual(albums_last["albums"][-1]["name"], "Reaper")
        self.assertTrue(albums_last["pagination"]["songs"]["hasMore"])
        self.assertTrue(albums_last["hasMore"])
        self.assertFalse(self.favorites.page(self.user, 19).to_api()["hasMore"])
