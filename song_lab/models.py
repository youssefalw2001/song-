from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class StylePreset(BaseModel):
    key: str
    title: str
    tempo_bpm: str
    mood: list[str]
    instruments: list[str]
    vocal_direction: str
    arrangement_notes: list[str]
    avoid: list[str]


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
    status: Literal["prompt_package_ready"] = "prompt_package_ready"
