"""Tests for the best-of-N LLM planning path in song_lab/autopilot.py.

All HTTP is mocked at the httpx transport boundary via httpx.MockTransport --
no real network calls. Verifies candidate generation, judge-based selection,
retry/error-mapping behavior, and that the offline fallback still works
standalone when no API key is configured.
"""

from __future__ import annotations

import json

import httpx
import pytest

from song_lab.autopilot import (
    AutopilotAuthError,
    AutopilotClientError,
    AutopilotInvalidResponseError,
    AutopilotRateLimitedError,
    AutopilotServerError,
    build_autopilot_plan,
)


GENERIC_CANDIDATE = {
    "style": "diss_track_trap",
    "lyrics": "[Intro]\nYou had one shot and you blew it twice\n\n[Hook]\nYou had one shot and you blew it twice\nWatch me glow, no notes\n\n[Hook Repeat]\nYou had one shot and you blew it twice",
    "story_text": "You had one shot and you blew it twice",
    "caption": "roasted", "hashtags": ["#Diss"], "duration": 45,
    "creative_angle": "a diss", "mood": "savage", "trend_dna": "trap",
    "instrumental_notes": "808s", "voice_direction": "confident rap",
    "tempo": "70-75 BPM", "structure": "intro hook", "concept": "roast",
    "video_idea": "vertical video", "why": ["fits"],
}

SPECIFIC_CANDIDATE = {
    "style": "diss_track_trap",
    "lyrics": "[Intro]\nJake you had it lined up\n\n[Verse 1]\nWide open at the buzzer, air balled it clean\n\n[Hook]\nJake blew the game-winner, we still bring it up\nJake blew the game-winner, worst airball I've seen\n\n[Verse 2]\nEvery Sunday pickup we replay the tape\n\n[Hook Repeat]\nJake blew the game-winner, we still bring it up",
    "story_text": "Jake blew the game-winner, we still bring it up",
    "caption": "lol jake never lives this down", "hashtags": ["#Diss", "#Roasted"], "duration": 45,
    "creative_angle": "roasting Jake for the airball", "mood": "savage-but-fun", "trend_dna": "trap, comedic",
    "instrumental_notes": "808s, trap hats", "voice_direction": "confident half-time rap",
    "tempo": "70-75 BPM", "structure": "intro verse hook verse hook", "concept": "Jake's airball, immortalized",
    "video_idea": "vertical video with the airball clip", "why": ["specific to Jake's actual moment"],
}


def _completion_response(candidates: list[dict]) -> dict:
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": json.dumps({"planner": "llm_best_of_n", "candidates": candidates}),
                },
                "finish_reason": "stop",
            }
        ]
    }


def _client_with_transport(transport: httpx.BaseTransport) -> httpx.Client:
    return httpx.Client(transport=transport, timeout=httpx.Timeout(5.0))


@pytest.fixture(autouse=True)
def _set_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTOPILOT_API_KEY", "sk-test-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("time.sleep", lambda _seconds: None)


class TestBestOfNSelection:
    def test_selects_the_more_specific_candidate_out_of_multiple(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_completion_response([GENERIC_CANDIDATE, SPECIFIC_CANDIDATE]))

        client = _client_with_transport(httpx.MockTransport(handler))
        plan = build_autopilot_plan({"idea": "diss track roasting my friend Jake for missing the game-winning shot", "mode": "meme"}, client=client)

        assert plan["planner"] == "llm_best_of_n"
        assert plan["candidate_count"] == 2
        assert "Jake" in plan["lyrics"]
        assert plan["story_text"] == "Jake blew the game-winner, we still bring it up"

    def test_single_candidate_still_works(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_completion_response([SPECIFIC_CANDIDATE]))

        client = _client_with_transport(httpx.MockTransport(handler))
        plan = build_autopilot_plan({"idea": "diss track about Jake"}, client=client)

        assert plan["planner"] == "llm_best_of_n"
        assert plan["candidate_count"] == 1

    def test_requests_the_configured_candidate_count(self):
        captured_payload = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured_payload.update(json.loads(request.content))
            return httpx.Response(200, json=_completion_response([SPECIFIC_CANDIDATE, GENERIC_CANDIDATE, SPECIFIC_CANDIDATE]))

        client = _client_with_transport(httpx.MockTransport(handler))
        build_autopilot_plan({"idea": "test"}, client=client, candidate_count=3)

        sent_content = json.loads(captured_payload["messages"][1]["content"])
        assert sent_content["candidate_count"] == 3

    def test_flat_single_plan_response_is_tolerated_as_one_candidate(self):
        """Some models may ignore the multi-candidate instruction and return one flat plan -- must not crash."""
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(SPECIFIC_CANDIDATE)}, "finish_reason": "stop"}]})

        client = _client_with_transport(httpx.MockTransport(handler))
        plan = build_autopilot_plan({"idea": "diss track about Jake"}, client=client)

        assert "Jake" in plan["lyrics"]


