"""Colonnes des morceaux : tags Subsonic et matrice d'affichage par compte et contexte."""
import unittest
from unittest.mock import patch

from pimedia.webapp.library.catalog import song_row
from pimedia.webapp.preferences import CHOICES, DEFAULTS, SONG_COLUMNS
from tests.fake_subsonic import _id3_song
from tests.webapp_support import WebAppTestCase


class SongStyleProjectionTest(unittest.TestCase):
    def test_style_keeps_the_track_tag_and_handles_missing_or_numeric_values(self):
        self.assertEqual(song_row({"id": "s1"})["genre"], "")
        for raw, expected in ((None, ""), ("", ""), (80, "80"), ("Indie / Rock", "Indie / Rock")):
            with self.subTest(genre=raw):
                self.assertEqual(song_row({"id": "s1", "genre": raw})["genre"], expected)

    def test_file_size_and_encoding_are_projected_from_the_original_file(self):
        row = song_row({"id": "s1", "size": 12_345_678, "suffix": "flac", "bitRate": 913})
        self.assertEqual((row["size"], row["suffix"], row["bitRate"]), (12_345_678, "flac", 913))
        self.assertIsNone(song_row({"id": "s1"})["size"])
        self.assertIsNone(song_row({"id": "s1", "size": None})["size"])
        self.assertEqual(song_row({"id": "s1", "size": 0})["size"], 0)

    def test_matrix_has_exactly_the_nine_subsonic_columns_in_display_order(self):
        self.assertEqual(SONG_COLUMNS, ("track", "artist", "album", "genre", "year", "bitrate", "duration",
                                       "format", "size"))
        matrix_keys = {context + "_" + column for context in ("browse", "queue") for column in SONG_COLUMNS}
        self.assertEqual({key for key in DEFAULTS if key.startswith(("browse_", "queue_"))}, matrix_keys)
        self.assertTrue(all(CHOICES[key] == (True, False) for key in matrix_keys))
        self.assertNotIn("song_genre", CHOICES)


class SongStylesHttpTest(WebAppTestCase):
    def test_track_styles_survive_every_song_list_without_album_fallback(self):
        bob = self.client("bob", "pw2")
        # Deux pistes du même album : le style manquant doit rester visible comme manquant.
        styles = {"s1": "Disco / Pop", "s2": ""}
        tags = {song_id: {"genre": style, "size": 12_000_000 + i}
                for i, (song_id, style) in enumerate(styles.items())}
        raw_songs = [dict(_id3_song(song_id), **values) for song_id, values in tags.items()]
        original_song = self.subsonic._song
        self.subsonic._song = lambda song_id, album: dict(original_song(song_id, album),
                                                        **tags.get(song_id, {}))
        self.subsonic.api_search3 = lambda h, p: h.reply_json({"searchResult3": {"song": raw_songs}})
        self.subsonic.api_getStarred2 = lambda h, p: h.reply_json({"starred2": {"song": raw_songs}})
        self.subsonic.api_getTopSongs = lambda h, p: h.reply_json({"topSongs": {"song": raw_songs}})
        created = bob.post_json("/api/playlist/create", {"name": "Styles", "songIds": list(styles)}).json()
        playlist_id = created["playlist"]["id"]
        with patch("tests.fake_subsonic._id3_song", side_effect=lambda song_id: dict(_id3_song(song_id),
                                                                                   **tags[song_id])):
            for url in ("/api/album?id=al1", "/api/album?id=fdir-al1", "/api/search?q=dancing",
                        "/api/starred", "/api/artist/top?name=ABBA", "/api/playlist?id=" + playlist_id):
                with self.subTest(source=url):
                    response = bob.get(url)
                    self.assertEqual(response.status, 200)
                    songs = response.json()["songs"]
                    self.assertEqual([(song["id"], song["genre"]) for song in songs], list(styles.items()))
                    self.assertEqual([song["size"] for song in songs], [12_000_000, 12_000_001])

    def test_matrix_defaults_and_schema_match_the_requested_subsonic_settings(self):
        bob = self.client("bob", "pw2")
        me = bob.get("/api/me").json()
        self.assertEqual(me["songColumns"], list(SONG_COLUMNS))
        for context, hidden in (("browse", {"format", "size"}), ("queue", {"track", "format", "size"})):
            for column in SONG_COLUMNS:
                with self.subTest(context=context, column=column):
                    self.assertIs(me["preferences"][context + "_" + column], column not in hidden)

    def test_every_column_persists_independently_by_context_and_user(self):
        bob, alice = self.client("bob", "pw2"), self.client("alice", "secret")
        expected = dict(DEFAULTS)
        for context in ("browse", "queue"):
            for column in SONG_COLUMNS:
                key = context + "_" + column
                expected[key] = not expected[key]
                with self.subTest(context=context, column=column):
                    saved = bob.post_json("/api/preferences", {"changes": {key: expected[key]}})
                    self.assertEqual(saved.status, 200)
                    self.assertEqual(saved.json()["preferences"], expected)
                    self.assertEqual(bob.get("/api/me").json()["preferences"], expected)
                    self.assertEqual(alice.get("/api/me").json()["preferences"], DEFAULTS)
        # Le réglage reste lié au compte lors d'une nouvelle session.
        another_session = self.client("bob", "pw2")
        self.assertEqual(another_session.get("/api/me").json()["preferences"], expected)

    def test_every_column_requires_a_strict_boolean(self):
        bob = self.client("bob", "pw2")
        for context in ("browse", "queue"):
            for column in SONG_COLUMNS:
                key = context + "_" + column
                for invalid in (0, 1, "true", "false", None, [], {}):
                    with self.subTest(key=key, value=invalid):
                        response = bob.post_json("/api/preferences", {"changes": {key: invalid}})
                        self.assertEqual(response.status, 400)
        self.assertEqual(bob.get("/api/me").json()["preferences"], DEFAULTS)

    def test_unknown_columns_and_invalid_batches_are_rejected_atomically(self):
        bob = self.client("bob", "pw2")
        for changes in ({"browse_unknown": True}, {"queue_title": False}, {"playlist_genre": False},
                        {"song_genre": False}, {"browse_genre": False, "queue_bitrate": 0},
                        {"browse_genre": False, "queue_unknown": True}):
            with self.subTest(changes=changes):
                self.assertEqual(bob.post_json("/api/preferences", {"changes": changes}).status, 400)
                self.assertEqual(bob.get("/api/me").json()["preferences"], DEFAULTS)

    def test_invalid_stored_choices_and_unreleased_setting_do_not_override_defaults(self):
        bob = self.client("bob", "pw2")
        user = self.app.users.by_name("bob")
        self.app.preferences.repository.save(user.id, {"browse_genre": 0, "queue_format": 1,
                                                       "browse_artist": "false", "song_genre": False})
        self.assertEqual(bob.get("/api/me").json()["preferences"], DEFAULTS)


if __name__ == "__main__":
    unittest.main()
