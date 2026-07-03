from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class TextPackageRequest(BaseModel):
    text: str = Field(..., min_length=1)
    style: str = "arabic_oud_ballad"
    source_label: str = "api_text_input"


class FilePackageRequest(BaseModel):
    text_file: Path
    style: str = "arabic_oud_ballad"
    source_label: str = "api_text_file"
    output_path: Path = Path("outputs/api-package.json")


class GenerateRequest(BaseModel):
    package_path: Path
    output_dir: Path = Path("outputs/audio")
    duration: int = Field(default=90, ge=10, le=600)


class AceGenerateRequest(GenerateRequest):
    base_url: str = "http://127.0.0.1:8001"
    api_key: str | None = None
    model: str = "acestep-v15-turbo"
    audio_format: str = "mp3"
    vocal_language: str = "ar"


class TextAceGenerateRequest(TextPackageRequest):
    lyrics: str = ""
    output_dir: Path = Path("outputs/audio")
    duration: int = Field(default=90, ge=10, le=600)
    base_url: str = "http://127.0.0.1:8001"
    api_key: str | None = None
    model: str = "acestep-v15-turbo"
    audio_format: str = "mp3"
    vocal_language: str = "ar"


class ScoreRequest(BaseModel):
    artifact: str
    version_label: str
    emotion: int = Field(ge=1, le=10)
    yemeni_identity: int = Field(ge=1, le=10)
    vocal_beauty: int = Field(ge=1, le=10)
    lyrics: int = Field(ge=1, le=10)
    instrumental: int = Field(ge=1, le=10)
    replay_value: int = Field(ge=1, le=10)
    notes: str = ""
    scorebook: Path = Path("outputs/scores.json")


class ImproveRequest(BaseModel):
    package_path: Path
    scorebook: Path = Path("outputs/scores.json")
    output_path: Path = Path("outputs/improved-package.json")
