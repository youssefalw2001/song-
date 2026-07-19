"""Tests for the deterministic heuristic judge in song_lab/candidate_scoring.py.

These tests exercise pure functions with no network/filesystem dependency --
every case here should run in milliseconds and never flake.
"""

from __future__ import annotations

import pytest

from song_lab.candidate_scoring import (
    extract_specificity_signals,
    score_candidate,
    select_best_candidate,
)


SPECIFIC_DISS_LYRICS = (
    "[Intro]\nJake you had it all lined up\n\n"
    "[Verse 1]\nWide open at the buzzer, air balled it clean\n"
    "The whole gym went silent, worst shot I've seen\n\n"
    "[Hook]\nJake blew the game-winner, we still bring it up\n"
    "Jake blew the game-winner, worst airball, no luck\n\n"
    "[Verse 2]\nEvery Sunday pickup we replay the tape\n"
    "Jake still can't live it down, no escape\n\n"
    "[Hook Repeat]\nJake blew the game-winner, we still bring it up"
)

GENERIC_DISS_LYRICS = (
    "[Intro]\nYou had one shot and you blew it twice\n\n"
    "[Verse 1]\nWatch me glow, reach for the stars\n"
    "You had one shot and you blew it twice\n\n"
    "[Hook]\nYou had one shot and you blew it twice\n"
    "Believe in yourself, living my best life\n\n"
    "[Verse 2]\nNo notes, no notes, shining bright\n\n"
    "[Hook Repeat]\nYou had one shot and you blew it twice"
)


class TestExtractSpecificitySignals:
    def test_detects_proper_nouns_excluding_common_words(self):
        signals = extract_specificity_signals(
            lyrics="Jake missed the shot. The Verse continues. I am here.",
            hook="Jake blew it",
            source_prompt="diss track about Jake",
        )
        assert "Jake" in signals.proper_noun_hits
        assert "Verse" not in signals.proper_noun_hits
        assert "I" not in signals.proper_noun_hits

    def test_detects_generic_filler_phrases(self):
        signals = extract_specificity_signals(
            lyrics="You had one shot and you blew it twice, watch me glow tonight",
            hook="watch me glow",
            source_prompt="anything",
        )
        assert "you had one shot" in signals.generic_phrase_hits
        assert "watch me glow" in signals.generic_phrase_hits

    def test_detects_structure_tags(self):
        signals = extract_specificity_signals(
            lyrics="[Verse 1]\nSome lyrics\n\n[Hook]\nA hook line",
            hook="A hook line",
            source_prompt="anything",
        )
        assert signals.has_structure_tags is True

    def test_missing_structure_tags_detected(self):
        signals = extract_specificity_signals(
            lyrics="just some plain lines with no section markers at all",
            hook="a hook",
            source_prompt="anything",
        )
        assert signals.has_structure_tags is False

    def test_hook_repetition_detected(self):
        signals = extract_specificity_signals(
            lyrics="[Hook]\nJake blew it big time\n\n[Hook Repeat]\nJake blew it big time",
            hook="Jake blew it big time",
            source_prompt="anything",
        )
        assert signals.hook_appears_twice is True

    def test_hook_repetition_false_when_hook_appears_once(self):
        signals = extract_specificity_signals(
            lyrics="[Hook]\nJake blew it big time\n\n[Verse]\nSomething else entirely",
            hook="Jake blew it big time",
            source_prompt="anything",
        )
        assert signals.hook_appears_twice is False

    def test_source_keyword_overlap_counts_shared_meaningful_words(self):
        signals = extract_specificity_signals(
            lyrics="Jake missed the basketball shot at the game last weekend",
            hook="Jake blew it",
            source_prompt="diss track about Jake missing a basketball shot",
        )
        assert signals.source_keyword_overlap >= 2  # at least "jake" and "basketball" or "shot"

    def test_empty_inputs_do_not_crash(self):
        signals = extract_specificity_signals(lyrics="", hook="", source_prompt="")
        assert signals.word_count == 0
        assert signals.hook_word_count == 0
        assert signals.hook_appears_twice is False


