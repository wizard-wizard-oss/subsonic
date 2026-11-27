"""Édition PC : envoi de fichiers audio ou d'un zip ; les albums du zip sont rangés aussitôt dans la bibliothèque
(Artiste/Album), le reste attend dans Incoming ; puis scan."""
import io
import os
import stat
import unittest
from unittest.mock import patch
import zipfile
from urllib.parse import quote

from pimedia.webapp.library.files import LibraryFiles
from pimedia.webapp.uploads import MAX_FILE_BYTES, MAX_ZIP_BYTES, Uploads, UploadError, incoming_dir, safe_name
from tests.webapp_support import WebAppTestCase

AUDIO = b"fLaC" + bytes(range(200))


def make_zip(entries):
    """Zip en mémoire : {nom dans le zip: contenu}."""
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return data.getvalue()


def make_legacy_zip(entries, encoding):
    """ZIP sans marqueur UTF-8, avec des noms réellement encodés dans l'encodage demandé."""
    class LegacyZipInfo(zipfile.ZipInfo):
        def _encodeFilenameFlags(self):
            return self.filename.encode(encoding), self.flag_bits & ~0x800

    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        for name, content in entries.items():
            archive.writestr(LegacyZipInfo(name), content)
    return data.getvalue()


def files_under(folder):
    return sorted(os.path.relpath(os.path.join(root, f), folder) for root, _, files in os.walk(folder) for f in files)


