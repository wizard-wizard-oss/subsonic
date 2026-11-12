"""Édition PC : mix et radios, playlists, scrobble, en écoute, marque-pages, file partagée, photos, radios Internet."""
import base64
import hashlib
import io
import random
import unittest
import urllib.error
import urllib.parse

from pimedia.shared.text import normalize
from pimedia.webapp.avatars import Gravatar, GravatarUnreachable, gravatar_url, image_type
from pimedia.webapp.mixes import MixError, MixOptions, spread_artists
from tests.fake_subsonic import PNG
from tests.webapp_support import FakeInfoSites, FakeLyricsSites, WebAppTestCase


def titles(response):
    return [s["title"] for s in response.json()["songs"]]


class MixRulesTest(unittest.TestCase):
    def test_genre_spellings_are_grouped(self):
        self.assertEqual({normalize(g) for g in ("Hip-Hop", "Hip hop", "hiphop", "HIP HOP")}, {"hiphop"})
        self.assertEqual(normalize("Électro"), "electro")

    def test_no_two_songs_of_the_same_artist_in_a_row_when_possible(self):
        songs = [{"id": str(i), "artist": a} for i, a in enumerate("AAABBC")]
        for seed in range(20):
            order = [s["artist"] for s in spread_artists(songs, random.Random(seed))]
            self.assertEqual(sorted(order), list("AAABBC"))
            self.assertFalse(any(x == y for x, y in zip(order, order[1:])), order)

    def test_options_are_validated(self):
        options = MixOptions.parse({"genres": ["Rock"] * 20, "decades": [1980, 1985, "1990"], "size": 1000,
                                    "seedArtistId": "ar1", "chronological": 1})
        self.assertEqual((len(options.genres), options.decades, options.size, options.chronological),
                         (12, [1980], 60, True))

    def test_depth_defaults_and_legacy_options(self):
        self.assertEqual(MixOptions.parse({}).depth, 4)
        self.assertEqual(MixOptions.parse({"wide": True}).depth, 4)
        self.assertEqual(MixOptions.parse({"wide": False}).depth, 1)
        self.assertEqual(MixOptions.parse({"wide": False, "depth": 3}).depth, 3)

    def test_depth_accepts_only_one_to_four_whole_levels(self):
        for depth in range(1, 5):
            with self.subTest(depth=depth):
                self.assertEqual(MixOptions.parse({"depth": depth}).depth, depth)
        for depth in (0, -1, 5, 1000, "2", None, True, False, 2.0, [], {}):
            with self.subTest(depth=depth), self.assertRaisesRegex(MixError, "mix.invalid"):
                MixOptions.parse({"depth": depth})


class GravatarTest(unittest.TestCase):
    """Lecture sur gravatar.com, avec un faux urlopen : 404 = pas de photo, autre erreur = injoignable."""

    def opener(self, outcome):
        def urlopen(request, timeout):
            self.url = request.full_url
            if isinstance(outcome, Exception):
                raise outcome
            return io.BytesIO(outcome)
        return urlopen

    def test_photo_missing_or_unreachable(self):
        self.assertEqual(Gravatar(self.opener(PNG)).fetch("a@b.fr"), PNG)
        self.assertTrue(self.url.startswith("https://gravatar.com/avatar/") and self.url.endswith("d=404"))
        missing = urllib.error.HTTPError("u", 404, "Not Found", {}, None)
        self.assertIsNone(Gravatar(self.opener(missing)).fetch("a@b.fr"))
        for error in (urllib.error.HTTPError("u", 500, "Oups", {}, None), urllib.error.URLError("pas de réseau"),
                      TimeoutError()):
            with self.assertRaises(GravatarUnreachable):
                Gravatar(self.opener(error)).fetch("a@b.fr")


