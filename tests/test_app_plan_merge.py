"""API-level tests confirming the autopilot plan's creative fields actually
reach the generated music_prompt/vocal_prompt through the FastAPI routes,
not just at the pipeline.py unit level.

Drives the real FastAPI app in-process via Starlette's TestClient -- no real
network calls, no real ACE-Step generation (uses the mock provider route).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from song_lab.api.app import app


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


class TestPackageFromTextPlanMerge:
    def test_plan_fields_merge_into_music_prompt(self, client: TestClient):
        response = client.post(
            "/package/from-text",
            json={
                "text": "diss track about Jake missing the shot",
                "style": "diss_track_trap",
                "source_label": "test",
                "creative_angle": "roasting Jake for the airball at pickup basketball",
                "mood": "gleeful and mocking",
                "trend_dna": "playground-taunt energy",
                "instrumental_notes": "sparse and cold, let the silence roast him",
                "voice_direction": "deadpan delivery, never yells",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "roasting Jake for the airball at pickup basketball" in data["music_prompt"]
        assert "gleeful and mocking" in data["music_prompt"]
        assert "playground-taunt energy" in data["music_prompt"]
        assert "sparse and cold, let the silence roast him" in data["music_prompt"]
        assert "deadpan delivery, never yells" in data["vocal_prompt"]

    def test_two_requests_same_style_different_plan_yield_different_music_prompts(self, client: TestClient):
        base_body = {"text": "a diss track", "style": "diss_track_trap", "source_label": "test"}

        response_a = client.post("/package/from-text", json={**base_body, "creative_angle": "roasting Jake for the airball"})
        response_b = client.post("/package/from-text", json={**base_body, "creative_angle": "roasting my roommate for the dishes"})

        assert response_a.json()["music_prompt"] != response_b.json()["music_prompt"]

    def test_no_plan_fields_falls_back_to_style_only_prompt(self, client: TestClient):
        response = client.post("/package/from-text", json={"text": "a diss track", "style": "diss_track_trap", "source_label": "test"})
        assert response.status_code == 200
        assert "This song's specific angle" not in response.json()["music_prompt"]

    def test_blank_plan_fields_are_treated_the_same_as_absent(self, client: TestClient):
        response = client.post(
            "/package/from-text",
            json={"text": "a diss track", "style": "diss_track_trap", "source_label": "test", "creative_angle": "", "mood": "", "trend_dna": "", "instrumental_notes": "", "voice_direction": ""},
        )
        assert response.status_code == 200
        assert "This song's specific angle" not in response.json()["music_prompt"]


class TestGenerateFromTextMockPlanMerge:
    def test_mock_generation_response_includes_plan_merged_package(self, client: TestClient):
        response = client.post(
            "/generate/from-text/mock",
            json={
                "text": "hype anthem before a big game",
                "style": "hype_motivation_anthem",
                "source_label": "test",
                "creative_angle": "pre-game hype before the championship match",
                "duration": 30,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "pre-game hype before the championship match" in data["package"]["music_prompt"]
        assert data["generation"]["status"] == "mock_generated"
