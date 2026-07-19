"""Tests for the hardened AceStepApiProvider.

All HTTP is mocked at the httpx transport boundary via httpx.MockTransport --
no real network calls are made. This exercises the provider's actual request
construction, retry/backoff logic, and error mapping rather than mocking the
provider's own methods, which would just test the mocks.
"""

from __future__ import annotations

import json

import httpx
import pytest

from song_lab.audio.jobs import SongJob
from song_lab.providers.ace_step_api import (
    AceStepApiProvider,
    AceStepAuthError,
    AceStepClientError,
    AceStepInvalidResponseError,
    AceStepRateLimitedError,
    AceStepServerError,
    AceStepTimeoutError,
)
from song_lab.rate_limit import ConcurrencyLimiter
from tests.audio_fixtures import build_silent_wav_data_url


def _completion_response(audio_url: str, response_id: str = "resp-1") -> dict:
    return {
        "id": response_id,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "## Metadata\n**Caption:** Test",
                    "audio": [{"type": "audio_url", "audio_url": {"url": audio_url}}],
                },
                "finish_reason": "stop",
            }
        ],
    }


def _make_provider(tmp_path, transport: httpx.BaseTransport, **overrides) -> AceStepApiProvider:
    defaults = dict(
        base_url="https://api.acemusic.ai",
        api_key="sk-test-key",
        max_retries=2,
        backoff_base_seconds=0.0,
        backoff_max_seconds=0.0,
        max_concurrent_requests=5,
        timeout_seconds=10,
    )
    defaults.update(overrides)
    return AceStepApiProvider(transport=transport, **defaults)


def _job(tmp_path, duration_seconds: int = 10) -> SongJob:
    return SongJob(prompt="a test prompt", lyrics="[Verse]\nhello", output_dir=tmp_path, duration_seconds=duration_seconds)


class TestSuccessfulCompletionGeneration:
    def test_generates_and_validates_a_single_candidate(self, tmp_path):
        audio_url = build_silent_wav_data_url(duration_seconds=1.0)
        call_count = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            call_count["n"] += 1
            return httpx.Response(200, json=_completion_response(audio_url))

        provider = _make_provider(tmp_path, httpx.MockTransport(handler))
        with provider:
            result = provider.run(_job(tmp_path))

        assert result.status == "generated"
        assert result.output_path.exists()
        assert result.output_path.stat().st_size > 0
        assert call_count["n"] == 1
        assert len(result.candidates) == 1
        assert result.candidates[0].is_best is True

    def test_best_of_n_selects_candidate_closest_to_requested_duration(self, tmp_path):
        short_url = build_silent_wav_data_url(duration_seconds=2.0)
        exact_url = build_silent_wav_data_url(duration_seconds=10.0)
        long_url = build_silent_wav_data_url(duration_seconds=25.0)

        def handler(request: httpx.Request) -> httpx.Response:
            response = _completion_response(short_url)
            response["choices"][0]["message"]["audio"] = [
                {"type": "audio_url", "audio_url": {"url": short_url}},
                {"type": "audio_url", "audio_url": {"url": exact_url}},
                {"type": "audio_url", "audio_url": {"url": long_url}},
            ]
            return httpx.Response(200, json=response)

        provider = _make_provider(tmp_path, httpx.MockTransport(handler), candidates=3)
        with provider:
            result = provider.run(_job(tmp_path, duration_seconds=10))

        assert len(result.candidates) == 3
        best = [c for c in result.candidates if c.is_best]
        assert len(best) == 1
        assert best[0].source_index == 1  # the exact_url candidate, requested duration 10s

    def test_bpm_hint_is_forwarded_in_audio_config(self, tmp_path):
        audio_url = build_silent_wav_data_url(duration_seconds=1.0)
        captured_payload = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured_payload.update(json.loads(request.content))
            return httpx.Response(200, json=_completion_response(audio_url))

        provider = _make_provider(tmp_path, httpx.MockTransport(handler))
        job = _job(tmp_path)
        job.bpm_hint = 88
        with provider:
            provider.run(job)

        assert captured_payload["audio_config"]["bpm"] == 88

    def test_api_key_sent_as_bearer_header(self, tmp_path):
        audio_url = build_silent_wav_data_url(duration_seconds=1.0)
        captured_headers = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured_headers.update(request.headers)
            return httpx.Response(200, json=_completion_response(audio_url))

        provider = _make_provider(tmp_path, httpx.MockTransport(handler), api_key="sk-secret-value")
        with provider:
            provider.run(_job(tmp_path))

        assert captured_headers["authorization"] == "Bearer sk-secret-value"


