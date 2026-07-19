"""Structured JSON logging and redaction helpers for the song generation pipeline.

Every log line emitted through `get_logger` is machine-parseable JSON with a
human-readable `message` field. Nothing that touches an API key, bearer
token, or raw audio payload may reach a log line unredacted -- callers must
route that data through `redact_secrets` / `redact_audio_payloads` first.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime, timezone
from typing import Any

_SECRET_KEY_PATTERN = re.compile(r"(?i)\b(api[_-]?key|authorization|bearer|token|secret)\b")
_DATA_URL_PATTERN = re.compile(r"data:audio/[a-zA-Z0-9.+-]+;base64,[A-Za-z0-9+/=]+")
_BEARER_HEADER_PATTERN = re.compile(r"(?i)Bearer\s+[A-Za-z0-9._\-]+")


class _JsonFormatter(logging.Formatter):
    """Renders each log record as a single JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        context = getattr(record, "context", None)
        if isinstance(context, dict):
            payload.update(context)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def get_logger(name: str) -> logging.Logger:
    """Return a module-scoped logger configured for structured JSON output.

    Safe to call repeatedly -- handlers are only attached once per logger
    name, so re-importing a module never duplicates log lines.
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(stream=sys.stdout)
        handler.setFormatter(_JsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


def log_with_context(logger: logging.Logger, level: int, message: str, **context: Any) -> None:
    """Emit a structured log line with arbitrary machine-parseable context fields."""
    logger.log(level, message, extra={"context": redact_secrets(context)})


def redact_secrets(value: Any) -> Any:
    """Recursively replace values behind secret-shaped keys and inline bearer tokens.

    Handles dicts, lists/tuples, and strings. Any other type is returned as-is.
    This is a defense-in-depth pass -- callers should still avoid passing raw
    secrets into logging contexts in the first place.
    """
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if isinstance(key, str) and _SECRET_KEY_PATTERN.search(key):
                redacted[key] = "<redacted>"
            else:
                redacted[key] = redact_secrets(item)
        return redacted
    if isinstance(value, (list, tuple)):
        return [redact_secrets(item) for item in value]
    if isinstance(value, str):
        return _BEARER_HEADER_PATTERN.sub("Bearer <redacted>", value)
    return value


def redact_audio_payloads(value: Any) -> Any:
    """Recursively strip base64 audio data URLs so they never reach a log line.

    Base64-encoded audio can be megabytes per song -- logging it verbatim
    both leaks payload data unnecessarily and floods log storage.
    """
    if isinstance(value, dict):
        return {key: redact_audio_payloads(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_audio_payloads(item) for item in value]
    if isinstance(value, str):
        return _DATA_URL_PATTERN.sub("<base64-audio-removed>", value)
    return value


def safe_context(value: Any) -> Any:
    """Apply both secret and audio redaction -- the one call sites should use before logging."""
    return redact_audio_payloads(redact_secrets(value))
