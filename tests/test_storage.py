"""Socle : base SQLite, réglages (.env et base), import des anciens fichiers, textes, emplacements."""
import json
import os
import stat
import tempfile
import unittest

from pimedia.envfile import EnvFile
from pimedia.i18n import Texts, flatten
from pimedia.paths import Paths, resolve_data_dir
from pimedia.settings import AppSettingsStore, Settings
from pimedia.storage.database import Database
from pimedia.storage.history import SearchHistory
from pimedia.storage.legacy import LegacyImport
from pimedia.storage.playlists import LocalPlaylists
from pimedia.storage.podcasts import PodcastLibrary
from pimedia.storage.schema import MIGRATIONS
from pimedia.storage.videos import UnplayableVideos
from tests.support import PROJECT, AppTestCase


class TempDirTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="pm-store-")

    def path(self, *parts):
        return os.path.join(self.dir, *parts)

    def write_json(self, name, data):
        os.makedirs(os.path.dirname(self.path(name)), exist_ok=True)
        with open(self.path(name), "w", encoding="utf-8") as f:
            json.dump(data, f)


class DatabaseTest(TempDirTest):
    def test_schema_is_versioned_and_applied_once(self):
        db = Database(self.path("pi-media.db"))
        self.assertEqual(db.version, len(MIGRATIONS))
        tables = {r[0] for r in db.query("SELECT name FROM sqlite_master WHERE type = 'table'")}
        for name in ("app_settings", "podcast_subscriptions", "episode_progress", "local_playlists", "playlist_tracks",
                     "external_favorites", "search_history", "unplayable_videos", "play_history",
                     "queue_items", "queue_state"):
            self.assertIn(name, tables)
        Database(self.path("pi-media.db"))                 # deuxième ouverture : aucune migration rejouée

    def test_transaction_is_all_or_nothing(self):
        db = Database(self.path("pi-media.db"))
        with self.assertRaises(RuntimeError):
            with db.transaction() as conn:
                conn.execute("INSERT INTO hidden_podcasts (feed_url) VALUES ('a')")
                raise RuntimeError("panne")
        self.assertEqual(db.query("SELECT * FROM hidden_podcasts"), [])


class EnvFileTest(TempDirTest):
    def test_parse_set_keep_comments_and_private_rights(self):
        with open(self.path(".env"), "w") as f:
            f.write("# Subsonic\nSUBSONIC_URL=http://old\nSUBSONIC_PASS='mot de passe'\n")
        env = EnvFile(self.path(".env"))
        self.assertEqual(env.values()["SUBSONIC_PASS"], "mot de passe")
        env.set(SUBSONIC_URL="https://new", PODCASTINDEX_KEY="k#1")
        with open(self.path(".env")) as f:
            text = f.read()
        self.assertTrue(text.startswith("# Subsonic\nSUBSONIC_URL=https://new\n"))
        self.assertEqual(env.values()["PODCASTINDEX_KEY"], "k#1")
        self.assertEqual(stat.S_IMODE(os.stat(self.path(".env")).st_mode), 0o600)


class SettingsTest(TempDirTest):
    def settings(self, environ=None):
        db = Database(self.path("pi-media.db"))
        return Settings(AppSettingsStore(db), EnvFile(self.path(".env")), environ or {})

    def test_lookup_order_and_types(self):
        EnvFile(self.path(".env")).set(SUBSONIC_URL="https://env/", PHONE_PORT="8200", PHONE_REMOTE="non",
                                       PODCAST_HOME="France Culture, Arte Radio", WEATHER_LATITUDE="48.85")
        settings = self.settings({"PI_MEDIA_SUBSONIC_URL": "https://process", "LANGUAGE": "en_US:en"})
        self.assertEqual(settings.subsonic_url, "https://process")          # variable PI_MEDIA_… avant le .env
        self.assertEqual((settings.get("phone_port"), settings.get("weather_latitude")), (8200, 48.85))
        self.assertEqual(settings.get("podcast_home"), ["France Culture", "Arte Radio"])
        self.assertIs(settings.get("phone_remote"), False)
        self.assertIsNone(settings.get("language"))                         # LANGUAGE du système ignoré
        settings.update(subsonic_url="https://typed-in-app")
        self.assertEqual(settings.subsonic_url, "https://typed-in-app")      # saisi dans l'appli : prioritaire
        self.assertEqual(self.settings().get("subsonic_url"), "https://typed-in-app")   # gardé en base

    def test_default(self):
        self.assertEqual(self.settings().get("phone_port", 8100), 8100)


