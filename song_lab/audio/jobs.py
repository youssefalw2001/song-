from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class SongJob(BaseModel):
    prompt: str = Field(..., min_length=1)
    lyrics: str | None = None
    output_dir: Path = Path("outputs/audio")
    duration_seconds: int = Field(default=90, ge=10, le=600)
    seed: int | None = None
    bpm_hint: int | None = Field(
        default=None,
        ge=40,
        le=220,
        description="Optional target BPM derived from a style preset. Forwarded to providers that document a BPM control.",
    )


class AudioCandidate(BaseModel):
    """One generated audio take, with the validation data used to rank it against siblings."""

    path: Path
    duration_seconds: float = Field(ge=0)
    file_size_bytes: int = Field(ge=0)
    source_index: int = Field(ge=0, description="Index of this candidate within the batch response.")
    score: float = 0.0
    is_best: bool = False


class SongJobResult(BaseModel):
    provider: str
    status: str
    output_path: Path
    metadata_path: Path | None = None
    message: str
    candidates: list[AudioCandidate] = Field(
        default_factory=list,
        description="All validated candidates generated for this job. Empty for providers that don't report per-candidate detail (e.g. mock).",
    )