class TestScoreCandidate:
    def test_specific_candidate_scores_higher_than_generic_candidate(self):
        specific = score_candidate(
            {"lyrics": SPECIFIC_DISS_LYRICS, "story_text": "Jake blew the game-winner, we still bring it up", "caption": "lol jake"},
            source_prompt="diss track roasting my friend Jake for missing the game-winning shot at basketball",
        )
        generic = score_candidate(
            {"lyrics": GENERIC_DISS_LYRICS, "story_text": "You had one shot and you blew it twice", "caption": "roasted"},
            source_prompt="diss track roasting my friend Jake for missing the game-winning shot at basketball",
        )
        assert specific.score > generic.score
        assert not specific.disqualified
        assert not generic.disqualified

    def test_generic_candidate_is_penalized_for_filler_phrases(self):
        result = score_candidate(
            {"lyrics": GENERIC_DISS_LYRICS, "story_text": "You had one shot and you blew it twice", "caption": "x"},
            source_prompt="anything",
        )
        assert result.breakdown["generic_phrase_penalty"] < 0

    def test_missing_hook_is_penalized(self):
        result = score_candidate(
            {"lyrics": SPECIFIC_DISS_LYRICS, "story_text": "", "caption": "x"},
            source_prompt="diss track about Jake",
        )
        assert result.breakdown["hook_length"] == -20.0

    def test_missing_structure_tags_is_penalized(self):
        result = score_candidate(
            {"lyrics": "just plain text with no tags at all and a decent amount of words to pass length sanity checks here", "story_text": "a short hook", "caption": "x"},
            source_prompt="anything",
        )
        assert result.breakdown["structure"] == -10.0

    def test_near_empty_lyrics_penalized_for_length(self):
        result = score_candidate(
            {"lyrics": "too short", "story_text": "hi", "caption": "x"},
            source_prompt="anything",
        )
        assert result.breakdown["length_sanity"] == -25.0

    @pytest.mark.parametrize(
        "unsafe_text",
        [
            "you should just kill yourself over this",
            "kys honestly",
            "i am going to kill you for this",
            "i will show up at your house tonight",
            "call me at 555-123-4567 anytime",
        ],
    )
    def test_disqualifies_unsafe_content_regardless_of_other_quality(self, unsafe_text):
        result = score_candidate(
            {"lyrics": SPECIFIC_DISS_LYRICS + "\n" + unsafe_text, "story_text": "Jake blew the game-winner, we still bring it up", "caption": "x"},
            source_prompt="diss track about Jake",
        )
        assert result.disqualified is True
        assert result.score == 0.0
        assert result.disqualification_reason is not None

    def test_safe_diss_track_language_is_not_falsely_disqualified(self):
        """Roast/diss content that is merely aggressive-in-tone (not an actual threat) must pass."""
        result = score_candidate(
            {"lyrics": SPECIFIC_DISS_LYRICS, "story_text": "Jake blew the game-winner, we still bring it up", "caption": "roasted him"},
            source_prompt="diss track about Jake missing a shot",
        )
        assert result.disqualified is False


class TestSelectBestCandidate:
    def test_selects_the_highest_scoring_eligible_candidate(self):
        candidates = [
            {"lyrics": GENERIC_DISS_LYRICS, "story_text": "You had one shot and you blew it twice", "caption": "x"},
            {"lyrics": SPECIFIC_DISS_LYRICS, "story_text": "Jake blew the game-winner, we still bring it up", "caption": "x"},
        ]
        best, all_scores = select_best_candidate(candidates, source_prompt="diss track about Jake missing a basketball shot")
        assert best is candidates[1]
        assert len(all_scores) == 2

    def test_raises_on_empty_candidate_list(self):
        with pytest.raises(ValueError):
            select_best_candidate([], source_prompt="anything")

    def test_skips_disqualified_candidates_and_picks_best_remaining(self):
        candidates = [
            {"lyrics": "kill yourself " + SPECIFIC_DISS_LYRICS, "story_text": "Jake blew the game-winner, we still bring it up", "caption": "x"},
            {"lyrics": GENERIC_DISS_LYRICS, "story_text": "You had one shot and you blew it twice", "caption": "x"},
        ]
        best, all_scores = select_best_candidate(candidates, source_prompt="diss track about Jake")
        assert best is candidates[1]
        assert all_scores[0].disqualified is True

    def test_raises_when_every_candidate_is_disqualified(self):
        candidates = [
            {"lyrics": "kill yourself", "story_text": "x", "caption": "x"},
            {"lyrics": "kys", "story_text": "y", "caption": "y"},
        ]
        with pytest.raises(ValueError, match="disqualified"):
            select_best_candidate(candidates, source_prompt="anything")