class MixHttpTest(WebAppTestCase):
    def test_simple_mixes(self):
        bob = self.client("bob", "pw2")
        self.assertEqual(len(bob.get("/api/mix?kind=random").json()["songs"]), 4)
        self.assertEqual(titles(bob.get("/api/mix?kind=random&genre=Electronic")), ["Army of Me"])
        self.assertEqual(titles(bob.get("/api/mix?kind=newest")), ["Army of Me", "Dancing Queen", "Knowing Me", "Waterloo"])
        response = bob.get("/api/mix?kind=favorites")
        self.assertEqual((response.status, response.json()["error"]), (400, "mix.empty"))     # aucun favori
        bob.post_json("/api/favorite", {"kind": "song", "id": "s4", "on": True})
        self.assertEqual(titles(bob.get("/api/mix?kind=favorites")), ["Army of Me"])
        self.assertEqual(bob.get("/api/mix?kind=nimporte").json()["error"], "mix.invalid")

    def test_song_radio_starts_with_the_song(self):
        bob = self.client("bob", "pw2")
        songs = titles(bob.get("/api/radio/song?id=s4"))
        self.assertEqual((songs[0], len(songs)), ("Army of Me", 4))
        self.subsonic.lastfm = False                    # sans Last.fm : même style, sinon au hasard
        self.assertEqual(titles(bob.get("/api/radio/song?id=s4")), ["Army of Me"])
        self.assertEqual(len(titles(bob.get("/api/radio/song?id=s1"))), 3)          # Pop : les autres titres d'ABBA

    def test_artist_radio_needs_lastfm(self):
        bob = self.client("bob", "pw2")
        self.assertEqual(len(titles(bob.get("/api/radio/artist?id=ar1&name=ABBA"))), 4)
        self.assertGreaterEqual(self.subsonic.calls["getArtistInfo2"], 1)          # artistes proches demandés
        self.subsonic.lastfm = False
        response = bob.get("/api/radio/artist?id=ar1&name=ABBA")
        self.assertEqual((response.status, response.json()["error"]), (400, "mix.no_lastfm"))
        self.assertEqual(bob.get("/api/radio/artist?id=../x&name=ABBA").status, 400)

    def test_mix_builder(self):
        bob = self.client("bob", "pw2")
        settings = bob.get("/api/mix/genres").json()
        genres = settings["genres"]
        self.assertEqual([g["key"] for g in genres], ["pop", "electronic"])
        self.assertEqual(settings["options"]["depths"], [1, 2, 3, 4])
        self.assertEqual(settings["options"]["sizes"], [30, 60, 100])
        self.assertEqual(MixOptions.parse({}).depth, settings["options"]["defaultDepth"])
        for depth in settings["options"]["depths"]:
            self.assertEqual(MixOptions.parse({"depth": depth}).depth, depth)
        built = bob.post_json("/api/mix/build", {"genres": ["pop"], "decades": [1970], "size": 30,
                                                 "chronological": True}).json()
        self.assertEqual(([s["year"] for s in built["songs"]], built["name"]), ([1974, 1976, 1976], "Mix Pop 70s"))
        built = bob.post_json("/api/mix/build", {"seedArtistId": "ar3", "seedArtistName": "Björk"}).json()
        self.assertEqual(([s["title"] for s in built["songs"]], built["name"]), (["Army of Me"], "Mix Björk"))
        empty = bob.post_json("/api/mix/build", {"genres": ["pop"], "decades": [2020]})
        self.assertEqual((empty.status, empty.json()["error"]), (400, "mix.empty"))
        self.assertEqual(bob.post_json("/api/mix/build", {}, csrf=False).status, 403)

    def test_mix_builder_stops_at_the_chosen_depth(self):
        # Une chaîne de cinq artistes : chaque niveau a son titre, sans hasard ni titres proches en parallèle.
        visited = []

        def neighbours(h, p):
            level = int(p["id"].split("-")[1])
            visited.append(level)
            h.reply_json({"artistInfo2": {"similarArtist": [
                {"id": "artist-%s" % (level + 1), "name": "Artist %s" % (level + 1)}]}})

        def top_songs(h, p):
            level = int(p["artist"].split()[1])
            h.reply_json({"topSongs": {"song": [
                {"id": "song-%s" % level, "title": "Level %s" % level, "artist": p["artist"]}]}})

        self.subsonic.api_getArtistInfo2 = neighbours
        self.subsonic.api_getTopSongs = top_songs
        self.subsonic.api_getRandomSongs = lambda h, p: h.reply_json({"randomSongs": {}})
        self.subsonic.api_getSimilarSongs2 = lambda h, p: h.reply_json({"similarSongs2": {}})
        bob = self.client("bob", "pw2")
        for depth in range(1, 5):
            with self.subTest(depth=depth):
                visited.clear()
                response = bob.post_json("/api/mix/build", {"seedArtistId": "artist-0", "depth": depth})
                self.assertEqual(response.status, 200)
                self.assertEqual({s["id"] for s in response.json()["songs"]},
                                 {"song-%s" % level for level in range(1, depth + 1)})
                self.assertEqual(visited, list(range(depth)))

    def test_mix_builder_rejects_invalid_depth_before_querying_subsonic(self):
        bob = self.client("bob", "pw2")
        for depth in (0, 5, "2", True, 2.5, None, [], {}):
            with self.subTest(depth=depth):
                response = bob.post_json("/api/mix/build", {"seedArtistId": "ar1", "depth": depth})
                self.assertEqual((response.status, response.json()["error"]), (400, "mix.invalid"))
        self.assertEqual(self.subsonic.calls["getArtistInfo2"], 0)

    def seeded_library(self):
        """Suggestions et recherche de titres volontairement polluées par du rock et du métal."""
        names = {"artist-0": "Raz Fresco X", **{
            "artist-%s" % i: "Proche %s" % i for i in range(1, 5)},
            "metal": "Groupe de métal", "rock": "Groupe de rock"}
        songs = {aid: {"id": "song-" + aid, "title": name, "artistId": aid, "artist": name,
                       "year": 2020, "genre": {"rock": "Rock", "metal": "Metal"}.get(aid, "Hip-Hop")}
                 for aid, name in names.items()}
        songs["artist-1"]["genre"] = "Hip hop"

        def artist(h, p):
            aid = p["id"]
            h.reply_json({"artist": {"id": aid, "name": names[aid], "album": [{"id": aid}]}})

        def top(h, p):
            tracks = [s for s in songs.values() if s["artist"] == p["artist"]]
            h.reply_json({"topSongs": {"song": tracks + [songs["rock"], songs["metal"]]}})

        def neighbours(h, p):
            aid = p["id"]
            level = int(aid.split("-")[1]) if aid.startswith("artist-") else 4
            ids = ["artist-%s" % (level + 1)] if level < 4 else []
            if level == 1:
                ids += ["metal"]
            h.reply_json({"artistInfo2": {"similarArtist": [
                {"id": i, "name": names[i]} for i in ids] + [{"id": "-1", "name": "Absent"}]}})

        self.subsonic.api_getArtist = artist
        self.subsonic.api_getGenres = lambda h, p: h.reply_json({"genres": {"genre": [
            {"value": genre, "songCount": 10} for genre in ("Hip-Hop", "Rock", "Metal")]}})
        self.subsonic.api_getTopSongs = top
        self.subsonic.api_getArtistInfo2 = neighbours
        self.subsonic.api_getAlbum = lambda h, p: h.reply_json({"album": {"song": [songs[p["id"]]]}})
        self.subsonic.api_getRandomSongs = lambda h, p: h.reply_json({"randomSongs": {"song": [songs["rock"]]}})
        self.subsonic.api_getSimilarSongs2 = lambda h, p: h.reply_json({"similarSongs2": {"song": list(songs.values())}})
        self.subsonic.api_getStarred2 = lambda h, p: h.reply_json({"starred2": {"song": [
            songs["rock"], songs["metal"], dict(songs["artist-1"], id="favorite-near"),
            dict(songs["rock"], id="unrelated-hiphop", genre="Hip-Hop")]}})
        return songs

    def test_seeded_mix_keeps_depth_and_style_without_random_or_opaque_suggestions(self):
        self.seeded_library()
        bob = self.client("bob", "pw2")
        for depth in range(1, 5):
            with self.subTest(depth=depth):
                response = bob.post_json("/api/mix/build", {"seedArtistId": "artist-0",
                                         "seedArtistName": "Raz Fresco X", "depth": depth})
                self.assertEqual(response.status, 200)
                self.assertEqual({s["artistId"] for s in response.json()["songs"]},
                                 {"artist-%s" % i for i in range(depth + 1)})
        self.assertEqual(self.subsonic.calls["getRandomSongs"], 0)
        self.assertEqual(self.subsonic.calls["getSimilarSongs2"], 0)

    def test_seeded_mix_filters_favorites_and_all_sources_by_genre_and_decade(self):
        self.seeded_library()
        bob = self.client("bob", "pw2")
        options = {"seedArtistId": "artist-0", "depth": 2, "favoritesFirst": True}
        response = bob.post_json("/api/mix/build", options)
        self.assertEqual(response.status, 200)
        songs = response.json()["songs"]
        self.assertIn("favorite-near", {s["id"] for s in songs})
        self.assertEqual({s["artistId"] for s in songs}, {"artist-0", "artist-1", "artist-2"})
        rock = bob.post_json("/api/mix/build", dict(options, genres=["rock"]))
        self.assertEqual((rock.status, rock.json()["error"]), (400, "mix.empty"))
        metal = bob.post_json("/api/mix/build", dict(options, genres=["metal"]))
        self.assertEqual(metal.status, 200)
        self.assertEqual({s["artistId"] for s in metal.json()["songs"]}, {"metal"})
        unknown = bob.post_json("/api/mix/build", dict(options, genres=["absent"]))
        self.assertEqual((unknown.status, unknown.json()["error"]), (400, "mix.empty"))
        old = bob.post_json("/api/mix/build", dict(options, decades=[1970]))
        self.assertEqual((old.status, old.json()["error"]), (400, "mix.empty"))

    def test_seeded_mix_uses_local_albums_without_lastfm(self):
        self.subsonic.lastfm = False
        bob = self.client("bob", "pw2")
        response = bob.post_json("/api/mix/build", {"seedArtistId": "ar1", "seedArtistName": "Nom erroné"})
        self.assertEqual(response.status, 200)
        self.assertEqual(set(titles(response)), {"Dancing Queen", "Knowing Me", "Waterloo"})
        self.assertEqual(self.subsonic.calls["getRandomSongs"], 0)

    def test_missing_seed_never_falls_back_to_the_whole_library(self):
        bob = self.client("bob", "pw2")
        response = bob.post_json("/api/mix/build", {"seedArtistId": "missing"})
        self.assertEqual((response.status, response.json()["error"]), (400, "mix.empty"))
        self.assertEqual(self.subsonic.calls["getRandomSongs"], 0)