class UploadHttpTest(WebAppTestCase):
    def setUp(self):
        super().setUp()
        self.music = os.path.join(self.tmp, "Music")
        self.incoming = os.path.join(self.music, "Incoming")
        os.makedirs(self.incoming)
        self.use(LibraryFiles(self.music, self.incoming))
        self.bob = self.client("bob", "pw2")

    def use(self, library):
        self.app.uploads.library = library
        self.app.uploads.directory = library.incoming

    def send(self, name, body=AUDIO, client=None):
        return (client or self.bob).request("POST", "/api/upload?name=" + name, body=body,
                                            headers={"Content-Type": "application/octet-stream"})

    def test_status_names_the_folder(self):
        status = self.bob.get("/api/upload/status").json()
        self.assertEqual((status["enabled"], status["folder"]), (True, "Incoming"))

    def test_lone_audio_files_are_refused_without_writing_or_history(self):
        for extension in ("mp3", "flac", "m4a", "ogg", "opus", "wav", "aiff", "MP3"):
            response = self.send("Mon%20titre." + extension)
            self.assertEqual((response.status, response.json()["error"]), (400, "upload.album_required"))
        self.assertEqual(os.listdir(self.incoming), [])
        self.assertEqual(self.bob.get("/api/upload/history").json()["entries"], [])

    def test_rejected_audio_never_overwrites_an_existing_file(self):
        path = os.path.join(self.incoming, "a.mp3")
        with open(path, "wb") as target:
            target.write(b"original")
        self.assertEqual(self.send("a.mp3").status, 400)
        with open(path, "rb") as target:
            self.assertEqual(target.read(), b"original")

    def test_zip_without_album_is_refused_before_extraction(self):
        archive = make_zip({"Artiste/01.mp3": AUDIO, "Artiste/Album/02.mp3": AUDIO})
        with patch.object(self.app.uploads, "_extract", side_effect=AssertionError("extraction inutile")):
            self.assertEqual(self.send("lot.zip", archive).json()["error"], "upload.album_required")

    def test_rejected_audio_name_does_not_leave_a_file(self):
        name = "Nán Fiero & Mon$rock [Live] !.flac"
        self.assertEqual(self.send(quote(name)).json()["error"], "upload.album_required")
        self.assertEqual(files_under(self.incoming), [])

    def test_path_tricks_cannot_publish_a_lone_file(self):
        for name in ("..%2F..%2Fx.mp3", "C%3A%5Cmusique%5Cy.mp3"):
            self.assertEqual(self.send(name).json()["error"], "upload.album_required")
        self.assertEqual(files_under(self.music), [])

    def test_refusals(self):
        for name, body, error in (("a.exe", AUDIO, "upload.bad_type"), ("sans-extension", AUDIO, "upload.bad_type"),
                                  ("a.zip", b"", "upload.bad_size")):
            response = self.send(name, body)
            self.assertEqual((response.status, response.json()["error"]), (400, error), name)
        self.assertEqual(os.listdir(self.incoming), [])
        self.assertEqual(self.bob.get("/api/me").status, 200)                      # la session continue après un refus

    def test_needs_the_upload_right_and_the_csrf_header(self):
        self.subsonic.roles["bob"] = {"uploadRole": False}
        bob = self.client("bob", "pw2")
        for refused in (self.send("a.mp3", client=bob), bob.get("/api/upload/status"),
                        bob.post_json("/api/upload/finish", {})):
            self.assertEqual((refused.status, refused.json()["error"]), (403, "auth.missing_right"))
        alice = self.client("alice", "secret")
        self.assertEqual(alice.request("POST", "/api/upload?name=a.mp3", body=AUDIO, csrf=False).status, 403)
        self.assertEqual(self.client().request("POST", "/api/upload?name=a.mp3", body=AUDIO).status, 401)
        self.assertEqual(os.listdir(self.incoming), [])

    def test_explains_why_it_cannot_work(self):
        for directory, reason in (("", "off"), (os.path.join(self.tmp, "absent", "Incoming"), "missing")):
            self.app.uploads.directory = directory
            self.assertEqual(self.bob.get("/api/upload/status").json()["reason"], reason)
            self.assertEqual(self.send("a.mp3").json()["error"], "upload." + reason)

    def test_incoming_is_created_in_the_music_root(self):
        root = os.path.join(self.tmp, "Autre")
        os.makedirs(root)
        self.use(LibraryFiles(root, incoming_dir(root, "Incoming")))
        self.assertEqual(self.bob.get("/api/upload/status").json()["enabled"], True)
        self.assertEqual(self.send("a.zip", make_zip({"Artist/Album/01.mp3": AUDIO})).status, 200)
        self.assertEqual(files_under(root), ["Artist/Album/01.mp3"])
        self.assertEqual(stat.S_IMODE(os.stat(os.path.join(root, "Incoming")).st_mode), 0o775)

    def test_not_writable_folder_is_reported_before_sending(self):
        os.chmod(self.incoming, 0o555)
        self.addCleanup(os.chmod, self.incoming, 0o755)
        if os.access(self.incoming, os.W_OK):
            self.skipTest("exécuté en root : tout est permis")
        self.assertEqual(self.bob.get("/api/upload/status").json()["reason"], "not_writable")
        self.assertEqual(self.send("a.mp3").json()["error"], "upload.not_writable")

    def test_finish_asks_subsonic_to_scan(self):
        self.assertEqual(self.bob.post_json("/api/upload/finish", {}).json(), {"scanning": True})
        self.assertEqual(self.subsonic.calls["startScan"], 1)

    def test_scan_without_anyone_uses_a_known_admin(self):
        self.assertFalse(self.app.uploads.scan_as_admin())               # bob n'est pas administrateur
        self.client("alice", "secret")
        self.assertTrue(self.app.uploads.scan_as_admin())

    def test_scan_falls_back_to_an_admin_when_the_account_may_not(self):
        self.client("alice", "secret")                         # administrateur connu du site
        answer = self.subsonic.api_startScan
        self.subsonic.api_startScan = lambda h, p: (h.reply_json({"status": "failed", "error": {"code": 50, "message": "no"}})
                                                    if p["u"] == "bob" else answer(h, p))
        self.assertEqual(self.bob.post_json("/api/upload/finish", {}).json(), {"scanning": True})
        self.subsonic.api_startScan = lambda h, p: h.reply_json({"status": "failed", "error": {"code": 50, "message": "no"}})
        self.assertEqual(self.bob.post_json("/api/upload/finish", {}).json(), {"scanning": False})


