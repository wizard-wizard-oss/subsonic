"""Préparation des recherches de paroles et choix des résultats, sans aucun accès réseau."""
import unittest
import urllib.parse
from unittest.mock import Mock

from pimedia.shared.external import LyricsFinder, filter_lyrics_candidates, lyrics_search_pairs


def lyric(artist="Guy Marchand", title="Destinée", duration=275, text="Paroles du bon morceau"):
    return {"artistName": artist, "trackName": title, "duration": duration,
            "plainLyrics": text, "syncedLyrics": "[00:01.00]" + text}


class LyricsSites:
    """Réponses HTTP préparées par adresse et paramètres, indépendamment des règles de recherche."""
    def __init__(self):
        self.answers, self.urls = {}, []

    def answer(self, path, params, body):
        self.answers[(path, tuple(sorted(params.items())))] = body

    def try_get(self, url, timeout=8):
        self.urls.append(url)
        address = urllib.parse.urlsplit(url)
        params = dict(urllib.parse.parse_qsl(address.query))
        return self.answers.get((address.path, tuple(sorted(params.items()))))


class LyricsSearchPairsTest(unittest.TestCase):
    def test_original_and_real_artist_from_a_channel_title(self):
        pairs = lyrics_search_pairs("AnyMusics", "Destinée ; Guy Marchand")
        self.assertEqual(pairs[0], ("Destinée ; Guy Marchand", "AnyMusics"))
        self.assertIn(("Destinée", "Guy Marchand"), pairs)

    def test_artist_first_and_title_first_with_common_video_separators(self):
        for separator in (" ; ", ";", " - ", " – ", " — ", " | "):
            for title in ("Guy Marchand" + separator + "Destinée", "Destinée" + separator + "Guy Marchand"):
                with self.subTest(title=title):
                    self.assertIn(("Destinée", "Guy Marchand"), lyrics_search_pairs("AnyMusics", title))

    def test_short_subtitle_variant_keeps_the_original_first(self):
        for title in ("Delirium (Ma chérie je t'écris...)", "Delirium [Ma chérie je t’écris…]"):
            pairs = lyrics_search_pairs("Guy Marchand", title)
            self.assertEqual(pairs[0], (title, "Guy Marchand"))
            self.assertIn(("Delirium", "Guy Marchand"), pairs)

    def test_combined_artist_credit_and_subtitle(self):
        self.assertIn(("Delirium", "Guy Marchand"), lyrics_search_pairs(
            "AnyMusics", "Guy Marchand - Delirium (Ma chérie je t'écris...)"))

    def test_version_suffix_is_cleaned_after_separating_the_artist(self):
        self.assertIn(("Delirium", "Guy Marchand"), lyrics_search_pairs(
            "AnyMusics", "Guy Marchand - Delirium - Live"))

    def test_preserves_hyphenated_names_and_never_queries_an_empty_title(self):
        self.assertEqual(lyrics_search_pairs("Jean-Louis Murat", "L'Au-delà"), [("L'Au-delà", "Jean-Louis Murat")])
        for title in ("(Interlude)", "; Guy Marchand", "Delirium ;"):
            self.assertTrue(all(song and artist for song, artist in lyrics_search_pairs("Guy Marchand", title)))


class LyricsFinderTest(unittest.TestCase):
    def setUp(self):
        self.sites = LyricsSites()
        self.subsonic = Mock(return_value="")
        self.finder = LyricsFinder(self.sites, self.subsonic)

    def test_search_filters_neighbouring_titles_and_names_before_choosing(self):
        correct = lyric()
        self.sites.answer("/api/search", {"track_name": "Destinée", "artist_name": "Guy Marchand"},
                          [lyric(artist="Autre artiste", text="Mauvais artiste"),
                           lyric(title="Une autre destinée", text="Mauvais titre"), correct])
        found = self.finder.find("AnyMusics", "Destinée ; Guy Marchand", duration=275)
        self.assertEqual(found, {"synced": correct["syncedLyrics"], "plain": correct["plainLyrics"], "src": "LRCLIB"})
        self.subsonic.assert_not_called()

    def test_literal_title_is_preferred_over_shorter_variants(self):
        title = "Delirium (Ma chérie je t'écris...)"
        correct = lyric(title=title, duration=180)
        self.sites.answer("/api/get", {"artist_name": "Guy Marchand", "track_name": title}, correct)
        self.sites.answer("/api/get", {"artist_name": "Guy Marchand", "track_name": "Delirium"},
                          lyric(title="Delirium", text="Autre version"))
        self.assertEqual(self.finder.find("Guy Marchand", title)["plain"], correct["plainLyrics"])
        self.assertFalse(any("track_name=Delirium&" in url or url.endswith("track_name=Delirium")
                             for url in self.sites.urls))

    def test_free_search_never_accepts_an_unrelated_song(self):
        self.sites.answer("/api/search", {"q": "Destinée Guy Marchand"},
                          [lyric(artist="Autre artiste"), lyric(title="Une autre destinée")])
        self.assertEqual(self.finder.find("Guy Marchand", "Destinée"), {})

    def test_short_catalogue_title_is_also_used_for_lyrics_ovh(self):
        self.sites.answer("/v1/Guy%20Marchand/Delirium", {}, {"lyrics": "Paroles de secours"})
        found = self.finder.find("Guy Marchand", "Delirium (Ma chérie je t'écris...)")
        self.assertEqual(found, {"synced": "", "plain": "Paroles de secours", "src": "lyrics.ovh"})
        self.subsonic.assert_not_called()

    def test_duration_still_selects_the_closest_matching_recording(self):
        correct = lyric(duration=275)
        self.sites.answer("/api/search", {"track_name": "Destinée", "artist_name": "Guy Marchand"},
                          [lyric(duration=193, text="Version courte"), correct])
        self.assertEqual(self.finder.find("AnyMusics", "Destinée ; Guy Marchand", duration=274)["plain"],
                         correct["plainLyrics"])


class LyricsCandidateFilterTest(unittest.TestCase):
    def test_shared_name_normalization_and_malformed_results(self):
        correct = lyric(artist="GUY MARCHAND", title="Destinee")
        invalid = [None, "wrong", {}, {"trackName": "Destinée"}, lyric(artist="Autre artiste"),
                   lyric(title="Autre destinée")]
        self.assertEqual(filter_lyrics_candidates(invalid + [correct], [("Destinée", "Guy Marchand")]), [correct])

    def test_ligatures_use_the_shared_normalization(self):
        correct = lyric(artist="Œdipe", title="Cœur")
        self.assertEqual(filter_lyrics_candidates([correct], [("Coeur", "Oedipe")]), [correct])