class TopSongsHttpTest(WebAppTestCase):
    def test_popular_songs_of_an_artist(self):
        bob = self.client("bob", "pw2")
        self.assertEqual(titles(bob.get("/api/artist/top?name=ABBA")), ["Dancing Queen", "Knowing Me", "Waterloo"])
        self.assertEqual(bob.get("/api/artist/top?name=").status, 400)
        self.subsonic.lastfm = False
        self.assertEqual(titles(bob.get("/api/artist/top?name=Bj%C3%B6rk")), [])              # sans Last.fm : rien
        self.assertEqual(len(titles(bob.get("/api/artist/top?name=abba"))), 3)                # gardé une heure


class SimilarArtistsHttpTest(WebAppTestCase):
    def test_similar_artists_of_the_library(self):
        bob = self.client("bob", "pw2")
        self.assertEqual(bob.get("/api/artist/similar?id=ar1").json()["artists"],
                         [{"id": "ar3", "name": "Björk", "coverId": "", "albumCount": 0}])
        self.assertEqual(bob.get("/api/artist/similar?id=../x").status, 400)
        self.subsonic.lastfm = False                                           # sans Last.fm : rien, sans erreur
        self.assertEqual(bob.get("/api/artist/similar?id=ar3").json()["artists"], [])
        self.assertEqual(len(bob.get("/api/artist/similar?id=ar1").json()["artists"]), 1)   # gardé une heure


