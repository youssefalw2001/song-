from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

_BPM_RANGE_PATTERN = re.compile(r"(\d{2,3})\s*-\s*(\d{2,3})")
_BPM_SINGLE_PATTERN = re.compile(r"(\d{2,3})")


def parse_bpm_range(tempo_bpm: str) -> int | None:
    """Return the midpoint BPM from a preset's tempo string, e.g. "76-84" -> 80.

    Falls back to a single detected number if no range is present, and returns
    None if no BPM can be confidently parsed. This is a plain arithmetic
    midpoint, not a music-theory judgment about the "correct" tempo.
    """
    if not tempo_bpm:
        return None
    range_match = _BPM_RANGE_PATTERN.search(tempo_bpm)
    if range_match:
        low, high = int(range_match.group(1)), int(range_match.group(2))
        return (low + high) // 2
    single_match = _BPM_SINGLE_PATTERN.search(tempo_bpm)
    if single_match:
        return int(single_match.group(1))
    return None


class StylePreset(BaseModel):
    key: str
    title: str
    tempo_bpm: str
    mood: list[str]
    instruments: list[str]
    vocal_direction: str
    arrangement_notes: list[str]
    avoid: list[str]

    @property
    def bpm_midpoint(self) -> int | None:
        return parse_bpm_range(self.tempo_bpm)


class ConversionPackage(BaseModel):
    source_text: str = Field(..., description="Original user-provided lyrics, summary, or vibe notes.")
    style: StylePreset
    analysis_prompt: str
    lyric_adaptation_prompt: str
    music_prompt: str
    vocal_prompt: str
    scoring_rubric: dict[str, str]
    iteration_checklist: list[str]
    legal_safety_note: str
    bpm_hint: int | None = Field(
        default=None,
        description="Midpoint BPM derived from the style preset's tempo range, passed to the audio provider as a hint.",
    )
    status: Literal["prompt_package_ready"] = "prompt_package_ready"
