from __future__ import annotations

import base64
import json
import logging
import os
import random
import re
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import httpx
import mutagen

from song_lab.audio.jobs import AudioCandidate, SongJob, SongJobResult
from song_lab.observability import get_logger, log_with_context, safe_context
from song_lab.providers.base import SongProvider
from song_lab.rate_limit import ConcurrencyLimiter, RateLimitTimeoutError

logger = get_logger(__name__)

# Minimum plausible size for a real audio file. Anything smaller is treated
# as a truncated/corrupt download rather than retried as valid output.
MIN_VALID_AUDIO_BYTES = 2048

# HTTP statuses worth retrying: rate limiting and transient server failures.
# 4xx client errors other than 429 indicate a request problem that a retry
# cannot fix (bad payload, auth failure, not found) and must not be retried.
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class AceStepApiError(RuntimeError):
    """Base error for all ACE-Step API failures."""


class AceStepAuthError(AceStepApiError):
    """Raised on 401/403 -- invalid or missing API key. Never retried."""


class AceStepClientError(AceStepApiError):
    """Raised on non-retryable 4xx responses (bad request, not found, validation). Never retried."""


class AceStepRateLimitedError(AceStepApiError):
    """Raised on 429 after retries are exhausted."""


class AceStepServerError(AceStepApiError):
    """Raised on 5xx after retries are exhausted."""


class AceStepTimeoutError(AceStepApiError):
    """Raised when a request or the overall job deadline is exceeded."""


class AceStepInvalidResponseError(AceStepApiError):
    """Raised when the API returns 200 but the payload/audio is missing, malformed, or corrupt."""


