from __future__ import annotations

import json
from datetime import datetime, timezone

from song_lab.audio.jobs import SongJob, SongJobResult
from song_lab.providers.base import SongProvider


class MockSongProvider(SongProvider):
    """Writes a metadata file instead of producing real sound.

    This keeps the end-to-end app flow testable before a GPU music model is installed.
    """

    name = "mock"

    def run(self, job: SongJob) -> SongJobResult:
        job.output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output_path = job.output_dir / f"mock-song-{timestamp}.json"

        payload = {
            "provider": self.name,
            "created_at": timestamp,
            "prompt": job.prompt,
            "lyrics": job.lyrics,
            "duration_seconds": job.duration_seconds,
            "seed": job.seed,
            "note": "Mock output only. Wire a real local model provider to produce an audio file.",
        }
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        return SongJobResult(
            provider=self.name,
            status="mock_generated",
            output_path=output_path,
            metadata_path=output_path,
            message="Mock song package written. No real audio was generated.",
        )
