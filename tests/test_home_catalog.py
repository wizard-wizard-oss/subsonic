"""Adaptateur de l’accueil : favoris de tous types, morceau courant et suggestions du même style."""
import unittest
from types import SimpleNamespace

from pimedia.webapp.personal_home.catalog import HomeCatalog
from pimedia.webapp.subsonic import SubsonicUnreachable


class HomeCatalogTest(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.starred = {}
        self.album = dict(id="a", name="Disque", artistId="ar", artist="Groupe", genre="Électro", coverArt="c")
        self.queue = dict(songs=[dict(id="s1", artist="A"), dict(id="s2", artist="B")], index=1, currentId="s2")
        self.library = SimpleNamespace(subsonic=SimpleNamespace(call=self.call), albums=self.albums)
        self.catalog = HomeCatalog(self.library, SimpleNamespace(play_queue=lambda user: self.queue))
        self.user = SimpleNamespace(username="alice", subsonic_salt="s", subsonic_token="t")

    def call(self, credentials, endpoint, params=()):
        self.calls.append((credentials.username, endpoint, params))
        return {"starred2": self.starred} if endpoint == "getStarred2" else {"artist": {"album": self.album}}

    def albums(self, user, kind, value, page):
        self.calls.append((kind, value, page))
        return dict(albums=[dict(id="a", name="Déjà écouté"), dict(id="other", name="Suggestion")], hasMore=False)

    def test_only_the_current_song_is_taken_from_the_queue(self):
        self.assertEqual(self.catalog.current(self.user).id, "s2")
        self.queue = dict(songs=[], index=0, currentId="")
        self.assertIsNone(self.catalog.current(self.user))

    def test_favorite_artist_is_expanded_through_existing_subsonic_client(self):
        self.starred = dict(artist=[dict(id="ar", name="Groupe")])
        seed = self.catalog.favorites(self.user)[0]
        self.assertEqual((seed.artist, seed.genre), ("Groupe", "Électro"))
        self.assertEqual([call[1] for call in self.calls], ["getStarred2", "getArtist"])
        self.assertTrue(all(call[0] == "alice" for call in self.calls))

    def test_album_favorites_supply_the_exact_genre_and_exclude_the_seed_album(self):
        self.starred = dict(album=self.album)
        seed = self.catalog.favorites(self.user)[0]
        result = self.catalog.suggestions(self.user, seed)
        self.assertEqual([album.id for album in result], ["other"])
        self.assertEqual(self.calls[-1], ("genre", "Électro", 0))

    def test_unavailable_queue_and_missing_genre_are_empty(self):
        def unavailable(user):
            raise SubsonicUnreachable()
        self.catalog.listening.play_queue = unavailable
        self.assertIsNone(self.catalog.current(self.user))
        self.assertEqual(self.catalog.suggestions(self.user, SimpleNamespace(genre="")), ())