class TestErrorMapping:
    def test_401_raises_auth_error_without_retry(self, tmp_path):
        call_count = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            call_count["n"] += 1
            return httpx.Response(401, json={"detail": "invalid key"})

        provider = _make_provider(tmp_path, httpx.MockTransport(handler))
        with provider:
            result = provider.run(_job(tmp_path))

        assert result.status == "failed"
        assert "AceStepAuthError" in result.message
        assert call_count["n"] == 1  # auth errors must never be retried

    def test_400_raises_client_error_without_retry(self, tmp_path):
        call_count = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            call_count["n"] += 1
            return httpx.Response(400, json={"detail": "bad request"})

        provider = _make_provider(tmp_path, httpx.MockTransport(handler))
        with provider:
            result = provider.run(_job(tmp_path))

        assert result.status == "failed"
        assert "AceStepClientError" in result.message
        assert call_count["n"] == 1

    def test_429_retries_then_raises_rate_limited_error(self, tmp_path):
        call_count = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            call_count["n"] += 1
            return httpx.Response(429, json={"detail": "rate limited"})

        provider = _make_provider(tmp_path, httpx.MockTransport(handler), max_retries=2)
        with provider:
            result = provider.run(_job(tmp_path))

        assert result.status == "failed"
        assert "AceStepRateLimitedError" in result.message
        assert call_count["n"] == 3  # initial attempt + 2 retries

    def test_503_retries_then_succeeds(self, tmp_path):
        audio_url = build_silent_wav_data_url(duration_seconds=1.0)
        call_count = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            call_count["n"] += 1
            if call_count["n"] < 3:
                return httpx.Response(503, json={"detail": "temporarily unavailable"})
            return httpx.Response(200, json=_completion_response(audio_url))

        provider = _make_provider(tmp_path, httpx.MockTransport(handler), max_retries=3)
        with provider:
            result = provider.run(_job(tmp_path))

        assert result.status == "generated"
        assert call_count["n"] == 3

    def test_persistent_500_raises_server_error(self, tmp_path):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"detail": "internal error"})

        provider = _make_provider(tmp_path, httpx.MockTransport(handler), max_retries=1)
        with provider:
            result = provider.run(_job(tmp_path))

        assert result.status == "failed"
        assert "AceStepServerError" in result.message

    def test_network_timeout_raises_timeout_error(self, tmp_path):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("simulated connect timeout")

        provider = _make_provider(tmp_path, httpx.MockTransport(handler), max_retries=1)
        with provider:
            result = provider.run(_job(tmp_path))

        assert result.status == "failed"
        assert "AceStepTimeoutError" in result.message

    def test_missing_audio_in_response_raises_invalid_response_error(self, tmp_path):
        def handler(request: httpx.Request) -> httpx.Response:
            response = _completion_response("")
            response["choices"][0]["message"]["audio"] = []
            return httpx.Response(200, json=response)

        provider = _make_provider(tmp_path, httpx.MockTransport(handler))
        with provider:
            result = provider.run(_job(tmp_path))

        assert result.status == "failed"
        assert "AceStepInvalidResponseError" in result.message

    def test_malformed_json_raises_invalid_response_error(self, tmp_path):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"not json at all")

        provider = _make_provider(tmp_path, httpx.MockTransport(handler))
        with provider:
            result = provider.run(_job(tmp_path))

        assert result.status == "failed"
        assert "AceStepInvalidResponseError" in result.message

    def test_truncated_audio_download_is_rejected(self, tmp_path):
        """A response that claims success but returns a too-small payload must not be reported as generated."""
        tiny_data_url = "data:audio/wav;base64," + "AAAA"  # decodes to a handful of bytes, well under the floor

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_completion_response(tiny_data_url))

        provider = _make_provider(tmp_path, httpx.MockTransport(handler))
        with provider:
            result = provider.run(_job(tmp_path))

        assert result.status == "failed"
        assert "AceStepInvalidResponseError" in result.message


class TestRedaction:
    def test_api_key_never_appears_in_failure_metadata(self, tmp_path):
        secret = "sk-super-secret-value-do-not-leak"

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"detail": f"rejected request with Authorization Bearer {secret}"})

        provider = _make_provider(tmp_path, httpx.MockTransport(handler), api_key=secret)
        with provider:
            result = provider.run(_job(tmp_path))

        metadata_text = result.metadata_path.read_text(encoding="utf-8")
        assert secret not in metadata_text
        assert result.output_path == result.metadata_path

    def test_audio_base64_never_appears_in_metadata_file(self, tmp_path):
        audio_url = build_silent_wav_data_url(duration_seconds=1.0)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_completion_response(audio_url))

        provider = _make_provider(tmp_path, httpx.MockTransport(handler))
        with provider:
            result = provider.run(_job(tmp_path))

        metadata_text = result.metadata_path.read_text(encoding="utf-8")
        assert "base64," not in metadata_text or "<base64-audio-removed>" in metadata_text


class TestConcurrencyLimiting:
    def test_rate_limit_timeout_maps_to_timeout_error(self, tmp_path):
        limiter = ConcurrencyLimiter(max_concurrent=1, wait_timeout_seconds=0.01)
        with limiter.acquire():
            def handler(request: httpx.Request) -> httpx.Response:
                raise AssertionError("Request must not be sent while the limiter slot is already held.")

            provider = _make_provider(tmp_path, httpx.MockTransport(handler), concurrency_limiter=limiter)
            with provider:
                result = provider.run(_job(tmp_path))

        assert result.status == "failed"
        assert "AceStepTimeoutError" in result.message


class TestResourceCleanup:
    def test_context_manager_closes_underlying_http_client(self, tmp_path):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_completion_response(build_silent_wav_data_url()))

        provider = _make_provider(tmp_path, httpx.MockTransport(handler))
        with provider as active:
            active.run(_job(tmp_path))
        assert provider._client.is_closed is True

    def test_close_is_idempotent(self, tmp_path):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_completion_response(build_silent_wav_data_url()))

        provider = _make_provider(tmp_path, httpx.MockTransport(handler))
        provider.close()
        provider.close()  # must not raise on a second close