class UploadHistoryTest(UploadHttpTest):
    def history(self, client=None, suffix=""):
        return (client or self.bob).get("/api/upload/history" + suffix).json()

    def test_attributes_each_upload_to_the_authenticated_account(self):
        self.assertEqual(self.history(), {"entries": [], "before": None})
        alice = self.client("alice", "secret")
        archive = make_zip({"Artist/Album/01.flac": AUDIO})
        self.send("same.zip&username=alice&userId=1", archive)
        self.send("same.zip", archive, client=alice)
        entries = self.history()["entries"]
        self.assertEqual([e["username"] for e in entries], ["alice", "bob"])
        self.assertEqual(entries[0]["waiting"], ["Artist"])
        self.assertEqual(entries[1]["placed"], ["Artist/Album"])
        self.assertEqual(entries[0]["bytes"], len(archive))
        self.assertGreater(entries[0]["uploadedAt"], 0)
        self.assertEqual(entries, self.history(alice)["entries"])
        self.assertNotIn("subsonic_token", str(entries))

    def test_zip_records_the_archive_and_its_actual_placement(self):
        self.send("Lot.zip", make_zip({"Converge/Jane Doe/01.flac": AUDIO,
                                        "Other/Album/02.flac": AUDIO, "notes.txt": b"x"}))
        entry = self.history()["entries"][0]
        self.assertEqual((entry["filename"], entry["files"], entry["skipped"]), ("Lot.zip", 2, 1))
        self.assertEqual(entry["placed"], ["Converge/Jane Doe", "Other/Album"])
        self.assertEqual(entry["waiting"], [])

    def test_failed_or_interrupted_upload_is_not_recorded(self):
        self.send("bad.exe")
        self.send("bad.zip", b"not a zip")
        bob = self.app.users.by_name("bob")
        with self.assertRaises(UploadError):
            self.app.uploads.save(bob, io.BytesIO(b"x"), len(AUDIO), "short.zip")
        self.assertEqual(self.history()["entries"], [])

    def test_history_survives_a_new_database_connection(self):
        from pimedia.storage.database import Database
        from pimedia.webapp.schema import MIGRATIONS
        from pimedia.webapp.storage.uploads import UploadRepository
        self.send(quote("Été.zip"), make_zip({"Artiste/Été/01.flac": AUDIO}))
        database = Database(self.app.db.path, MIGRATIONS)
        try:
            entries = UploadRepository(database).page(None, 50)
            self.assertEqual((entries[0].username, entries[0].filename), ("bob", "Été.zip"))
        finally:
            database.close()

    def test_history_requires_only_authentication(self):
        self.assertEqual(self.client().get("/api/upload/history").status, 401)
        self.subsonic.roles["bob"] = {"uploadRole": False}
        bob = self.client("bob", "pw2")
        self.assertEqual(bob.get("/api/upload/history").status, 200)

    def test_album_and_home_show_the_sender_without_upload_or_download_right(self):
        self.send("Arrival.zip", make_zip({"ABBA/Arrival/CD1/01.flac": AUDIO}))
        self.subsonic.roles["bob"] = {"uploadRole": False, "downloadRole": False}
        viewer = self.client("bob", "pw2")
        for identity in ("al1", "fdir-al1"):
            album = viewer.get("/api/album?id=" + identity).json()
            self.assertEqual(album["uploadedBy"]["username"], "bob")
        newest = viewer.get("/api/home").json()["newest"]
        arrival = next(a for a in newest if a["id"] == "al1")
        self.assertEqual(arrival["uploadedBy"]["username"], "bob")
        self.assertNotIn("uploadedBy", viewer.get("/api/album?id=al2").json())

    def test_attribution_still_works_when_tags_differ_from_directory_names(self):
        self.send("Arrival.zip", make_zip({"ABBA/Arrival/01.flac": AUDIO}))
        from pimedia.webapp.upload_attribution import UploadAttribution
        service = UploadAttribution(self.app.uploads, self.app.subsonic)
        card = {"id": "al1", "artist": "Other tags", "name": "Deluxe edition"}
        service.annotate(self.app.users.by_name("bob"), [card])
        self.assertEqual(card["uploadedBy"]["username"], "bob")

    def test_same_tags_never_attribute_another_folder(self):
        self.send("Arrival.zip", make_zip({"ABBA/Arrival/01.flac": AUDIO}))
        # Les tags restent identiques mais le chemin Subsonic désigne un autre dossier.
        self.app.upload_attribution.paths.get = lambda key, load: "Other/Arrival"
        self.assertNotIn("uploadedBy", self.bob.get("/api/album?id=al1").json())
        self.assertTrue(all("uploadedBy" not in a for a in self.bob.get("/api/home").json()["newest"]))

    def test_uploads_from_another_music_root_are_not_attributed(self):
        self.send("Arrival.zip", make_zip({"ABBA/Arrival/01.flac": AUDIO}))
        other = os.path.join(self.tmp, "Other")
        os.makedirs(other)
        self.use(LibraryFiles(other, incoming_dir(other, "Incoming")))
        self.assertNotIn("uploadedBy", self.bob.get("/api/album?id=al1").json())

    def test_simultaneous_uploads_of_the_same_name_keep_the_correct_authors(self):
        import threading
        from concurrent.futures import ThreadPoolExecutor
        self.client("alice", "secret")
        barrier = threading.Barrier(2)

        class Together(io.BytesIO):
            def read(self, size=-1):
                barrier.wait(timeout=5)
                return super().read(size)

        def save(username, body):
            try:
                user = self.app.users.by_name(username)
                self.app.uploads.save(user, Together(make_zip({"Artist/Album/01.flac": body})),
                                      len(make_zip({"Artist/Album/01.flac": body})), "same.zip")
            finally:
                self.app.db.close()

        with ThreadPoolExecutor(2) as pool:
            a = pool.submit(save, "alice", b"alice")
            b = pool.submit(save, "bob", b"bob")
            a.result(timeout=10)
            b.result(timeout=10)
        entries = self.history()["entries"]
        self.assertEqual(len(entries), 2)
        for entry in entries:
            base = self.music if entry["placed"] else self.incoming
            folder = entry["placed"][0] if entry["placed"] else "Artist/Album"
            with open(os.path.join(base, folder, "01.flac"), "rb") as received:
                self.assertEqual(received.read(), entry["username"].encode())

    def test_cursor_bounds_are_validated(self):
        for value in ("-1", "0", str(2 ** 100)):
            response = self.bob.get("/api/upload/history?before=" + value)
            self.assertEqual((response.status, response.json()["error"]), (400, "upload.bad_cursor"))

    def test_cursor_does_not_duplicate_entries_when_an_upload_arrives(self):
        from pimedia.webapp.uploads import HISTORY_PAGE_SIZE
        user = self.app.users.by_name("bob")
        result = {"files": 1, "skipped": 0, "placed": [], "waiting": ["a.flac"]}
        for n in range(HISTORY_PAGE_SIZE + 2):
            self.app.uploads.history.add(user, "a.flac", len(AUDIO), result, n)
        first = self.history()
        self.assertEqual(len(first["entries"]), HISTORY_PAGE_SIZE)
        self.send("latest.zip", make_zip({"Artist/Latest/01.flac": AUDIO}))
        last = self.history(suffix="?before=" + str(first["before"]))
        self.assertEqual(len(last["entries"]), 2)
        self.assertIsNone(last["before"])
        self.assertFalse({e["id"] for e in first["entries"]} & {e["id"] for e in last["entries"]})


