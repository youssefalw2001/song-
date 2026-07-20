from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class TextPackageRequest(BaseModel):
    text: str = Field(..., min_length=1)
    style: str = "hype_motivation_anthem"
    source_label: str = "api_text_input"
    creative_angle: str = Field(default="", description="Per-song creative angle from the autopilot plan, merged into the music/vocal prompts on top of the style preset.")
    mood: str = Field(default="", description="Per-song mood from the autopilot plan, merged on top of the style preset's baseline mood.")
    trend_dna: str = Field(default="", description="Per-song style DNA from the autopilot plan, merged into the music prompt.")
    instrumental_notes: str = Field(default="", description="Per-song instrumental direction from the autopilot plan, merged into the music prompt.")
    voice_direction: str = Field(default="", description="Per-song vocal character from the autopilot plan, merged into the vocal prompt.")


class FilePackageRequest(BaseModel):
    text_file: Path
    style: str = "hype_motivation_anthem"
    source_label: str = "api_text_file"
    output_path: Path = Path("outputs/api-package.json")


class GenerateRequest(BaseModel):
    package_path: Path
    output_dir: Path = Path("outputs/audio")
    duration: int = Field(default=90, ge=10, le=600)
    bpm_hint: int | None = Field(default=None, ge=40, le=220)


class AceGenerateRequest(GenerateRequest):
    base_url: str = "http://127.0.0.1:8001"
    api_key: str | None = None
    model: str = "acestep-v15-turbo"
    audio_format: str = "mp3"
    vocal_language: str = "en"
    candidates: int = Field(default=1, ge=1, le=4, description="Number of takes to generate; the closest match to the requested duration is selected automatically.")


class TextAceGenerateRequest(TextPackageRequest):
    lyrics: str = ""
    author_lyrics: bool = Field(
        default=True,
        description="When True (the product default), ACE-Step's own built-in LM authors the lyrics/hook from a natural-language brief -- no external LLM needed. Set False (and pass `lyrics`) to keep the hand-written tagged path.",
    )
    output_dir: Path = Path("outputs/audio")
    duration: int = Field(default=90, ge=10, le=600)
    base_url: str = "http://127.0.0.1:8001"
    api_key: str | None = None
    model: str = "acestep-v15-turbo"
    audio_format: str = "mp3"
    vocal_language: str = "en"
    candidates: int = Field(default=1, ge=1, le=4, description="Number of takes to generate; the closest match to the requested duration is selected automatically.")


class LyricsGenerateRequest(BaseModel):
    """The lyrics-first flow: the user writes the words, then taps to pick the sound.

    The backend composes accent/genre/vibe/voice/tempo into a tuned ACE-Step style
    prompt and generates via the reliable hand-written-lyrics path (no LM authoring).
    """

    lyrics: str = Field(..., min_length=1, description="The user's own lyrics, ideally with [Verse]/[Chorus] section tags.")
    accent: str = Field(default="rnb_smooth", description="Vocal style key from sound_options.VOCAL_STYLES.")
    genre: str = Field(default="pop", description="Beat/genre key from sound_options.GENRES.")
    vibe: str = Field(default="hype", description="Mood key from sound_options.VIBES.")
    voice: str = Field(default="male", description="Voice key: male, female, or duet.")
    tempo: str = Field(default="medium", description="Tempo key: slow, medium, or fast.")
    aesthetic: str = Field(default="none", description="Optional trend pack from sound_options.AESTHETICS (e.g. sadgirl_cinematic, slowed_reverb). 'none' = no overlay.")
    prompt_override: str | None = Field(default=None, description="If set, bypass compose_style entirely and send this raw producer-style prompt to ACE-Step. Used for hand-tuned per-song specs.")
    bpm_override: int | None = Field(default=None, ge=40, le=220, description="If set, use this BPM as the audio-config hint instead of the composed one.")
    max_quality: bool = Field(default=False, description="Enable ACE-Step's thinking + chain-of-thought reasoning for a richer, more musical output. Slower and slightly more prone to upstream 504s.")
    duration: int = Field(default=45, ge=10, le=600)
    output_dir: Path = Path("outputs/audio")
    base_url: str = "http://127.0.0.1:8001"
    api_key: str | None = None
    model: str = "acestep-v15-turbo"
    audio_format: str = "mp3"
    vocal_language: str = "en"
    candidates: int = Field(default=1, ge=1, le=4, description="Number of takes to generate; the closest match to the requested duration is selected automatically.")


class ScoreRequest(BaseModel):
    artifact: str
    version_label: str
    emotion: int = Field(ge=1, le=10)
    shareability: int = Field(ge=1, le=10)
    vocal_quality: int = Field(ge=1, le=10)
    lyrics: int = Field(ge=1, le=10)
    instrumental: int = Field(ge=1, le=10)
    replay_value: int = Field(ge=1, le=10)
    notes: str = ""
    scorebook: Path = Path("outputs/scores.json")


class ImproveRequest(BaseModel):
    package_path: Path
    scorebook: Path = Path("outputs/scores.json")
    output_path: Path = Path("outputs/improved-package.json")
