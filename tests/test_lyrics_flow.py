"""Tests for the lyrics-first curated-sound flow.

Covers the pure style composer (deterministic prompt + BPM mapping, graceful
fallbacks) and the /generate/from-lyrics API route, which must use the reliable
hand-written-lyrics path (author_lyrics=False) rather than LM lyric authoring.
"""

from __future__ import annotations

import importlib

from fastapi.testclient import TestClient

from song_lab.sound_options import (
    DEFAULT_GENRE,
    DEFAULT_VOCAL_STYLE,
    GENRES,
    compose_style,
)


class TestComposeStyle:
    def test_choices_appear_in_prompt_and_summary(self):
        c = compose_style(accent="jamaican", genre="dancehall", vibe="funny", voice="female", tempo="medium")
        assert "Jamaican" in c.prompt
        assert "dancehall" in c.prompt.lower()
        assert "funny" in c.prompt.lower()
        assert "female vocalist" in c.prompt
        assert "English lyrics" in c.prompt
        assert c.summary.count("\u00b7") == 4  # accent · genre · vibe · voice · bpm

    def test_tempo_selects_the_matching_bpm_anchor(self):
        low = compose_style(genre="dancehall", tempo="slow").bpm
        mid = compose_style(genre="dancehall", tempo="medium").bpm
        high = compose_style(genre="dancehall", tempo="fast").bpm
        assert (low, mid, high) == GENRES["dancehall"].bpm
        assert low < mid < high

    def test_unknown_keys_fall_back_to_defaults_without_raising(self):
        c = compose_style(accent="not_real", genre="also_fake", vibe="???", voice="alien", tempo="warp")
        assert c.vocal_style == DEFAULT_VOCAL_STYLE
        assert c.genre == DEFAULT_GENRE
        assert c.voice == "male"
        assert c.tempo == "medium"
        assert c.bpm == GENRES[DEFAULT_GENRE].bpm[1]

    def test_all_option_combinations_produce_a_nonempty_coherent_prompt(self):
        # A light fuzz over the menus: no combination should crash or blank out.
        from song_lab.sound_options import VIBES, VOCAL_STYLES, VOICES, TEMPOS

        for accent in VOCAL_STYLES:
            for genre in GENRES:
                c = compose_style(accent=accent, genre=genre, vibe=next(iter(VIBES)), voice="duet", tempo=next(iter(TEMPOS)))
                assert c.prompt.strip()
                assert 40 <= c.bpm <= 220


def _install_fake_provider(monkeypatch, captured):
    from pathlib import Path

    from song_lab.audio.jobs import SongJobResult

    app_module = importlib.import_module("song_lab.api.app")

    class _FakeProvider:
        def __init__(self, **kwargs):
            captured["provider_kwargs"] = kwargs

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
            )

    monkeypatch.setattr(app_module, "AceStepApiProvider", _FakeProvider)


class TestGenerateFromLyricsRoute:
    def test_uses_hand_written_lyrics_path_and_composes_sound(self, monkeypatch):
        from song_lab.api.app import app

        captured = {}
        _install_fake_provider(monkeypatch, captured)

        with TestClient(app) as client:
            response = client.post(
                "/generate/from-lyrics",
                json={
                    "lyrics": "[Verse 1]\nyo this is my song\n[Chorus]\nsing it all night long",
                    "accent": "jamaican",
                    "genre": "dancehall",
                    "vibe": "funny",
                    "voice": "male",
                    "tempo": "fast",
                    "duration": 45,
                },
            )

        assert response.status_code == 200
        job = captured["job"]
        # The reliable path: the user's lyrics are sent verbatim, LM authoring is OFF.
        assert job.author_lyrics is False
        assert "sing it all night long" in job.lyrics
        assert "dancehall" in job.prompt.lower()
        assert "Jamaican" in job.prompt
        assert job.bpm_hint == GENRES["dancehall"].bpm[2]  # fast anchor
        assert job.duration_seconds == 45

        data = response.json()
        assert data["sound"]["summary"].startswith("Jamaican Dancehall")
        assert data["sound"]["bpm"] == GENRES["dancehall"].bpm[2]
        assert data["generation"]["status"] == "generated"

    def test_fail_fast_retries_are_applied(self, monkeypatch):
        from song_lab.api.app import app

        captured = {}
        _install_fake_provider(monkeypatch, captured)

        with TestClient(app) as client:
            client.post("/generate/from-lyrics", json={"lyrics": "[Chorus]\nhello"})

        # Fail-fast: the generation provider is built with one retry, not the stock three.
        assert captured["provider_kwargs"]["max_retries"] == 1

    def test_whitespace_only_lyrics_are_rejected(self, monkeypatch):
        from song_lab.api.app import app

        _install_fake_provider(monkeypatch, {})
        with TestClient(app) as client:
            response = client.post("/generate/from-lyrics", json={"lyrics": "   \n  "})
        # min_length=1 lets whitespace past the schema, so the server guards it explicitly.
        assert response.status_code == 400

    def test_missing_lyrics_field_is_a_validation_error(self, monkeypatch):
        from song_lab.api.app import app

        _install_fake_provider(monkeypatch, {})
        with TestClient(app) as client:
            response = client.post("/generate/from-lyrics", json={"accent": "jamaican"})
        assert response.status_code == 422


class TestSoundOptionsRoute:
    def test_lists_all_menus(self):
        from song_lab.api.app import app

        with TestClient(app) as client:
            response = client.get("/sound-options")
        assert response.status_code == 200
        data = response.json()
        for section in ("accents", "genres", "vibes", "voices", "tempos", "lyric_starters"):
            assert isinstance(data[section], list) and data[section]
        assert any(a["key"] == "jamaican" for a in data["accents"])
        assert any(s["key"] == "birthday" for s in data["lyric_starters"])
