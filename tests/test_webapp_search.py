"""Recherche d'artistes par nom de dossier, même quand les tags ne trouvent rien."""
from urllib.parse import urlencode
from unittest.mock import patch

from pimedia.webapp.subsonic import SubsonicUnreachable
from tests.webapp_support import WebAppTestCase


class SearchHttpTest(WebAppTestCase):
    def add_artists(self, *artists):
        self.subsonic.indexes.append({"name": "G", "artist": list(artists)})

    def search(self, client, query):
        response = client.get('/api/search?' + urlencode({'q': query}))
        self.assertEqual(response.status, 200, response.body)
        return response.json()

    def test_partial_name_finds_gurriers_when_id3_search_is_empty(self):
        self.add_artists({"id": "dir-gurriers", "name": "Gurriers"})
        bob = self.client("bob", "pw2")
        for query in ("gurr", "GURR", "  gurriers  ", "rrier"):
            with self.subTest(query=query):
                result = self.search(bob, query)
                self.assertEqual(result['artists'], [{"id": "fdir-gurriers", "name": "Gurriers"}])
                self.assertEqual((result['albums'], result['songs']), ([], []))
        self.assertEqual(self.subsonic.index_builds, 1)
        self.assertEqual(self.subsonic.calls['getArtists'], 0)

    def test_accents_ligatures_and_punctuation_use_the_common_comparison(self):
        self.add_artists({"id": "oe", "name": "Œdipe"}, {"id": "daft", "name": "Daft Punk"})
        bob = self.client("bob", "pw2")
        for query, artist in (("bjor", {"id": "fdir-ar3", "name": "Björk"}),
                              ("OED", {"id": "foe", "name": "Œdipe"}),
                              ("daft-pu", {"id": "fdaft", "name": "Daft Punk"})):
            with self.subTest(query=query):
                self.assertEqual(self.search(bob, query)['artists'], [artist])

    def test_folder_and_tag_results_do_not_duplicate_the_same_artist(self):
        result = self.search(self.client("bob", "pw2"), "björk")
        self.assertEqual(result['artists'], [{"id": "fdir-ar3", "name": "Björk"}])

    def test_artists_found_only_by_tags_remain_available(self):
        def tags(handler, params):
            handler.reply_json({'searchResult3': {'artist': [{'id': 'guest', 'name': 'Guest Artist'}]}})
        self.subsonic.api_search3 = tags
        self.assertEqual(self.search(self.client("bob", "pw2"), "guest")['artists'],
                         [{'id': 'guest', 'name': 'Guest Artist'}])

    def test_exact_match_and_prefix_come_before_other_matches_and_limit(self):
        self.add_artists(*({'id': 'other%d' % i, 'name': 'Other Gurr %02d' % i} for i in range(12)),
                         {'id': 'gurriers', 'name': 'Gurriers'}, {'id': 'gurr', 'name': 'Gurr'})
        artists = self.search(self.client("bob", "pw2"), "gurr")['artists']
        self.assertEqual([a['name'] for a in artists[:2]], ['Gurr', 'Gurriers'])
        self.assertEqual(len(artists), 8)

    def test_search_uses_the_index_for_the_accounts_visible_folders(self):
        self.subsonic.music_folders['alice'] = [1]
        self.subsonic.music_folders['bob'] = [2]
        original = self.subsonic.api_getIndexes

        def indexes(handler, params):
            self.subsonic.indexes = [{'name': 'G', 'artist': [{'id': 'gurriers', 'name': 'Gurriers'}]}] \
                if params['u'] == 'alice' else []
            original(handler, params)

        self.subsonic.api_getIndexes = indexes
        alice, bob = self.client("alice", "secret"), self.client("bob", "pw2")
        self.assertEqual(self.search(alice, 'gurr')['artists'], [{'id': 'fgurriers', 'name': 'Gurriers'}])
        self.assertEqual(self.search(bob, 'gurr')['artists'], [])

    def test_hidden_folders_and_mac_leftovers_are_not_search_results(self):
        self.add_artists({'id': 'mac', 'name': '__MACOSX'}, {'id': 'file', 'name': '._Gurriers'})
        bob = self.client("bob", "pw2")
        for query in ('incoming', 'macos', 'gurr'):
            with self.subTest(query=query):
                self.assertEqual(self.search(bob, query)['artists'], [])

    def test_unavailable_index_keeps_the_existing_tag_search_working(self):
        bob = self.client("bob", "pw2")
        with patch.object(self.app.artist_indexes, 'for_user', side_effect=SubsonicUnreachable()):
            result = self.search(bob, 'björk')
        self.assertEqual(result['artists'], [{'id': 'ar3', 'name': 'Björk'}])

    def test_albums_songs_and_empty_queries_still_work(self):
        bob = self.client("bob", "pw2")
        self.assertEqual(self.search(bob, '  '), {'artists': [], 'albums': [], 'songs': []})
        self.assertEqual(self.subsonic.calls['search3'], 0)
        self.assertEqual(self.subsonic.calls['getIndexes'], 0)
        self.assertEqual([a['name'] for a in self.search(bob, 'post')['albums']], ['Post'])
        self.assertEqual([s['title'] for s in self.search(bob, 'army')['songs']], ['Army of Me'])