class LyricsHttpTest(WebAppTestCase):
    def setUp(self):
        super().setUp()
        self.sites = self.app.lyrics.finder.fetcher

    def test_synced_then_plain_then_nothing_without_subsonic(self):
        bob = self.client("bob", "pw2")
        found = bob.get("/api/lyrics?artist=Bj%C3%B6rk&title=Army+of+Me&album=Post&duration=235").json()
        self.assertEqual((found["synced"], found["src"]), (FakeLyricsSites.LRC, "LRCLIB"))
        found = bob.get("/api/lyrics?artist=ABBA&title=Waterloo").json()
        self.assertEqual((found["plain"], found["synced"], found["src"]), ("My my, at Waterloo", "", "lyrics.ovh"))
        self.assertEqual(bob.get("/api/lyrics?artist=ABBA&title=Inconnu").json(), {})
        self.assertEqual(self.subsonic.calls["getLyrics"], 0)                          # jamais par Subsonic
        asked = len(self.sites.urls)
        bob.get("/api/lyrics?artist=ABBA&title=Waterloo")
        self.assertEqual(len(self.sites.urls), asked)                                  # gardé en mémoire
        self.assertEqual(bob.get("/api/lyrics?artist=&title=x").status, 400)
        self.assertEqual(self.client().get("/api/lyrics?artist=a&title=b").status, 401)

    def test_youtube_title_contains_the_artist_instead_of_the_channel(self):
        bob = self.client("bob", "pw2")
        query = urllib.parse.urlencode({"artist": "AnyMusics", "title": "Destinée ; Guy Marchand", "duration": 275})
        found = bob.get("/api/lyrics?" + query).json()
        self.assertEqual((found.get("synced"), found.get("src")), (FakeLyricsSites.LRC, "LRCLIB"))
        asked = len(self.sites.urls)
        self.assertEqual(bob.get("/api/lyrics?" + query).json(), found)
        self.assertEqual(len(self.sites.urls), asked)
        self.assertEqual(self.subsonic.calls["getLyrics"], 0)

    def test_title_with_a_subtitle_finds_the_short_catalogue_title(self):
        bob = self.client("bob", "pw2")
        query = urllib.parse.urlencode({"artist": "Guy Marchand", "title": "Delirium (Ma chérie je t'écris...)",
                                        "duration": 180})
        found = bob.get("/api/lyrics?" + query).json()
        self.assertEqual((found.get("synced"), found.get("src")), (FakeLyricsSites.LRC, "LRCLIB"))
        self.assertEqual(self.subsonic.calls["getLyrics"], 0)


class ArtistBioHttpTest(WebAppTestCase):
    def test_wikipedia_in_french_first(self):
        bob = self.client("bob", "pw2")
        bio = bob.get("/api/artist/bio?name=ABBA&id=ar1").json()
        self.assertEqual((bio["src"], bio["img"], bio["url"]),
                         ("Wikipédia", FakeInfoSites.PHOTO, "https://fr.wikipedia.org/wiki/ABBA"))
        self.assertTrue(bio["text"].startswith("ABBA est un groupe de pop suédois"))
        self.assertEqual(self.subsonic.calls["getArtistInfo2"], 0)            # Last.fm pas demandé

    def test_lastfm_by_subsonic_when_wikipedia_has_nothing(self):
        bob = self.client("bob", "pw2")
        bio = bob.get("/api/artist/bio?name=Bj%C3%B6rk&id=ar3").json()
        self.assertEqual((bio["src"], bio["url"]), ("Last.fm", "https://www.last.fm/music/Björk"))
        self.assertIn("Icelandic singer", bio["text"])
        self.assertNotIn("Read more", bio["text"])                            # lien Last.fm retiré
        asked = self.subsonic.calls["getArtistInfo2"]
        bob.get("/api/artist/bio?name=Bj%C3%B6rk&id=ar3")
        self.assertEqual(self.subsonic.calls["getArtistInfo2"], asked)         # gardé en mémoire

    def test_nothing_found_and_bad_requests(self):
        bob = self.client("bob", "pw2")
        self.assertEqual(bob.get("/api/artist/bio?name=Inconnu").json(), {})
        self.subsonic.lastfm = False
        self.assertEqual(bob.get("/api/artist/bio?name=Bj%C3%B6rk&id=ar3").json(), {})   # sans Last.fm ni Wikipédia
        self.assertEqual(bob.get("/api/artist/bio?name=").status, 400)
        self.assertEqual(bob.get("/api/artist/bio?name=ABBA&id=../x").status, 400)
        self.assertEqual(self.client().get("/api/artist/bio?name=ABBA").status, 401)


class SongFactsHttpTest(WebAppTestCase):
    def test_release_song_and_artist_facts(self):
        bob = self.client("bob", "pw2")
        found = bob.get("/api/facts?artist=ABBA&title=Dancing+Queen&album=Arrival&artistId=ar1").json()
        kinds = [f["k"] for f in found["facts"]]
        self.assertEqual(kinds[0], "Sortie")
        self.assertIn("Album « Arrival », sorti en 1976", found["facts"][0]["t"])
        self.assertIn("La chanson", kinds)
        self.assertEqual(found["img"], FakeInfoSites.PHOTO)

    def test_artist_facts_from_lastfm_biography(self):
        bob = self.client("bob", "pw2")
        found = bob.get("/api/facts?artist=Bj%C3%B6rk&title=Army+of+Me&album=Post&artistId=ar3").json()
        self.assertIn("L’artiste", [f["k"] for f in found["facts"]])
        self.assertEqual(bob.get("/api/facts?artist=Inconnu&title=Rien").json(), {})
        self.assertEqual(bob.get("/api/facts?artist=&title=x").status, 400)
        self.assertEqual(self.client().get("/api/facts?artist=a&title=b").status, 401)


