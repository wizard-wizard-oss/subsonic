"""Tests d'intégration, mode Raspberry Pi (un seul compte, pas de connexion)."""
import gzip

from tests.fake_subsonic import AUDIO, PNG
from tests.support import AppTestCase


class PiModeTest(AppTestCase):
    def rest(self, endpoint, query=""):
        return self.client.get("/rest/%s.view?%s" % (endpoint, query), csrf=False)

    def subsonic_json(self, endpoint, query=""):
        return self.rest(endpoint, query).json()["subsonic-response"]

    # --- identité ---
    def test_no_account_routes(self):
        for method, path in (("GET", "/me"), ("POST", "/login"), ("POST", "/upload")):
            self.assertEqual(self.client.request(method, path).status, 404, path)

    # --- relais et cache ---
    def test_proxy_adds_credentials_and_caches(self):
        first = self.rest("getGenres")
        second = self.rest("getGenres")
        self.assertEqual(first.json()["subsonic-response"]["status"], "ok")
        self.assertEqual(first.headers["x-cache"], "MISS")
        self.assertEqual(second.headers["x-cache"], "HIT")
        self.assertEqual(self.subsonic.calls["getGenres"], 1)

    def test_browser_cannot_override_credentials(self):
        response = self.rest("getGenres", "u=bob&t=x&s=y&p=z")
        self.assertEqual(response.json()["subsonic-response"]["status"], "ok")

    def test_write_invalidates_starred_cache(self):
        self.rest("getStarred2")
        self.rest("star", "id=s1")
        again = self.rest("getStarred2")
        self.assertEqual(again.headers["x-cache"], "MISS")

    def test_cover_is_cached_on_disk(self):
        first = self.rest("getCoverArt", "id=al1&size=300")
        second = self.rest("getCoverArt", "id=al1&size=300")
        self.assertEqual(first.body, PNG)
        self.assertEqual(second.headers["x-cache"], "HIT")
        self.assertEqual(self.subsonic.calls["getCoverArt"], 1)

    def test_stream_supports_range(self):
        whole = self.rest("stream", "id=s1")
        self.assertEqual(whole.body, AUDIO)
        part = self.client.get("/rest/stream.view?id=s1", csrf=False, headers={"Range": "bytes=10-19"})
        self.assertEqual(part.status, 206)
        self.assertEqual(part.body, AUDIO[10:20])
        self.assertEqual(part.headers["content-range"], "bytes 10-19/%d" % len(AUDIO))

    def test_wrong_upstream_credentials_are_reported(self):
        self.subsonic.users["alice"] = "changed"
        self.assertEqual(self.subsonic_json("getGenres")["status"], "failed")

    def test_unreachable_server_gives_readable_failure(self):
        self.subsonic.stop()
        body = self.subsonic_json("getUnknownThing")
        self.assertEqual(body["status"], "failed")

    # --- mode dossiers ---
    def test_folder_mode_merges_duplicate_artists(self):
        artists = self.subsonic_json("getArtists")["artists"]["index"]
        names = [a["name"] for group in artists for a in group["artist"]]
        self.assertEqual(names, ["ABBA", "Björk"])
        self.assertEqual(artists[0]["artist"][0]["id"], "ar1|ar2")

    def test_folder_artist_lists_albums_once(self):
        artist = self.subsonic_json("getArtist", "id=ar1|ar2")["artist"]
        self.assertEqual(sorted(a["name"] for a in artist["album"]), ["Arrival", "Waterloo"])

    def test_folder_album_tracks_are_sorted(self):
        album = self.subsonic_json("getAlbum", "id=al1")["album"]
        self.assertEqual([s["title"] for s in album["song"]], ["Knowing Me", "Dancing Queen"])
        self.assertEqual(album["songCount"], 2)
        self.assertEqual(album["duration"], 470)

    def test_folder_search_and_info(self):
        found = self.subsonic_json("search3", "query=abba")["searchResult3"]
        self.assertEqual(len(found["artist"]), 1)
        info = self.subsonic_json("getArtistInfo2", "id=ar1|ar2")["artistInfo2"]
        self.assertIn("ABBA", info["biography"])

    # --- réglages ---
    def test_settings_switch_to_tags_and_are_saved(self):
        self.assertEqual(self.client.get("/settings").json()["browse_mode"], "folders")
        changed = self.client.get("/settings?browse_mode=tags").json()
        self.assertEqual(changed, {"browse_mode": "tags"})
        self.assertEqual(self.app.db.one("SELECT value FROM app_settings WHERE key = 'browse_mode'")[0], '"tags"')

    def test_settings_ignore_invalid_values(self):
        changed = self.client.get("/settings?browse_mode=nope").json()
        self.assertEqual(changed, {"browse_mode": "folders"})

    # --- cache ---
    def test_refresh_clears_library_but_keeps_covers(self):
        self.rest("getGenres")
        self.rest("getCoverArt", "id=al1")
        self.client.get("/cache/clear")
        self.assertEqual(self.rest("getGenres").headers["x-cache"], "MISS")
        self.assertEqual(self.rest("getCoverArt", "id=al1").headers["x-cache"], "HIT")

    def test_clear_all_removes_covers_too(self):
        self.rest("getCoverArt", "id=al1")
        self.client.get("/cache/clear?all=1")
        self.assertEqual(self.rest("getCoverArt", "id=al1").headers["x-cache"], "MISS")

    def test_new_albums_are_detected(self):
        self.app.watcher.check_new()
        self.rest("getGenres")
        self.subsonic.newest = ["al3", "al1", "al2"]
        self.assertTrue(self.app.watcher.check_new())
        self.assertEqual(self.rest("getGenres").headers["x-cache"], "MISS")

    # --- commandes du Pi ---
    def test_pi_commands_roundtrip(self):
        self.client.get("/control/send?cmd=pause")
        self.assertEqual(self.client.get("/control/poll").json(), {"cmd": "pause"})
        self.assertEqual(self.client.get("/control/poll").json(), {"cmd": None})

    def test_awake_flag(self):
        self.assertFalse(self.client.get("/control/awake").json()["awake"])
        self.assertTrue(self.client.get("/control/awake?on=1").json()["awake"])

    def test_mode_endpoint(self):
        self.assertEqual(self.client.get("/control/mode?m=tags").json(), {"mode": "tags"})

    # --- interface web ---
    def test_index_has_versioned_assets_and_etag(self):
        page = self.client.get("/")
        self.assertEqual(page.status, 200)
        self.assertNotIn(b"{{V}}", page.body)
        self.assertIn(b"/static/", page.body)
        again = self.client.get("/", headers={"If-None-Match": page.headers["etag"]})
        self.assertEqual(again.status, 304)

    def test_static_files_cache_and_compression(self):
        first = self.client.get("/static/js/core.js?v=1", headers={"Accept-Encoding": "gzip"})
        self.assertEqual(first.status, 200)
        self.assertEqual(first.headers["content-encoding"], "gzip")
        self.assertIn("immutable", first.headers["cache-control"])
        self.assertIn(b"function", gzip.decompress(first.body))
        again = self.client.get("/static/js/core.js?v=1",
                                headers={"Accept-Encoding": "gzip", "If-None-Match": first.headers["etag"]})
        self.assertEqual(again.status, 304)

    def test_static_rejects_path_traversal(self):
        for path in ("/static/../config.json", "/static/%2e%2e/config.json", "/static/..%2fconfig.json",
                     "/static/js/nope.js"):
            self.assertEqual(self.client.get(path).status, 404, path)

    def test_unknown_path_is_404(self):
        self.assertEqual(self.client.get("/nothing").status, 404)