class LegacyImportTest(TempDirTest):
    def setUp(self):
        super().setUp()
        self.write_json("config.json", {"subsonic_url": "https://s", "subsonic_user": "thomas", "subsonic_pass": "p w",
                                        "admins": ["alice"], "ext_youtube_on": True, "podcast_french": False,
                                        "ext_youtube_key": "AIza-cle-youtube", "ext_jamendo_id": "jam123",
                                        "podcastindex_key": "PIK", "podcastindex_secret": "PIS",
                                        "nom": "Salon", "ville": "Lyon", "latitude": 45.76, "veille_secondes": 120})
        self.write_json("podcasts.json", {
            "subs": {"https://f": {"feed": "https://f", "title": "Histoire", "image": "i", "author": "a", "added": 5}},
            "hidden": ["https://h"],
            "progress": {"e1": {"id": "e1", "feed": "https://f", "title": "Ép", "podcast": "Histoire", "image": "",
                                "audio": "https://a", "pos": 300, "dur": 1000, "played": False, "t": 9}}})
        self.write_json("playlists.json", {"lists": [
            {"id": "abc", "name": "Soirée", "songs": [{"id": "s1", "title": "T"}, {"id": "s2", "title": "U"}, {"bad": 1}]},
            {"id": "favoris", "name": "Favoris d'ailleurs", "songs": [{"id": "yt-1", "title": "V", "youtubeId": "1"}]}]})
        self.write_json("recherches.json", {"music": ["récente", "ancienne"], "podcasts": ["histoire"]})
        self.write_json("youtube-illisibles.json", {"ids": ["abc123def45"]})
        with open(self.path("corrompu.json"), "w") as f:
            f.write("{pas du json")

    def run_import(self):
        paths = Paths(self.dir, self.dir, self.path("cache"))
        db = Database(paths.db_file)
        env = EnvFile(paths.env_file)
        store = AppSettingsStore(db)
        LegacyImport(paths, db, env, store).run()
        return db, env, store

    def test_everything_is_imported_once_and_files_are_kept(self):
        db, env, store = self.run_import()
        values = env.values()
        self.assertEqual((values["SUBSONIC_URL"], values["SUBSONIC_PASS"]), ("https://s", "p w"))
        self.assertEqual((values["DEVICE_NAME"], values["WEATHER_CITY"], values["WEATHER_LATITUDE"], values["SCREENSAVER_SECONDS"]),
                         ("Salon", "Lyon", "45.76", "120"))           # anciennes clés françaises du menu renommées
        self.assertEqual((store.get("ext_youtube_on"), store.get("podcast_french")), (True, False))
        self.assertEqual((values["EXT_YOUTUBE_KEY"], values["EXT_JAMENDO_ID"], values["PODCASTINDEX_KEY"], values["PODCASTINDEX_SECRET"]),
                         ("AIza-cle-youtube", "jam123", "PIK", "PIS"))       # clés saisies dans l'ancienne version : reprises
        stored = {r[0] for r in db.query("SELECT key FROM app_settings")}
        self.assertNotIn("subsonic_pass", stored)                          # secret : pas en base
        self.assertNotIn("admins", stored)                                 # ancienne édition serveur : ignoré
        library = PodcastLibrary(db)
        self.assertEqual(library.subscriptions()[0].title, "Histoire")
        self.assertTrue(library.is_hidden("https://h"))
        self.assertEqual(library.resume_list()[0].position_s, 300)
        playlists = LocalPlaylists(db)
        self.assertEqual([p.to_api() for p in playlists.overview()], [{"id": "abc", "name": "Soirée", "count": 2}])
        self.assertEqual([t.id for t in playlists.favorites()], ["yt-1"])
        self.assertEqual(SearchHistory(db).entries("music"), ["récente", "ancienne"])
        self.assertIn("abc123def45", UnplayableVideos(db))
        self.assertTrue(os.path.exists(self.path("podcasts.json.importe")))
        self.assertFalse(os.path.exists(self.path("podcasts.json")))
        self.write_json("podcasts.json", {"subs": {"https://x": {"title": "Nouveau"}}})
        LegacyImport(Paths(self.dir, self.dir, self.path("cache")), db, env, store).run()   # déjà fait : rien de plus
        self.assertEqual(len(library.subscriptions()), 1)

    def test_existing_env_values_are_not_overwritten(self):
        EnvFile(self.path(".env")).set(SUBSONIC_URL="https://deja-la")
        _, env, _ = self.run_import()
        self.assertEqual(env.values()["SUBSONIC_URL"], "https://deja-la")


class PathsAndTextsTest(TempDirTest):
    def test_data_dir(self):
        self.assertEqual(resolve_data_dir("/home/t/.local/share/pi-media/releases/2026.10.25", {}), "/home/t/.local/share/pi-media")
        self.assertEqual(resolve_data_dir("/src/pi-media-station", {}), "/src/pi-media-station")
        self.assertEqual(resolve_data_dir("/x", {"PI_MEDIA_DATA": "/data"}), "/data")

    def test_texts(self):
        self.assertEqual(flatten({"a": {"b": "c", "d": {"e": 1}}}), {"a.b": "c", "a.d.e": "1"})
        texts = Texts(os.path.join(PROJECT, "i18n"))
        self.assertEqual(texts.t("launcher.weather.codes.63"), "Pluie")
        self.assertEqual(texts.t("server.player.unavailable", reason="panne"), "Lecteur haute fidélité indisponible : panne")
        self.assertEqual(texts.t("missing.key"), "missing.key")
        self.assertIn("queue.title", texts.section("web."))


class TextsApiTest(AppTestCase):
    def test_page_texts_are_served(self):
        texts = self.client.get("/i18n.json", csrf=False).json()
        self.assertEqual(texts["queue.title"], "File d’attente")
        self.assertNotIn("launcher.weather.unknown", texts)

    def test_health_gives_the_version(self):
        self.assertEqual(self.client.get("/health", csrf=False).json(), {"ok": True, "version": "dev"})


if __name__ == "__main__":
    unittest.main()
