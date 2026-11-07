"""Édition PC : envoi de fichiers audio ou d'un zip ; les albums du zip sont rangés aussitôt dans la bibliothèque
(Artiste/Album), le reste attend dans Incoming ; puis scan."""
import io
import os
import stat
import zipfile
from urllib.parse import quote

from pimedia.webapp.layout import MusicTree
from pimedia.webapp.uploads import MAX_FILE_BYTES, Uploads, UploadError, incoming_dir, safe_name
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
        self.use(MusicTree(self.music, self.incoming))
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

    def test_a_lone_file_waits_in_incoming(self):
        response = self.send("Mon%20titre.flac")
        self.assertEqual((response.status, response.json()),
                         (200, {"files": 1, "skipped": 0, "placed": [], "waiting": ["Mon titre.flac"]}))
        path = os.path.join(self.incoming, "Mon titre.flac")
        with open(path, "rb") as saved:
            self.assertEqual(saved.read(), AUDIO)
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o664)               # lisible par Subsonic, modifiable par le groupe
        self.assertEqual(os.listdir(self.incoming), ["Mon titre.flac"])           # pas de reste « .part »

    def test_never_overwrites(self):
        self.send("a.mp3")
        self.assertEqual(self.send("a.mp3").json()["waiting"], ["a (2).mp3"])
        self.assertEqual(self.send("a.mp3").json()["waiting"], ["a (3).mp3"])

    def test_lone_file_keeps_accents_and_punctuation(self):
        name = "Nán Fiero & Mon$rock [Live] !.flac"
        response = self.send(quote(name))
        self.assertEqual((response.status, response.json()["waiting"]), (200, [name]))
        self.assertEqual(files_under(self.incoming), [name])

    def test_path_tricks_stay_in_the_folder(self):
        self.assertEqual(self.send("..%2F..%2Fx.mp3").json()["waiting"], ["x.mp3"])
        self.assertEqual(self.send("C%3A%5Cmusique%5Cy.mp3").json()["waiting"], ["y.mp3"])
        self.assertEqual(files_under(self.music), ["Incoming/x.mp3", "Incoming/y.mp3"])

    def test_refusals(self):
        for name, body, error in (("a.exe", AUDIO, "upload.bad_type"), ("sans-extension", AUDIO, "upload.bad_type"),
                                  ("a.mp3", b"", "upload.bad_size")):
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
        self.use(MusicTree(root, incoming_dir(root, "Incoming")))
        self.assertEqual(self.bob.get("/api/upload/status").json()["enabled"], True)
        self.assertEqual(self.send("a.mp3").status, 200)
        self.assertEqual(files_under(root), ["Incoming/a.mp3"])
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
            "Converge/Jane Doe/01.flac": AUDIO,                  # rangé
            "Converge/axe to fall/01.flac": AUDIO,               # déjà dans la bibliothèque (majuscules mises à part)
            "minuscule/Petitioning/01.flac": AUDIO,              # artiste sans majuscule
            "Converge/Live/Face A/01.flac": AUDIO,               # « Face A » n'est pas un disque
            "Seul/01.flac": AUDIO,                               # album sans artiste
            "02.flac": AUDIO}))                                  # à la racine du zip : album au nom du zip, sans artiste
        self.assertEqual(response.json()["placed"], ["Converge/Jane Doe"])
        self.assertEqual(files_under(self.incoming), ["Converge/Live/Face A/01.flac", "Converge/axe to fall/01.flac",
                                                      "Lot/02.flac", "Seul/01.flac", "minuscule/Petitioning/01.flac"])
        self.assertEqual(response.json()["waiting"], ["Converge", "Lot", "Seul", "minuscule"])

    def test_a_known_artist_above_makes_it_doubtful(self):
        self.existing("Converge", "Axe to Fall", "01.flac")
        response = self.send("a.zip", make_zip({"Converge/Live/Face A/01.flac": AUDIO}))   # pas « Live / Face A »
        self.assertEqual(response.json()["placed"], [])
        self.assertEqual(files_under(self.incoming), ["Converge/Live/Face A/01.flac"])

    def test_same_waiting_album_twice_never_overwrites(self):
        self.send("a.zip", make_zip({"Seul/01.flac": AUDIO}))
        self.send("b.zip", make_zip({"Seul/01.flac": b"autre"}))
        self.assertEqual(files_under(self.incoming), ["Seul/01 (2).flac", "Seul/01.flac"])

    def test_paths_inside_the_zip_stay_in_the_folder(self):
        response = self.send("a.zip", make_zip({"../../Evil/Album/a.mp3": AUDIO, "/abs/x.flac": AUDIO,
                                                "C:\\win\\y.ogg": AUDIO}))
        self.assertEqual(response.json()["files"], 3)
        self.assertEqual(files_under(self.music), ["Evil/Album/a.mp3", "Incoming/C_/win/y.ogg", "Incoming/abs/x.flac"])

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
        self.uploads = Uploads(self.subsonic, self.app.users, MusicTree(self.tmp, self.incoming))
        self.user = self.app.users.save_login("zoé/../x", "s", "t", frozenset({"upload"}))

    def test_interrupted_upload_leaves_nothing(self):
        with self.assertRaises(UploadError) as raised:
            self.uploads.save(self.user, io.BytesIO(AUDIO[:50]), len(AUDIO), "a.flac")
        self.assertEqual(raised.exception.args[0], "upload.interrupted")
        self.assertEqual([f for _, _, files in os.walk(self.incoming) for f in files], [])

    def test_too_big_is_refused_without_reading(self):
        stream = io.BytesIO(AUDIO)
        with self.assertRaises(UploadError):
            self.uploads.save(self.user, stream, MAX_FILE_BYTES + 1, "a.flac")
        self.assertEqual(stream.tell(), 0)

    def test_names_are_made_safe(self):
        self.assertEqual(safe_name("../../etc/passwd", "x"), "passwd")
        self.assertEqual(safe_name("..", "x"), "x")
        self.assertEqual(safe_name("  .caché.mp3", "x"), "caché.mp3")
        self.assertEqual(safe_name("a<b>:c*.flac", "x"), "a_b__c_.flac")
        self.assertEqual(safe_name("", "user"), "user")
        self.assertEqual(self.uploads.save(self.user, io.BytesIO(AUDIO), len(AUDIO), "a.flac")["waiting"], ["a.flac"])

    def test_names_keep_punctuation_and_both_unicode_forms(self):
        for name in ("Mon$rock", "Nán Fiero", "Na\u0301n Fiero", "Mon\u0308rock", "Médalla [Deluxe] ! #;=", "!!!"):
            with self.subTest(name=name):
                self.assertEqual(safe_name(name, "x"), name)

    def test_control_characters_are_removed(self):
        self.assertEqual(safe_name("a\x00\n\x7f.flac", "x"), "a___.flac")
