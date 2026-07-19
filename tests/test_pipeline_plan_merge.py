"""Tests for merging an autopilot plan's per-song creative fields into the
music/vocal prompts (song_lab/pipeline.py).

This closes the gap where two songs using the same style preset (e.g. two
diss tracks) produced near-identical instructions to the audio model,
because build_music_prompt/build_vocal_prompt only ever read the fixed style
scaffold and silently discarded the autopilot's per-song creative_angle,
mood, trend_dna, instrumental_notes, and voice_direction.
"""

from __future__ import annotations

from song_lab.pipeline import build_conversion_package, build_music_prompt, build_vocal_prompt
from song_lab.presets import STYLE_PRESETS


class TestBuildMusicPromptWithoutPlan:
    def test_no_plan_produces_style_only_prompt_unchanged(self):
        """Backward compatibility: existing callers (CLI, manual studio, no-plan requests) must be unaffected."""
        style = STYLE_PRESETS["diss_track_trap"]
        prompt = build_music_prompt(style)
        assert style.title in prompt
        assert "This song's specific angle" not in prompt
        assert "This song's specific mood" not in prompt

    def test_none_plan_is_equivalent_to_no_plan_argument(self):
        style = STYLE_PRESETS["diss_track_trap"]
        assert build_music_prompt(style) == build_music_prompt(style, None)

    def test_empty_plan_dict_is_equivalent_to_no_plan(self):
        style = STYLE_PRESETS["diss_track_trap"]
        assert build_music_prompt(style) == build_music_prompt(style, {})


class TestBuildMusicPromptWithPlan:
    def test_plan_creative_angle_appears_in_output(self):
        style = STYLE_PRESETS["diss_track_trap"]
        plan = {"creative_angle": "roasting Jake for the airball at pickup basketball"}
        prompt = build_music_prompt(style, plan)
        assert "roasting Jake for the airball at pickup basketball" in prompt

    def test_plan_mood_is_layered_on_top_of_style_baseline_mood(self):
        style = STYLE_PRESETS["diss_track_trap"]
        plan = {"mood": "gleeful, mocking, playground-taunt energy"}
        prompt = build_music_prompt(style, plan)
        assert "gleeful, mocking, playground-taunt energy" in prompt
        # style baseline mood must still be present -- merge, not replace
        assert "aggressive" in prompt or "confident" in prompt

    def test_plan_trend_dna_appears_in_output(self):
        style = STYLE_PRESETS["diss_track_trap"]
        plan = {"trend_dna": "mid-2000s dancehall riddim with playful sing-rap ad-libs"}
        prompt = build_music_prompt(style, plan)
        assert "mid-2000s dancehall riddim with playful sing-rap ad-libs" in prompt

    def test_plan_instrumental_notes_appears_in_output(self):
        style = STYLE_PRESETS["diss_track_trap"]
        plan = {"instrumental_notes": "sparse, cold, minimal -- let the silence do the roasting"}
        prompt = build_music_prompt(style, plan)
        assert "sparse, cold, minimal -- let the silence do the roasting" in prompt

    def test_two_different_plans_produce_two_different_music_prompts_for_the_same_style(self):
        """The actual bug being fixed: same style preset, different plan, must yield different prompts."""
        style = STYLE_PRESETS["diss_track_trap"]
        plan_a = {"creative_angle": "roasting Jake for missing the game-winning shot", "mood": "gleeful and mocking", "trend_dna": "playground-taunt energy"}
        plan_b = {"creative_angle": "roasting my roommate for never doing dishes", "mood": "exasperated but affectionate", "trend_dna": "domestic-sitcom energy"}
        prompt_a = build_music_prompt(style, plan_a)
        prompt_b = build_music_prompt(style, plan_b)
        assert prompt_a != prompt_b
        assert "Jake" in prompt_a
        assert "dishes" in prompt_b

    def test_partial_plan_only_fills_in_provided_fields(self):
        style = STYLE_PRESETS["diss_track_trap"]
        plan = {"creative_angle": "only this field is set"}
        prompt = build_music_prompt(style, plan)
        assert "only this field is set" in prompt
        assert "This song's specific mood" not in prompt
        assert "This song's specific style DNA" not in prompt

    def test_plan_with_non_string_values_does_not_crash(self):
        """Defensive: a malformed plan (e.g. None values from a partial LLM response) must not raise."""
        style = STYLE_PRESETS["diss_track_trap"]
        plan = {"creative_angle": None, "mood": None, "trend_dna": None, "instrumental_notes": None}
        prompt = build_music_prompt(style, plan)
        assert style.title in prompt


class TestBuildVocalPromptWithPlan:
    def test_no_plan_produces_style_only_vocal_prompt(self):
        style = STYLE_PRESETS["diss_track_trap"]
        prompt = build_vocal_prompt(style)
        assert style.vocal_direction in prompt
        assert "This song's specific vocal character" not in prompt

    def test_plan_voice_direction_is_layered_on_top_of_style_baseline(self):
        style = STYLE_PRESETS["diss_track_trap"]
        plan = {"voice_direction": "cold, deadpan delivery -- the roast lands harder without yelling"}
        prompt = build_vocal_prompt(style, plan)
        assert "cold, deadpan delivery -- the roast lands harder without yelling" in prompt
        assert style.vocal_direction in prompt

    def test_two_plans_produce_different_vocal_prompts_for_the_same_style(self):
        style = STYLE_PRESETS["diss_track_trap"]
        prompt_a = build_vocal_prompt(style, {"voice_direction": "gleeful, bouncing, can't stop laughing while rapping"})
        prompt_b = build_vocal_prompt(style, {"voice_direction": "cold, clinical, delivered like a court verdict"})
        assert prompt_a != prompt_b


class TestBuildConversionPackageWithPlan:
    def test_package_music_prompt_reflects_the_plan(self):
        plan = {"creative_angle": "roasting Jake for the airball", "voice_direction": "mocking sing-song delivery"}
        package = build_conversion_package(source_text="diss track about Jake", style_key="diss_track_trap", plan=plan)
        assert "roasting Jake for the airball" in package.music_prompt
        assert "mocking sing-song delivery" in package.vocal_prompt

    def test_package_without_plan_still_works_exactly_as_before(self):
        package = build_conversion_package(source_text="diss track about Jake", style_key="diss_track_trap")
        assert package.style.key == "diss_track_trap"
        assert "This song's specific angle" not in package.music_prompt

    def test_invalid_style_key_still_raises_regardless_of_plan(self):
        import pytest

        with pytest.raises(ValueError):
            build_conversion_package(source_text="x", style_key="not_a_real_style", plan={"mood": "x"})