class PlaylistHttpTest(WebAppTestCase):
    def test_create_add_remove_rename_delete(self):
        bob = self.client("bob", "pw2")
        created = bob.post_json("/api/playlist/create", {"name": " Soirée ", "songIds": ["s1", "s4"]}).json()["playlist"]
        self.assertEqual((created["name"], created["mine"], created["songCount"]), ("Soirée", True, 2))
        playlist_id = created["id"]
        self.assertEqual(bob.post_json("/api/playlist/add", {"id": playlist_id, "songIds": ["s3"]}).status, 200)
        self.assertEqual(bob.post_json("/api/playlist/remove", {"id": playlist_id, "positions": [0]}).status, 200)
        self.assertEqual(bob.post_json("/api/playlist/rename", {"id": playlist_id, "name": "Dimanche"}).status, 200)
        playlist = bob.get("/api/playlist?id=" + playlist_id).json()
        self.assertEqual((playlist["name"], [s["title"] for s in playlist["songs"]]), ("Dimanche", ["Army of Me", "Waterloo"]))
        self.assertEqual([p["name"] for p in bob.get("/api/playlists").json()["playlists"]], ["Dimanche"])
        alice = self.client("alice", "secret")
        self.assertEqual(alice.get("/api/playlists").json()["playlists"], [])          # privée : invisible
        self.assertEqual(alice.post_json("/api/playlist/delete", {"id": playlist_id}).status, 502)  # refusé par Subsonic
        self.assertEqual(bob.post_json("/api/playlist/delete", {"id": playlist_id}).status, 200)
        self.assertEqual(self.subsonic.playlists, {})

    def test_public_playlists_of_others_come_after_mine(self):
        self.subsonic.playlists["pl9"] = {"id": "pl9", "name": "Années 70", "owner": "alice", "public": True, "songs": ["s3"]}
        bob = self.client("bob", "pw2")
        bob.post_json("/api/playlist/create", {"name": "Zen"})
        self.assertEqual([(p["name"], p["mine"], p["owner"]) for p in bob.get("/api/playlists").json()["playlists"]],
                         [("Zen", True, "bob"), ("Années 70", False, "alice")])

    def test_validation(self):
        bob = self.client("bob", "pw2")
        for body in ({"name": ""}, {"name": "x" * 101}, {"name": 5}):
            response = bob.post_json("/api/playlist/create", body)
            self.assertEqual((response.status, response.json()["error"]), (400, "playlist.bad_name"), body)
        for body in ({"name": "a", "songIds": "s1"}, {"name": "a", "songIds": ["../x"]},
                     {"name": "a", "songIds": ["s1"] * 501}):
            self.assertEqual(bob.post_json("/api/playlist/create", body).status, 400)
        self.assertEqual(bob.post_json("/api/playlist/remove", {"id": "pl1", "positions": [-1]}).status, 400)
        self.assertEqual(bob.post_json("/api/playlist/remove", {"id": "pl1", "positions": [True]}).status, 400)

    def test_the_owner_changes_the_order(self):
        bob = self.client("bob", "pw2")
        pid = bob.post_json("/api/playlist/create", {"name": "Compil", "songIds": ["s1", "s3", "s4"]}).json()["playlist"]["id"]
        order = [{"position": 0}, {"position": 2}, {"position": 1}]                # le dernier remonte d'un cran
        self.assertEqual(bob.post_json("/api/playlist/reorder", {"id": pid, "order": order}).status, 200)
        self.assertEqual(self.subsonic.playlists[pid]["songs"], ["s1", "s4", "s3"])
        self.assertEqual(self.subsonic.posts["updatePlaylist"], 1)                   # longue liste : dans le corps
        order = [{"position": 2}, {"position": 0}, {"position": 1}]
        bob.post_json("/api/playlist/reorder", {"id": pid, "order": order})
        self.assertEqual([s["id"] for s in bob.get("/api/playlist?id=" + pid).json()["songs"]], ["s3", "s1", "s4"])
        unchanged = self.subsonic.calls["updatePlaylist"]
        bob.post_json("/api/playlist/reorder", {"id": pid, "order": [{"position": i} for i in range(3)]})
        self.assertEqual(self.subsonic.calls["updatePlaylist"], unchanged)          # même ordre : rien à écrire

    def test_a_song_listed_twice_keeps_both_places(self):
        bob = self.client("bob", "pw2")
        pid = bob.post_json("/api/playlist/create", {"name": "Bis", "songIds": ["s1", "s3", "s1"]}).json()["playlist"]["id"]
        bob.post_json("/api/playlist/reorder", {"id": pid, "order": [{"position": 1}, {"position": 0}, {"position": 2}]})
        self.assertEqual(self.subsonic.playlists[pid]["songs"], ["s3", "s1", "s1"])

    def test_order_from_an_old_page_or_someone_else_is_refused(self):
        bob, alice = self.client("bob", "pw2"), self.client("alice", "secret")
        pid = bob.post_json("/api/playlist/create", {"name": "À tous", "songIds": ["s1", "s3"], "community": True}).json()["playlist"]["id"]
        swap = {"id": pid, "order": [{"position": 1}, {"position": 0}]}
        refused = alice.post_json("/api/playlist/reorder", swap)                    # communautaire : ajouter oui, réordonner non
        self.assertEqual((refused.status, refused.json()["error"]), (400, "playlist.not_owner"))
        alice.post_json("/api/playlist/add", {"id": pid, "songIds": ["s4"]})       # ajouté pendant que bob avait la page
        stale = bob.post_json("/api/playlist/reorder", swap)
        self.assertEqual((stale.status, stale.json()["error"]), (400, "playlist.changed"))
        for order in ([{"position": 0}, {"position": 0}, {"position": 1}], [{"position": 0}, {"position": 1}, {"position": 5}]):
            self.assertEqual(bob.post_json("/api/playlist/reorder", {"id": pid, "order": order}).json()["error"],
                             "playlist.changed", order)
        self.assertEqual(self.subsonic.playlists[pid]["songs"], ["s1", "s3", "s4"])
        for order in ("x", [{"position": -1}], [{"position": True}], [{"extId": 0}], [{"position": 0, "extId": 1}],
                      [{"other": 1}], [{"position": 0}] * 5001):
            self.assertEqual(bob.post_json("/api/playlist/reorder", {"id": pid, "order": order}).status, 400)


