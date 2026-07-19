from __future__ import annotations

import pytest

from song_lab.models import parse_bpm_range
from song_lab.pipeline import build_conversion_package
from song_lab.presets import STYLE_PRESETS


class TestParseBpmRange:
    @pytest.mark.parametrize(
        "tempo_bpm,expected",
        [
            ("76-84", 80),
            ("70-88", 79),
            ("96-112", 104),
            ("104-124", 114),
            ("120", 120),
            ("", None),
        ],
    )
    def test_returns_midpoint_or_single_value(self, tempo_bpm, expected):
        assert parse_bpm_range(tempo_bpm) == expected

    def test_returns_none_for_unparseable_text(self):
        assert parse_bpm_range("fast and groovy") is None


class TestStylePresetBpmMidpoint:
    def test_every_registered_preset_produces_a_parseable_bpm(self):
        for key, preset in STYLE_PRESETS.items():
            assert preset.bpm_midpoint is not None, f"Preset '{key}' has an unparseable tempo_bpm: {preset.tempo_bpm!r}"
            assert 40 <= preset.bpm_midpoint <= 220


class TestConversionPackageBpmHint:
    def test_build_conversion_package_populates_bpm_hint_from_style(self):
        package = build_conversion_package(source_text="test vibe notes", style_key="yemeni_oud_dream_pop")
        assert package.bpm_hint == STYLE_PRESETS["yemeni_oud_dream_pop"].bpm_midpoint
        assert package.bpm_hint is not None
