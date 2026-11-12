"""Pertinence des versions, liens Discogs, limites de recherche, cache et protection du parcours HTTP."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from pimedia.webapp.discogs_entities import DiscogsVideo
from pimedia.webapp.entities import ImportedTrack
from pimedia.webapp.extmusic import ExtMusicError
from pimedia.webapp.youtube_matching import match_score, search_query
from pimedia.webapp.youtube_versions import MAX_VERSIONS, YouTubeVersions, ranked_versions
from tests.fake_discogs import FakeDiscogs
from tests.support import youtube_music_down
from tests.test_podcasts import FakeHttp
from tests.test_webapp_ext import KEYS, VIDEOS, YOUTUBE
from tests.webapp_support import WebAppTestCase


def video(title="Daft Punk - One More Time (Official Audio)", artist="Daft Punk", duration=320, identity="abc123def45"):
    return dict(id="yt-" + identity, youtubeId=identity, ext="youtube", title=title, artist=artist, duration=duration, album="")


class YouTubeMatchingTest(unittest.TestCase):
    track = ImportedTrack("One More Time", "Daft Punk", "Discovery", 320)

    def test_artist_can_be_in_metadata_or_credited_in_the_video_title(self):
        self.assertGreater(match_score(self.track, video()), 0)
        self.assertGreater(match_score(self.track, video("One More Time", "Daft Punk - Topic")), 0)
        self.assertGreater(match_score(self.track, video(artist="Une chaîne de disques")), 0)
        self.assertGreater(match_score(self.track, video("Daft Punk – One More Time [HD]", artist="Upload")), 0)

    def test_unrelated_title_or_artist_is_never_saved_by_popularity(self):
        for item in (video("One More Time", "Another Artist"), video("Another song"),
                     dict(video("Another song"), playedHere=999999), video("Another Artist - One More Time"),
                     video("One More Time", "Daft Punk Tribute Band")):
            self.assertEqual(match_score(self.track, item), 0)
        self.assertGreater(match_score(self.track, video("One More Time", "Daft Punk, Pharrell Williams")), 0)

    def test_partial_artist_names_and_short_numeric_titles_are_not_fuzzy_matches(self):
        self.assertEqual(match_score(ImportedTrack("John", "Pop"), video("John", "Popertelli", 0)), 0)
        track = ImportedTrack("241", "The Jaffa Kid")
        for title in ("The Jaffa Kid - 242", "The Jaffa Kid - 2410", "The Jaffa Kid - 241 live"):
            self.assertEqual(match_score(track, video(title, "Upload", 0)), 0)
        self.assertGreater(match_score(track, video("The Jaffa Kid - 241", "Upload", 0)), 0)

    def test_unicode_and_punctuation_follow_shared_musical_normalization(self):
        track = ImportedTrack("Dissidænce", "Œdipe", duration=240)
        self.assertGreater(match_score(track, video("Oedipe - Dissidaence", "Upload", 244)), 0)

    def test_previews_full_albums_and_different_durations_are_excluded(self):
        for item in (video(duration=30), video(duration=3600), video("Daft Punk - One More Time (Preview)"),
                     video("Daft Punk - One More Time Full Album", duration=0)):
            self.assertEqual(match_score(self.track, item, linked=True), 0)

    def test_requested_remix_stays_distinct_from_other_versions(self):
        track = ImportedTrack("A Very Long Track Name (Original Mix)", "Artist", duration=300)
        for title in ("A Very Long Track Name (Radio Mix)", "A Very Long Track Name", "A Very Long Track Name (Original Mix) (Live)"):
            self.assertEqual(match_score(track, video(title, "Artist", 300)), 0)
        self.assertGreater(match_score(track, video("Artist - A Very Long Track Name (Original Mix) [Official Audio]", "Upload", 305)), 0)
        self.assertIn("Original Mix", search_query(track))

    def test_at_most_three_relevant_unique_choices_out_of_fifty_results(self):
        items = [video("Another song %d" % i, identity="noise%d" % i) for i in range(45)]
        good = [video(identity="valid%d" % i) for i in range(5)]
        results = ranked_versions(self.track, items + good + good)
        self.assertEqual(len(results), MAX_VERSIONS)
        self.assertEqual(len({v["youtubeId"] for v in results}), MAX_VERSIONS)
        self.assertTrue(all(v["youtubeId"].startswith("valid") for v in results))

    def test_discogs_typo_with_known_label_and_catalogue_annotations(self):
        track = ImportedTrack("Endless Pavments", "Zmatsutsi", "Hooked Up", 375)
        labels = ("Macadam Mambo",)
        linked = video('Zmatsutsi "Endless Pavements" - Macadam Mambo [MMLP1001]', "Macadam Mambo", 377)
        self.assertGreater(match_score(track, linked, labels=labels), 0)
        self.assertGreater(match_score(track, video("Zmatsutsi - Endless Pavement [MMLP1001]", "Upload", 376)), 0)
        self.assertEqual(match_score(track, video("Zmatsutsi - Hooked Up [MMLP1001]", "Upload", 380), labels=labels), 0)

    def test_unknown_suffixes_and_musical_numbers_are_kept(self):
        track = ImportedTrack("A Very Long Song", "Artist", duration=300)
        for title in ("Artist - A Very Long Song [PART2]", "Artist - A Very Long Song [REMIX2]",
                      "Artist - A Very Long Song - Unknown label"):
            self.assertEqual(match_score(track, video(title, "Upload", 300), labels=("Known label",)), 0)
        self.assertGreater(match_score(track, video("Artist - A Very Long Song [ABC123]", "Upload", 300)), 0)

    def test_more_than_one_spelling_difference_needs_a_close_known_duration(self):
        track = ImportedTrack("Endless Pavments", "Zmatsutsi", duration=375)
        self.assertEqual(match_score(track, video("Zmatsutsi - Endless Pavement", "Upload", 0)), 0)
        self.assertEqual(match_score(track, video("Zmatsutsi - Endless Pavement", "Upload", 400)), 0)


class YouTubeVersionsTest(unittest.TestCase):
    def setUp(self):
        self.external = Mock()
        self.external.linked.return_value = []
        self.external.search.return_value = []
        self.service = YouTubeVersions(self.external)
        self.track = ImportedTrack("Sladjana", "Muslim Disco Club", duration=343)
        self.user = SimpleNamespace(username="listener")
        self.link = DiscogsVideo("linked12345", "Muslim Disco Club - Sladjana", 343)

    def test_matching_discogs_video_is_verified_without_a_text_search(self):
        self.external.linked.return_value = [video(self.link.title, "Upload", 343, self.link.youtube_id)]
        result = self.service.find(self.user, self.track, [self.link, self.link])
        self.assertEqual(result.items[0]["discoverySource"], "discogs")
        self.external.search.assert_not_called()

    def test_label_annotations_and_typo_work_for_the_discogs_link_before_searching(self):
        track = ImportedTrack("Endless Pavments", "Zmatsutsi", "Hooked Up", 375)
        link = DiscogsVideo("7AZo3JiA0Yc", 'Zmatsutsi "Endless Pavements" - Macadam Mambo [MMLP1001]', 377)
        self.external.linked.return_value = [video(link.title, "Macadam Mambo", 377, link.youtube_id)]
        result = self.service.find(self.user, track, [link], labels=("Macadam Mambo",))
        self.assertEqual(result.items[0]["youtubeId"], link.youtube_id)
        self.external.search.assert_not_called()

    def test_replaced_or_mislabelled_link_cannot_bypass_matching(self):
        self.external.linked.return_value = [video("Another artist - Another song", "Other", 343, self.link.youtube_id)]
        self.assertEqual(self.service.find(self.user, self.track, [self.link]).items, ())
        self.external.search.assert_called_once_with(self.user, "youtube", "Muslim Disco Club Sladjana", allow_versions=True)

    def test_unrelated_discogs_link_is_not_even_looked_up(self):
        self.service.find(self.user, self.track, [DiscogsVideo("unrelated12", "Artist - Full Album", 3600)])
        self.external.linked.assert_not_called()
        self.external.search.assert_called_once()

    def test_link_failure_can_use_search_but_quota_failure_stops_immediately(self):
        self.external.linked.side_effect = ExtMusicError("ext.unreachable")
        result = self.service.find(self.user, self.track, [self.link])
        self.assertEqual(result.warning, "discovery.youtube_links_unavailable")
        self.external.reset_mock()
        self.external.linked.side_effect = ExtMusicError("ext.too_many_searches")
        with self.assertRaisesRegex(ExtMusicError, "ext.too_many_searches"):
            self.service.find(self.user, self.track, [self.link])
        self.external.search.assert_not_called()


class YouTubeVersionsHttpTest(WebAppTestCase):
    environ = dict(KEYS, PI_MEDIA_WEB_DISCOGS_API_KEY="discogs-test")

    def setUp(self):
        super().setUp()
        self.app.discogs.http = FakeDiscogs()
        self.app.discogs.sleep = lambda seconds: None
        self.http = FakeHttp({"youtube/v3/videos": VIDEOS, "youtube/v3/search": YOUTUBE})
        self.app.extmusic.youtube.http = self.http
        self.app.extmusic.youtube.music = youtube_music_down()
        self.body = dict(release="103", track=ImportedTrack("One More Time", "Daft Punk", duration=320).to_api())

    def test_session_csrf_and_track_membership_are_checked(self):
        self.assertEqual(self.client().post_json("/api/labels/versions", self.body).status, 401)
        bob = self.client("bob", "pw2")
        self.assertEqual(bob.post_json("/api/labels/versions", self.body, csrf=False).status, 403)
        invalid = dict(self.body, track=dict(self.body["track"], title="Another song"))
        self.assertEqual(bob.post_json("/api/labels/versions", invalid).status, 400)
        self.assertEqual(bob.post_json("/api/labels/versions", dict(self.body, release="invalid")).status, 400)
        self.assertEqual(self.http.calls, [])

    def test_linked_metadata_and_repeated_selection_share_the_existing_video_cache(self):
        bob = self.client("bob", "pw2")
        first = bob.post_json("/api/labels/versions", self.body)
        self.assertEqual(first.status, 200)
        self.assertEqual(first.json()["items"][0]["discoverySource"], "discogs")
        calls = len(self.http.calls)
        self.assertGreater(calls, 0)
        again = bob.post_json("/api/labels/versions", self.body)
        self.assertEqual(again.json(), first.json())
        self.assertEqual(len(self.http.calls), calls)
        self.assertFalse(any("/search?" in url for url, _ in self.http.calls))
        self.assertNotIn(b"secret", first.body)

    def test_search_filters_irrelevant_results_instead_of_returning_the_whole_youtube_list(self):
        bob = self.client("bob", "pw2")
        body = dict(release="104", track=ImportedTrack("Rare", "Artiste discret").to_api())
        response = bob.post_json("/api/labels/versions", body)
        self.assertEqual(response.status, 200)
        self.assertEqual(response.json()["items"], [])
        self.assertEqual(bob.post_json("/api/labels/versions", body).json(), response.json())
        self.assertEqual(sum("/search?" in url for url, _ in self.http.calls), 1)

    def test_linked_videos_respect_refusals_and_search_budget(self):
        user = SimpleNamespace(username="listener")
        self.app.extmusic.videos.add("abc123def45", "101")
        self.assertEqual(self.app.extmusic.linked(user, ["abc123def45"]), [])
        self.assertEqual(self.http.calls, [])
        self.app.extmusic.budget.limit = 0
        with self.assertRaisesRegex(ExtMusicError, "ext.too_many_searches"):
            self.app.extmusic.linked(user, ["otherone123"])
        self.assertEqual(self.http.calls, [])
