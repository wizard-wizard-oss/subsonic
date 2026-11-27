"""Parcours HTTP réel : API Subsonic locale, fichiers de test, aperçu puis écriture et scan."""
import json
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from mutagen.flac import FLAC

from pimedia.webapp.tags.audio import AudioTagError
from pimedia.webapp.tags.entities import TAG_FIELDS
from pimedia.webapp.tags.entities import AlbumTagPatch, TagError
from pimedia.webapp.tags.sources import SourceMatches, SourceRelease, SourceTrack
from tests.fake_subsonic import ID3_ARTISTS
from tests.test_audio_tags import make_flac
from tests.webapp_support import WebAppTestCase


class AlbumTagsHttpTest(WebAppTestCase):
    def setUp(self):
        super().setUp()
        self.music = Path(self.tmp) / "Music"
        self.records, self.paths = {}, {}
        for index, identity in enumerate(("s1", "s2"), 1):
            relative = f"ABBA/Arrival/CD{index}/{identity}.flac"
            path = self.music / relative
            make_flac(path)
            audio = FLAC(path)
            audio["artist"] = ["ABBA feat. Invitée" if index == 2 else "ABBA"]
            audio["genre"] = ["Pop"]
            audio["album"] = ["Album dans les tags"]
            audio.save()
            song = self.subsonic._song(identity, ID3_ARTISTS["ar1"]["album"][0])
            self.records[identity] = dict(song, path=relative, genre="Pop", year=1976, album="Album dans les tags")
            self.paths[identity] = path
        self.app.audio_tags.music_dir = str(self.music.resolve())
        self.expose_albumartist = True
        self.scan_count = 0
        self.subsonic.api_getSong = self.read_song
        self.subsonic.api_startScan = self.scan
        self.subsonic.api_getScanStatus = lambda h, p: h.reply_json({"scanStatus": {"scanning": False}})
        self.alice = self.client("alice", "secret")

    def read_song(self, handler, params):
        record = self.records.get(params.get("id"))
        if record is None:
            return self.subsonic._failed(handler)
        handler.reply_json({"song": record})

    def scan(self, handler, params):
        self.scan_count += 1
        fields = {"title": "title", "artist": "artist", "album": "album", "year": "year", "genre": "genre",
                  "track": "track", "disc": "discNumber"}
        for identity, raw in self.records.items():
            values = self.app.audio_tags.inspect(raw["path"]).tags
            for name, target in fields.items():
                raw[target] = values[name]
            if self.expose_albumartist:
                raw["albumArtist"] = values["albumArtist"]
        handler.reply_json({"scanStatus": {"scanning": False}})

    def snapshot(self):
        response = self.alice.get("/api/tags/album?id=fdir-al1")
        self.assertEqual(response.status, 200, response.body)
        return response.json()

    def body(self, changes=None):
        snapshot = self.snapshot()
        return dict(albumId=snapshot["albumId"], revision=snapshot["revision"],
                    tracks=[dict(id="s1", changes=changes or {"genre": "Experimental"})])

    def operation(self, response, client=None):
        self.assertEqual(response.status, 200, response.body)
        identity = response.json()["operationId"]
        for _ in range(200):
            result = (client or self.alice).get("/api/tags/operation?id=" + identity).json()
            if result["state"] == "failed" or result["state"] == "saved" and result["scan"] in ("updated", "failed"):
                return result
            time.sleep(0.01)
        self.fail("L'opération locale ne termine pas")

    def test_status_is_an_entity(self):
        status = self.app.album_tags.status(self.app.users.by_name("alice"))
        self.assertEqual(type(status).__name__, "TagEditorStatus")
        self.assertEqual(set(status.to_api()), {"writable", "reason", "providers", "formats", "limits", "fields"})
        self.assertEqual(status.to_api()["fields"], list(TAG_FIELDS))

    def test_reads_api_keeps_folder_headers_and_completes_missing_album_artist(self):
        snapshot = self.snapshot()
        self.assertEqual((snapshot["name"], snapshot["artist"]), ("Arrival", "ABBA"))
        self.assertEqual(snapshot["tracks"][0]["tags"]["album"], "Album dans les tags")
        self.assertEqual(snapshot["tracks"][0]["tags"]["year"], "2021")
        self.assertIn("tags.index_outdated", snapshot["warnings"])
        self.assertEqual(snapshot["tracks"][0]["tags"]["albumArtist"], "Artiste album")
        self.assertTrue(all(track["editable"] for track in snapshot["tracks"]))
        self.assertNotIn(str(self.music), json.dumps(snapshot))
        self.assertEqual(self.scan_count, 0)

    def test_preview_does_not_write_and_save_preserves_unselected_tracks_and_audio(self):
        before = {identity: path.read_bytes() for identity, path in self.paths.items()}
        tables = self.app.db.query("SELECT name FROM sqlite_master WHERE type='table'")
        body = self.body()
        preview = self.alice.post_json("/api/tags/preview", body)
        self.assertEqual(preview.status, 200, preview.body)
        self.assertEqual(preview.json()["changes"], [dict(id="s1", title="Titre initial", field="genre", before="Pop", after="Experimental")])
        self.assertEqual(self.paths["s1"].read_bytes(), before["s1"])
        result = self.operation(self.alice.post_json("/api/tags/save", body))
        self.assertEqual((result["state"], result["scan"], result["completed"]), ("saved", "updated", 1))
        self.assertEqual(FLAC(self.paths["s1"])["genre"], ["Experimental"])
        self.assertEqual(self.paths["s2"].read_bytes(), before["s2"])
        self.assertEqual(self.scan_count, 1)
        self.assertEqual(self.app.db.query("SELECT name FROM sqlite_master WHERE type='table'"), tables)
        self.assertTrue(self.paths["s1"].exists())

    def test_editing_styles_keeps_the_original_sender(self):
        self.client("bob", "pw2")
        sender = self.app.users.by_name("bob")
        self.app.uploads.library.music_dir = str(self.music)
        self.app.uploads.history.add(sender, "Arrival.zip", 100,
            dict(files=2, skipped=0, placed=["ABBA/Arrival"], waiting=[]), 123, self.app.uploads.library_key)
        before = self.alice.get("/api/album?id=fdir-al1").json()["uploadedBy"]
        self.assertEqual(before, dict(username="bob", uploadedAt=123))
        result = self.operation(self.alice.post_json("/api/tags/save", self.body()))
        self.assertEqual((result["state"], result["scan"]), ("saved", "updated"))
        after = self.alice.get("/api/album?id=fdir-al1").json()["uploadedBy"]
        self.assertEqual(after, before)
        self.assertEqual(self.app.uploads.history.page(None, 50)[0].username, "bob")

    def test_style_scan_discards_an_old_attribution_for_a_reused_album_id(self):
        self.client("bob", "pw2")
        self.app.uploads.library.music_dir = str(self.music)
        for username, path in (("bob", "ABBA/Arrival"), ("alice", "Other/Album")):
            self.app.uploads.history.add(self.app.users.by_name(username), "album.zip", 100,
                dict(files=2, skipped=0, placed=[path], waiting=[]), 123, self.app.uploads.library_key)
        call = self.app.subsonic.call

        def previous_album(user, endpoint, params=(), **kwargs):
            if endpoint == "getAlbum":
                return {"album": {"song": [{"path": "Other/Album/01.mp3"}]}}
            return call(user, endpoint, params, **kwargs)

        user = self.app.users.by_name("alice")
        previous = {"id": "al1"}
        with patch.object(self.app.subsonic, "call", side_effect=previous_album):
            self.app.upload_attribution.annotate(user, [previous])
        self.assertEqual(previous["uploadedBy"]["username"], "alice")
        result = self.operation(self.alice.post_json("/api/tags/save", self.body()))
        self.assertEqual(result["scan"], "updated")
        album = self.alice.get("/api/album?id=fdir-al1").json()
        self.assertEqual(album["uploadedBy"]["username"], "bob")

    def test_preview_describes_the_actual_value_when_subsonic_index_is_outdated(self):
        response = self.alice.post_json("/api/tags/preview", self.body({"title": "Dancing Queen"}))
        self.assertEqual(response.status, 200, response.body)
        self.assertEqual(response.json()["changes"][0]["before"], "Titre initial")
        self.assertEqual(response.json()["changes"][0]["after"], "Dancing Queen")
        self.assertEqual(FLAC(self.paths["s1"])["title"], ["Titre initial"])

    def test_release_route_adds_mapping_without_assuming_same_order_or_writing(self):
        release = SourceRelease("discogs", "42", "Arrival", "ABBA", "1976", "1976", "SE", "CD", "Pop",
                                ("Pop",), (), (SourceTrack("1", 1, 1, "Other title", "ABBA", 230),
                                               SourceTrack("2", 2, 1, "Another title", "ABBA", 240)))
        asked = []
        self.app.tag_sources.release = lambda *args: asked.append(args) or release
        before = self.paths["s1"].read_bytes()
        response = self.alice.get("/api/tags/release?id=fdir-al1&source=discogs&release=42")
        self.assertEqual(response.status, 200, response.body)
        self.assertEqual(response.json()["mapping"], [None, None])
        self.assertEqual(response.json()["source"], "discogs")
        self.assertEqual(asked, [("discogs", "42")])
        self.assertEqual(self.paths["s1"].read_bytes(), before)

    def test_artist_album_does_not_overwrite_track_artist_and_missing_api_confirmation_is_explicit(self):
        self.expose_albumartist = False
        before = FLAC(self.paths["s1"])["artist"]
        result = self.operation(self.alice.post_json("/api/tags/save", self.body({"albumArtist": "ABBA"})))
        self.assertEqual(FLAC(self.paths["s1"])["albumartist"], ["ABBA"])
        self.assertEqual(FLAC(self.paths["s1"])["artist"], before)
        self.assertEqual(result["state"], "saved")
        self.assertEqual(result["scan"], "updated")
        self.assertIn("tags.verification_partial", result["warnings"])

    def test_a_file_modified_since_opening_is_a_conflict(self):
        body = self.body()
        audio = FLAC(self.paths["s1"])
        audio["title"] = ["Autre correction externe"]
        audio.save()
        before = self.paths["s1"].read_bytes()
        for route in ("preview", "save"):
            response = self.alice.post_json("/api/tags/" + route, body)
            self.assertEqual((response.status, response.json()["error"]), (409, "tags.conflict"))
        self.assertEqual(self.paths["s1"].read_bytes(), before)
        self.assertEqual(self.scan_count, 0)

    def test_cover_art_right_and_csrf_are_required_even_for_an_admin(self):
        body = self.body()
        self.assertEqual(self.client().get("/api/tags/status").status, 401)
        self.subsonic.roles["bob"] = {"coverArtRole": False, "adminRole": True}
        bob = self.client("bob", "pw2")
        for route in ("status", "album?id=fdir-al1", "search?id=fdir-al1&source=musicbrainz&artist=A&album=B"):
            self.assertEqual(bob.get("/api/tags/" + route).status, 403)
        self.assertEqual(bob.post_json("/api/tags/save", body).status, 403)
        self.assertEqual(self.alice.request("POST", "/api/tags/save", body=json.dumps(body).encode(), csrf=False).status, 403)

    def test_non_admin_with_edit_right_can_save_and_scan_uses_a_known_admin(self):
        self.subsonic.api_getScanStatus = lambda h, p: h.reply_json({"scanStatus": {"scanning": False}}) \
            if p.get("u") == "alice" else self.subsonic._failed(h, 50)
        original = self.subsonic.api_startScan
        scan_users = []
        def admin_scan(handler, params):
            scan_users.append(params.get("u"))
            if params.get("u") != "alice":
                return self.subsonic._failed(handler, 50)
            return original(handler, params)
        self.subsonic.api_startScan = admin_scan
        bob = self.client("bob", "pw2")
        self.assertEqual(bob.get("/api/tags/album?id=fdir-al1").status, 200)
        result = self.operation(bob.post_json("/api/tags/save", self.body()), client=bob)
        self.assertEqual((result["state"], result["scan"]), ("saved", "updated"))
        self.assertEqual(scan_users, ["bob", "alice"])
        self.assertEqual(FLAC(self.paths["s1"])["genre"], ["Experimental"])

    def test_rejects_tracks_outside_album_and_browser_paths(self):
        body = self.body()
        body["tracks"][0]["id"] = "s4"
        self.assertEqual(self.alice.post_json("/api/tags/save", body).json()["error"], "tags.bad_track")
        body = self.body()
        body["tracks"][0]["path"] = "ABBA/Arrival/CD1/s1.flac"
        self.assertEqual(self.alice.post_json("/api/tags/save", body).json()["error"], "tags.bad_request")
        self.records["s1"]["path"] = "../outside.flac"
        self.assertEqual(self.alice.get("/api/tags/album?id=fdir-al1").json()["error"], "tags.bad_track")

    def test_a_path_inside_music_but_outside_selected_album_is_not_editable(self):
        self.records["s1"]["path"] = "Other/Album/file.flac"
        with patch.object(self.app.audio_tags, "inspect", wraps=self.app.audio_tags.inspect) as inspect:
            response = self.alice.get("/api/tags/album?id=fdir-al1")
        self.assertEqual(response.json()["error"], "tags.bad_track")
        self.assertNotIn("Other/Album/file.flac", [call.args[0] for call in inspect.call_args_list])

    def test_file_errors_keep_public_keys_and_unknown_formats_are_readonly(self):
        self.paths["s1"].unlink()
        response = self.alice.get("/api/tags/album?id=fdir-al1")
        self.assertEqual(response.json()["error"], "tags.file_unavailable")
        self.paths["s1"].write_bytes(b"unsupported audio")
        snapshot = self.snapshot()
        self.assertFalse(snapshot["tracks"][0]["editable"])
        body = self.body()
        response = self.alice.post_json("/api/tags/save", body)
        self.assertEqual(response.status, 400)
        self.assertEqual(self.scan_count, 0)

    def test_scan_failure_keeps_successfully_written_tags(self):
        self.subsonic.api_startScan = lambda h, p: self.subsonic._failed(h, 10)
        result = self.operation(self.alice.post_json("/api/tags/save", self.body()))
        self.assertEqual((result["state"], result["scan"]), ("saved", "failed"))
        self.assertIn("tags.scan_failed", result["warnings"])
        self.assertEqual(FLAC(self.paths["s1"])["genre"], ["Experimental"])

    def test_write_failure_does_not_claim_success(self):
        with patch.object(self.app.audio_tags, "apply", side_effect=AudioTagError("tags.write_failed")):
            result = self.operation(self.alice.post_json("/api/tags/save", self.body()))
        self.assertEqual((result["state"], result["error"]), ("failed", "tags.write_failed"))
        self.assertEqual(FLAC(self.paths["s1"])["genre"], ["Pop"])
        self.assertEqual(self.scan_count, 0)

    def test_same_album_cannot_be_saved_twice_and_operations_are_private(self):
        entered, release = threading.Event(), threading.Event()
        original = self.app.audio_tags.apply
        def delayed(edits, progress=None):
            entered.set()
            release.wait(5)
            return original(edits, progress)
        body = self.body()
        with patch.object(self.app.audio_tags, "apply", side_effect=delayed):
            response = self.alice.post_json("/api/tags/save", body)
            self.assertTrue(entered.wait(1))
            second = self.alice.post_json("/api/tags/save", body)
            self.assertEqual((second.status, second.json()["error"]), (409, "tags.busy"))
            self.subsonic.roles["bob"] = {"adminRole": True}
            bob = self.client("bob", "pw2")
            self.assertEqual(bob.get("/api/tags/operation?id=" + response.json()["operationId"]).status, 404)
            release.set()
            self.operation(response)

    def test_operation_exposes_live_preparation_and_publication_progress(self):
        preparing, publishing = threading.Event(), threading.Event()
        release_preparing, release_publishing = threading.Event(), threading.Event()
        original = self.app.audio_tags.apply
        def delayed(edits, progress=None):
            def report(phase, completed, total):
                progress(phase, completed, total)
                if completed == 1:
                    if phase == "preparing":
                        preparing.set()
                        release_preparing.wait(10)
                    elif phase == "publishing":
                        publishing.set()
                        release_publishing.wait(10)
            return original(edits, report)
        body = self.body()
        body["tracks"].append(dict(id="s2", changes={"genre": "Experimental"}))
        before = {identity: path.read_bytes() for identity, path in self.paths.items()}
        with patch.object(self.app.audio_tags, "apply", side_effect=delayed):
            response = self.alice.post_json("/api/tags/save", body)
            self.assertEqual(response.status, 200, response.body)
            self.assertEqual((response.json()["phase"], response.json()["completed"], response.json()["total"]),
                             ("preparing", 0, 2))
            endpoint = "/api/tags/operation?id=" + response.json()["operationId"]
            try:
                self.assertTrue(preparing.wait(2))
                operation = self.alice.get(endpoint).json()
                self.assertEqual((operation["state"], operation["phase"], operation["completed"], operation["total"]),
                                 ("saving", "preparing", 1, 2))
                self.assertEqual({identity: path.read_bytes() for identity, path in self.paths.items()}, before)
                self.assertEqual(self.scan_count, 0)
                release_preparing.set()
                self.assertTrue(publishing.wait(2))
                operation = self.alice.get(endpoint).json()
                self.assertEqual((operation["state"], operation["phase"], operation["completed"], operation["total"]),
                                 ("saving", "publishing", 1, 2))
                self.assertEqual(FLAC(self.paths["s1"])["genre"], ["Experimental"])
                self.assertEqual(self.paths["s2"].read_bytes(), before["s2"])
                self.assertEqual(self.scan_count, 0)
            finally:
                release_preparing.set()
                release_publishing.set()
            result = self.operation(response)
        self.assertEqual((result["state"], result["scan"], result["completed"], result["total"]),
                         ("saved", "updated", 2, 2))

    def test_source_selection_is_explicit_and_errors_are_translated(self):
        called = []
        self.app.tag_sources.search = lambda *args: called.append(args) or SourceMatches(args[0], ())
        response = self.alice.get("/api/tags/search?id=fdir-al1&source=discogs&artist=ABBA&album=Arrival")
        self.assertEqual(response.json(), {"source": "discogs", "candidates": []})
        self.assertEqual(called, [("discogs", "ABBA", "Arrival")])
        def unavailable(*args):
            raise ValueError("tags.source_unavailable")
        self.app.tag_sources.search = unavailable
        response = self.alice.get("/api/tags/search?id=fdir-al1&source=musicbrainz&artist=A&album=B")
        self.assertEqual((response.status, response.json()["error"]), (503, "tags.source_unavailable"))


class TagPatchTest(unittest.TestCase):
    def test_rejects_unknown_fields_and_invalid_values(self):
        base = dict(albumId="f123", revision="a" * 64)
        for changes in ({"path": "../elsewhere"}, {"year": "2026-01-01"}, {"track": "-1"}, {"disc": "0"},
                        {"title": "bad\nline"}, {"artist": 123}, {"genre": "x" * 501}):
            with self.subTest(changes=changes), self.assertRaises(TagError):
                AlbumTagPatch.parse(dict(base, tracks=[dict(id="s1", changes=changes)]))

    def test_clear_is_explicit_and_missing_fields_are_unchanged(self):
        patch = AlbumTagPatch.parse(dict(albumId="f123", revision="a" * 64,
                                        tracks=[dict(id="s1", changes={"genre": "", "track": "02"})]))
        self.assertEqual([(change.field, change.value) for change in patch.tracks[0].changes], [("genre", ""), ("track", "2")])
