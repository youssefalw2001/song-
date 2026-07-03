from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class TranscriptSegment(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    text: str


class Transcript(BaseModel):
    source_path: Path
    language: str | None = None
    text: str
    segments: list[TranscriptSegment] = []