class UploadMigrationTest(unittest.TestCase):
    def test_existing_database_is_upgraded_and_logins_preserved(self):
        import tempfile
        from pimedia.storage.database import Database
        from pimedia.webapp.schema import MIGRATIONS
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "old.db")
            old = Database(path, MIGRATIONS[:18])
            old.execute("INSERT INTO users (username, subsonic_salt, subsonic_token, created_at, last_seen_at) "
                        "VALUES ('kept', 's', 't', 1, 1)")
            old.close()
            upgraded = Database(path, MIGRATIONS)
            try:
                self.assertEqual(upgraded.version, len(MIGRATIONS))
                self.assertEqual(upgraded.one("SELECT username FROM users")[0], "kept")
                self.assertEqual(upgraded.query("SELECT * FROM upload_history"), [])
                self.assertEqual(upgraded.query("SELECT * FROM upload_albums"), [])
            finally:
                upgraded.close()


class UploadZipTest(UploadHttpTest):
    """Un zip est décompressé, puis chaque album trouvé dedans part aussitôt chez son artiste dans la bibliothèque."""
    ALBUM = {"Converge/Jane Doe/01 Concubine.flac": AUDIO, "Converge/Jane Doe/CD2/02 Fault.mp3": AUDIO,
             "Converge/Jane Doe/cover.jpg": b"jpg", "Converge/Jane Doe/notes.txt": b"x", "Converge/.DS_Store": b"x",
             "__MACOSX/Converge/._cover.jpg": b"x"}

    def existing(self, *parts):
        path = os.path.join(self.music, *parts)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as out:
            out.write(b"x")

    def test_album_goes_straight_to_a_new_artist_folder(self):
        response = self.send("Jane%20Doe.zip", make_zip(self.ALBUM))
        self.assertEqual((response.status, response.json()),
                         (200, {"files": 3, "skipped": 3, "placed": ["Converge/Jane Doe"], "waiting": []}))
        self.assertEqual(files_under(self.music), ["Converge/Jane Doe/01 Concubine.flac", "Converge/Jane Doe/CD2/02 Fault.mp3",
                                                   "Converge/Jane Doe/cover.jpg"])   # ni zip, ni __MACOSX, ni reste caché
        with open(os.path.join(self.music, "Converge", "Jane Doe", "CD2", "02 Fault.mp3"), "rb") as saved:
            self.assertEqual(saved.read(), AUDIO)
        self.assertEqual(stat.S_IMODE(os.stat(os.path.join(self.music, "Converge")).st_mode), 0o775)
        self.assertEqual(stat.S_IMODE(os.stat(os.path.join(self.music, "Converge", "Jane Doe", "cover.jpg")).st_mode), 0o664)
        self.assertEqual(os.listdir(self.incoming), [])

    def test_one_folder_per_artist_whatever_the_accents_and_case(self):
        self.existing("Dälek", "Absence", "01.flac")
        self.existing("DJ Naze", "Ancien", "01.flac")
        response = self.send("a.zip", make_zip({"Dalek/Precipice/01.flac": AUDIO, "DJ NaZe/Nouveau/01.flac": AUDIO}))
        self.assertEqual(response.json()["placed"], ["DJ Naze/Nouveau", "Dälek/Precipice"])
        self.assertEqual(sorted(os.listdir(self.music)), ["DJ Naze", "Dälek", "Incoming"])

    def test_trentemoller_self_titled_album_is_capitalised_and_joins_its_artist(self):
        self.existing("Trentemøller", "Fixion", "01.mp3")
        response = self.send(quote("Trentemøller.zip"), make_zip({
            "Trentemøller/trentemøller/01 Swerve.mp3": AUDIO,
            "Trentemøller/trentemøller/02 Terrified.mp3": AUDIO}))
        self.assertEqual((response.status, response.json()),
                         (200, {"files": 2, "skipped": 0, "placed": ["Trentemøller/Trentemøller"], "waiting": []}))
        self.assertEqual(sorted(os.listdir(self.music)), ["Incoming", "Trentemøller"])
        self.assertEqual(files_under(self.music), ["Trentemøller/Fixion/01.mp3",
                                                   "Trentemøller/Trentemøller/01 Swerve.mp3",
                                                   "Trentemøller/Trentemøller/02 Terrified.mp3"])
        entry = self.bob.get("/api/upload/history").json()["entries"][0]
        self.assertEqual(entry["placed"], ["Trentemøller/Trentemøller"])

    def test_lowercase_artist_reuses_existing_spelling_and_capitalises_the_album(self):
        self.existing("DJ NaZe", "Ancien", "01.flac")
        response = self.send("a.zip", make_zip({"dj naze/new album [live]/01.flac": AUDIO}))
        self.assertEqual(response.json()["placed"], ["DJ NaZe/New Album [Live]"])
        self.assertEqual(sorted(os.listdir(self.music)), ["DJ NaZe", "Incoming"])
        self.assertEqual(files_under(self.music), ["DJ NaZe/Ancien/01.flac", "DJ NaZe/New Album [Live]/01.flac"])

    def test_new_artist_word_initials_preserve_accents_acronyms_and_track_names(self):
        response = self.send("a.zip", make_zip({"jean-michel & DJ NaZe/été après minuit/01 été.flac": AUDIO}))
        self.assertEqual(response.json()["placed"], ["Jean-Michel & DJ NaZe/Été Après Minuit"])
        self.assertEqual(files_under(self.music), ["Jean-Michel & DJ NaZe/Été Après Minuit/01 été.flac"])

    def test_capitalised_upload_never_overwrites_an_existing_album_match(self):
        self.existing("DJ NaZe", "Long live [DELUXE]", "01.flac")
        response = self.send("a.zip", make_zip({"dj naze/long-live deluxe/02.flac": AUDIO}))
        self.assertEqual((response.json()["placed"], response.json()["waiting"]), ([], ["dj naze"]))
        self.assertEqual(files_under(self.music), ["DJ NaZe/Long live [DELUXE]/01.flac",
                                                   "Incoming/dj naze/long-live deluxe/02.flac"])
        with open(os.path.join(self.music, "DJ NaZe", "Long live [DELUXE]", "01.flac"), "rb") as saved:
            self.assertEqual(saved.read(), b"x")

    def test_album_collision_after_capitalisation_keeps_the_upload_in_incoming(self):
        self.existing("Müzisyen", "Işık", "01.flac")
        response = self.send("a.zip", make_zip({"Müzisyen/ışık/02.flac": AUDIO}))
        self.assertEqual((response.status, response.json()["placed"], response.json()["waiting"]),
                         (200, [], ["Müzisyen"]))
        self.assertEqual(files_under(self.music), ["Incoming/Müzisyen/ışık/02.flac", "Müzisyen/Işık/01.flac"])
        with open(os.path.join(self.incoming, "Müzisyen", "ışık", "02.flac"), "rb") as saved:
            self.assertEqual(saved.read(), AUDIO)

    def test_an_album_destination_that_is_a_file_keeps_the_upload_in_incoming(self):
        self.existing("Artiste", "Album")
        response = self.send("a.zip", make_zip({"Artiste/Album/01.flac": AUDIO}))
        self.assertEqual((response.status, response.json()["placed"], response.json()["waiting"]),
                         (200, [], ["Artiste"]))
        self.assertEqual(files_under(self.music), ["Artiste/Album", "Incoming/Artiste/Album/01.flac"])
        with open(os.path.join(self.music, "Artiste", "Album"), "rb") as saved:
            self.assertEqual(saved.read(), b"x")
        with open(os.path.join(self.incoming, "Artiste", "Album", "01.flac"), "rb") as saved:
            self.assertEqual(saved.read(), AUDIO)

    def test_zip_preserves_artist_album_and_track_names(self):
        album = "BigDaddyChop, Mon$rock & Nán Fiero/Médalla [Deluxe]"
        track = album + "/01 Été ! #$;.flac"
        response = self.send("a.zip", make_zip({track: AUDIO}))
        self.assertEqual((response.status, response.json()["placed"], response.json()["waiting"]),
                         (200, [album], []))
        self.assertEqual(files_under(self.music), [track])

    def test_utf8_zip_without_flag_preserves_decomposed_accents(self):
        album = "BigDaddyChop, Mon$rock & Na\u0301n Fiero/Me\u0301dalla"
        track = album + "/01 E\u0301te\u0301.flac"
        body = make_legacy_zip({track: AUDIO}, "utf-8")
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            member = archive.infolist()[0]
            self.assertFalse(member.flag_bits & 0x800)
            self.assertIn("Na╠ün Fiero", member.filename)       # devenait « Na_ün Fiero » avant la correction
        response = self.send("a.zip", body)
        self.assertEqual((response.status, response.json()["placed"]), (200, [album]))
        self.assertEqual(files_under(self.music), [track])
        with open(os.path.join(self.music, track), "rb") as saved:
            self.assertEqual(saved.read(), AUDIO)

    def test_cp437_zip_keeps_its_original_accents(self):
        album = "Dälek/Été"
        track = album + "/01 Ça.flac"
        response = self.send("a.zip", make_legacy_zip({track: AUDIO}, "cp437"))
        self.assertEqual((response.status, response.json()["placed"]), (200, [album]))
        self.assertEqual(files_under(self.music), [track])

    def test_decomposed_artist_matches_without_renaming_existing_folder(self):
        self.existing("Nán Fiero", "Ancien", "01.flac")
        response = self.send("a.zip", make_legacy_zip({"Na\u0301n Fiero/Nouveau/01.flac": AUDIO}, "utf-8"))
        self.assertEqual(response.json()["placed"], ["Nán Fiero/Nouveau"])
        self.assertEqual(sorted(os.listdir(self.music)), ["Incoming", "Nán Fiero"])
        self.assertEqual(files_under(self.music), ["Nán Fiero/Ancien/01.flac", "Nán Fiero/Nouveau/01.flac"])

    def test_extra_folders_around_the_artist_are_dropped(self):
        response = self.send("a.zip", make_zip({"Mes envois/Converge/Jane Doe/01.flac": AUDIO,
                                                "Mes envois/Converge/Jane Doe/cover.jpg": b"jpg"}))
        self.assertEqual(response.json()["placed"], ["Converge/Jane Doe"])
        self.assertEqual(files_under(self.music), ["Converge/Jane Doe/01.flac", "Converge/Jane Doe/cover.jpg"])

    def test_what_cannot_be_placed_waits_in_incoming_as_organised(self):
        self.existing("Converge", "Axe to Fall", "01.flac")
        response = self.send("Lot.zip", make_zip({
            "Converge/Jane Doe/01.flac": AUDIO,
            "Converge/axe to fall/01.flac": AUDIO,
            "minuscule/Petitioning/01.flac": AUDIO,
            "Converge/Live/Face A/01.flac": AUDIO}))
        self.assertEqual(response.json()["placed"], ["Converge/Jane Doe", "Minuscule/Petitioning"])
        self.assertEqual(files_under(self.incoming), ["Converge/Live/Face A/01.flac", "Converge/axe to fall/01.flac"])
        self.assertEqual(response.json()["waiting"], ["Converge"])

    def test_zip_with_loose_tracks_is_refused_atomically_before_placing_any_album(self):
        for loose in ("01.mp3", "Album/01.mp3"):
            response = self.send("Lot.zip", make_zip({"Artist/Album/01.flac": AUDIO, loose: AUDIO}))
            self.assertEqual((response.status, response.json()["error"]), (400, "upload.album_required"))
            self.assertEqual(files_under(self.music), [])
            self.assertEqual(self.bob.get("/api/upload/history").json()["entries"], [])

    def test_a_known_artist_above_makes_it_doubtful(self):
        self.existing("Converge", "Axe to Fall", "01.flac")
        response = self.send("a.zip", make_zip({"Converge/Live/Face A/01.flac": AUDIO}))   # pas « Live / Face A »
        self.assertEqual(response.json()["placed"], [])
        self.assertEqual(files_under(self.incoming), ["Converge/Live/Face A/01.flac"])

    def test_same_waiting_album_twice_never_overwrites(self):
        self.existing("Artist", "Album", "original.flac")
        self.send("a.zip", make_zip({"Artist/Album/01.flac": AUDIO}))
        self.send("b.zip", make_zip({"Artist/Album/01.flac": b"autre"}))
        self.assertEqual(files_under(self.incoming), ["Artist/Album/01 (2).flac", "Artist/Album/01.flac"])

    def test_paths_inside_the_zip_stay_in_the_folder(self):
        response = self.send("a.zip", make_zip({"../../Evil/Album/a.mp3": AUDIO, "/abs/Album/x.flac": AUDIO,
                                                "C:\\win\\y.ogg": AUDIO}))
        self.assertEqual(response.json()["files"], 3)
        self.assertEqual(files_under(self.music), ["Abs/Album/x.flac", "C_/Win/y.ogg", "Evil/Album/a.mp3"])

    def test_bad_or_empty_zip_is_refused_and_leaves_nothing(self):
        for body, error in ((b"pas un zip" * 10, "upload.bad_zip"), (make_zip({"notes.txt": b"x"}), "upload.empty_zip")):
            response = self.send("a.zip", body)
            self.assertEqual((response.status, response.json()["error"]), (400, error))
        self.assertEqual(files_under(self.music), [])
        self.assertEqual(os.listdir(self.incoming), [])


