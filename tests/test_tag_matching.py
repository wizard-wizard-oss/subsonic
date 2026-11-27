"""Appariement conservateur : preuves musicales, désordre, disques et ambiguïtés globales."""
import unittest

from pimedia.webapp.tags.entities import TagTrack, TagValues
from pimedia.webapp.tags.matching import propose_mapping, rank_candidates
from pimedia.webapp.tags.sources import SourceCandidate, SourceTrack


def local(title="", track="", disc="", duration=0):
    return TagTrack("local", "flac", True, "", TagValues(title=title, track=track, disc=disc), duration)


def source(title="", track=None, disc=None, duration=None):
    return SourceTrack("", track, disc, title, "", duration)


class CandidateRankingTest(unittest.TestCase):
    def candidate(self, identity, title, artist="Trentemøller", date="2026"):
        return SourceCandidate(identity, title, artist, date, "", "CD", 0, "")

    def test_current_self_titled_album_is_shown_before_old_eps_and_chronicles(self):
        candidates = (self.candidate("ep", "Trentemøller EP", date="2003"),
                      self.candidate("chronicles", "The Trentemøller Chronicles", date="2007"),
                      self.candidate("vinyl", "Trentemøller", date="2026-11-13"),
                      self.candidate("cd", "trentemøller", date="2026-11-13"))
        found = rank_candidates(candidates, "Trentemøller", "trentemøller", 2026)
        self.assertEqual([candidate.id for candidate in found], ["vinyl", "cd", "ep", "chronicles"])

    def test_album_year_disambiguates_editions_without_overriding_the_title(self):
        candidates = (self.candidate("old", "Album", date="2006"),
                      self.candidate("other", "Other", date="2026"),
                      self.candidate("new", "Album", date="2026-01-01"))
        found = rank_candidates(candidates, "Trentemøller", "Album", 2026)
        self.assertEqual([candidate.id for candidate in found], ["new", "old", "other"])

    def test_no_year_keeps_provider_order_between_equally_named_editions(self):
        candidates = (self.candidate("old", "Album", date="2006"), self.candidate("new", "Album", date="2026"))
        self.assertEqual(rank_candidates(candidates, "Trentemøller", "Album"), candidates)

    def test_matching_names_use_shared_normalization_and_preserve_original_labels(self):
        wrong = self.candidate("wrong", "Different", "Other")
        expected = self.candidate("expected", "Dissidænce!", "Dälek")
        found = rank_candidates((wrong, expected), "DALEK", "Dissidaence", "2026")
        self.assertIs(found[0], expected)
        self.assertEqual(expected.title, "Dissidænce!")


class TagMatchingTest(unittest.TestCase):
    def test_mapping_follows_evidence_when_source_order_is_reversed(self):
        tracks = [local("First", "1", "1", 60), local("Second", "2", "1", 120)]
        candidates = [source("Second", 2, 1, 120), source("First", 1, 1, 60)]
        self.assertEqual(propose_mapping(tracks, candidates), (1, 0))

    def test_same_count_or_order_never_proves_a_match(self):
        tracks = [local("Unknown", duration=60), local("Else", duration=120)]
        candidates = [source("Other", duration=60), source("Different", duration=120)]
        self.assertEqual(propose_mapping(tracks, candidates), (None, None))

    def test_numbers_and_durations_can_match_when_all_titles_are_missing(self):
        tracks = [local(track="2", disc="1", duration=120), local(track="1", disc="1", duration=60)]
        candidates = [source(track=1, disc=1, duration=63), source(track=2, disc=1, duration=117)]
        self.assertEqual(propose_mapping(tracks, candidates), (1, 0))

    def test_number_only_or_duration_only_is_insufficient(self):
        self.assertEqual(propose_mapping([local(track="1", disc="1")], [source(track=1, disc=1)]), (None,))
        self.assertEqual(propose_mapping([local(duration=60)], [source(duration=60)]), (None,))

    def test_known_disc_is_required_for_number_and_duration_proof(self):
        self.assertEqual(propose_mapping([local(track="1", duration=60)], [source(track=1, disc=1, duration=60)]), (None,))

    def test_disc_numbers_disambiguate_repeated_titles_across_discs(self):
        tracks = [local("Intro", "1", "2", 60), local("Intro", "1", "1", 60)]
        candidates = [source("Intro", 1, 1, 60), source("Intro", 1, 2, 60)]
        self.assertEqual(propose_mapping(tracks, candidates), (1, 0))

    def test_conflicting_discs_cannot_match_on_duration_and_track_number(self):
        self.assertEqual(propose_mapping([local(track="1", disc="2", duration=60)],
                                        [source(track=1, disc=1, duration=60)]), (None,))

    def test_unique_normalized_title_and_close_duration_can_repair_wrong_numbers(self):
        self.assertEqual(propose_mapping([local("Dissidænce!", "5", "1", 60)],
                                        [source("DISSIDAENCE", 2, 1, 62)]), (0,))

    def test_unique_title_with_missing_duration_can_match_without_guessing_a_number(self):
        self.assertEqual(propose_mapping([local("An Ending", duration=0)], [source("an ending", duration=60)]), (0,))
        self.assertEqual(propose_mapping([local("An Ending", duration=60)], [source("an ending", duration=None)]), (0,))

    def test_title_fallback_rejects_duration_difference_beyond_three_seconds(self):
        self.assertEqual(propose_mapping([local("Song", duration=60)], [source("Song", duration=64)]), (None,))

    def test_title_and_numbers_are_proof_even_when_duration_is_unavailable(self):
        self.assertEqual(propose_mapping([local("Song", "01", "02")], [source("Song", 1, 2)]), (0,))

    def test_duplicate_source_matches_stay_unassigned(self):
        self.assertEqual(propose_mapping([local("Song", "1", "1", 60)],
                                        [source("Song", 1, 1, 60), source("Song", 1, 1, 60)]), (None,))

    def test_a_source_cannot_be_claimed_by_two_local_tracks(self):
        self.assertEqual(propose_mapping([local("Song", "1", "1", 60), local("Song", "1", "1", 60)],
                                        [source("Song", 1, 1, 60)]), (None, None))

    def test_a_competing_ambiguous_local_track_also_prevents_assignment(self):
        tracks = [local("First", "1", "1"), local(track="1", disc="1", duration=60)]
        candidates = [source("First", 1, 1, 60), source("Second", 1, 1, 60)]
        self.assertEqual(propose_mapping(tracks, candidates), (None, None))

    def test_empty_titles_are_not_title_evidence(self):
        self.assertEqual(propose_mapping([local(""), local("")], [source(""), source("")]), (None, None))

    def test_titles_composed_of_signs_keep_the_shared_comparison_rules(self):
        self.assertEqual(propose_mapping([local("!!!")], [source("?!"), source("!!!")]), (1,))

    def test_invalid_numeric_tags_are_not_silently_converted(self):
        self.assertEqual(propose_mapping([local(track="1/10", disc="1", duration=60)],
                                        [source(track=1, disc=1, duration=60)]), (None,))

    def test_empty_inputs_and_unmatched_extra_tracks(self):
        self.assertEqual(propose_mapping([], []), ())
        self.assertEqual(propose_mapping([local("Song")], []), (None,))
        self.assertEqual(propose_mapping([], [source("Song")]), ())
        self.assertEqual(propose_mapping([local("Song")], [source("Song"), source("Extra")]), (0,))


if __name__ == "__main__":
    unittest.main()
