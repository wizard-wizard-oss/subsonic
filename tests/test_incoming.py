"""Édition PC : nomenclature de la bibliothèque (layout.py) et rattrapage d'Incoming corrigé à la main (incoming.py)."""
import os
import shutil
import stat
import tempfile
import time
import unittest

from pimedia.webapp.incoming import HOUR, IncomingSorter
from pimedia.webapp.layout import MusicTree, capitalised, find_albums, is_disc, normalised, tracks_fit


def files_under(folder):
    return sorted(os.path.relpath(os.path.join(root, f), folder) for root, _, files in os.walk(folder) for f in files)


class MusicTestCase(unittest.TestCase):
    def setUp(self):
        self.music = tempfile.mkdtemp(prefix="pmw-music-")
        self.addCleanup(shutil.rmtree, self.music, True)
        self.incoming = os.path.join(self.music, "Incoming")
        os.mkdir(self.incoming)
        self.library = MusicTree(self.music, self.incoming)

    def write(self, *parts, base=None):
        path = os.path.join(base or self.incoming, *parts)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as out:
            out.write(b"x")
        return path


class LayoutTest(MusicTestCase):
    def test_names(self):
        self.assertTrue(all(is_disc(n) for n in ("CD1", "cd 2", "Disc 1", "Disk2", "Disque 3")))
        self.assertFalse(any(is_disc(n) for n in ("Face A", "CD", "Bonus", "CD1 Bonus")))
        self.assertTrue(all(capitalised(n) for n in ("Converge", "38 Spesh", "Årabrot", "...Et Après", "Le$")))
        self.assertFalse(any(capitalised(n) for n in ("converge", "dälek", "")))
        self.assertEqual(normalised("Dälek"), normalised("DALEK"))
        self.assertEqual(normalised("A.A.Williams"), normalised("A.A. Williams"))
        self.assertEqual(normalised("AC/DC"), normalised("Ac-Dc"))
        self.assertNotEqual(normalised("!!!"), normalised("?!"))                 # rien que des signes : gardés

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
        self.assertIsNone(self.library.place(album, "converge", "Autre"))              # minuscule
        self.assertIsNone(self.library.place(album, "Incoming", "Autre"))              # pas un artiste
        self.assertEqual(self.library.place(album, "Converge", "Autre"), "Converge/Autre")
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

    def test_waits_while_it_may_still_be_edited(self):
        self.write("Converge", "Jane Doe", "01.flac")
        self.now = time.time() + HOUR / 2
        self.assertEqual(self.sorter.sort(), [])
        self.assertEqual(self.scans, [])

    def test_what_does_not_fit_stays(self):
        for parts in (["loose.mp3"], ["minuscule", "Album", "01.mp3"], ["Artiste", "album", "01.mp3"],
                      ["Artiste", "Vide", "notes.txt"], ["Artiste", "Live", "Face A", "01.mp3"],
                      ["__MACOSX", "Album", "._01.mp3"]):
            self.write(*parts)
        before = files_under(self.incoming)
        self.assertEqual(self.sorter.sort(), [])
        self.assertEqual(files_under(self.incoming), before)

    def test_never_overwrites_an_album_already_in_the_library(self):
        self.write("Converge", "Jane Doe", "01.flac", base=self.music)
        self.write("Converge", "Jane Doe", "02.flac")
        self.write("Converge", "Axe to Fall", "01.flac")
        self.assertEqual(self.sorter.sort(), ["Converge/Axe to Fall"])
        self.assertEqual(files_under(self.incoming), ["Converge/Jane Doe/02.flac"])

    def test_off_when_wait_is_zero_or_no_music_dir(self):
        self.assertFalse(IncomingSorter(self.library, 0, None).enabled)
        self.assertFalse(IncomingSorter(MusicTree("", ""), 1, None).enabled)


if __name__ == "__main__":
    unittest.main()
