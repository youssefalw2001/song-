"""Tests for the 'ACE-Step authors its own lyrics' path (author mode).

Author mode hands ACE-Step's own built-in LM a natural-language brief and lets
it write the lyrics/hook itself via sample_mode -- no external LLM required.
All HTTP is mocked at the httpx transport boundary; the pure brief builder is
tested directly. These tests prove:
  * the brief builder fuses idea + style + plan + guardrails into free text,
  * author mode builds a sample_mode payload with the brief as the message and
    NO hand-written <lyrics> tag,
  * the LM-authored caption/lyrics are parsed out of the response,
  * best-of-N still selects the closest candidate in author mode,
  * author_lyrics=False keeps the exact old tagged payload (backward compat).
"""

from __future__ import annotations

import json

import httpx

from song_lab.audio.jobs import SongJob
from song_lab.pipeline import build_song_brief
from song_lab.presets import STYLE_PRESETS
from song_lab.providers.ace_step_api import AceStepApiProvider
from tests.audio_fixtures import build_silent_wav_data_url


AUTHORED_CONTENT = (
    "## Metadata\n"
    "**Caption:** bouncy dancehall diss, playful savage energy, 96 BPM\n"
    "## Lyrics\n"
    "[Intro]\n"
    "yeah, you already know\n"
    "[Verse 1]\n"
    "you showed up late again, classic you\n"
    "[Hook]\n"
    "always on your own clock, never on time\n"
)


def _authored_response(audio_url: str, content: str = AUTHORED_CONTENT, response_id: str = "resp-auth-1") -> dict:
    return {
        "id": response_id,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content,
                    "audio": [{"type": "audio_url", "audio_url": {"url": audio_url}}],
                },
                "finish_reason": "stop",
            }
        ],
    }


def _make_provider(transport: httpx.BaseTransport, **overrides) -> AceStepApiProvider:
    defaults = dict(
        base_url="https://api.acemusic.ai",
        api_key="sk-test-key",
        max_retries=1,
        backoff_base_seconds=0.0,
        backoff_max_seconds=0.0,
        max_concurrent_requests=5,
        timeout_seconds=10,
    )
    defaults.update(overrides)
    return AceStepApiProvider(transport=transport, **defaults)


def _author_job(tmp_path, brief: str, duration_seconds: int = 10) -> SongJob:
    return SongJob(
        prompt="a dancehall diss about a friend who is always late",
        lyrics=None,
        output_dir=tmp_path,
        duration_seconds=duration_seconds,
        author_lyrics=True,
        brief=brief,
    )


class TestBuildSongBrief:
    def test_brief_fuses_idea_style_and_guardrails(self):
        style = STYLE_PRESETS["dancehall_roast_anthem"]
        brief = build_song_brief(style, "roast my friend Marcus for always being late", plan=None)

        assert "Marcus" in brief
        assert style.title in brief
        assert "English" in brief
        # A safety guardrail must always be present.
        assert "protected characteristics" in brief
        # No XML-style tags -- sample_mode reads free text.
        assert "<prompt>" not in brief and "<lyrics>" not in brief

    def test_plan_fields_override_and_extend_the_brief(self):
        style = STYLE_PRESETS["dancehall_roast_anthem"]
        plan = {
            "creative_angle": "petty but hilarious courtroom testimony",
            "mood": "gleeful and smug",
            "trend_dna": "group sing-back hook",
            "instrumental_notes": "extra cowbell on the turnaround",
            "voice_direction": "mocking sing-song delivery",
        }
        brief = build_song_brief(style, "roast my friend", plan=plan)

        assert "petty but hilarious courtroom testimony" in brief
        assert "gleeful and smug" in brief
        assert "group sing-back hook" in brief
        assert "extra cowbell on the turnaround" in brief
        assert "mocking sing-song delivery" in brief


class TestAuthorModePayload:
    def test_author_mode_sets_sample_mode_and_sends_brief_without_lyrics_tag(self, tmp_path):
        audio_url = build_silent_wav_data_url(duration_seconds=1.0)
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured.update(json.loads(request.content))
            return httpx.Response(200, json=_authored_response(audio_url))

        brief = "Write a complete, original dancehall diss. Keep it playful."
        provider = _make_provider(httpx.MockTransport(handler))
        with provider:
            provider.run(_author_job(tmp_path, brief))

        assert captured["sample_mode"] is True
        message_content = captured["messages"][0]["content"]
        # The brief is wrapped in <prompt> (the AceMusic API rejects bare text),
        # but no hand-written <lyrics> tag is sent -- the LM authors them.
        assert message_content == f"<prompt>{brief}</prompt>"
        assert "<lyrics>" not in message_content
        # audio_config and batch_size still apply.
        assert captured["audio_config"]["duration"] == 10
        assert "batch_size" in captured

    def test_author_mode_parses_authored_caption_and_lyrics_into_result(self, tmp_path):
        audio_url = build_silent_wav_data_url(duration_seconds=1.0)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_authored_response(audio_url))

        provider = _make_provider(httpx.MockTransport(handler))
        with provider:
            result = provider.run(_author_job(tmp_path, "brief text"))

        assert result.status == "generated"
        assert result.authored_caption == "bouncy dancehall diss, playful savage energy, 96 BPM"
        assert "[Verse 1]" in result.authored_lyrics
        assert "always on your own clock" in result.authored_lyrics
        # The metadata heading itself must not leak into the lyrics block.
        assert "## Metadata" not in result.authored_lyrics
        assert "**Caption:**" not in result.authored_lyrics

    def test_best_of_n_still_works_in_author_mode(self, tmp_path):
        short_url = build_silent_wav_data_url(duration_seconds=2.0)
        exact_url = build_silent_wav_data_url(duration_seconds=10.0)
        long_url = build_silent_wav_data_url(duration_seconds=25.0)

        def handler(request: httpx.Request) -> httpx.Response:
            response = _authored_response(short_url)
            response["choices"][0]["message"]["audio"] = [
                {"type": "audio_url", "audio_url": {"url": short_url}},
                {"type": "audio_url", "audio_url": {"url": exact_url}},
                {"type": "audio_url", "audio_url": {"url": long_url}},
            ]
            return httpx.Response(200, json=response)

        provider = _make_provider(httpx.MockTransport(handler), candidates=3)
        with provider:
            result = provider.run(_author_job(tmp_path, "brief text", duration_seconds=10))

        assert len(result.candidates) == 3
        best = [c for c in result.candidates if c.is_best]
        assert len(best) == 1
        assert best[0].source_index == 1
        # Authored content is still parsed even with multiple candidates.
        assert result.authored_caption.startswith("bouncy dancehall diss")


