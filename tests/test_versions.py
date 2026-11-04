"""Édition PC : versions du site (i18n/versions.yaml) lues pour la page « Versions »."""
import datetime
import os
import tempfile
import unittest

from pimedia.webapp import versions
from pimedia.webapp.versions import InvalidVersions, read_releases

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")


@unittest.skipIf(versions.yaml is None, "PyYAML absent")
class VersionsTest(unittest.TestCase):
    def read(self, text):
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            f.write(text)
        self.addCleanup(os.remove, f.name)
        return read_releases(f.name)

    def test_the_real_file_is_well_kept(self):
        releases = read_releases(os.path.join(SRC, "i18n", "versions.yaml"))
        self.assertGreaterEqual(len(releases), 4)
        self.assertEqual(releases[-1].version, "0.1")

    def test_reads_newest_first(self):
        releases = self.read('- {version: "1.10", date: 2026-11-02, title: " Plus ", changes: [" Un "]}\n'
                             '- {version: "1.9", date: "2026-11-01", title: Moins, changes: [Deux, Trois]}\n')
        self.assertEqual([r.version for r in releases], ["1.10", "1.9"])          # 10 > 9, pas l'ordre alphabétique
        self.assertEqual(releases[0].to_api(), {"version": "1.10", "date": "2026-11-02", "title": "Plus",
                                                "changes": ["Un"]})
        self.assertEqual(releases[1].date, datetime.date(2026, 11, 1))

    def test_a_fix_number_comes_after_its_version(self):
        releases = self.read('- {version: "1.5.1", date: 2026-11-01, title: Fix, changes: [Un]}\n'
                             '- {version: "1.5", date: 2026-10-31, title: Neuf, changes: [Deux]}\n')
        self.assertEqual([r.version for r in releases], ["1.5.1", "1.5"])

    def test_refuses_a_badly_kept_file(self):
        for text in ('- {version: "1.1", date: 2026-11-01, title: A, changes: [x]}\n'
                     '- {version: "1.2", date: 2026-10-01, title: B, changes: [y]}\n',     # numéro qui recule
                     '- {version: "1.2", date: 2026-10-01, title: A, changes: [x]}\n'
                     '- {version: "1.1", date: 2026-11-01, title: B, changes: [y]}\n',     # date qui recule
                     '- {version: "1.2.3.4", date: 2026-11-01, title: A, changes: [x]}\n',
                     '- {version: "1.2.", date: 2026-11-01, title: A, changes: [x]}\n',
                     '- {version: "1.2", date: 2026-11-01, title: A, changes: [x]}\n'
                     '- {version: "1.2.1", date: 2026-11-02, title: B, changes: [y]}\n',    # correction avant la version : ordre inversé
                     '- {version: "1.2", date: demain, title: A, changes: [x]}\n',
                     '- {version: "1.2", date: 2026-11-01, title: A, changes: []}\n',
                     '- {version: "1.2", date: 2026-11-01, changes: [x]}\n',
                     'version: "1.2"\n'):
            with self.assertRaises(InvalidVersions, msg=text):
                self.read(text)

    def test_no_file_no_history(self):
        self.assertEqual(read_releases(os.path.join(SRC, "absent.yaml")), [])


if __name__ == "__main__":
    unittest.main()
