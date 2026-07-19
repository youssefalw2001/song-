from __future__ import annotations

import pytest

from song_lab.audio.jobs import SongJob, SongJobResult
from song_lab.providers.ace_step_api import AceStepApiError
from song_lab.providers.base import SongProvider
from song_lab.providers.fallback import AllProvidersFailedError, FallbackSongProvider


class _StubProvider(SongProvider):
    """A minimal test double that either returns a fixed result or raises."""

    def __init__(self, name: str, *, result: SongJobResult | None = None, error: Exception | None = None) -> None:
        self.name = name
        self._result = result
        self._error = error
        self.close_called = False
        self.run_called = False

    def run(self, job: SongJob) -> SongJobResult:
        self.run_called = True
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result

    def close(self) -> None:
        self.close_called = True


def _job(tmp_path) -> SongJob:
    return SongJob(prompt="test", output_dir=tmp_path, duration_seconds=30)


def _success_result(provider_name: str, tmp_path) -> SongJobResult:
    path = tmp_path / f"{provider_name}.mp3"
    path.write_bytes(b"fake-audio-bytes")
    return SongJobResult(provider=provider_name, status="generated", output_path=path, message="ok")


class TestFallbackSongProvider:
    def test_requires_at_least_one_fallback(self):
        primary = _StubProvider("primary", result=None)
        with pytest.raises(ValueError):
            FallbackSongProvider(primary=primary, fallbacks=[])

    def test_uses_primary_result_when_primary_succeeds(self, tmp_path):
        primary = _StubProvider("primary", result=_success_result("primary", tmp_path))
        fallback = _StubProvider("fallback", result=_success_result("fallback", tmp_path))
        provider = FallbackSongProvider(primary=primary, fallbacks=[fallback])

        result = provider.run(_job(tmp_path))

        assert result.provider == "primary"
        assert fallback.run_called is False

    def test_falls_back_when_primary_raises(self, tmp_path):
        primary = _StubProvider("primary", error=AceStepApiError("primary is down"))
        fallback = _StubProvider("fallback", result=_success_result("fallback", tmp_path))
        provider = FallbackSongProvider(primary=primary, fallbacks=[fallback])

        result = provider.run(_job(tmp_path))

        assert result.provider == "fallback"
        assert fallback.run_called is True

    def test_falls_back_when_primary_returns_failed_status(self, tmp_path):
        failed_result = SongJobResult(provider="primary", status="failed", output_path=tmp_path / "meta.json", message="failed for a documented reason")
        primary = _StubProvider("primary", result=failed_result)
        fallback = _StubProvider("fallback", result=_success_result("fallback", tmp_path))
        provider = FallbackSongProvider(primary=primary, fallbacks=[fallback])

        result = provider.run(_job(tmp_path))

        assert result.provider == "fallback"

    def test_tries_fallbacks_in_order_and_uses_first_success(self, tmp_path):
        primary = _StubProvider("primary", error=AceStepApiError("down"))
        fallback_a = _StubProvider("fallback_a", error=AceStepApiError("also down"))
        fallback_b = _StubProvider("fallback_b", result=_success_result("fallback_b", tmp_path))
        provider = FallbackSongProvider(primary=primary, fallbacks=[fallback_a, fallback_b])

        result = provider.run(_job(tmp_path))

        assert result.provider == "fallback_b"
        assert fallback_a.run_called is True

    def test_raises_all_providers_failed_when_every_provider_fails(self, tmp_path):
        primary = _StubProvider("primary", error=AceStepApiError("primary down"))
        fallback = _StubProvider("fallback", error=AceStepApiError("fallback down"))
        provider = FallbackSongProvider(primary=primary, fallbacks=[fallback])

        with pytest.raises(AllProvidersFailedError):
            provider.run(_job(tmp_path))

    def test_close_closes_every_wrapped_provider(self, tmp_path):
        primary = _StubProvider("primary", result=_success_result("primary", tmp_path))
        fallback = _StubProvider("fallback", result=_success_result("fallback", tmp_path))
        provider = FallbackSongProvider(primary=primary, fallbacks=[fallback])

        provider.close()

        assert primary.close_called is True
        assert fallback.close_called is True

    def test_usable_as_a_context_manager(self, tmp_path):
        primary = _StubProvider("primary", result=_success_result("primary", tmp_path))
        fallback = _StubProvider("fallback", result=_success_result("fallback", tmp_path))

        with FallbackSongProvider(primary=primary, fallbacks=[fallback]) as provider:
            provider.run(_job(tmp_path))

        assert primary.close_called is True
        assert fallback.close_called is True
