"""Même comparaison des noms pour les métadonnées, les genres et les dossiers."""
import unittest

from pimedia.shared.text import normalize


class NameComparisonTest(unittest.TestCase):
    def test_equivalent_spellings(self):
        for left, right in (("Dälek", "DALEK"), ("A.A.Williams", "A.A. Williams"),
                            ("AC/DC", "Ac-Dc"), ("Hip-Hop", "hip hop"),
                            ("DISSIDÆNCE", "Dissidaence"), ("ŒUVRES", "Oeuvres"),
                            ("Straße", "STRASSE"), ("Nán Fiero", "Na\u0301n Fiero")):
            with self.subTest(left=left, right=right):
                self.assertEqual(normalize(left), normalize(right))

    def test_distinct_names_remain_distinct(self):
        for left, right in (("!!!", "?!"), ("Episode 1", "Episode 2"),
                            ("Arrival", "Arrival Live"), ("東京", "北京")):
            with self.subTest(left=left, right=right):
                self.assertNotEqual(normalize(left), normalize(right))

    def test_empty_and_numeric_metadata(self):
        self.assertEqual(normalize(None), "")
        self.assertEqual(normalize("  "), "")
        self.assertEqual(normalize(1989), normalize("1989"))

    def test_non_latin_letters_are_kept(self):
        self.assertEqual(normalize("東京事変"), "東京事変")
        self.assertEqual(normalize("КИНО"), normalize("Кино"))