class CommunityPlaylistTest(WebAppTestCase):
    """Playlist communautaire : le site écrit avec le jeton du créateur, et garde qui a ajouté chaque titre."""

    def setUp(self):
        super().setUp()
        self.bob = self.client("bob", "pw2")
        self.alice = self.client("alice", "secret")
        self.created = self.bob.post_json("/api/playlist/create", {"name": "À tous", "songIds": ["s1"], "community": True}).json()["playlist"]
        self.id = self.created["id"]

    def authors(self, client):
        return [(s["id"], s["addedBy"]) for s in client.get("/api/playlist?id=" + self.id).json()["songs"]]

    def test_creation_makes_it_public_and_open_to_all(self):
        self.assertEqual((self.created["community"], self.created["public"], self.created["canAdd"]), (True, True, True))
        self.assertTrue(self.subsonic.playlists[self.id]["public"])
        seen = self.alice.get("/api/playlists").json()["playlists"]
        self.assertEqual([(p["name"], p["mine"], p["community"], p["canAdd"]) for p in seen], [("À tous", False, True, True)])

    def test_added_by_someone_else_is_written_as_the_owner_but_credited_to_them(self):
        self.assertEqual(self.alice.post_json("/api/playlist/add", {"id": self.id, "songIds": ["s3"]}).status, 200)
        self.assertEqual(self.subsonic.playlists[self.id]["owner"], "bob")
        self.assertEqual(self.subsonic.playlists[self.id]["songs"], ["s1", "s3"])
        self.assertEqual(self.authors(self.alice), [("s1", "bob"), ("s3", "alice")])
        self.assertEqual(self.authors(self.bob), [("s1", "bob"), ("s3", "alice")])

    def test_a_song_is_added_once_to_a_community_playlist(self):
        added = self.alice.post_json("/api/playlist/add", {"id": self.id, "songIds": ["s1", "s3", "s3"]}).json()
        self.assertEqual(added["added"], 1)                                        # s1 y est déjà, s3 en double
        self.assertEqual(self.alice.post_json("/api/playlist/add", {"id": self.id, "songIds": ["s1"]}).json()["added"], 0)
        self.assertEqual(self.subsonic.playlists[self.id]["songs"], ["s1", "s3"])
        self.assertEqual(self.authors(self.bob), [("s1", "bob"), ("s3", "alice")])

    def test_songs_added_outside_the_site_are_credited_to_the_owner(self):
        self.subsonic.playlists[self.id]["songs"].append("s4")                    # par une appli de téléphone
        self.assertEqual(self.authors(self.alice)[-1], ("s4", "bob"))

    def test_not_community_means_owner_only(self):
        private = self.bob.post_json("/api/playlist/create", {"name": "Perso"}).json()["playlist"]["id"]
        self.assertEqual(self.bob.post_json("/api/playlist/community", {"id": private, "on": True}).status, 200)
        self.assertEqual(self.bob.post_json("/api/playlist/community", {"id": private, "on": False}).status, 200)
        refused = self.alice.post_json("/api/playlist/add", {"id": private, "songIds": ["s3"]})
        self.assertEqual((refused.status, refused.json()["error"]), (400, "playlist.not_community"))
        self.assertEqual(self.subsonic.playlists[private]["songs"], [])
        self.bob.post_json("/api/playlist/community", {"id": private, "on": True})
        self.assertEqual(self.alice.post_json("/api/playlist/add", {"id": private, "songIds": ["s3"]}).status, 200)

    def test_only_the_owner_changes_the_setting(self):
        refused = self.alice.post_json("/api/playlist/community", {"id": self.id, "on": False})
        self.assertEqual((refused.status, refused.json()["error"]), (400, "playlist.not_owner"))
        self.assertTrue(self.alice.get("/api/playlists").json()["playlists"][0]["community"])
        self.assertEqual(self.alice.post_json("/api/playlist/community", {"id": self.id, "on": "oui"}).status, 400)

    def test_public_playlist_that_is_not_community_stays_read_only(self):
        self.subsonic.playlists["pl9"] = {"id": "pl9", "name": "Années 70", "owner": "bob", "public": True, "songs": []}
        card = [p for p in self.alice.get("/api/playlists").json()["playlists"] if p["id"] == "pl9"][0]
        self.assertEqual((card["community"], card["canAdd"]), (False, False))
        self.assertEqual(self.alice.post_json("/api/playlist/add", {"id": "pl9", "songIds": ["s3"]}).status, 400)

    def test_others_remove_only_what_they_added(self):
        self.alice.post_json("/api/playlist/add", {"id": self.id, "songIds": ["s3"]})
        refused = self.alice.post_json("/api/playlist/remove", {"id": self.id, "positions": [0]})
        self.assertEqual((refused.status, refused.json()["error"]), (400, "playlist.not_yours"))
        self.assertEqual(self.alice.post_json("/api/playlist/remove", {"id": self.id, "positions": [9]}).status, 400)
        self.assertEqual(self.alice.post_json("/api/playlist/remove", {"id": self.id, "positions": [1]}).status, 200)
        self.assertEqual(self.subsonic.playlists[self.id]["songs"], ["s1"])
        self.alice.post_json("/api/playlist/add", {"id": self.id, "songIds": ["s4"]})
        self.assertEqual(self.bob.post_json("/api/playlist/remove", {"id": self.id, "positions": [1, 0]}).status, 200)
        self.assertEqual(self.subsonic.playlists[self.id]["songs"], [])
        self.assertEqual(self.app.playlists.community.authors(self.id), {})        # plus de trace des titres retirés

    def test_owner_who_changed_password_must_reconnect(self):
        self.subsonic.users["bob"] = "nouveau"                                      # le jeton gardé ne vaut plus rien
        refused = self.alice.post_json("/api/playlist/add", {"id": self.id, "songIds": ["s3"]})
        self.assertEqual((refused.status, refused.json()["error"]), (400, "playlist.owner_unavailable"))
        self.client("bob", "nouveau")                                               # reconnexion : jeton renouvelé
        self.assertEqual(self.alice.post_json("/api/playlist/add", {"id": self.id, "songIds": ["s3"]}).status, 200)

    def test_delete_forgets_everything_and_validation(self):
        self.alice.post_json("/api/playlist/add", {"id": self.id, "songIds": ["s3"]})
        self.bob.post_json("/api/playlist/delete", {"id": self.id})
        self.assertEqual((self.app.playlists.community.community_ids(), self.app.playlists.community.authors(self.id)),
                         (set(), {}))
        self.assertEqual(self.bob.post_json("/api/playlist/create", {"name": "x", "community": "oui"}).status, 400)

    def test_other_users_cannot_rename_or_delete(self):
        self.assertEqual(self.alice.post_json("/api/playlist/rename", {"id": self.id, "name": "Mienne"}).status, 502)
        self.assertEqual(self.alice.post_json("/api/playlist/delete", {"id": self.id}).status, 502)
        self.assertIn(self.id, self.app.playlists.community.community_ids())


