"""Nomenclature des dossiers du site et comparaison Unicode avec variantes latines."""
import unittest

from pimedia.shared.text import normalize
from pimedia.webapp.library.naming import LibraryNaming, album_folder


class LibraryNamingTest(unittest.TestCase):
    def test_artist_and_album_initials_keep_accents_punctuation_and_internal_capitals(self):
        for received, expected in (("trentemøller", "Trentemøller"), ("dälek", "Dälek"),
                                   ("jean-michel jarre", "Jean-Michel Jarre"),
                                   ("...et après", "...Et Après"), ("l'impératrice", "L'impératrice"),
                                   ("38 spesh", "38 Spesh"), ("DJ NaZe & AC-DC", "DJ NaZe & AC-DC"),
                                   ("bJo\u0308rk", "BJo\u0308rk"), ("東京事変", "東京事変"),
                                   ("!!!", "!!!"), ("", "")):
            with self.subTest(received=received):
                self.assertEqual(LibraryNaming.normalize_artist(received), expected)
                self.assertEqual(LibraryNaming.normalize_album(received), expected)

    def test_latin_comparison_recognises_non_decomposable_letters(self):
        for left, right in (("Trentemøller", "TRENTEMOLLER"), ("Łona", "Lona"), ("Đorđe", "Dorde")):
            with self.subTest(left=left, right=right):
                self.assertEqual(LibraryNaming.comparison_key(left), LibraryNaming.comparison_key(right))
                self.assertNotEqual(LibraryNaming.comparison_key(left, latin_aliases=False),
                                    LibraryNaming.comparison_key(right, latin_aliases=False))

    def test_native_comparison_keeps_the_existing_shared_rules(self):
        for value in (None, "", 1989, "Trentemøller", "Łona", "عَرَبِيّ", "東京事変", "КИНО", "ʔ", "!!!"):
            with self.subTest(value=value):
                self.assertEqual(LibraryNaming.comparison_key(value, latin_aliases=False), normalize(value))
        self.assertNotEqual(normalize("Trentemøller"), normalize("Trentemoller"))

    def test_arabic_vowels_follow_native_normalisation_without_latin_transliteration(self):
        self.assertEqual(LibraryNaming.comparison_key("عَرَبِيّ"), "عربي")
        self.assertEqual(LibraryNaming.comparison_key("عربي"), "عربي")
        self.assertNotEqual(LibraryNaming.comparison_key("عربي"), LibraryNaming.comparison_key("arabiy"))

    def test_non_latin_alphabets_remain_distinct_from_romanisations(self):
        self.assertEqual(LibraryNaming.comparison_key("東京事変"), "東京事変")
        self.assertEqual(LibraryNaming.comparison_key("КИНО"), "кино")
        self.assertNotEqual(LibraryNaming.comparison_key("東京"), LibraryNaming.comparison_key("DongJing"))
        self.assertNotEqual(LibraryNaming.comparison_key("Кино"), LibraryNaming.comparison_key("Kino"))

    def test_glottal_stop_and_names_made_only_of_symbols_are_preserved(self):
        self.assertEqual(LibraryNaming.comparison_key("ʔ"), "ʔ")
        self.assertEqual(LibraryNaming.comparison_key("!!!"), "!!!")
        self.assertNotEqual(LibraryNaming.comparison_key("!!!"), LibraryNaming.comparison_key("?!"))

    def test_empty_and_numeric_metadata_are_still_supported(self):
        self.assertEqual(LibraryNaming.comparison_key(None), "")
        self.assertEqual(LibraryNaming.comparison_key("  "), "")
        self.assertEqual(LibraryNaming.comparison_key(1989), "1989")


class AlbumFolderTest(unittest.TestCase):
    def test_one_rule_for_songs_disc_folders_and_disc_songs(self):
        self.assertEqual(album_folder(["ABBA/Arrival/01.mp3"]), "ABBA/Arrival")
        self.assertEqual(album_folder(["ABBA/Arrival/CD1"]), "ABBA/Arrival")
        self.assertEqual(album_folder(["", "ABBA/Arrival/CD2/03.flac"]), "ABBA/Arrival")
        self.assertEqual(album_folder(["\\ABBA\\Arrival\\01.mp3"]), "ABBA/Arrival")
        self.assertEqual(album_folder(["single.mp3", ""]), "")
