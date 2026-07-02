from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class SongJob(BaseModel):
    prompt: str = Field(..., min_length=1)
    lyrics: str | None = None
    output_dir: Path = Path("outputs/audio")
    duration_seconds: int = Field(default=90, ge=10, le=600)
    seed: int | None = None


class SongJobResult(BaseModel):
    provider: str
    status: str
    output_path: Path
    metadata_path: Path | None = None
    message: str
