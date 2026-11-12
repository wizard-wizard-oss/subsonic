"""Édition PC : liste des artistes de la barre (dossiers, getIndexes), une pour tout le site, gardée en base et comparée
à Subsonic. Sur music.foos.fr, getIndexes complet met 19 s ; avec ifModifiedSince, 0,1 s si rien n'a changé."""
import unittest

from pimedia.webapp.app import WebApplication
from pimedia.webapp.artist_index import ArtistIndexes, parse_index
from pimedia.webapp.subsonic import SLOW_TIMEOUT
from tests.support import PROJECT
from tests.webapp_support import WebAppTestCase, read_event

CARDIGANS = {"name": "C", "artist": [{"id": "dir-ar4", "name": "The Cardigans"}]}


def names(index):
    return [a["name"] for group in index for a in group["artists"]]


class ArtistIndexHttpTest(WebAppTestCase):
    def restart(self):
        """Nouveau site sur les mêmes données (comme après un redémarrage)."""
        self.app = WebApplication(PROJECT, environ={"PI_MEDIA_WEB_SUBSONIC_URL": self.subsonic.url},
                                  data_dir=self.tmp)
        return self.app.artist_indexes

    def test_folders_not_tags_and_incoming_hidden(self):
        index = self.client("bob", "pw2").get("/api/artists").json()["index"]
        self.assertEqual(index, [{"letter": "A", "artists": [{"id": "fdir-ar1", "name": "ABBA"}]},
                                 {"letter": "B", "artists": [{"id": "fdir-ar3", "name": "Björk"}]}])

    def test_compilations_folder_is_pinned_when_it_exists(self):
        bob = self.client("bob", "pw2")
        self.assertEqual(bob.get("/api/artists").json()["shortcuts"], [])
        self.subsonic.indexes.append({"name": "C", "artist": [{"id": "dir-comp", "name": "compilations"}]})
        self.subsonic.scan()
        self.app.artist_indexes.refresh()
        answer = bob.get("/api/artists").json()
        self.assertEqual(answer["shortcuts"], [{"id": "fdir-comp", "name": "compilations"}])   # majuscules mises à part
        self.assertIn("compilations", names(answer["index"]))                                  # reste aussi à sa lettre

    def test_one_index_for_everyone_kept_after_a_restart(self):
        alice, bob = self.client("alice", "secret"), self.client("bob", "pw2")
        self.assertEqual(names(alice.get("/api/artists").json()["index"]), ["ABBA", "Björk"])
        self.assertEqual(names(bob.get("/api/artists").json()["index"]), ["ABBA", "Björk"])
        self.assertEqual(self.subsonic.index_builds, 1)                 # calculé une fois pour tout le site
        indexes = self.restart()
        self.assertEqual(names(indexes.for_user(self.app.users.by_name("bob"))), ["ABBA", "Björk"])
        self.assertEqual(self.subsonic.index_builds, 1)                 # gardé en base

    def test_warmed_up_at_start_with_a_known_account(self):
        self.client("bob", "pw2")
        self.assertEqual(self.subsonic.index_builds, 0)
        self.app.artist_indexes.warm_up()
        self.assertEqual(self.subsonic.index_builds, 1)
        self.assertEqual(names(self.client("alice", "secret").get("/api/artists").json()["index"]), ["ABBA", "Björk"])
        self.assertEqual(self.subsonic.index_builds, 1)                 # personne n'attend
        self.app.artist_indexes.warm_up()                                      # redémarrage : simple comparaison
        self.assertEqual(self.subsonic.index_builds, 1)

    def test_warm_up_without_any_account_does_nothing(self):
        self.app.artist_indexes.warm_up()
        self.assertEqual(self.subsonic.calls["getIndexes"], 0)

    def test_refresh_asks_subsonic_only_whether_something_changed(self):
        bob = self.client("bob", "pw2")
        bob.get("/api/artists")
        indexes = self.app.artist_indexes
        indexes.refresh()
        self.assertEqual((self.subsonic.index_builds, self.subsonic.calls["getIndexes"]), (1, 2))
        events = self.open_events(bob)
        self.subsonic.scan()                                      # nouveau scan, un artiste en plus
        self.subsonic.indexes.append(CARDIGANS)
        indexes.refresh()
        self.assertEqual(self.subsonic.index_builds, 2)
        self.assertEqual(names(bob.get("/api/artists").json()["index"]), ["ABBA", "Björk", "The Cardigans"])
        read_event(events, "artists")                                          # les barres ouvertes se rechargent
        indexes.refresh()
        self.assertEqual(self.subsonic.index_builds, 2)                 # rien de neuf depuis ce scan

    def test_a_scan_that_changes_nothing_reloads_no_page(self):
        bob = self.client("bob", "pw2")
        bob.get("/api/artists")
        published = []
        self.app.artist_indexes.hub = type("Hub", (), {"publish": lambda _, kind, data: published.append(kind)})()
        self.subsonic.scan()
        self.app.artist_indexes.refresh()
        self.assertEqual((self.subsonic.index_builds, published), (2, []))

    def test_accounts_that_see_other_music_folders_get_their_own_index(self):
        self.subsonic.music_folders["bob"] = [1]
        self.client("alice", "secret").get("/api/artists")
        self.client("bob", "pw2").get("/api/artists")
        self.assertEqual(self.subsonic.index_builds, 2)
        self.assertEqual(sorted(i.folders for i in self.app.artist_indexes.repository.all()), ["1", "1,2"])

    def test_refresh_survives_a_refused_account(self):
        self.client("bob", "pw2").get("/api/artists")
        self.subsonic.users["bob"] = "nouveau"                                 # mot de passe changé dans Subsonic
        self.subsonic.scan()
        self.app.artist_indexes.refresh()                                      # aucune exception
        self.assertEqual(self.subsonic.index_builds, 1)


class ArtistIndexRulesTest(unittest.TestCase):
    def test_shortcuts_and_hidden_names_use_the_common_comparison(self):
        raw = {"indexes": {"index": [{"name": "O", "artist": [
            {"id": "oe", "name": "Œdipe"}, {"id": "hidden", "name": "À ranger"}]}]}}
        index = parse_index(raw, hidden=("A RANGER",))
        service = ArtistIndexes(None, None, None, None, shortcuts=("OEDIPE",))
        self.assertEqual(names(index), ["Œdipe"])
        self.assertEqual(service.shortcuts(index), [{"id": "foe", "name": "Œdipe"}])

    def test_the_index_waits_longer_than_other_calls(self):
        calls = []

        class Subsonic:
            def call(self, credentials, endpoint, params=(), timeout=None):
                calls.append((endpoint, timeout))
                if endpoint == "getMusicFolders":
                    return {"musicFolders": {"musicFolder": {"id": 1, "name": "Music"}}}   # un seul : pas de liste
                return {"indexes": {"lastModified": 5, "index": {"name": "#", "artist": {"id": 9, "name": 311}}}}

        class Repository:
            def get(self, folders):
                return None

            def save(self, index):
                self.saved = index
        user = type("User", (), {"username": "bob", "subsonic_salt": "s", "subsonic_token": "t"})()
        index = ArtistIndexes(Subsonic(), Repository(), None, None).for_user(user)
        self.assertEqual(index, [{"letter": "#", "artists": [{"id": "f9", "name": "311"}]}])
        self.assertEqual(calls, [("getMusicFolders", None), ("getIndexes", SLOW_TIMEOUT)])