class AceStepApiProvider(SongProvider):
    """Provider for ACE-Step local/native API and AceMusic cloud completion API.

    Hardened for production use against a free, unauthenticated-by-default
    demo service (acemusic.ai) that publishes no SLA: every network call has
    explicit timeouts, transient failures retry with exponential backoff and
    jitter up to a hard ceiling, concurrent in-flight requests are capped by
    a shared limiter, and every downloaded audio file is validated before
    being reported as a successful generation. Supports best-of-N candidate
    generation to pick the strongest take out of a batch.
    """

    name = "ace_step_api"

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        poll_seconds: float = 2.0,
        timeout_seconds: int = 900,
        connect_timeout_seconds: float = 5.0,
        request_timeout_seconds: float = 120.0,
        max_retries: int = 3,
        backoff_base_seconds: float = 1.0,
        backoff_max_seconds: float = 20.0,
        max_concurrent_requests: int | None = None,
        candidates: int = 1,
        vocal_language: str = "en",
        audio_format: str = "mp3",
        thinking: bool = True,
        use_format: bool = True,
        use_cot: bool = True,
        api_mode: str | None = None,
        concurrency_limiter: ConcurrencyLimiter | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = (base_url or os.getenv("ACESTEP_API_URL") or "http://127.0.0.1:8001").rstrip("/")
        self.api_key = api_key or os.getenv("ACESTEP_API_KEY") or os.getenv("ACEMUSIC_API_KEY")
        self.model = model or os.getenv("ACESTEP_MODEL") or "acestep-v15-turbo"
        self.poll_seconds = poll_seconds
        self.timeout_seconds = timeout_seconds
        self.max_retries = max(0, max_retries)
        self.backoff_base_seconds = backoff_base_seconds
        self.backoff_max_seconds = backoff_max_seconds
        self.candidates = max(1, candidates)
        self.vocal_language = vocal_language
        self.audio_format = audio_format
        self.thinking = thinking
        self.use_format = use_format
        # Chain-of-thought caption/language reasoning. Useful when ACE-Step must
        # author its own lyrics; pure overhead (and extra latency that risks the
        # upstream's ~60s gateway timeout) on the tagged path where we already
        # supply both the lyrics and the full style prompt.
        self.use_cot = use_cot
        configured_mode = api_mode or os.getenv("ACESTEP_API_MODE") or os.getenv("ACEMUSIC_API_MODE")
        if configured_mode:
            self.api_mode = configured_mode.strip().lower()
        elif "api.acemusic.ai" in self.base_url or "acemusic.ai" in self.base_url:
            self.api_mode = "completion"
        else:
            self.api_mode = "native"

        resolved_max_concurrent = max_concurrent_requests or int(os.getenv("ACESTEP_MAX_CONCURRENT", "2"))
        self._limiter = concurrency_limiter or ConcurrencyLimiter(
            max_concurrent=resolved_max_concurrent,
            wait_timeout_seconds=float(self.timeout_seconds),
        )
        self._owns_limiter = concurrency_limiter is None

        self._client = httpx.Client(
            timeout=httpx.Timeout(
                connect=connect_timeout_seconds,
                read=request_timeout_seconds,
                write=connect_timeout_seconds,
                pool=connect_timeout_seconds,
            ),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def run(self, job: SongJob) -> SongJobResult:
        return self._run_and_wrap(job, source_audio_path=None, task_type="text2music", cover_strength=None)

    def run_with_audio(
        self,
        job: SongJob,
        source_audio_path: Path,
        task_type: str = "cover",
        cover_strength: float | None = 0.55,
    ) -> SongJobResult:
        return self._run_and_wrap(job, source_audio_path=source_audio_path, task_type=task_type, cover_strength=cover_strength)

    def _run_and_wrap(
        self,
        job: SongJob,
        source_audio_path: Path | None,
        task_type: str,
        cover_strength: float | None,
    ) -> SongJobResult:
        job.output_dir.mkdir(parents=True, exist_ok=True)
        metadata_path = job.output_dir / self._metadata_name()

        try:
            if self.api_mode == "completion":
                candidates, response = self.run_completion(
                    job,
                    source_audio_path=source_audio_path,
                    task_type=task_type,
                    cover_strength=cover_strength,
                )
                best = _select_best_candidate(candidates)
                metadata = {
                    "provider": self.name,
                    "api_mode": self.api_mode,
                    "task_type": task_type,
                    "source_audio_path": str(source_audio_path) if source_audio_path else None,
                    "response_id": response.get("id"),
                    "response": safe_context(response),
                    "downloaded_path": str(best.path),
                    "candidate_count": len(candidates),
                }
                authored_caption, authored_lyrics = ("", "")
                if job.author_lyrics and job.brief.strip():
                    authored_caption, authored_lyrics = self._parse_authored_content(response)
                metadata["authored_caption"] = authored_caption
                metadata["authored_lyrics"] = authored_lyrics
                metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
                return SongJobResult(
                    provider=self.name,
                    status="generated",
                    output_path=best.path,
                    metadata_path=metadata_path,
                    message=f"ACE-Step completion API generated {len(candidates)} candidate(s); selected best match.",
                    candidates=candidates,
                    authored_caption=authored_caption,
                    authored_lyrics=authored_lyrics,
                )

            if source_audio_path:
                raise AceStepApiError("Audio upload mode currently requires AceMusic completion API mode.")

            task_id = self.release_task(job)
            task_results = self.wait_for_task(task_id)
            candidates = self.download_all_audio(task_results, job, task_id)
            best = _select_best_candidate(candidates)
            metadata = {
                "provider": self.name,
                "api_mode": self.api_mode,
                "task_id": task_id,
                "result_count": len(task_results),
                "downloaded_path": str(best.path),
                "candidate_count": len(candidates),
            }
            metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
            return SongJobResult(
                provider=self.name,
                status="generated",
                output_path=best.path,
                metadata_path=metadata_path,
                message=f"ACE-Step native API generated {len(candidates)} candidate(s); selected best match.",
                candidates=candidates,
            )
        except AceStepApiError as exc:
            log_with_context(logger, logging.ERROR, "ACE-Step generation failed", job_prompt_length=len(job.prompt), error_type=type(exc).__name__, error=str(exc))
            metadata_path.write_text(
                json.dumps({"provider": self.name, "api_mode": self.api_mode, "error_type": type(exc).__name__, "error": str(exc)}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return SongJobResult(
                provider=self.name,
                status="failed",
                output_path=metadata_path,
                metadata_path=metadata_path,
                message=f"ACE-Step generation failed ({type(exc).__name__}): {exc}",
            )

    def health(self) -> dict[str, Any]:
        return self._request_json("GET", "/health")

    def run_completion(
        self,
        job: SongJob,
        source_audio_path: Path | None = None,
        task_type: str = "text2music",
        cover_strength: float | None = None,
    ) -> tuple[list[AudioCandidate], dict[str, Any]]:
        model = self._completion_model_id(self.model)

        # Author mode: hand ACE-Step's own built-in LM a natural-language brief
        # and let it write the caption/prompt and lyrics itself (sample_mode).
        # No hand-written <lyrics> tag is sent -- the LM authors them. The
        # tagged path below is kept byte-identical for backward compatibility
        # when author mode is off.
        # The AceMusic completion API parses the message content for a <prompt>
        # tag even in sample_mode -- a bare free-text body is rejected with
        # "No input provided in messages". So the brief is wrapped in <prompt>
        # (verified live against api.acemusic.ai); the difference from the
        # tagged path is that no hand-written <lyrics> tag is sent, which is
        # what makes ACE-Step's own LM author the lyrics/hook itself.
        author_mode = bool(job.author_lyrics and job.brief.strip())
        if author_mode:
            content = f"<prompt>{job.brief.strip()}</prompt>"
        else:
            content = f"<prompt>{job.prompt}</prompt>"
            if job.lyrics:
                content += f"<lyrics>{job.lyrics}</lyrics>"

        if source_audio_path:
            audio_format = source_audio_path.suffix.lstrip(".").lower() or "mp3"
            audio_b64 = base64.b64encode(source_audio_path.read_bytes()).decode("ascii")
            messages: list[dict[str, Any]] = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": content},
                        {"type": "input_audio", "input_audio": {"data": audio_b64, "format": audio_format}},
                    ],
                }
            ]
        else:
            messages = [{"role": "user", "content": content}]

        audio_config: dict[str, Any] = {
            "format": self.audio_format,
            "vocal_language": self.vocal_language,
            "duration": job.duration_seconds,
        }
        if job.bpm_hint is not None:
            audio_config["bpm"] = job.bpm_hint

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "thinking": self.thinking,
            "use_format": self.use_format,
            "sample_mode": author_mode,
            "use_cot_caption": self.use_cot,
            "use_cot_language": self.use_cot,
            "batch_size": self.candidates,
            "audio_config": audio_config,
        }
        if source_audio_path:
            payload["task_type"] = task_type or "cover"
        if cover_strength is not None:
            payload["audio_cover_strength"] = cover_strength
        if job.seed is not None:
            payload["seed"] = job.seed

        with self._acquire_slot():
            response = self._request_json("POST", "/v1/chat/completions", payload, timeout=700)

        choice = (response.get("choices") or [{}])[0]
        if choice.get("finish_reason") == "error":
            message = (choice.get("message") or {}).get("content") or response
            raise AceStepInvalidResponseError(f"AceMusic completion API returned an error result: {safe_context(message)}")

        audio_items = ((choice.get("message") or {}).get("audio") or [])
        if not audio_items:
            raise AceStepInvalidResponseError(f"Completion response contained no audio: {safe_context(response)}")

        suffix = self.audio_format.lstrip(".") or "mp3"
        response_id = str(response.get("id") or self._timestamp()).replace("/", "-")
        candidates: list[AudioCandidate] = []
        for index, item in enumerate(audio_items):
            audio_url = (((item or {}).get("audio_url") or {}).get("url") or "")
            if not audio_url:
                log_with_context(logger, logging.WARNING, "Skipping candidate with no audio_url", candidate_index=index)
                continue
            output_path = job.output_dir / f"ace-step-{response_id}-{index}.{suffix}"
            self._save_audio_data_url(audio_url, output_path)
            candidates.append(self._validate_and_build_candidate(output_path, index, job.duration_seconds))

        if not candidates:
            raise AceStepInvalidResponseError("All candidates in completion response were missing audio_url.")
        return candidates, response

    def release_task(self, job: SongJob) -> str:
        payload: dict[str, Any] = {
            "prompt": job.prompt,
            "lyrics": job.lyrics or "",
            "audio_duration": job.duration_seconds,
            "audio_format": self.audio_format,
            "vocal_language": self.vocal_language,
            "thinking": self.thinking,
            "use_format": self.use_format,
            "model": self.model,
            "batch_size": self.candidates,
        }
        if job.bpm_hint is not None:
            payload["bpm"] = job.bpm_hint
        if job.seed is not None:
            payload["use_random_seed"] = False
            payload["seed"] = job.seed
        with self._acquire_slot():
            response = self._request_json("POST", "/release_task", payload)
        data = self._unwrap(response)
        task_id = data.get("task_id")
        if not task_id:
            raise AceStepInvalidResponseError(f"ACE-Step did not return task_id: {safe_context(response)}")
        return str(task_id)

    def wait_for_task(self, task_id: str) -> list[dict[str, Any]]:
        deadline = time.monotonic() + self.timeout_seconds
        while time.monotonic() < deadline:
            response = self._request_json("POST", "/query_result", {"task_id_list": [task_id]})
            data = self._unwrap(response)
            if not isinstance(data, list) or not data:
                raise AceStepInvalidResponseError(f"Invalid query_result response: {safe_context(response)}")
            item = data[0]
            status = int(item.get("status", 0))
            if status == 1:
                parsed = self._parse_result_json(item.get("result"))
                if not parsed:
                    raise AceStepInvalidResponseError(f"Task succeeded but returned no result: {safe_context(item)}")
                return parsed
            if status == 2:
                raise AceStepInvalidResponseError(f"ACE-Step task failed: {safe_context(item)}")
            time.sleep(self.poll_seconds)
        raise AceStepTimeoutError(f"ACE-Step task timed out after {self.timeout_seconds} seconds: {task_id}")

    def download_all_audio(self, results: list[dict[str, Any]], job: SongJob, task_id: str) -> list[AudioCandidate]:
        suffix = self.audio_format.lstrip(".") or "mp3"
        candidates: list[AudioCandidate] = []
        for index, result in enumerate(results):
            file_url = result.get("file")
            if not file_url:
                log_with_context(logger, logging.WARNING, "Skipping native result with no file URL", candidate_index=index)
                continue
            url = file_url if file_url.startswith(("http://", "https://")) else f"{self.base_url}{file_url}"
            output_path = job.output_dir / f"ace-step-{task_id}-{index}.{suffix}"
            self._download_file(url, output_path)
            candidates.append(self._validate_and_build_candidate(output_path, index, job.duration_seconds))
        if not candidates:
            raise AceStepInvalidResponseError("No downloadable audio files were present in the native task result.")
        return candidates

    def download_first_audio(self, result: dict[str, Any], output_dir: Path, task_id: str) -> Path:
        """Retained for backward compatibility with callers expecting a single-file download."""
        file_url = result.get("file")
        if not file_url:
            raise AceStepInvalidResponseError(f"Result missing audio file URL: {safe_context(result)}")
        url = file_url if file_url.startswith(("http://", "https://")) else f"{self.base_url}{file_url}"
        suffix = self.audio_format.lstrip(".") or "mp3"
        output_path = output_dir / f"ace-step-{task_id}.{suffix}"
        self._download_file(url, output_path)
        return output_path

    def _download_file(self, url: str, output_path: Path) -> None:
        with self._client.stream("GET", url, headers=self._headers(include_json=False)) as response:
            response.raise_for_status()
            with output_path.open("wb") as handle:
                for chunk in response.iter_bytes():
                    handle.write(chunk)

    def _validate_and_build_candidate(self, path: Path, index: int, requested_duration_seconds: int) -> AudioCandidate:
        """Open the downloaded file with mutagen and raise if it isn't a real, decodable audio file.

        A corrupt or truncated download is a silent-failure risk: without
        this check, a broken file would be reported as a successful
        generation and only discovered when a paying user hits play.
        """
        file_size = path.stat().st_size if path.exists() else 0
        if file_size < MIN_VALID_AUDIO_BYTES:
            raise AceStepInvalidResponseError(
                f"Downloaded audio candidate {index} at {path} is only {file_size} bytes -- treating as a truncated/corrupt download."
            )
        try:
            parsed = mutagen.File(path)
        except Exception as exc:
            raise AceStepInvalidResponseError(f"Candidate {index} at {path} could not be parsed as audio: {exc}") from exc
        if parsed is None:
            raise AceStepInvalidResponseError(f"Candidate {index} at {path} was not recognized as a valid audio file by mutagen.")

        duration_seconds = float(getattr(parsed.info, "length", 0.0) or 0.0)
        if duration_seconds <= 0.0:
            log_with_context(logger, logging.WARNING, "Candidate has no reliable duration metadata", candidate_index=index, path=str(path))
            score = float("inf")
        else:
            score = abs(duration_seconds - float(requested_duration_seconds))

        return AudioCandidate(
            path=path,
            duration_seconds=duration_seconds,
            file_size_bytes=file_size,
            source_index=index,
            score=score,
        )

    @contextmanager
    def _acquire_slot(self) -> Iterator[None]:
        try:
            with self._limiter.acquire():
                yield
        except RateLimitTimeoutError as exc:
            raise AceStepTimeoutError(str(exc)) from exc

    def _request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        attempt = 0
        while True:
            attempt += 1
            try:
                response = self._client.request(
                    method,
                    url,
                    json=payload,
                    headers=self._headers(include_json=True),
                    timeout=httpx.Timeout(connect=5.0, read=float(timeout) if timeout else None, write=10.0, pool=5.0) if timeout else None,
                )
            except httpx.TimeoutException as exc:
                if attempt > self.max_retries:
                    raise AceStepTimeoutError(f"Request to {url} timed out after {attempt} attempt(s): {exc}") from exc
                self._sleep_backoff(attempt, reason="timeout")
                continue
            except httpx.TransportError as exc:
                if attempt > self.max_retries:
                    raise AceStepApiError(f"Could not reach ACE-Step API at {url} after {attempt} attempt(s): {exc}") from exc
                self._sleep_backoff(attempt, reason="transport_error")
                continue

            if response.status_code == 401 or response.status_code == 403:
                raise AceStepAuthError(f"Authentication failed for {url}: HTTP {response.status_code}: {self._safe_body(response)}")

            if response.status_code in _RETRYABLE_STATUS_CODES:
                if attempt > self.max_retries:
                    error_cls = AceStepRateLimitedError if response.status_code == 429 else AceStepServerError
                    raise error_cls(f"Request to {url} failed after {attempt} attempt(s): HTTP {response.status_code}: {self._safe_body(response)}")
                self._sleep_backoff(attempt, reason=f"http_{response.status_code}")
                continue

            if response.status_code >= 400:
                raise AceStepClientError(f"Request to {url} rejected: HTTP {response.status_code}: {self._safe_body(response)}")

            try:
                return response.json()
            except ValueError as exc:
                raise AceStepInvalidResponseError(f"Response from {url} was not valid JSON: {exc}") from exc

    def _sleep_backoff(self, attempt: int, reason: str) -> None:
        delay = min(self.backoff_max_seconds, self.backoff_base_seconds * (2 ** (attempt - 1)))
        jitter = random.uniform(0, delay * 0.25)
        sleep_for = delay + jitter
        log_with_context(logger, logging.WARNING, "Retrying ACE-Step request after transient failure", attempt=attempt, reason=reason, sleep_seconds=round(sleep_for, 2))
        time.sleep(sleep_for)

    @staticmethod
    def _safe_body(response: httpx.Response) -> str:
        try:
            return safe_context(response.text)[:500]
        except Exception:
            return "<unreadable response body>"

    def _headers(self, include_json: bool) -> dict[str, str]:
        headers: dict[str, str] = {"User-Agent": "song-lab-ace-step-provider/2.0"}
        if include_json:
            headers["Content-Type"] = "application/json; charset=utf-8"
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _save_audio_data_url(self, data_url: str, output_path: Path) -> None:
        if data_url.startswith("data:") and ";base64," in data_url:
            encoded = data_url.split(";base64,", 1)[1]
            output_path.write_bytes(base64.b64decode(encoded))
            return
        if data_url.startswith(("http://", "https://")):
            self._download_file(data_url, output_path)
            return
        output_path.write_bytes(base64.b64decode(data_url))

    @staticmethod
    def _parse_authored_content(response: dict[str, Any]) -> tuple[str, str]:
        """Extract the LM-authored caption and lyrics from a sample_mode response.

        ACE-Step's LM returns the text it authored in the assistant message
        content, typically shaped like:

            ## Metadata
            **Caption:** upbeat dancehall, playful diss, 96 BPM ...
            ## Lyrics
            [Verse 1]
            ...

        Parsing is best-effort and never raises: audio generation already
        succeeded by the time this runs, so a missing or differently-shaped
        text block must not fail the whole job -- it just yields empty
        strings for whichever piece could not be found.
        """
        choice = (response.get("choices") or [{}])[0]
        content = (choice.get("message") or {}).get("content") or ""
        if not isinstance(content, str) or not content.strip():
            return "", ""

        caption = ""
        lyrics = ""
        lyrics_lines: list[str] = []
        section: str | None = None
        for raw_line in content.splitlines():
            line = raw_line.rstrip()
            lowered = line.strip().lower()
            if lowered.startswith("## "):
                heading = lowered[3:].strip()
                if heading.startswith("lyric"):
                    section = "lyrics"
                elif heading.startswith("metadata") or heading.startswith("caption"):
                    section = "metadata"
                else:
                    section = None
                continue
            caption_match = re.match(r"^\s*\*{0,2}caption\*{0,2}\s*:\s*(.+)$", line, re.IGNORECASE)
            if caption_match and not caption:
                caption = caption_match.group(1).strip().strip("*").strip()
                continue
            if section == "lyrics":
                lyrics_lines.append(line)

        lyrics = "\n".join(lyrics_lines).strip()
        return caption, lyrics

    @staticmethod
    def _completion_model_id(model: str) -> str:
        return model if "/" in model else f"acemusic/{model}"

    @staticmethod
    def _unwrap(response: dict[str, Any]) -> Any:
        if response.get("code") != 200:
            raise AceStepInvalidResponseError(f"ACE-Step API error: {safe_context(response)}")
        return response.get("data")

    @staticmethod
    def _parse_result_json(raw_result: Any) -> list[dict[str, Any]]:
        if isinstance(raw_result, list):
            return raw_result
        if isinstance(raw_result, str):
            parsed = json.loads(raw_result)
            if isinstance(parsed, list):
                return parsed
        raise AceStepInvalidResponseError(f"Cannot parse ACE-Step result JSON: {safe_context(raw_result)}")

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    @staticmethod
    def _metadata_name() -> str:
        return f"ace-step-run-{AceStepApiProvider._timestamp()}.json"


def _select_best_candidate(candidates: list[AudioCandidate]) -> AudioCandidate:
    """Pick the candidate whose duration is closest to the requested length.

    Mutates the winning candidate's `is_best` flag in place so callers that
    inspect `SongJobResult.candidates` can see which one was chosen without
    re-running the comparison.
    """
    if not candidates:
        raise AceStepInvalidResponseError("Cannot select a best candidate from an empty candidate list.")
    best = min(candidates, key=lambda candidate: candidate.score)
    best.is_best = True
    return best
