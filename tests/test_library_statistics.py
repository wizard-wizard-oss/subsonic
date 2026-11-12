"""Compteurs natifs Subsonic : jamais de collecte REST ni d'expiration du cache au fil des visites."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pimedia.webapp.library_statistics import MAX_PROPERTIES_BYTES, SubsonicStatistics, parse_statistics
from tests.webapp_support import WebAppTestCase

SCAN = 1794150239000
COUNTS = "5440 11843 137315 1587931675620 33224428"


def properties(counts=COUNTS, scanned=SCAN):
    return "Password=secret-never-returned\nLastScanned=%s\nMediaLibraryStatistics=%s\n" % (scanned, counts)


class SubsonicStatisticsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "subsonic.properties"
        self.source = SubsonicStatistics(str(self.path))

    def write(self, counts=COUNTS, scanned=SCAN):
        self.path.write_text(properties(counts, scanned), encoding="iso-8859-1")

    def test_reads_the_native_five_counters_in_their_order_and_units(self):
        result = parse_statistics(properties()).to_api()
        self.assertEqual(result, {"artists": 5440, "albums": 11843, "songs": 137315,
                                  "bytes": 1587931675620, "seconds": 33224428, "lastScan": SCAN})
        self.assertEqual(parse_statistics(properties("0 0 0 0 0")).songs, 0)

    def test_missing_partial_negative_and_malformed_snapshots_are_unavailable(self):
        for content in ("", "MediaLibraryStatistics=" + COUNTS,
                        properties("1 2 3"), properties("1 2 3 4 5 6"), properties("-1 2 3 4 5"),
                        properties("1 2 none 4 5"), properties(scanned=0), properties(scanned="bad"),
                        properties(scanned=9_000_000_000_000_000)):
            with self.subTest(content=content):
                self.assertIsNone(parse_statistics(content))

    def test_no_path_or_missing_file_does_not_prevent_the_page_loading(self):
        self.assertIsNone(SubsonicStatistics("").get())
        self.assertIsNone(self.source.get())

    def test_unchanged_file_is_not_reread_and_survives_a_site_restart(self):
        self.write()
        first = self.source.get()
        with patch("builtins.open", side_effect=AssertionError("inutile de relire")):
            for _ in range(20):
                self.assertIs(self.source.get(), first)
        self.assertEqual(SubsonicStatistics(str(self.path)).get(), first)

    def test_other_settings_changes_do_not_replace_the_scan_but_a_new_scan_does(self):
        self.write()
        first = self.source.get()
        self.write("1 2 3 4 5")
        self.assertIs(self.source.get(), first)
        self.write("1 2 3 4 5", SCAN + 1000)
        self.assertEqual(self.source.get().to_api(), {"artists": 1, "albums": 2, "songs": 3,
                                                     "bytes": 4, "seconds": 5, "lastScan": SCAN + 1000})

    def test_partial_save_and_temporary_unavailability_keep_the_last_valid_snapshot(self):
        self.write()
        first = self.source.get()
        self.path.write_text("LastScanned=", encoding="ascii")
        self.assertIs(self.source.get(), first)
        self.path.unlink()
        self.assertIs(self.source.get(), first)
        self.path.write_text(properties("1 2 3 4 5", SCAN + 1000).rstrip("\n"))
        self.assertIs(self.source.get(), first)  # cinq nombres ne suffisent pas si le dernier est encore tronqué
        self.write("1 2 3 4 5", SCAN + 1000)
        self.assertEqual(self.source.get().songs, 3)

    def test_replaced_file_is_read_and_oversized_file_is_ignored(self):
        self.write()
        first = self.source.get()
        replacement = self.path.with_suffix(".new")
        replacement.write_text(properties("1 2 3 4 5", SCAN + 1000), encoding="ascii")
        replacement.replace(self.path)
        self.assertEqual(self.source.get().songs, 3)
        self.path.write_text(properties(scanned=SCAN + 2000) + "x" * MAX_PROPERTIES_BYTES)
        self.assertEqual(self.source.get().songs, 3)
        self.assertEqual(first.songs, 137315)


class LibraryStatisticsHttpTest(WebAppTestCase):
    def setUp(self):
        self.statistics_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.statistics_tmp.cleanup)
        self.path = Path(self.statistics_tmp.name) / "subsonic.properties"
        self.path.write_text(properties(), encoding="ascii")
        self.environ = {"PI_MEDIA_WEB_SUBSONIC_STATISTICS_FILE": str(self.path)}
        super().setUp()

    def test_home_reuses_the_server_totals_without_a_catalogue_crawl_or_secrets(self):
        self.assertEqual(self.client().get("/api/home").status, 401)
        client = self.client("bob", "pw2")
        self.subsonic.music_folders["bob"] = [1]    # les chiffres sont explicitement ceux de la collection du serveur
        response = client.get("/api/home")
        self.assertEqual(response.status, 200)
        self.assertEqual(response.json()["statistics"]["songs"], 137315)
        self.assertNotIn(b"secret-never-returned", response.body)
        self.assertNotIn(os.fsencode(self.path), response.body)
        for endpoint in ("getArtists", "getArtist", "getAlbum", "getIndexes", "getMusicDirectory", "getScanStatus"):
            self.assertEqual(self.subsonic.calls[endpoint], 0, endpoint)
        self.assertEqual(self.path.read_text(), properties())

    def test_a_completed_scan_changes_the_next_home_without_waiting_for_a_ttl(self):
        client = self.client("bob", "pw2")
        self.assertEqual(client.get("/api/home").json()["statistics"]["songs"], 137315)
        self.path.write_text(properties("2 3 4 5 6", SCAN + 1000))
        self.assertEqual(client.get("/api/home").json()["statistics"]["songs"], 4)

    def test_missing_source_has_no_fake_zero_counters(self):
        self.path.unlink()
        response = self.client("bob", "pw2").get("/api/home")
        self.assertEqual(response.status, 200)
        self.assertIsNone(response.json()["statistics"])
        self.assertTrue(response.json()["newest"])
