"""Édition PC : nomenclature (library.naming), fichiers (library.files) et rangement d'Incoming (library.incoming)."""
import os
import shutil
import stat
import tempfile
import time
import unittest

from pimedia.shared.text import normalize
from pimedia.webapp.library.incoming import HOUR, IncomingSorter
from pimedia.webapp.library.files import LibraryFiles, find_albums, is_disc, tracks_fit
from pimedia.webapp.library.naming import LibraryNaming


def files_under(folder):
    return sorted(os.path.relpath(os.path.join(root, f), folder) for root, _, files in os.walk(folder) for f in files)


class MusicTestCase(unittest.TestCase):
    def setUp(self):
        self.music = tempfile.mkdtemp(prefix="pmw-music-")
        self.addCleanup(shutil.rmtree, self.music, True)
        self.incoming = os.path.join(self.music, "Incoming")
        os.mkdir(self.incoming)
        self.library = LibraryFiles(self.music, self.incoming)

    def write(self, *parts, base=None):
        path = os.path.join(base or self.incoming, *parts)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as out:
            out.write(b"x")
        return path


class LayoutTest(MusicTestCase):
    def test_ligature_matches_existing_folder_and_keeps_its_spelling(self):
        self.write("Œdipe", "Premier", "01.flac", base=self.music)
        album = os.path.dirname(self.write("Envoi", "Deuxième", "01.flac"))
        self.assertEqual(self.library.place(album, "OEDIPE", "Deuxième"), "Œdipe/Deuxième")
        self.assertEqual(files_under(os.path.join(self.music, "Œdipe")),
                         ["Deuxième/01.flac", "Premier/01.flac"])

    def test_names(self):
        self.assertTrue(all(is_disc(n) for n in ("CD1", "cd 2", "Disc 1", "Disk2", "Disque 3")))
        self.assertFalse(any(is_disc(n) for n in ("Face A", "CD", "Bonus", "CD1 Bonus")))
        self.assertEqual(normalize("Dälek"), normalize("DALEK"))
        self.assertEqual(normalize("A.A.Williams"), normalize("A.A. Williams"))
        self.assertEqual(normalize("AC/DC"), normalize("Ac-Dc"))
        self.assertNotEqual(normalize("!!!"), normalize("?!"))                 # rien que des signes : gardés

    def test_lowercase_artist_reuses_its_existing_folder_without_renaming_it(self):
        self.write("DJ NaZe", "Ancien", "01.flac", base=self.music)
        album = os.path.dirname(self.write("dj naze", "new album", "01.flac"))
        self.assertEqual(self.library.place(album, "dj naze", "new album"), "DJ NaZe/New Album")
        self.assertEqual(sorted(os.listdir(self.music)), ["DJ NaZe", "Incoming"])
        self.assertEqual(files_under(os.path.join(self.music, "DJ NaZe")),
                         ["Ancien/01.flac", "New Album/01.flac"])

    def test_placement_uses_artist_and_album_naming_rules_separately(self):
        class DistinctNaming(LibraryNaming):
            @staticmethod
            def normalize_artist(name):
                return "Artist " + LibraryNaming.normalize_artist(name)

            @staticmethod
            def normalize_album(name):
                return "Album " + LibraryNaming.normalize_album(name)

        library = LibraryFiles(self.music, self.incoming, naming=DistinctNaming())
        album = os.path.dirname(self.write("received artist", "received album", "01.flac"))
        self.assertEqual(library.place(album, "received artist", "received album"),
                         "Artist Received Artist/Album Received Album")
        self.assertEqual(files_under(self.music), ["Artist Received Artist/Album Received Album/01.flac"])

    def test_new_artist_and_album_receive_capitals_at_each_word(self):
        album = os.path.dirname(self.write("jean-michel jarre", "oxygène [live]", "01.flac"))
        self.assertEqual(self.library.place(album, "jean-michel jarre", "oxygène [live]"),
                         "Jean-Michel Jarre/Oxygène [Live]")
        self.assertEqual(files_under(self.music), ["Jean-Michel Jarre/Oxygène [Live]/01.flac"])

    def test_new_artist_folder_never_replaces_an_existing_file(self):
        original = self.write("Artiste", base=self.music)
        album = os.path.dirname(self.write("artiste", "album", "01.flac"))
        self.assertIsNone(self.library.place(album, "artiste", "album"))
        self.assertEqual(files_under(self.music), ["Artiste", "Incoming/artiste/album/01.flac"])
        with open(original, "rb") as saved:
            self.assertEqual(saved.read(), b"x")

    def test_capitalising_does_not_overwrite_a_normalised_album_match(self):
        original = self.write("DJ NaZe", "Long live [DELUXE]", "01.flac", base=self.music)
        album = os.path.dirname(self.write("dj naze", "long-live deluxe", "02.flac"))
        self.assertIsNone(self.library.place(album, "dj naze", "long-live deluxe"))
        self.assertEqual(files_under(self.music), ["DJ NaZe/Long live [DELUXE]/01.flac",
                                                   "Incoming/dj naze/long-live deluxe/02.flac"])
        with open(original, "rb") as saved:
            self.assertEqual(saved.read(), b"x")

    def test_album_duplicates_are_checked_before_and_after_folder_normalisation(self):
        for number, existing_name in enumerate(("Işık", "ışık")):
            with self.subTest(existing_name=existing_name):
                artist = "Müzisyen " + str(number)
                self.write(artist, existing_name, "01.flac", base=self.music)
                album = os.path.dirname(self.write(artist, "ışık", "02.flac"))
                self.assertIsNone(self.library.place(album, artist, "ışık"))
                self.assertEqual(files_under(os.path.join(self.music, artist)), [existing_name + "/01.flac"])
                self.assertEqual(files_under(album), ["02.flac"])

    def test_artist_matching_also_checks_the_normalised_folder_name(self):
        self.write("IŞıK", "Ancien", "01.flac", base=self.music)
        album = os.path.dirname(self.write("ışık", "yeni albüm", "02.flac"))
        self.assertEqual(self.library.place(album, "ışık", "yeni albüm"), "IŞıK/Yeni Albüm")
        self.assertEqual(sorted(os.listdir(self.music)), ["Incoming", "IŞıK"])
        self.assertEqual(files_under(os.path.join(self.music, "IŞıK")),
                         ["Ancien/01.flac", "Yeni Albüm/02.flac"])

    def test_albums_are_the_folders_holding_tracks(self):
        self.write("Converge", "Jane Doe", "CD1", "01.flac")
        self.write("Converge", "Jane Doe", "CD2", "01.flac")
        self.write("Converge", "Live", "Face A", "01.flac")
        self.write("Converge", "Jane Doe", "cover.jpg")
        self.assertEqual([os.path.relpath(a, self.incoming) for a in find_albums(self.incoming)],
                         ["Converge/Jane Doe", "Converge/Live/Face A"])
        self.assertTrue(tracks_fit(os.path.join(self.incoming, "Converge", "Jane Doe")))
        self.assertFalse(tracks_fit(os.path.join(self.incoming, "Converge", "Live")))

    def test_place_refuses_and_keeps_everything_when_it_cannot(self):
        self.write("Converge", "Jane Doe", "01.flac", base=self.music)
        album = os.path.dirname(self.write("x", "JANE DOE", "01.flac"))
        self.assertIsNone(self.library.place(album, "Converge", "JANE DOE"))           # déjà là
        self.assertIsNone(self.library.place(album, "Incoming", "Autre"))              # pas un artiste
        self.assertIsNone(self.library.place(album, "ıncoming", "Autre"))              # même dossier après nomenclature
        self.assertIsNone(self.library.place(album, "", "Autre"))                      # artiste absent
        self.assertIsNone(self.library.place(album, "Converge", ""))                   # album absent
        self.assertEqual(self.library.place(album, "converge", "autre"), "Converge/Autre")
        self.assertEqual(files_under(os.path.join(self.music, "Converge")), ["Autre/01.flac", "Jane Doe/01.flac"])