class UploadUnitTest(WebAppTestCase):
    def setUp(self):
        super().setUp()
        self.incoming = os.path.join(self.tmp, "Incoming")
        os.makedirs(self.incoming)
        self.uploads = Uploads(self.subsonic, self.app.users, LibraryFiles(self.tmp, self.incoming), self.app.uploads.history)
        self.user = self.app.users.save_login("zoé/../x", "s", "t", frozenset({"upload"}))

    def test_interrupted_upload_leaves_nothing(self):
        with self.assertRaises(UploadError) as raised:
            self.uploads.save(self.user, io.BytesIO(AUDIO[:50]), len(AUDIO), "a.zip")
        self.assertEqual(raised.exception.args[0], "upload.interrupted")
        self.assertEqual([f for _, _, files in os.walk(self.incoming) for f in files], [])

    def test_too_big_is_refused_without_reading(self):
        stream = io.BytesIO(AUDIO)
        with self.assertRaises(UploadError):
            self.uploads.save(self.user, stream, MAX_ZIP_BYTES + 1, "a.zip")
        self.assertEqual(stream.tell(), 0)

    def test_names_are_made_safe(self):
        self.assertEqual(safe_name("../../etc/passwd", "x"), "passwd")
        self.assertEqual(safe_name("..", "x"), "x")
        self.assertEqual(safe_name("  .caché.mp3", "x"), "caché.mp3")
        self.assertEqual(safe_name("a<b>:c*.flac", "x"), "a_b__c_.flac")
        self.assertEqual(safe_name("", "user"), "user")
        archive = make_zip({"Artist/Album/01.flac": AUDIO})
        self.assertEqual(self.uploads.save(self.user, io.BytesIO(archive), len(archive), "album.zip")["placed"], ["Artist/Album"])

    def test_names_keep_punctuation_and_both_unicode_forms(self):
        for name in ("Mon$rock", "Nán Fiero", "Na\u0301n Fiero", "Mon\u0308rock", "Médalla [Deluxe] ! #;=", "!!!"):
            with self.subTest(name=name):
                self.assertEqual(safe_name(name, "x"), name)

    def test_control_characters_are_removed(self):
        self.assertEqual(safe_name("a\x00\n\x7f.flac", "x"), "a___.flac")