class TestBackwardCompatibility:
    def test_author_lyrics_false_keeps_the_old_tagged_payload(self, tmp_path):
        audio_url = build_silent_wav_data_url(duration_seconds=1.0)
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured.update(json.loads(request.content))
            return httpx.Response(200, json=_authored_response(audio_url))

        job = SongJob(
            prompt="a test prompt",
            lyrics="[Verse]\nhello world",
            output_dir=tmp_path,
            duration_seconds=10,
            author_lyrics=False,
        )
        provider = _make_provider(httpx.MockTransport(handler))
        with provider:
            result = provider.run(job)

        assert captured["sample_mode"] is False
        content = captured["messages"][0]["content"]
        assert content == "<prompt>a test prompt</prompt><lyrics>[Verse]\nhello world</lyrics>"
        # Authored fields stay empty when author mode is off.
        assert result.authored_caption == ""
        assert result.authored_lyrics == ""

    def test_author_lyrics_true_but_empty_brief_falls_back_to_tagged_path(self, tmp_path):
        audio_url = build_silent_wav_data_url(duration_seconds=1.0)
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured.update(json.loads(request.content))
            return httpx.Response(200, json=_authored_response(audio_url))

        # author_lyrics=True but no brief -> not enough to author; keep tagged path.
        job = SongJob(
            prompt="a test prompt",
            lyrics="[Verse]\nhello",
            output_dir=tmp_path,
            duration_seconds=10,
            author_lyrics=True,
            brief="   ",
        )
        provider = _make_provider(httpx.MockTransport(handler))
        with provider:
            result = provider.run(job)

        assert captured["sample_mode"] is False
        assert "<prompt>" in captured["messages"][0]["content"]
        assert result.authored_caption == ""
        assert result.authored_lyrics == ""



class TestAppWiringAuthorMode:
    """API-level: /generate/from-text/ace builds a brief, threads author mode into
    the job, and surfaces the LM-authored caption/lyrics in the response JSON.

    The real ACE-Step provider is replaced with a fake that records the job it
    received and returns authored content -- so no network call happens, but the
    app.py wiring (brief construction + response surfacing) is fully exercised.
    """

    def _install_fake_provider(self, monkeypatch, captured):
        from pathlib import Path

        import importlib

        from song_lab.audio.jobs import SongJobResult

        # song_lab/api/__init__.py rebinds the `app` attribute to the FastAPI
        # instance, shadowing the submodule for attribute-style access. Resolve
        # the real module object so we can patch the provider symbol on it.
        app_module = importlib.import_module("song_lab.api.app")

        class _FakeProvider:
            def __init__(self, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def run(self, job):
                captured["job"] = job
                return SongJobResult(
                    provider="ace_step_api",
                    status="generated",
                    output_path=Path("outputs/audio/fake.mp3"),
                    metadata_path=Path("outputs/audio/fake.json"),
                    message="fake",
                    authored_caption="playful dancehall diss, 96 BPM",
                    authored_lyrics="[Hook]\nalways late, never on time",
                )

        monkeypatch.setattr(app_module, "AceStepApiProvider", _FakeProvider)

    def test_default_request_authors_lyrics_and_surfaces_them(self, monkeypatch):
        from fastapi.testclient import TestClient

        from song_lab.api.app import app

        captured = {}
        self._install_fake_provider(monkeypatch, captured)

        with TestClient(app) as client:
            response = client.post(
                "/generate/from-text/ace",
                json={
                    "text": "roast my friend for always being late, dancehall style",
                    "style": "dancehall_roast_anthem",
                    "source_label": "test",
                },
            )

        assert response.status_code == 200
        job = captured["job"]
        assert job.author_lyrics is True
        assert job.brief.strip() != ""
        assert "English" in job.brief
        data = response.json()
        assert data["generation"]["authored_caption"] == "playful dancehall diss, 96 BPM"
        assert "always late" in data["generation"]["authored_lyrics"]
        assert data["package"]["song_brief"].strip() != ""

    def test_user_supplied_lyrics_disable_author_mode(self, monkeypatch):
        from fastapi.testclient import TestClient

        from song_lab.api.app import app

        captured = {}
        self._install_fake_provider(monkeypatch, captured)

        with TestClient(app) as client:
            response = client.post(
                "/generate/from-text/ace",
                json={
                    "text": "a diss track",
                    "style": "dancehall_roast_anthem",
                    "source_label": "test",
                    "lyrics": "[Verse]\nmy own hand-written words",
                    "author_lyrics": True,
                },
            )

        assert response.status_code == 200
        job = captured["job"]
        # Explicit hand-written lyrics take precedence: author mode is turned off.
        assert job.author_lyrics is False
        assert job.brief == ""