class IncomingSorterTest(MusicTestCase):
    def setUp(self):
        super().setUp()
        self.now = time.time() + 2 * HOUR                         # tout ce qui est écrit maintenant a « 2 heures »
        self.scans = []
        self.logs = []
        self.sorter = IncomingSorter(self.library, 1, lambda: self.scans.append(1) or True,
                                     clock=lambda: self.now, log=self.logs.append)

    def test_album_fixed_by_hand_takes_its_place(self):
        self.write("Converge", "Jane Doe", "01 Concubine.flac")
        self.write("Converge", "Jane Doe", "cover.jpg")
        self.write("Converge", ".DS_Store")
        self.assertEqual(self.sorter.sort(), ["Converge/Jane Doe"])
        self.assertEqual(files_under(self.music), ["Converge/Jane Doe/01 Concubine.flac", "Converge/Jane Doe/cover.jpg"])
        self.assertEqual(stat.S_IMODE(os.stat(os.path.join(self.music, "Converge")).st_mode), 0o775)
        self.assertEqual(os.listdir(self.incoming), [])                     # l'artiste vidé quitte Incoming
        self.assertEqual(self.scans, [1])

    def test_joins_the_existing_artist_whatever_the_accents(self):
        self.write("Dälek", "Absence", "01.mp3", base=self.music)
        self.write("Dalek", "Precipice", "CD1", "01.mp3")
        self.sorter.sort()
        self.assertEqual(files_under(self.music), ["Dälek/Absence/01.mp3", "Dälek/Precipice/CD1/01.mp3"])

    def test_joins_the_existing_artist_whatever_the_spaces_and_dots(self):
        self.write("A.A. Williams", "Forever Blue", "01.flac", base=self.music)
        self.write("A.A.Williams", "Songs From Isolation", "01.flac")
        self.sorter.sort()
        self.assertEqual(files_under(self.music), ["A.A. Williams/Forever Blue/01.flac",
                                                   "A.A. Williams/Songs From Isolation/01.flac"])

    def test_trentemoller_lowercase_album_joins_the_existing_artist(self):
        self.write("Trentemøller", "Fixion", "01.mp3", base=self.music)
        self.write("Trentemøller", "trentemøller", "01 Swerve.mp3")
        self.assertEqual(self.sorter.sort(), ["Trentemøller/Trentemøller"])
        self.assertEqual(files_under(self.music), ["Trentemøller/Fixion/01.mp3",
                                                   "Trentemøller/Trentemøller/01 Swerve.mp3"])
        self.assertEqual(os.listdir(self.incoming), [])
        self.assertEqual(self.scans, [1])

    def test_lowercase_artist_and_album_are_capitalised_when_sorted(self):
        self.write("new artist", "new album", "01.mp3")
        self.assertEqual(self.sorter.sort(), ["New Artist/New Album"])
        self.assertEqual(files_under(self.music), ["New Artist/New Album/01.mp3"])
        self.assertEqual(os.listdir(self.incoming), [])

    def test_ascii_artist_alias_joins_the_existing_latin_spelling(self):
        self.write("Trentemøller", "Fixion", "01.mp3", base=self.music)
        self.write("Trentemoller", "Dreamweaver", "02.mp3")
        self.assertEqual(self.sorter.sort(), ["Trentemøller/Dreamweaver"])
        self.assertEqual(sorted(os.listdir(self.music)), ["Incoming", "Trentemøller"])
        self.assertEqual(files_under(self.music), ["Trentemøller/Dreamweaver/02.mp3", "Trentemøller/Fixion/01.mp3"])

    def test_native_artist_key_takes_priority_over_latin_aliases(self):
        self.write("Trentemøller", "Fixion", "01.mp3", base=self.music)
        self.write("Trentemoller", "Autre", "01.mp3", base=self.music)
        self.write("trente møller", "new album", "02.mp3")
        self.assertEqual(self.sorter.sort(), ["Trentemøller/New Album"])
        self.assertEqual(files_under(os.path.join(self.music, "Trentemoller")), ["Autre/01.mp3"])
        self.assertEqual(files_under(os.path.join(self.music, "Trentemøller")),
                         ["Fixion/01.mp3", "New Album/02.mp3"])

    def test_exact_artist_name_takes_priority_over_an_ambiguous_native_key(self):
        self.write("Trentemöller", "Premier", "01.mp3", base=self.music)
        self.write("Trentemoller", "Autre", "01.mp3", base=self.music)
        self.write("Trentemöller", "new album", "02.mp3")
        self.assertEqual(self.sorter.sort(), ["Trentemöller/New Album"])
        self.assertEqual(files_under(os.path.join(self.music, "Trentemoller")), ["Autre/01.mp3"])
        self.assertEqual(files_under(os.path.join(self.music, "Trentemöller")),
                         ["New Album/02.mp3", "Premier/01.mp3"])

    def test_ambiguous_latin_artist_alias_stays_in_incoming(self):
        self.write("Trentemöller", "Premier", "01.mp3", base=self.music)
        self.write("Trentemoller", "Autre", "01.mp3", base=self.music)
        self.write("Trentemøller", "new album", "02.mp3")
        before = files_under(self.music)
        self.assertEqual(self.sorter.sort(), [])
        self.assertEqual(files_under(self.music), before)
        self.assertEqual(sorted(os.listdir(self.music)), ["Incoming", "Trentemoller", "Trentemöller"])
        self.assertTrue(self.library.is_artist("Trentemøller"))
        self.assertEqual(self.scans, [])

    def test_latin_alias_of_an_existing_album_is_not_overwritten(self):
        self.write("Artiste", "Łona", "01.mp3", base=self.music)
        self.write("Artiste", "Lona", "02.mp3")
        before = files_under(self.music)
        self.assertEqual(self.sorter.sort(), [])
        self.assertEqual(files_under(self.music), before)
        self.assertEqual(self.scans, [])

    def test_waits_while_it_may_still_be_edited(self):
        self.write("Converge", "Jane Doe", "01.flac")
        self.now = time.time() + HOUR / 2
        self.assertEqual(self.sorter.sort(), [])
        self.assertEqual(self.scans, [])

    def test_what_does_not_fit_stays(self):
        for parts in (["loose.mp3"], ["Artiste", "Vide", "notes.txt"], ["Artiste", "Live", "Face A", "01.mp3"],
                      ["__MACOSX", "Album", "._01.mp3"]):
            self.write(*parts)
        before = files_under(self.incoming)
        self.assertEqual(self.sorter.sort(), [])
        self.assertEqual(files_under(self.incoming), before)

    def test_never_overwrites_an_album_already_in_the_library(self):
        self.write("Converge", "Jane Doe", "01.flac", base=self.music)
        self.write("Converge", "Jane Doe", "02.flac")
        self.write("Converge", "Axe to Fall", "01.flac")
        self.assertEqual(self.sorter.sort(), ["Converge/Axe To Fall"])
        self.assertEqual(files_under(self.incoming), ["Converge/Jane Doe/02.flac"])

    def test_off_when_wait_is_zero_or_no_music_dir(self):
        self.assertFalse(IncomingSorter(self.library, 0, None).enabled)
        self.assertFalse(IncomingSorter(LibraryFiles("", ""), 1, None).enabled)


if __name__ == "__main__":
    unittest.main()