class ListeningHttpTest(WebAppTestCase):
    def test_scrobble_now_playing_then_counted(self):
        bob = self.client("bob", "pw2")
        bob.post_json("/api/scrobble", {"id": "s4", "submission": False})
        entries = self.client("alice", "secret").get("/api/now-playing").json()["entries"]
        self.assertEqual([(e["username"], e["title"]) for e in entries], [("bob", "Army of Me")])
        bob.post_json("/api/scrobble", {"id": "s4", "submission": True})
        self.assertEqual(self.subsonic.scrobbles, [("bob", "s4", False), ("bob", "s4", True)])
        self.assertEqual(bob.post_json("/api/scrobble", {"id": "s4", "submission": "true"}).status, 200)
        self.assertEqual(self.subsonic.scrobbles[-1], ("bob", "s4", False))      # seul true compte une écoute

    def test_bookmarks_made_by_phone_apps_are_found_and_resumed(self):
        self.subsonic.bookmarks[("bob", "s2")] = (95000, "fin de trajet", 1)      # posé par une appli de téléphone
        bob = self.client("bob", "pw2")
        bob.post_json("/api/bookmark/save", {"id": "s4", "position": 61.5, "comment": "à reprendre"})
        bookmarks = bob.get("/api/bookmarks").json()["bookmarks"]
        self.assertEqual([(b["song"]["title"], b["position"], b["comment"]) for b in bookmarks],
                         [("Army of Me", 61.5, "à reprendre"), ("Knowing Me", 95.0, "fin de trajet")])
        self.assertEqual(self.client("alice", "secret").get("/api/bookmarks").json()["bookmarks"], [])
        bob.post_json("/api/bookmark/delete", {"id": "s2"})
        self.assertEqual(len(bob.get("/api/bookmarks").json()["bookmarks"]), 1)
        for position in (-1, "10", None, True):
            self.assertEqual(bob.post_json("/api/bookmark/save", {"id": "s4", "position": position}).status, 400)

    def test_play_queue_is_shared_with_other_apps(self):
        bob = self.client("bob", "pw2")
        self.assertEqual(bob.get("/api/play-queue").json()["songs"], [])
        bob.post_json("/api/play-queue/save", {"ids": ["s1", "s2", "s4"], "current": "s2", "position": 42})
        self.assertEqual(self.subsonic.play_queues["bob"], {"ids": ["s1", "s2", "s4"], "current": "s2", "position": 42000})
        queue = bob.get("/api/play-queue").json()
        self.assertEqual(([s["title"] for s in queue["songs"]], queue["index"], queue["position"]),
                         (["Dancing Queen", "Knowing Me", "Army of Me"], 1, 42.0))
        self.assertEqual(bob.post_json("/api/play-queue/save", {"ids": "s1"}).status, 400)

    def test_play_queue_survives_logout_and_is_private(self):
        bob = self.client("bob", "pw2")
        self.assertEqual(bob.post_json("/api/play-queue/save", {
            "ids": ["s2", "s1", "s2"], "current": "s1", "position": 12.375}).status, 200)
        bob.post_json("/api/logout", {})
        self.assertEqual(bob.get("/api/play-queue").status, 401)
        self.assertEqual(bob.post_json("/api/play-queue/save", {"ids": ["s4"]}).status, 401)
        alice = self.client("alice", "secret")
        self.assertEqual(alice.get("/api/play-queue").json()["songs"], [])
        queue = self.client("bob", "pw2").get("/api/play-queue").json()
        self.assertEqual(([s["id"] for s in queue["songs"]], queue["index"], queue["position"]),
                         (["s2", "s1", "s2"], 1, 12.375))

    def test_large_queue_is_sent_as_post_without_truncation(self):
        bob = self.client("bob", "pw2")
        ids = ["s1", "s2"] * 1500
        self.assertEqual(bob.post_json("/api/play-queue/save", {
            "ids": ids, "current": "s2", "position": 9}).status, 200)
        self.assertEqual(self.subsonic.play_queues["bob"]["ids"], ids)
        self.assertEqual(self.subsonic.posts["savePlayQueue"], 1)

    def test_play_queue_validation_and_csrf(self):
        bob = self.client("bob", "pw2")
        for body in ({"ids": "s1"}, {"ids": ["s1"] * 5001}, {"ids": ["s1"], "position": -1},
                     {"ids": ["s1"], "position": True}, {"ids": ["s1"], "position": float("inf")}):
            with self.subTest(body_keys=list(body)):
                self.assertEqual(bob.post_json("/api/play-queue/save", body).status, 400)
        self.assertEqual(bob.post_json("/api/play-queue/save", {"ids": ["s1"]}, csrf=False).status, 403)


