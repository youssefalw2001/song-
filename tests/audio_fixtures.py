"""Helpers for producing tiny, valid audio payloads for provider tests.

Using a real WAV file (built via the stdlib `wave` module) rather than a
hand-rolled byte string means mutagen's parser exercises the same code path
it would on a genuine ACE-Step response, so the validation tests are honest
about what they're proving.
"""

from __future__ import annotations

import base64
import io
import wave


def build_silent_wav_bytes(duration_seconds: float = 1.0, sample_rate: int = 8000) -> bytes:
    buffer = io.BytesIO()
    frame_count = int(duration_seconds * sample_rate)
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(b"\x00\x00" * frame_count)
    return buffer.getvalue()


def build_silent_wav_data_url(duration_seconds: float = 1.0, sample_rate: int = 8000) -> str:
    raw = build_silent_wav_bytes(duration_seconds=duration_seconds, sample_rate=sample_rate)
    encoded = base64.b64encode(raw).decode("ascii")
    return f"data:audio/wav;base64,{encoded}"