class TestSafetyDisqualificationInPractice:
    def test_unsafe_candidate_is_never_selected_when_a_safe_alternative_exists(self):
        unsafe_candidate = dict(SPECIFIC_CANDIDATE)
        unsafe_candidate["lyrics"] = SPECIFIC_CANDIDATE["lyrics"] + "\nkill yourself over this"

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_completion_response([unsafe_candidate, GENERIC_CANDIDATE]))

        client = _client_with_transport(httpx.MockTransport(handler))
        plan = build_autopilot_plan({"idea": "diss track about Jake"}, client=client)

        assert "kill yourself" not in plan["lyrics"].lower()
        assert plan["story_text"] == GENERIC_CANDIDATE["story_text"]

    def test_falls_back_to_offline_planner_when_every_candidate_is_unsafe(self):
        unsafe_a = dict(GENERIC_CANDIDATE); unsafe_a["lyrics"] = "kill yourself"
        unsafe_b = dict(SPECIFIC_CANDIDATE); unsafe_b["lyrics"] = "kys"

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_completion_response([unsafe_a, unsafe_b]))

        client = _client_with_transport(httpx.MockTransport(handler))
        plan = build_autopilot_plan({"idea": "diss track about Jake"}, client=client)

        # Must degrade to the safe offline fallback, never surface a disqualified candidate.
        assert plan["planner"] == "prompt_only_fallback_after_llm_error"
        assert "kill yourself" not in plan["lyrics"].lower()
        assert "kys" not in plan["lyrics"].lower()


class TestErrorHandlingAndFallback:
    def test_auth_error_falls_back_to_offline_planner(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": "invalid key"})

        client = _client_with_transport(httpx.MockTransport(handler))
        plan = build_autopilot_plan({"idea": "birthday song for Maria"}, client=client)

        assert plan["planner"] == "prompt_only_fallback_after_llm_error"
        assert plan["style"] == "birthday_banger_pop"

    def test_persistent_rate_limit_falls_back_to_offline_planner(self):
        call_count = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            call_count["n"] += 1
            return httpx.Response(429, json={"error": "rate limited"})

        client = _client_with_transport(httpx.MockTransport(handler))
        plan = build_autopilot_plan({"idea": "hype anthem"}, client=client)

        assert plan["planner"] == "prompt_only_fallback_after_llm_error"
        assert call_count["n"] > 1  # confirms retries actually happened before giving up

    def test_transient_server_error_retries_then_succeeds(self):
        call_count = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            call_count["n"] += 1
            if call_count["n"] < 2:
                return httpx.Response(503, json={"error": "temporarily unavailable"})
            return httpx.Response(200, json=_completion_response([SPECIFIC_CANDIDATE]))

        client = _client_with_transport(httpx.MockTransport(handler))
        plan = build_autopilot_plan({"idea": "diss track about Jake"}, client=client)

        assert plan["planner"] == "llm_best_of_n"
        assert call_count["n"] == 2

    def test_malformed_json_response_falls_back_gracefully(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"not json")

        client = _client_with_transport(httpx.MockTransport(handler))
        plan = build_autopilot_plan({"idea": "love song"}, client=client)

        assert plan["planner"] == "prompt_only_fallback_after_llm_error"

    def test_response_with_no_candidates_and_no_flat_plan_falls_back(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"planner": "llm_best_of_n", "candidates": []})}, "finish_reason": "stop"}]})

        client = _client_with_transport(httpx.MockTransport(handler))
        plan = build_autopilot_plan({"idea": "love song"}, client=client)

        assert plan["planner"] == "prompt_only_fallback_after_llm_error"


class TestOfflineFallbackStandalone:
    def test_no_api_key_uses_offline_planner_directly(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("AUTOPILOT_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        plan = build_autopilot_plan({"idea": "birthday song for my sister Maria turning 25"})

        assert plan["planner"] == "prompt_only_fallback"
        assert plan["style"] == "birthday_banger_pop"

    def test_offline_planner_never_calls_network(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("AUTOPILOT_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        def handler(request: httpx.Request) -> httpx.Response:
            raise AssertionError("Offline planner must never make a network call.")

        client = _client_with_transport(httpx.MockTransport(handler))
        plan = build_autopilot_plan({"idea": "hype anthem"}, client=client)
        assert plan["planner"] == "prompt_only_fallback"
