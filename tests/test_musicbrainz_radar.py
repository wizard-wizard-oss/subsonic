"""Requêtes MusicBrainz du radar : artistes groupés, label (nouveautés seulement), recherche de labels, tags."""
import tempfile
import unittest
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from pimedia.shared.providers.metadata import Pacer
from pimedia.shared.providers.musicbrainz.client import MusicBrainz
from pimedia.storage.database import Database
from pimedia.webapp.schema import MIGRATIONS
from pimedia.webapp.storage.exploration import ExplorationRepository

START, END = date(2026, 11, 13), date(2027, 1, 26)


def mbid(number):
    return "00000000-0000-4000-8000-%012d" % number


def group(number, title, artist, released, kind="Album", tags=()):
    return {"id": mbid(number), "title": title, "first-release-date": released, "primary-type": kind,
            "artist-credit": [{"name": artist, "artist": {"id": mbid(900 + number), "name": artist}}],
            "tags": [{"name": tag, "count": len(tags) - index} for index, tag in enumerate(tags)]}


class MusicBrainzRadarTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        db = Database(Path(temp.name) / "web.db", MIGRATIONS)
        self.addCleanup(db.close)
        self.urls, self.responses = [], {}
        self.client = MusicBrainz(ExplorationRepository(db), self, clock=lambda: 1000, sleep=lambda delay: None,
                                  pacer=Pacer(0))

    def get_json(self, url, headers=None):
        self.urls.append(url)
        path = urlsplit(url).path.removeprefix("/ws/2/")
        query = parse_qs(urlsplit(url).query).get("query", [""])[0]
        for (expected_path, marker), response in self.responses.items():
            if path == expected_path and marker in query:
                return response
        raise AssertionError("requête inattendue : " + url)

    def query(self, index=-1):
        return parse_qs(urlsplit(self.urls[index]).query)["query"][0]

    def test_artists_are_grouped_in_one_query(self):
        ids = tuple(mbid(n) for n in range(20))
        self.responses[("release-group", "arid:")] = {"count": 1, "release-groups": [
            group(1, "Nouveau", "Moderat", "2026-11-27", tags=("techno", "electronic"))]}
        page = self.client.groups_by_artists(ids, START, END)
        self.assertEqual(len(self.urls), 1)
        for identity in ids:
            self.assertIn("arid:" + identity, self.query())
        self.assertIn("firstreleasedate:[2026-11-13 TO 2027-01-26]", self.query())
        self.assertIn("(primarytype:album OR primarytype:ep)", self.query())
        self.assertEqual([(a.title, a.released_on) for a in page.albums], [("Nouveau", date(2026, 11, 27))])

    def test_tags_are_parsed_most_voted_first(self):
        self.responses[("release-group", "arid:")] = {"count": 1, "release-groups": [
            group(1, "Nouveau", "Moderat", "2026-11-27", tags=("techno", "electronic"))]}
        album = self.client.groups_by_artists((mbid(1),), START, END).albums[0]
        self.assertEqual(album.tags, ("techno", "electronic"))

    def test_credited_artist_ids_are_kept(self):
        self.responses[("release-group", "arid:")] = {"count": 1, "release-groups": [
            group(1, "Nouveau", "Moderat", "2026-11-27")]}
        album = self.client.groups_by_artists((mbid(901),), START, END).albums[0]
        self.assertEqual(album.artist_ids, (mbid(901),))

    def test_label_keeps_only_new_groups(self):
        new, reissue, single = mbid(1), mbid(2), mbid(3)
        self.responses[("release", "laid:")] = {"count": 3, "releases": [
            {"id": mbid(51), "release-group": {"id": new, "primary-type": "Album"}},
            {"id": mbid(52), "release-group": {"id": reissue, "primary-type": "EP"}},
            {"id": mbid(53), "release-group": {"id": new, "primary-type": "Album"}},
            {"id": mbid(54), "release-group": {"id": single, "primary-type": "Single"}}]}
        self.responses[("release-group", "rgid:")] = {"count": 1, "release-groups": [
            group(1, "Nouveauté", "Artiste", "2026-12-04")]}
        page = self.client.label_groups(mbid(700), START, END)
        self.assertIn("laid:" + mbid(700), self.query(0))
        self.assertIn("date:[2026-11-13 TO 2027-01-26]", self.query(0))
        groups_query = self.query(1)
        self.assertIn("rgid:" + new, groups_query)
        self.assertIn("rgid:" + reissue, groups_query)
        self.assertNotIn(single, groups_query)
        self.assertEqual(groups_query.count(new), 1)
        self.assertIn("firstreleasedate:[2026-11-13 TO 2027-01-26]", groups_query)
        self.assertEqual([a.id for a in page.albums], [new])

    def test_label_without_release_makes_one_call(self):
        self.responses[("release", "laid:")] = {"count": 0, "releases": []}
        self.assertEqual(self.client.label_groups(mbid(700), START, END).albums, ())
        self.assertEqual(len(self.urls), 1)

    def test_search_labels(self):
        self.responses[("label", 'label:"Warp"')] = {"labels": [
            {"id": mbid(700), "name": "Warp", "country": "GB", "disambiguation": ""},
            {"id": "pas-un-mbid", "name": "Mauvais"}]}
        found = self.client.search_labels("Warp")
        self.assertEqual([(label.id, label.name, label.country) for label in found.value], [(mbid(700), "Warp", "GB")])

    def test_release_label_takes_first_matching_edition_with_a_label(self):
        credit = [{"name": "Moderat", "artist": {"id": mbid(5), "name": "Moderat"}}]
        self.responses[("release", "release:")] = {"releases": [
            {"id": mbid(60), "title": "III", "artist-credit": [{"name": "Autre"}],
             "label-info": [{"label": {"id": mbid(701), "name": "Faux"}}]},
            {"id": mbid(61), "title": "III", "artist-credit": credit, "label-info": []},
            {"id": mbid(62), "title": "III", "artist-credit": credit,
             "label-info": [{"label": {"id": mbid(700), "name": "Monkeytown"}}]}]}
        found = self.client.release_label("III", "Moderat")
        self.assertEqual((found.label.id, found.label.name, found.release_id), (mbid(700), "Monkeytown", mbid(62)))
        self.assertEqual(len(self.urls), 1)

    def test_release_label_none_when_nothing_matches(self):
        self.responses[("release", "release:")] = {"releases": []}
        self.assertIsNone(self.client.release_label("III", "Moderat"))

    def test_artist_tags(self):
        self.responses[("artist/" + mbid(5), "")] = {"id": mbid(5), "tags": [
            {"name": "rock", "count": 2}, {"name": "noise rock", "count": 5}, {"name": "zéro", "count": 0}]}
        self.assertEqual(self.client.artist_tags(mbid(5)), ("noise rock", "rock"))


if __name__ == "__main__":
    unittest.main()
