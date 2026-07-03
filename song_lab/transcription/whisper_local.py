from __future__ import annotations

from pathlib import Path

from song_lab.transcription.types import Transcript


class LocalWhisperTranscriber:
    """Placeholder local transcriber.

    Full local Whisper transcription is optional and is not required for the Render API startup.
    """

    def transcribe(self, audio_path: str | Path) -> Transcript:
        raise NotImplementedError("Local Whisper transcription is not installed in this deployment.")
