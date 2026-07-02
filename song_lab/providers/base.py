from __future__ import annotations

from abc import ABC, abstractmethod

from song_lab.audio.jobs import SongJob, SongJobResult


class SongProvider(ABC):
    name: str

    @abstractmethod
    def run(self, job: SongJob) -> SongJobResult:
        """Run a song generation job and return the result."""
