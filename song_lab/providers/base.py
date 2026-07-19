from __future__ import annotations

from abc import ABC, abstractmethod
from types import TracebackType

from song_lab.audio.jobs import SongJob, SongJobResult


class SongProvider(ABC):
    """Base contract for anything that turns a SongJob into generated audio.

    Providers are usable as context managers so that any pooled resources
    (HTTP connection pools, in-memory rate-limit slots) are guaranteed to be
    released via __exit__ even when generation raises. Providers that hold
    no such resources can rely on the no-op default implementations below.
    """

    name: str

    @abstractmethod
    def run(self, job: SongJob) -> SongJobResult:
        """Run a song generation job and return the result."""

    def close(self) -> None:
        """Release any held resources. Safe to call multiple times."""

    def __enter__(self) -> "SongProvider":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
