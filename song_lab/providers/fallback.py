"""Primary/secondary failover wrapper for song generation providers.

The intended deployment shape (see project conversation history): a
self-hosted ACE-Step instance as the primary provider once revenue funds
owned GPU compute, with the free acemusic.ai hosted demo kept as an
emergency fallback for when the primary is down for maintenance or
unexpectedly overloaded -- never the other way around, and never silently
degrading to the mock provider in a way that could make a paying customer
believe they received real audio when they did not.
"""

from __future__ import annotations

import logging
from types import TracebackType

from song_lab.audio.jobs import SongJob, SongJobResult
from song_lab.observability import get_logger, log_with_context
from song_lab.providers.ace_step_api import AceStepApiError
from song_lab.providers.base import SongProvider

logger = get_logger(__name__)


class AllProvidersFailedError(RuntimeError):
    """Raised when both the primary and every configured fallback provider fail."""

    def __init__(self, primary_error: Exception, fallback_errors: list[Exception]):
        self.primary_error = primary_error
        self.fallback_errors = fallback_errors
        summary = "; ".join(f"{type(err).__name__}: {err}" for err in [primary_error, *fallback_errors])
        super().__init__(f"All providers failed: {summary}")


class FallbackSongProvider(SongProvider):
    """Tries a primary provider, then each fallback in order, on failure.

    Never falls back to a mock/no-op provider implicitly -- if a mock
    fallback is desired for a non-production environment, pass a
    MockSongProvider explicitly as one of the `fallbacks`, making that
    choice visible in the calling code rather than hidden in this class.
    """

    name = "fallback"

    def __init__(self, primary: SongProvider, fallbacks: list[SongProvider]) -> None:
        if not fallbacks:
            raise ValueError("FallbackSongProvider requires at least one fallback provider.")
        self._primary = primary
        self._fallbacks = fallbacks

    def run(self, job: SongJob) -> SongJobResult:
        providers = [self._primary, *self._fallbacks]
        errors: list[Exception] = []
        for index, provider in enumerate(providers):
            role = "primary" if index == 0 else f"fallback[{index - 1}]"
            try:
                result = provider.run(job)
            except AceStepApiError as exc:
                log_with_context(
                    logger,
                    logging.WARNING,
                    "Provider raised during generation; trying next provider if available",
                    role=role,
                    provider_name=getattr(provider, "name", type(provider).__name__),
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
                errors.append(exc)
                continue

            if result.status == "failed":
                log_with_context(
                    logger,
                    logging.WARNING,
                    "Provider returned a failed result; trying next provider if available",
                    role=role,
                    provider_name=getattr(provider, "name", type(provider).__name__),
                    result_message=result.message,
                )
                errors.append(RuntimeError(result.message))
                continue

            if index > 0:
                log_with_context(
                    logger,
                    logging.INFO,
                    "Fallback provider succeeded after primary failure",
                    role=role,
                    provider_name=getattr(provider, "name", type(provider).__name__),
                )
            return result

        raise AllProvidersFailedError(primary_error=errors[0], fallback_errors=errors[1:])

    def close(self) -> None:
        for provider in [self._primary, *self._fallbacks]:
            provider.close()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
