from __future__ import annotations

from song_lab.observability import redact_audio_payloads, redact_secrets, safe_context


class TestRedactSecrets:
    def test_redacts_dict_keys_matching_secret_pattern(self):
        payload = {"api_key": "sk-real-value", "user": "alice"}
        result = redact_secrets(payload)
        assert result["api_key"] == "<redacted>"
        assert result["user"] == "alice"

    def test_redacts_nested_secret_keys(self):
        payload = {"outer": {"authorization": "Bearer abc123", "safe": "value"}}
        result = redact_secrets(payload)
        assert result["outer"]["authorization"] == "<redacted>"
        assert result["outer"]["safe"] == "value"

    def test_redacts_inline_bearer_tokens_in_strings(self):
        payload = "request failed with Authorization: Bearer sk-abc.def-123"
        result = redact_secrets(payload)
        assert "sk-abc.def-123" not in result
        assert "Bearer <redacted>" in result

    def test_redacts_secret_keys_within_lists(self):
        payload = [{"token": "abc"}, {"user": "bob"}]
        result = redact_secrets(payload)
        assert result[0]["token"] == "<redacted>"
        assert result[1]["user"] == "bob"

    def test_passes_through_non_string_non_container_values(self):
        assert redact_secrets(42) == 42
        assert redact_secrets(None) is None
        assert redact_secrets(3.14) == 3.14


class TestRedactAudioPayloads:
    def test_strips_base64_audio_data_urls(self):
        payload = {"audio_url": {"url": "data:audio/mpeg;base64,SGVsbG8gV29ybGQ="}}
        result = redact_audio_payloads(payload)
        assert result["audio_url"]["url"] == "<base64-audio-removed>"

    def test_leaves_non_audio_strings_untouched(self):
        payload = {"message": "generation succeeded"}
        result = redact_audio_payloads(payload)
        assert result["message"] == "generation succeeded"


class TestSafeContext:
    def test_applies_both_secret_and_audio_redaction(self):
        payload = {
            "api_key": "sk-real",
            "response": {"audio": [{"audio_url": {"url": "data:audio/wav;base64,AAAA"}}]},
        }
        result = safe_context(payload)
        assert result["api_key"] == "<redacted>"
        assert result["response"]["audio"][0]["audio_url"]["url"] == "<base64-audio-removed>"
