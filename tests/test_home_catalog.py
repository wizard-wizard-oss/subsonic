"""Adaptateur de l’accueil : favoris de tous types, morceau courant et suggestions du même style."""
import unittest
from types import SimpleNamespace

from pimedia.webapp.personal_home.catalog import HomeCatalog
from pimedia.webapp.personal_home.entities import PAGE_SIZE
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

    def test_suggestions_deduplicate_ids_and_album_names_across_pages(self):
        first = dict(id="first", name="Début", artist="Björk", coverId="original")
        pages = [dict(albums=[first] * PAGE_SIZE + [dict(id="another-copy", name="DEBUT", artist="Bjork")], hasMore=True),
                 dict(albums=[dict(id="third-copy", name="Début!", artist="BJÖRK"),
                              dict(id="different-artist", name="Début", artist="Autre groupe"),
                              dict(id="deluxe", name="Début (Deluxe)", artist="Björk")], hasMore=False)]
        self.library.albums = lambda user, kind, genre, page: self.calls.append(page) or pages[page]
        seed = SimpleNamespace(genre="Rock", album_id="seed", album="Autre album", artist="Artiste")
        albums = self.catalog.suggestions(self.user, seed)
        self.assertEqual([album.id for album in albums], ["first", "different-artist", "deluxe"])
        self.assertEqual((albums[0].name, albums[0].artist, albums[0].cover_id), ("Début", "Björk", "original"))
        self.assertEqual(self.calls, [0, 1])

    def test_suggestions_exclude_the_seed_by_identity_or_normalized_artist_and_title(self):
        seed = SimpleNamespace(genre="Rock", album_id="seed", album="L’Apocalypse", artist="Cœur de Pirate")
        self.library.albums = lambda *args: dict(albums=[
            dict(id="seed", name="Autre libellé", artist="Autre artiste"),
            dict(id="seed-copy", name="L Apocalypse", artist="COEUR DE PIRATE"),
            dict(id="other", name="L’Apocalypse", artist="Autre artiste")], hasMore=False)
        self.assertEqual([album.id for album in self.catalog.suggestions(self.user, seed)], ["other"])

    def test_suggestions_do_not_merge_distinct_albums_with_incomplete_metadata(self):
        seed = SimpleNamespace(genre="Rock", album_id="seed", album="", artist="")
        self.library.albums = lambda *args: dict(albums=[
            dict(id="a", name="Untitled"), dict(id="b", name="Untitled"),
            dict(id="c", name="", artist="Groupe"), dict(id="d", name="", artist="Groupe")], hasMore=False)
        self.assertEqual([album.id for album in self.catalog.suggestions(self.user, seed)], ["a", "b", "c", "d"])