class ProfileHttpTest(WebAppTestCase):
    def test_avatar_from_site_then_subsonic_then_nothing(self):
        bob, alice = self.client("bob", "pw2"), self.client("alice", "secret")
        response = alice.get("/api/avatar?user=bob")                       # photo choisie dans Subsonic
        self.assertEqual((response.status, response.headers["content-type"], response.body), (200, "image/png", PNG))
        self.assertEqual(alice.get("/api/avatar?user=alice").status, 404)  # rien : la page met l'initiale
        jpeg = b"\xff\xd8\xff\xe0" + b"0" * 100
        upload = alice.post_json("/api/avatar/upload", {"image": "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()})
        self.assertEqual(upload.status, 200)
        response = bob.get("/api/avatar?user=alice")
        self.assertEqual((response.headers["content-type"], response.body), ("image/jpeg", jpeg))
        self.assertIn("alice", bob.get("/api/avatars").json()["versions"])
        alice.post_json("/api/avatar/delete", {})
        self.assertEqual(bob.get("/api/avatar?user=alice").status, 404)

    def test_avatar_validation(self):
        alice = self.client("alice", "secret")
        big = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * (300 * 1024)).decode()
        for image, key in (("pas une image", "avatar.bad_format"), ("data:x;base64,%%%", "avatar.bad_format"),
                           ("data:image/png;base64," + base64.b64encode(b"<svg>").decode(), "avatar.bad_type"),
                           ("data:image/png;base64," + big, "avatar.too_big")):
            response = alice.post_json("/api/avatar/upload", {"image": image})
            self.assertEqual((response.status, response.json()["error"]), (400, key))
        self.assertIsNone(image_type(b"RIFF0000WAVE"))                     # RIFF sans WEBP : refusé
        self.assertEqual(image_type(b"GIF89a..."), "image/gif")             # Gravatar peut en renvoyer

    def test_versions_list_everyone_with_a_photo(self):
        bob, alice = self.client("bob", "pw2"), self.client("alice", "secret")
        versions = bob.get("/api/avatars").json()["versions"]
        self.assertEqual(set(versions), {"bob"})                           # photo Subsonic ; alice n'en a aucune
        self.assertTrue(versions["bob"].startswith("s"))
        self.subsonic.avatars["bob"] = PNG + b"autre"                      # changée dans Subsonic : relue après 1 h
        self.app.avatars.cache.forget("subsonic-avatar")
        self.assertNotEqual(bob.get("/api/avatars").json()["versions"]["bob"], versions["bob"])

    def test_account_page_says_where_the_photo_comes_from(self):
        bob, alice = self.client("bob", "pw2"), self.client("alice", "secret")
        account = alice.get("/api/account").json()
        self.assertEqual((account["source"], account["email"]), (None, "Alice@Exemple.fr"))
        self.assertEqual(account["subsonicSettings"], self.subsonic.url + "/personalSettings.view")
        self.assertEqual((bob.get("/api/account").json()["source"], bob.get("/api/account").json()["email"]),
                         ("subsonic", ""))
        alice.post_json("/api/avatar/gravatar", {})
        self.assertEqual(alice.get("/api/account").json()["source"], "site")

    def test_gravatar_photo_is_copied_on_the_site(self):
        bob, alice = self.client("bob", "pw2"), self.client("alice", "secret")
        response = alice.post_json("/api/avatar/gravatar", {"email": ""})   # vide : l'adresse du compte Subsonic
        self.assertEqual(response.status, 200)
        self.assertEqual(self.app.avatars.gravatar.asked, ["Alice@Exemple.fr"])
        self.assertEqual(bob.get("/api/avatar?user=alice").body, PNG + b"gravatar")
        self.assertIn("alice", bob.get("/api/avatars").json()["versions"])
        for client, body, key in ((bob, {}, "avatar.no_email"),                    # bob : aucune adresse dans Subsonic
                                  (bob, {"email": "pas-une-adresse"}, "avatar.bad_email"),
                                  (bob, {"email": "bob@exemple.fr"}, "avatar.gravatar_none")):
            response = client.post_json("/api/avatar/gravatar", body)
            self.assertEqual((response.status, response.json()["error"]), (400, key))
        self.app.avatars.gravatar.down = True
        response = bob.post_json("/api/avatar/gravatar", {"email": "alice@exemple.fr"})
        self.assertEqual(response.json()["error"], "avatar.gravatar_unreachable")
        self.assertEqual(bob.get("/api/avatar?user=bob").body, PNG)         # rien changé : toujours celle de Subsonic

    def test_gravatar_address_is_the_sha256_of_the_trimmed_lowercase_email(self):
        self.assertEqual(gravatar_url(" MyEmailAddress@example.com "), "https://gravatar.com/avatar/" +
                         hashlib.sha256(b"myemailaddress@example.com").hexdigest() + "?s=256&d=404")

    def test_internet_radios_only_relay_listed_stations(self):
        bob = self.client("bob", "pw2")
        stations = bob.get("/api/radios").json()["stations"]
        self.assertEqual([(s["id"], s["name"]) for s in stations], [("1", "FIP")])      # ftp:// écarté
        response = bob.get("/api/radios/stream?id=1")
        self.assertEqual((response.status, response.headers["content-type"], len(response.body)), (200, "audio/mpeg", 10240))
        self.assertEqual(bob.get("/api/radios/stream?id=2").status, 404)
        self.assertEqual(bob.get("/api/radios/stream?id=http://ailleurs").status, 400)
        self.assertEqual(self.client().get("/api/radios").status, 401)


if __name__ == "__main__":
    unittest.main()
